import pandas as pd
import numpy as np
import math
from typing import List, Dict, Optional
from datetime import datetime, timezone, timedelta
from database.models import TokenMetrics, get_session
import logging

logger = logging.getLogger(__name__)


def safe_value(v):
    """Return 0 if v is None, NaN, or Inf"""
    if v is None:
        return 0
    if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
        return 0
    if isinstance(v, (int, float)):
        return v
    return 0


def safe_div(a, b):
    """Safe division — returns 0 if b is 0 or invalid"""
    a, b = safe_value(a), safe_value(b)
    if b == 0:
        return 0
    result = a / b
    if math.isnan(result) or math.isinf(result):
        return 0
    return result


class MetricsEngine:
    """Calculate derived metrics for token analysis"""

    def __init__(self):
        self.session = get_session()

    def calculate_volume_acceleration(self, current_volume: float, historical: pd.DataFrame) -> float:
        """Calculate volume acceleration: volume_velocity / avg_velocity_1h"""
        try:
            if len(historical) < 12:
                return 1.0
            avg_velocity = safe_value(historical['volume_5m'].pct_change().mean()) + 1
            if avg_velocity <= 0:
                return 1.0
            if len(historical) >= 2:
                prev_volume = safe_value(historical.iloc[-2]['volume_5m'])
                current_volume = safe_value(current_volume)
                volume_velocity = safe_div(current_volume, prev_volume) if prev_volume > 0 else 1.0
            else:
                volume_velocity = 1.0
            result = safe_div(volume_velocity, avg_velocity)
            return result if result > 0 else 1.0
        except Exception as e:
            logger.debug(f"Error calculating volume acceleration: {e}")
            return 1.0

    def calculate_buy_pressure(self, buy_volume: float, sell_volume: float) -> float:
        """Calculate buy pressure: buy_volume / sell_volume"""
        try:
            buy_volume = safe_value(buy_volume)
            sell_volume = safe_value(sell_volume)
            result = safe_div(buy_volume, sell_volume)
            return result if result > 0 else 1.0
        except Exception as e:
            logger.debug(f"Error calculating buy pressure: {e}")
            return 1.0

    def calculate_tx_growth(self, current_tx: int, historical: pd.DataFrame) -> float:
        """Calculate transaction growth: current_tx / avg_tx_1h"""
        try:
            if len(historical) < 12:
                return 1.0
            avg_tx_1h = safe_value(historical.tail(12)['tx_count_5m'].mean())
            if avg_tx_1h <= 0:
                return 1.0
            current_tx = safe_value(current_tx)
            result = safe_div(current_tx, avg_tx_1h)
            return result if result > 0 else 1.0
        except Exception as e:
            logger.debug(f"Error calculating tx growth: {e}")
            return 1.0

    def calculate_liquidity_velocity(self, current_liquidity: float, historical: pd.DataFrame) -> float:
        """Calculate liquidity velocity: current / previous"""
        try:
            if len(historical) < 2:
                return 1.0
            prev_liquidity = safe_value(historical.iloc[-2]['liquidity'])
            if prev_liquidity <= 0:
                return 1.0
            current_liquidity = safe_value(current_liquidity)
            result = safe_div(current_liquidity, prev_liquidity)
            return result if result > 0 else 1.0
        except Exception as e:
            logger.debug(f"Error calculating liquidity velocity: {e}")
            return 1.0

    def calculate_holders_velocity(self, token_address: str, chain: str) -> float:
        """Calculate holders velocity (placeholder)"""
        return 1.0

    def calculate_whale_activity(self, volume_5m: float, liquidity: float) -> bool:
        """Detect whale activity: volume_5m > 5% of liquidity"""
        try:
            if liquidity <= 0:
                return False
            return volume_5m > (liquidity * 0.05)
        except Exception as e:
            logger.debug(f"Error calculating whale activity: {e}")
            return False

    def calculate_metrics(self, current: Dict, historical: List[Dict]) -> Dict:
        """Calculate all metrics for a token with NaN protection"""
        metrics = current.copy()
        if not historical or len(historical) < 2:
            metrics.update({
                'volume_velocity': 1.0, 'volume_acceleration': 1.0,
                'buy_pressure': 1.0, 'tx_growth': 1.0,
                'liquidity_velocity': 1.0, 'holders_velocity': 1.0,
            })
            return metrics
        try:
            df = pd.DataFrame(historical)
            df['timestamp'] = pd.to_datetime(df['timestamp'])
            df = df.sort_values('timestamp')
            
            current_volume = safe_value(current.get('volume_5m', 0))
            prev_volume = safe_value(df.iloc[-2]['volume_5m'] if len(df) >= 2 else current_volume)
            metrics['volume_velocity'] = safe_div(current_volume, prev_volume) if prev_volume > 0 else 1.0
            metrics['volume_acceleration'] = self.calculate_volume_acceleration(current_volume, df)
            
            buy_vol = safe_value(current.get('buy_volume_5m', 0))
            sell_vol = safe_value(current.get('sell_volume_5m', 0))
            metrics['buy_pressure'] = self.calculate_buy_pressure(buy_vol, sell_vol)
            
            current_tx = safe_value(current.get('tx_count_5m', 0))
            metrics['tx_growth'] = self.calculate_tx_growth(current_tx, df)
            
            current_liquidity = safe_value(current.get('liquidity', 0))
            metrics['liquidity_velocity'] = self.calculate_liquidity_velocity(current_liquidity, df)
            
            token_address = current.get('token_address', '')
            chain = current.get('chain', '')
            metrics['holders_velocity'] = self.calculate_holders_velocity(token_address, chain)
            
            volume_5m = safe_value(current.get('volume_5m', 0))
            metrics['whale_activity'] = self.calculate_whale_activity(volume_5m, current_liquidity)
            
            # Validate all metrics for NaN/Inf
            for key in ['volume_velocity', 'volume_acceleration', 'buy_pressure', 
                       'tx_growth', 'liquidity_velocity', 'holders_velocity']:
                val = metrics.get(key, 0)
                if isinstance(val, float) and (math.isnan(val) or math.isinf(val)):
                    metrics[key] = 0.0
                    logger.warning(f"NaN/Inf detected in {key}, set to 0")
                    
        except Exception as e:
            logger.error(f"Error in calculate_metrics: {e}")
            metrics.update({
                'volume_velocity': 1.0, 'volume_acceleration': 1.0,
                'buy_pressure': 1.0, 'tx_growth': 1.0,
                'liquidity_velocity': 1.0, 'holders_velocity': 1.0,
                'whale_activity': False,
            })
        return metrics

    def get_historical_data(self, token_address: str, hours: int = 1) -> List[Dict]:
        """Get historical metrics for a token"""
        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
        records = self.session.query(TokenMetrics).filter(
            TokenMetrics.token_address == token_address,
            TokenMetrics.timestamp >= cutoff
        ).all()
        return [{
            'timestamp': r.timestamp,
            'volume_5m': r.volume_5m,
            'liquidity': r.liquidity,
            'tx_count_5m': r.tx_count_5m,
        } for r in records]

    def calculate_timeframe_strength(self, ohlcv_data: Dict) -> Dict[str, float]:
        """
        Calculate strength indicators for each timeframe.

        Args:
            ohlcv_data: Dictionary with '1m', '5m', '15m', '1h' candles

        Returns:
            Dictionary with timeframe strength scores
        """
        strength = {
            '1m_impulse': 0.0,
            '5m_trend': 0.0,
            '15m_sustainability': 0.0,
            '1h_direction': 0.0,
        }

        try:
            # 1m: Short impulse detection (last 5 candles)
            candles_1m = ohlcv_data.get('1m', [])
            if len(candles_1m) >= 5:
                recent = candles_1m[-5:]
                price_change = (recent[-1]['close'] - recent[0]['open']) / recent[0]['open'] if recent[0]['open'] > 0 else 0
                volume_avg = sum(c['volume'] for c in recent) / len(recent)
                volume_prev = sum(c['volume'] for c in candles_1m[-10:-5]) / 5 if len(candles_1m) >= 10 else volume_avg
                volume_spike = volume_avg / volume_prev if volume_prev > 0 else 1.0

                strength['1m_impulse'] = (price_change * 10) + (volume_spike - 1)

            # 5m: Trend confirmation (last 3 candles)
            candles_5m = ohlcv_data.get('5m', [])
            if len(candles_5m) >= 3:
                recent = candles_5m[-3:]
                # Check for consistent direction
                ups = sum(1 for c in recent if c['close'] > c['open'])
                downs = 3 - ups

                if ups == 3:
                    strength['5m_trend'] = 1.0  # Strong uptrend
                elif ups == 2:
                    strength['5m_trend'] = 0.5  # Weak uptrend
                elif downs == 3:
                    strength['5m_trend'] = -1.0  # Strong downtrend
                elif downs == 2:
                    strength['5m_trend'] = -0.5  # Weak downtrend
                else:
                    strength['5m_trend'] = 0.0  # Neutral

            # 15m: Sustainability (EMA alignment)
            candles_15m = ohlcv_data.get('15m', [])
            if len(candles_15m) >= 4:
                closes = [c['close'] for c in candles_15m[-4:]]
                # Simple EMA check
                ema_short = sum(closes[-2:]) / 2
                ema_long = sum(closes) / 4

                if ema_short > ema_long:
                    strength['15m_sustainability'] = 0.5 + (ema_short / ema_long - 1)
                else:
                    strength['15m_sustainability'] = -0.5 - (1 - ema_short / ema_long)

            # 1h: Global direction
            candles_1h = ohlcv_data.get('1h', [])
            if len(candles_1h) >= 6:
                # Compare recent 3h vs previous 3h
                recent_vol = sum(c['volume'] for c in candles_1h[-3:])
                prev_vol = sum(c['volume'] for c in candles_1h[-6:-3])
                recent_price = candles_1h[-1]['close']
                prev_price = candles_1h[-4]['close'] if len(candles_1h) >= 4 else candles_1h[0]['open']

                price_change = (recent_price - prev_price) / prev_price if prev_price > 0 else 0
                volume_ratio = recent_vol / prev_vol if prev_vol > 0 else 1.0

                strength['1h_direction'] = (price_change * 5) + (volume_ratio - 1) * 0.5

        except Exception as e:
            logger.debug(f"Error calculating timeframe strength: {e}")

        return strength

    def save_metrics(self, metrics: Dict):
        """Save calculated metrics to database"""
        try:
            valid_fields = [
                'token_address', 'chain', 'symbol', 'name', 'price',
                'price_change_5m', 'price_change_1h', 'price_change_24h', 'market_cap',
                'volume_24h', 'volume_5m', 'volume_1h',
                'tx_count_24h', 'tx_count_5m', 'buy_count_5m', 'sell_count_5m',
                'buy_volume_5m', 'sell_volume_5m',
                'liquidity', 'liquidity_change_5m',
                'pair_address', 'dex_id', 'token_age_hours', 'top_holder_share', 'holders_count',
                'buy_pressure', 'volume_velocity', 'volume_acceleration', 'tx_growth',
                'liquidity_velocity', 'holders_velocity'
            ]
            filtered_metrics = {k: v for k, v in metrics.items() if k in valid_fields}
            for key in ['token_address', 'pair_address']:
                if key in filtered_metrics and filtered_metrics[key]:
                    filtered_metrics[key] = str(filtered_metrics[key])[:100]
            for key in ['symbol', 'name', 'chain', 'dex_id']:
                if key in filtered_metrics and filtered_metrics[key]:
                    if key == 'symbol':
                        filtered_metrics[key] = str(filtered_metrics[key])[:50]
                    elif key == 'name':
                        filtered_metrics[key] = str(filtered_metrics[key])[:200]
                    elif key == 'chain':
                        filtered_metrics[key] = str(filtered_metrics[key])[:20]
                    elif key == 'dex_id':
                        filtered_metrics[key] = str(filtered_metrics[key])[:50]
            for key, value in filtered_metrics.items():
                if isinstance(value, np.floating):
                    filtered_metrics[key] = float(value)
                elif isinstance(value, np.integer):
                    filtered_metrics[key] = int(value)
                elif value is None:
                    if key in ['buy_pressure', 'volume_velocity', 'volume_acceleration',
                               'tx_growth', 'liquidity_velocity', 'holders_velocity']:
                        filtered_metrics[key] = 1.0
                    elif key in ['price', 'market_cap', 'volume_24h', 'liquidity']:
                        filtered_metrics[key] = 0.0
            record = TokenMetrics(**filtered_metrics)
            self.session.add(record)
            self.session.commit()
        except Exception as e:
            logger.error(f"Error saving metrics: {e}")
            self.session.rollback()
