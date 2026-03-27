#!/usr/bin/env python3
"""
Crypto Hunter v2 - Main Scanner
DEX Pump/Dump Detection System with Self-Healing Architecture

Features:
- SQLite database (replaces PostgreSQL)
- GeckoTerminal + DexScreener with caching
- 3-level self-healing watchdog
- Performance tracking for signal quality
"""

import asyncio
import logging
import os
import sys
import signal
from datetime import datetime, timezone, timedelta
from typing import Dict, List

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv
load_dotenv()

from scanner.multi_scanner import MultiScanner
from scanner.metrics_engine import MetricsEngine
from detectors.signal_detectors import (
    PumpDetector, DipDetector, WhaleDetector, 
    RiskEngine, AlphaCalculator
)
from telegram_bot.notifier import TelegramNotifier
from database.models import get_session, Signal, ActiveToken, cleanup_old_data, init_database, SignalResult
from utils.watchdog import Watchdog, GracefulShutdown
from utils.cache import get_cache

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)-8s | %(message)s',
    handlers=[
        logging.FileHandler('logs/scanner.log'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)


class CryptoHunter:
    """Main scanner orchestrator with self-healing architecture"""
    
    def __init__(self):
        # Initialize components
        self.scanner = MultiScanner()
        self.metrics_engine = MetricsEngine()
        self.pump_detector = PumpDetector()
        self.dip_detector = DipDetector()
        self.whale_detector = WhaleDetector()
        self.risk_engine = RiskEngine()
        self.alpha_calc = AlphaCalculator()
        self.notifier = TelegramNotifier()
        self.cache = get_cache()
        
        # Watchdog (3 levels)
        self.watchdog = Watchdog(
            max_cycle_duration=120.0,  # 2 min max per cycle
            max_consecutive_failures=3,
            pause_duration=300.0,  # 5 min pause after failures
            hard_watchdog_interval=60.0,
        )
        
        # Session
        self.session = get_session()
        
        # Stats
        self.scan_count = 0
        self.signals_generated = 0
        self._last_stats_report = datetime.now(timezone.utc)
        
        # Signal cooldown - prevent same token signals within 10 minutes
        self._last_signal_tokens = {}  # token_address -> timestamp
        
        # Settings
        self.scan_interval = int(os.getenv('SCAN_INTERVAL_SEC', 30))
        self.max_tokens = int(os.getenv('MAX_TOKENS', 500))
        
        # Graceful shutdown handler
        self._shutdown = False
    
    async def init(self):
        """Initialize components"""
        await self.scanner.init_session()
        self.watchdog.start()
        self.watchdog.register_callback(self._request_shutdown)
        logger.info("Crypto Hunter initialized with self-healing architecture")
    
    def _request_shutdown(self):
        """Callback for watchdog shutdown request"""
        logger.warning("Shutdown requested by watchdog")
        self._shutdown = True
    
    async def cleanup(self):
        """Cleanup resources"""
        self.watchdog.stop()
        await self.scanner.close_session()
        self.session.close()
        logger.info("Crypto Hunter shutdown complete")
    
    async def process_token(self, token_data: Dict) -> None:
        """Process a single token through the detection pipeline"""
        import time
        start_time = time.time()
        
        try:
            token_address = token_data.get('token_address')
            chain = token_data.get('chain')
            symbol = token_data.get('symbol', 'UNKNOWN')
            
            if not token_address or not chain:
                return
            
            # Get historical data from database
            historical = self.metrics_engine.get_historical_data(token_address, hours=1)
            
            # Calculate metrics
            metrics = self.metrics_engine.calculate_metrics(token_data, historical)
            
            # Log metrics for debugging
            logger.debug(f"{symbol} | vol={metrics.get('volume_velocity', 0):.2f}, "
                        f"bp={metrics.get('buy_pressure', 0):.2f}, "
                        f"tx={metrics.get('tx_growth', 0):.2f}")
            
            # Save metrics to database for future velocity calculations
            self.metrics_engine.save_metrics(metrics)
            
            # Update active token
            self._update_active_token(token_data)
            
            # Risk check
            risk = self.risk_engine.check_risk(metrics)
            if risk['is_rug_pull_risk']:
                logger.debug(f"FILTERED {symbol}: Rug pull risk")
                return
            
            # Detect whale activity
            whale_activity = self.whale_detector.detect(metrics)
            
            # Multi-timeframe data is provided by MultiScanner (DexScreener enrichment)
            # For now, skip OHLCV fetching to save API calls
            timeframe_strength = None  # Can be enabled later with OHLCV API
            
            # Try pump detection
            pump_signal = self.pump_detector.detect(metrics)
            if pump_signal:
                alpha = self.alpha_calc.calculate(metrics, whale_activity, timeframe_strength)
                
                logger.info(f"🚀 PUMP {symbol}: score={pump_signal.get('pump_score', 0):.3f}, "
                           f"alpha={alpha.get('alpha_score', 0):.3f}, {alpha.get('signal_strength')}")
                
                await self._handle_signal(token_data, metrics, pump_signal, alpha, risk, whale_activity)
                return
            
            # Try dip detection
            dip_signal = self.dip_detector.detect(metrics)
            if dip_signal:
                alpha = self.alpha_calc.calculate(metrics, whale_activity, timeframe_strength)
                
                logger.info(f"🎯 DIP {symbol}: score={dip_signal.get('dip_score', 0):.3f}, "
                           f"alpha={alpha.get('alpha_score', 0):.3f}, {alpha.get('signal_strength')}")
                
                await self._handle_signal(token_data, metrics, dip_signal, alpha, risk, whale_activity)
                return
            
            elapsed = time.time() - start_time
            logger.debug(f"{symbol} | PASS (no signal) - {elapsed:.3f}s")
            
        except Exception as e:
            logger.error(f"Error processing token {token_data.get('token_address')}: {e}")
            try:
                self.session.rollback()
            except:
                pass
    
    def _update_active_token(self, token_data: Dict):
        """Update active token in database"""
        try:
            existing = self.session.query(ActiveToken).filter_by(
                token_address=token_data.get('token_address'),
                chain=token_data.get('chain')
            ).first()
            
            if existing:
                existing.last_updated = datetime.now(timezone.utc)
                existing.price = token_data.get('price')
                existing.liquidity = token_data.get('liquidity')
                existing.volume_24h = token_data.get('volume_24h')
            else:
                new_token = ActiveToken(
                    token_address=token_data.get('token_address'),
                    chain=token_data.get('chain'),
                    symbol=token_data.get('symbol'),
                    name=token_data.get('name'),
                    price=token_data.get('price'),
                    liquidity=token_data.get('liquidity'),
                    volume_24h=token_data.get('volume_24h'),
                    market_cap=token_data.get('market_cap'),
                    token_age_hours=token_data.get('token_age_hours'),
                )
                self.session.add(new_token)
            
            self.session.commit()
        except Exception as e:
            logger.error(f"Error updating active token: {e}")
            self.session.rollback()
    
    async def _handle_signal(self, token_data: Dict, metrics: Dict,
                           signal: Dict, alpha: Dict, risk: Dict, whale: bool):
        """Handle detected signal - save to DB and send notification"""
        import math
        import time
        
        try:
            # Cooldown check - don't signal same token within 10 minutes
            token_address = token_data.get('token_address')
            now = time.time()
            if token_address in self._last_signal_tokens:
                last_signal_time = self._last_signal_tokens[token_address]
                if now - last_signal_time < 600:  # 10 minutes cooldown
                    logger.debug(f"Signal COOLDOWN for {token_data.get('symbol')}: {now - last_signal_time:.0f}s since last signal")
                    return
            
            # Update last signal time
            self._last_signal_tokens[token_address] = now
            # Cleanup old entries (keep only last 100)
            if len(self._last_signal_tokens) > 100:
                oldest = min(self._last_signal_tokens.values())
                if now - oldest > 3600:
                    self._last_signal_tokens = {k: v for k, v in self._last_signal_tokens.items() if now - v < 3600}
            # Validate metrics
            nan_detected = False
            debug_info = []
            
            pump_score = signal.get('pump_score', 0) or 0
            dip_score = signal.get('dip_score', 0) or 0
            alpha_score = alpha.get('alpha_score', 0) or 0
            
            for name, val in [('pump_score', pump_score), ('dip_score', dip_score), ('alpha_score', alpha_score)]:
                if isinstance(val, float) and (math.isnan(val) or math.isinf(val)):
                    nan_detected = True
                    debug_info.append(f"{name}=NaN/Inf")
            
            for key in ['volume_velocity', 'buy_pressure', 'tx_growth', 'liquidity_velocity']:
                val = metrics.get(key, 0)
                if isinstance(val, float) and (math.isnan(val) or math.isinf(val)):
                    nan_detected = True
                    metrics[key] = 0.0
            
            if nan_detected:
                logger.warning(f"Signal SKIPPED for {token_data.get('symbol')}: NaN metrics")
                skip_notification = {
                    'symbol': token_data.get('symbol'),
                    'chain': token_data.get('chain'),
                    'reason': f"invalid metrics: {'; '.join(debug_info)}",
                }
                await self.notifier.send_skipped_signal(skip_notification)
                return
            
            # Create signal record
            signal_record = Signal(
                signal_type=str(signal.get('signal_type')),
                token_address=str(token_data.get('token_address')),
                chain=str(token_data.get('chain')),
                symbol=str(token_data.get('symbol')),
                name=str(token_data.get('name')) if token_data.get('name') else None,
                price_at_signal=float(token_data.get('price')) if token_data.get('price') else None,
                pump_score=float(pump_score),
                dip_score=float(dip_score),
                alpha_score=float(alpha_score),
                signal_strength=str(alpha.get('signal_strength')) if alpha.get('signal_strength') else None,
                volume_velocity=float(metrics.get('volume_velocity')) if metrics.get('volume_velocity') else None,
                buy_pressure=float(metrics.get('buy_pressure')) if metrics.get('buy_pressure') else None,
                tx_growth=float(metrics.get('tx_growth')) if metrics.get('tx_growth') else None,
                liquidity_velocity=float(metrics.get('liquidity_velocity')) if metrics.get('liquidity_velocity') else None,
                whale_activity=bool(whale),
                rug_pull_risk=bool(risk.get('is_rug_pull_risk')),
                liquidity_ratio=float(risk.get('liquidity_ratio')) if risk.get('liquidity_ratio') else None,
                nan_detected=False,
                metrics_valid=True,
            )
            
            self.session.add(signal_record)
            self.session.commit()
            
            # Create SignalResult for performance tracking
            result = SignalResult(
                signal_id=signal_record.id,
                token_address=token_data.get('token_address'),
                chain=token_data.get('chain'),
                symbol=token_data.get('symbol'),
                signal_type=signal.get('signal_type'),
                price_at_signal=float(token_data.get('price')) if token_data.get('price') else None,
                alpha_score=float(alpha_score),
                signal_strength=alpha.get('signal_strength'),
            )
            self.session.add(result)
            self.session.commit()
            
            self.signals_generated += 1
            
            # Send Telegram notification
            notification_data = {
                'symbol': token_data.get('symbol'),
                'name': token_data.get('name') or token_data.get('symbol'),
                'chain': token_data.get('chain'),
                'price': token_data.get('price'),
                'token_address': token_data.get('token_address'),
                'alpha_score': alpha_score,
                'signal_strength': alpha.get('signal_strength'),
                'pump_score': pump_score,
                'dip_score': dip_score,
                'metrics': {
                    'volume_velocity': metrics.get('volume_velocity'),
                    'buy_pressure': metrics.get('buy_pressure'),
                    'tx_growth': metrics.get('tx_growth'),
                    'liquidity_velocity': metrics.get('liquidity_velocity'),
                    'whale_activity': whale,
                },
                'risk': risk,
                'metrics_valid': True,
                'saved': True,
            }
            
            if signal.get('signal_type') == 'PUMP':
                await self.notifier.send_pump_signal(notification_data)
            elif signal.get('signal_type') == 'DIP':
                await self.notifier.send_dip_signal(notification_data)
            
            logger.info(f"Signal saved: {token_data.get('symbol')} - {alpha.get('signal_strength')}")
            
        except Exception as e:
            logger.error(f"Error handling signal: {e}")
            self.session.rollback()
    
    async def scan_cycle(self):
        """Execute one scan cycle with watchdog integration"""
        cycle_start = datetime.now(timezone.utc)
        
        # Mark cycle start for watchdog
        self.watchdog.start_cycle()
        
        try:
            self.scan_count += 1
            logger.info(f"=== Scan cycle #{self.scan_count} ===")
            
            # Check if paused
            if self.watchdog.check_paused():
                pause_remaining = self.watchdog.stats.pause_until - time.time() if self.watchdog.stats.pause_until else 0
                logger.warning(f"Scanner PAUSED for {pause_remaining:.0f}s more")
                return
            
            # Scan chains with caching
            chains = ["ethereum", "bsc", "arbitrum", "polygon", "optimism", "base", "avalanche", "solana"]
            all_pairs = await self.scanner.scan_all_chains(chains)
            
            logger.info(f"Fetched {len(all_pairs)} pairs")
            
            # Filter tokens
            filtered = self.scanner.filter_tokens(all_pairs)
            logger.info(f"After filtering: {len(filtered)} tokens")
            
            # Process tokens
            processed = 0
            signals_before = self.signals_generated
            
            for token_data in filtered[:self.max_tokens]:
                if self._shutdown:
                    logger.info("Shutdown requested, stopping scan")
                    break
                
                await self.process_token(token_data)
                processed += 1
                await asyncio.sleep(0.05)  # Rate limiting
            
            new_signals = self.signals_generated - signals_before
            cycle_duration = (datetime.now(timezone.utc) - cycle_start).total_seconds()
            
            logger.info(f"Cycle #{self.scan_count} complete: processed={processed}, "
                       f"signals={new_signals}, duration={cycle_duration:.1f}s")
            
            # Cleanup old data every 10 cycles
            if self.scan_count % 10 == 0:
                cleanup_old_data(self.session)
                self.cache.cleanup()  # Cleanup expired cache entries
                logger.info("Cleanup completed")
            
            # Send heartbeat every hour
            self._maybe_send_heartbeat()
            
            # Mark cycle success for watchdog
            self.watchdog.end_cycle(success=True)
            
        except Exception as e:
            logger.error(f"Error in scan cycle: {e}")
            self.watchdog.end_cycle(success=False, error=str(e))
            await self.notifier.send_error_alert(str(e))
    
    def _maybe_send_heartbeat(self):
        """Send heartbeat stats every hour"""
        now = datetime.now(timezone.utc)
        if now - self._last_stats_report >= timedelta(hours=1):
            self._last_stats_report = now
            
            stats = {
                'scan_count': self.scan_count,
                'total_signals': self.signals_generated,
                'watchdog_stats': self.watchdog.get_stats(),
                'cache_stats': self.cache.stats(),
            }
            
            # Run async in sync context
            try:
                loop = asyncio.get_event_loop()
                if not loop.is_closed():
                    loop.create_task(self.notifier.send_heartbeat(stats))
            except:
                pass
    
    async def run(self):
        """Main loop with graceful shutdown"""
        await self.init()
        
        try:
            with GracefulShutdown() as shutdown_handler:
                while not (self._shutdown or shutdown_handler.shutdown_requested):
                    await self.scan_cycle()
                    
                    if not self._shutdown:
                        logger.info(f"Next scan in {self.scan_interval}s...")
                        await asyncio.sleep(self.scan_interval)
        
        except KeyboardInterrupt:
            logger.info("Keyboard interrupt received")
        finally:
            await self.cleanup()


async def main():
    """Entry point"""
    # Initialize database (SQLite with WAL mode)
    init_database()
    logger.info("Database initialized (SQLite)")
    
    # Create logs directory
    os.makedirs('logs', exist_ok=True)
    
    # Start scanner
    hunter = CryptoHunter()
    await hunter.run()


if __name__ == "__main__":
    asyncio.run(main())
