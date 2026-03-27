"""
In-memory cache with TTL support for API rate limiting.
Reduces API calls from ~72k/hour to ~5-7k/hour.
"""

import threading
import time
import logging
from typing import Dict, Any, Optional, List
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

class CacheEntry:
    """Single cache entry with TTL"""
    def __init__(self, data: Any, ttl: int):
        self.data = data
        self.expires_at = time.time() + ttl
        self.created_at = time.time()
    
    def is_expired(self) -> bool:
        return time.time() > self.expires_at

class APICache:
    """
    Thread-safe in-memory cache with TTL.
    
    Usage:
        cache = APICache()
        cache.set("pairs_list", data, ttl=300)  # 5 min
        data = cache.get("pairs_list")
    """
    
    def __init__(self):
        self._cache: Dict[str, CacheEntry] = {}
        self._lock = threading.RLock()
        self._hits = 0
        self._misses = 0
    
    def set(self, key: str, data: Any, ttl: int) -> None:
        """Set cache entry with TTL in seconds"""
        with self._lock:
            self._cache[key] = CacheEntry(data, ttl)
            logger.debug(f"Cache SET: {key} (TTL={ttl}s)")
    
    def get(self, key: str) -> Optional[Any]:
        """Get cache entry if exists and not expired"""
        with self._lock:
            entry = self._cache.get(key)
            if entry is None:
                self._misses += 1
                return None
            
            if entry.is_expired():
                del self._cache[key]
                self._misses += 1
                logger.debug(f"Cache EXPIRED: {key}")
                return None
            
            self._hits += 1
            return entry.data
    
    def delete(self, key: str) -> None:
        """Delete specific cache entry"""
        with self._lock:
            if key in self._cache:
                del self._cache[key]
    
    def clear(self) -> None:
        """Clear all cache"""
        with self._lock:
            self._cache.clear()
            logger.info("Cache cleared")
    
    def cleanup_expired(self) -> int:
        """Remove all expired entries, return count removed"""
        removed = 0
        with self._lock:
            expired_keys = [
                k for k, v in self._cache.items() 
                if v.is_expired()
            ]
            for key in expired_keys:
                del self._cache[key]
                removed += 1
            
            if removed > 0:
                logger.debug(f"Cache cleanup: removed {removed} expired entries")
        
        return removed
    
    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics"""
        with self._lock:
            total = self._hits + self._misses
            hit_rate = (self._hits / total * 100) if total > 0 else 0
            
            return {
                'entries': len(self._cache),
                'hits': self._hits,
                'misses': self._misses,
                'hit_rate': f"{hit_rate:.1f}%",
                'total_requests': total,
            }


class TokenCache:
    """
    Specialized cache for token data.
    Implements 5-minute TTL for pairs list and 60-second TTL for OHLCV.
    """
    
    # Cache TTLs
    PAIRS_LIST_TTL = 300      # 5 minutes for pairs list
    OHLCV_TTL = 60            # 1 minute for OHLCV data
    METRICS_TTL = 60           # 1 minute for metrics
    
    def __init__(self):
        self._cache = APICache()
        self._last_cleanup = time.time()
    
    def get_pairs_list(self, chains: List[str]) -> Optional[List[Dict]]:
        """Get cached pairs list for chains"""
        key = f"pairs_{'_'.join(sorted(chains))}"
        return self._cache.get(key)
    
    def set_pairs_list(self, chains: List[str], pairs: List[Dict]) -> None:
        """Cache pairs list for chains"""
        key = f"pairs_{'_'.join(sorted(chains))}"
        self._cache.set(key, pairs, self.PAIRS_LIST_TTL)
    
    def get_ohlcv(self, token_address: str, timeframe: str) -> Optional[List[Dict]]:
        """Get cached OHLCV data for token"""
        key = f"ohlcv_{token_address}_{timeframe}"
        return self._cache.get(key)
    
    def set_ohlcv(self, token_address: str, timeframe: str, data: List[Dict]) -> None:
        """Cache OHLCV data for token"""
        key = f"ohlcv_{token_address}_{timeframe}"
        self._cache.set(key, data, self.OHLCV_TTL)
    
    def get_token_metrics(self, token_address: str) -> Optional[Dict]:
        """Get cached metrics for token"""
        return self._cache.get(f"metrics_{token_address}")
    
    def set_token_metrics(self, token_address: str, metrics: Dict) -> None:
        """Cache metrics for token"""
        self._cache.set(f"metrics_{token_address}", metrics, self.METRICS_TTL)
    
    def invalidate_token(self, token_address: str) -> None:
        """Invalidate all cache entries for token"""
        with self._cache._lock:
            keys_to_delete = [
                k for k in self._cache._cache.keys()
                if token_address in k
            ]
            for key in keys_to_delete:
                del self._cache._cache[key]
    
    def cleanup(self) -> int:
        """Cleanup expired entries"""
        return self._cache.cleanup_expired()
    
    def stats(self) -> Dict[str, Any]:
        """Get cache statistics"""
        return self._cache.get_stats()


# Global cache instance
_global_cache: Optional[TokenCache] = None
_cache_lock = threading.Lock()

def get_cache() -> TokenCache:
    """Get global cache instance (singleton)"""
    global _global_cache
    with _cache_lock:
        if _global_cache is None:
            _global_cache = TokenCache()
            logger.info("Global TokenCache initialized")
        return _global_cache
