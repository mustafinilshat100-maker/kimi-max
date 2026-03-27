"""
Self-healing watchdog system with 3 levels of protection:
1. Hard watchdog - monitors process health every minute
2. Soft watchdog - monitors scan cycle duration
3. Job restart queue - handles consecutive failures

Prevents the scanner from hanging or crashing permanently.
"""

import os
import signal
import asyncio
import logging
import time
import threading
from datetime import datetime, timezone
from typing import Optional, Callable
from dataclasses import dataclass, field
from collections import deque

logger = logging.getLogger(__name__)

@dataclass
class WatchdogStats:
    """Statistics for watchdog monitoring"""
    scan_cycles_total: int = 0
    scan_cycles_success: int = 0
    scan_cycles_failed: int = 0
    consecutive_failures: int = 0
    last_cycle_start: Optional[float] = None
    last_cycle_end: Optional[float] = None
    last_cycle_duration: float = 0.0
    avg_cycle_duration: float = 0.0
    max_cycle_duration: float = 120.0  # 2 minutes max
    is_paused: bool = False
    pause_until: Optional[float] = None
    failure_history: deque = field(default_factory=lambda: deque(maxlen=10))
    
    @property
    def success_rate(self) -> float:
        if self.scan_cycles_total == 0:
            return 0.0
        return self.scan_cycles_success / self.scan_cycles_total * 100


class Watchdog:
    """
    3-level self-healing watchdog for scanner.
    
    Level 1 - Hard Watchdog:
        Checks if process is responsive every N seconds.
        Uses PID file to detect if process died.
    
    Level 2 - Soft Watchdog:
        Monitors scan cycle duration.
        If cycle takes > max_duration, sends SIGINT to request graceful shutdown.
    
    Level 3 - Job Restart Queue:
        Tracks consecutive failures.
        After max_failures, pauses for cooldown period before resuming.
    """
    
    def __init__(
        self,
        max_cycle_duration: float = 120.0,
        max_consecutive_failures: int = 3,
        pause_duration: float = 300.0,
        hard_watchdog_interval: float = 60.0,
    ):
        self.max_cycle_duration = max_cycle_duration
        self.max_consecutive_failures = max_consecutive_failures
        self.pause_duration = pause_duration
        self.hard_watchdog_interval = hard_watchdog_interval
        
        self.stats = WatchdogStats(max_cycle_duration=max_cycle_duration)
        self._running = False
        self._shutdown_requested = False
        self._hard_watchdog_timer: Optional[threading.Timer] = None
        self._callbacks: list = []
        self._pid_file = "/root/.openclaw/workspace/crypto_hunter/.watchdog.pid"
        
        logger.info(f"Watchdog initialized: max_cycle={max_cycle_duration}s, "
                   f"max_failures={max_consecutive_failures}, pause={pause_duration}s")
    
    def _write_pid_file(self):
        """Write current PID to file for hard watchdog"""
        try:
            with open(self._pid_file, 'w') as f:
                f.write(str(os.getpid()))
        except Exception as e:
            logger.warning(f"Failed to write PID file: {e}")
    
    def _check_pid_alive(self) -> bool:
        """Check if PID file exists and process is alive"""
        try:
            if not os.path.exists(self._pid_file):
                return False
            
            with open(self._pid_file, 'r') as f:
                pid = int(f.read().strip())
            
            # Send signal 0 to check if process exists
            os.kill(pid, 0)
            return True
        except (ProcessLookupError, FileNotFoundError, ValueError):
            return False
        except PermissionError:
            # Process exists but we can't send signal - it's alive
            return True
        except Exception:
            return False
    
    def _hard_watchdog_check(self):
        """Level 1: Hard watchdog - check if process is alive"""
        if not self._running:
            return
        
        try:
            pid_alive = self._check_pid_alive()
            
            if not pid_alive:
                logger.error("HARD WATCHDOG: Process not responding! PID file missing or process dead.")
                self._trigger_shutdown()
            else:
                logger.debug("HARD WATCHDOG: Process alive and responsive")
            
            # Cleanup old PID file if process restarted
            if pid_alive:
                current_pid = os.getpid()
                try:
                    with open(self._pid_file, 'r') as f:
                        file_pid = int(f.read().strip())
                    if file_pid != current_pid:
                        self._write_pid_file()
                except:
                    self._write_pid_file()
                    
        except Exception as e:
            logger.error(f"HARD WATCHDOG: Check failed with error: {e}")
        
        # Schedule next check
        if self._running:
            self._hard_watchdog_timer = threading.Timer(
                self.hard_watchdog_interval,
                self._hard_watchdog_check
            )
            self._hard_watchdog_timer.daemon = True
            self._hard_watchdog_timer.start()
    
    def register_callback(self, callback: Callable):
        """Register callback to be called on shutdown request"""
        self._callbacks.append(callback)
    
    def _trigger_shutdown(self):
        """Trigger graceful shutdown via callbacks"""
        logger.warning("TRIGGERING GRACEFUL SHUTDOWN")
        for callback in self._callbacks:
            try:
                callback()
            except Exception as e:
                logger.error(f"Callback error: {e}")
    
    def start_cycle(self):
        """Mark the start of a scan cycle (call at cycle start)"""
        self.stats.last_cycle_start = time.time()
        self.stats.scan_cycles_total += 1
        logger.debug(f"CYCLE START: #{self.stats.scan_cycles_total}")
    
    def end_cycle(self, success: bool = True, error: str = None):
        """
        Mark the end of a scan cycle (call at cycle end).
        
        Level 2: Soft watchdog checks cycle duration here.
        Level 3: Job restart queue tracks consecutive failures.
        """
        now = time.time()
        duration = now - self.stats.last_cycle_start if self.stats.last_cycle_start else 0
        self.stats.last_cycle_end = now
        self.stats.last_cycle_duration = duration
        
        # Update average duration (rolling average)
        if self.stats.avg_cycle_duration == 0:
            self.stats.avg_cycle_duration = duration
        else:
            self.stats.avg_cycle_duration = (self.stats.avg_cycle_duration * 0.7 + duration * 0.3)
        
        if success:
            self.stats.scan_cycles_success += 1
            self.stats.consecutive_failures = 0
            logger.info(f"CYCLE END: SUCCESS (duration={duration:.1f}s, avg={self.stats.avg_cycle_duration:.1f}s)")
        else:
            self.stats.scan_cycles_failed += 1
            self.stats.consecutive_failures += 1
            self.stats.failure_history.append({
                'time': now,
                'error': error,
                'duration': duration
            })
            logger.warning(f"CYCLE END: FAILED (consecutive={self.stats.consecutive_failures}, error={error})")
        
        # Level 2: Check cycle duration
        if duration > self.max_cycle_duration:
            logger.error(f"SOFT WATCHDOG: Cycle took too long ({duration:.1f}s > {self.max_cycle_duration}s)")
            self._trigger_shutdown()
        
        # Level 3: Check consecutive failures
        if self.stats.consecutive_failures >= self.max_consecutive_failures:
            self._pause_scanner()
    
    def _pause_scanner(self):
        """Level 3: Pause scanner due to consecutive failures"""
        self.stats.is_paused = True
        self.stats.pause_until = time.time() + self.pause_duration
        logger.warning(f"JOB RESTART QUEUE: Pausing scanner for {self.pause_duration}s "
                      f"({self.stats.consecutive_failures} consecutive failures)")
    
    def check_paused(self) -> bool:
        """Check if scanner is paused, and auto-resume if pause period expired"""
        if not self.stats.is_paused:
            return False
        
        if time.time() >= self.stats.pause_until:
            self.stats.is_paused = False
            self.stats.pause_until = None
            self.stats.consecutive_failures = 0
            logger.info("JOB RESTART QUEUE: Scanner resumed after cooldown")
            return False
        
        return True
    
    def start(self):
        """Start the watchdog system"""
        self._running = True
        self._write_pid_file()
        
        # Start hard watchdog
        self._hard_watchdog_timer = threading.Timer(
            self.hard_watchdog_interval,
            self._hard_watchdog_check
        )
        self._hard_watchdog_timer.daemon = True
        self._hard_watchdog_timer.start()
        
        logger.info("Watchdog started (3 levels active)")
    
    def stop(self):
        """Stop the watchdog system"""
        self._running = False
        if self._hard_watchdog_timer:
            self._hard_watchdog_timer.cancel()
        try:
            if os.path.exists(self._pid_file):
                os.remove(self._pid_file)
        except:
            pass
        logger.info("Watchdog stopped")
    
    def get_stats(self) -> dict:
        """Get watchdog statistics"""
        return {
            'cycles_total': self.stats.scan_cycles_total,
            'cycles_success': self.stats.scan_cycles_success,
            'cycles_failed': self.stats.scan_cycles_failed,
            'success_rate': f"{self.stats.success_rate:.1f}%",
            'consecutive_failures': self.stats.consecutive_failures,
            'is_paused': self.stats.is_paused,
            'pause_remaining': max(0, self.stats.pause_until - time.time()) if self.stats.pause_until else 0,
            'avg_cycle_duration': f"{self.stats.avg_cycle_duration:.1f}s",
            'last_cycle_duration': f"{self.stats.last_cycle_duration:.1f}s",
        }


class GracefulShutdown:
    """
    Context manager for graceful shutdown handling.
    Catches SIGINT/SIGTERM and sets shutdown flag.
    """
    
    def __init__(self):
        self._shutdown = False
        self._original_handlers = {}
    
    def __enter__(self):
        # Register signal handlers
        self._original_handlers[signal.SIGINT] = signal.signal(signal.SIGINT, self._handle_signal)
        self._original_handlers[signal.SIGTERM] = signal.signal(signal.SIGTERM, self._handle_signal)
        return self
    
    def __exit__(self, *args):
        # Restore original handlers
        for sig, handler in self._original_handlers.items():
            signal.signal(sig, handler)
    
    def _handle_signal(self, signum, frame):
        """Handle shutdown signal"""
        sig_name = signal.Signals(signum).name
        logger.info(f"Received {sig_name}, initiating graceful shutdown...")
        self._shutdown = True
    
    @property
    def shutdown_requested(self) -> bool:
        return self._shutdown
