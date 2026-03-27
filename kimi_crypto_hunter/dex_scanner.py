"""
DEX Scanner - GeckoTerminal primary source (more reliable than DexScreener search).
DexScreener is only used for Solana pairs where GeckoTerminal may be limited.
"""

import aiohttp
import asyncio
import logging
import json
from datetime import datetime, timezone
from typing import List, Dict, Optional
import os
from dotenv import load_dotenv
from utils.cache import get_cache

load_dotenv()

logger = logging.getLogger(__name__)

class DEXScanner:
    """Scanner for DEX data - GeckoTerminal primary, DexScreener fallback"""
    
    # API endpoints
    GECKOTERMINAL_API = "https://api.geckoterminal.com/api/v2"
    DEXSCREENER_API = "https://api.dexscreener.com/latest/dex"
    
    # Network mapping for GeckoTerminal
    GECKO_NETWORK_MAP = {
        'ethereum': 'eth',
        'bsc': 'bsc',
        'solana': 'solana',
        'base': 'base',
        'arbitrum': 'arbitrum',
        'polygon': 'polygon_pos',
        'optimism': 'optimism',
        'avalanche': 'avax',
    }
    
    def __init__(self):
        self.session: Optional[aiohttp.ClientSession] = None
        self.cache = get_cache()
        self.chain_thresholds = self._load_chain_thresholds()
        logger.info(f"Loaded thresholds for {len(self.chain_thresholds)} chains")
    
    def _load_chain_thresholds(self) -> Dict:
        """Load per-chain thresholds from environment"""
        default_thresholds = {
            "ethereum": {"min_liquidity": 5000, "min_volume": 10000, "pump_score_adjust": 1.0},
            "bsc": {"min_liquidity": 3000, "min_volume": 5000, "pump_score_adjust": 0.95},
            "solana": {"min_liquidity": 2000, "min_volume": 3000, "pump_score_adjust": 0.85},
            "base": {"min_liquidity": 3000, "min_volume": 5000, "pump_score_adjust": 0.90},
            "arbitrum": {"min_liquidity": 3000, "min_volume": 5000, "pump_score_adjust": 0.90},
            "polygon": {"min_liquidity": 2000, "min_volume": 4000, "pump_score_adjust": 0.90},
            "optimism": {"min_liquidity": 3000, "min_volume": 5000, "pump_score_adjust": 0.90},
            "avalanche": {"min_liquidity": 2000, "min_volume": 3000, "pump_score_adjust": 0.90},
            "default": {"min_liquidity": 5000, "min_volume": 10000, "pump_score_adjust": 1.0}
        }
        
        try:
            chain_config = os.getenv('CHAIN_THRESHOLDS')
            if chain_config:
                loaded = json.loads(chain_config.replace('\n', '').replace('  ', ' '))
                logger.info("Loaded custom chain thresholds from .env")
                return loaded
        except Exception as e:
            logger.warning(f"Failed to load CHAIN_THRESHOLDS: {e}")
        
        return default_thresholds
    
    def get_chain_thresholds(self, chain: str) -> Dict:
        """Get thresholds for specific chain"""
        chain_lower = chain.lower()
        return self.chain_thresholds.get(chain_lower, self.chain_thresholds.get("default"))
    
    async def init_session(self):
        """Initialize aiohttp session"""
        timeout = aiohttp.ClientTimeout(total=30, connect=10)
        self.session = aiohttp.ClientSession(timeout=timeout)
        logger.info("Scanner session initialized")
    
    async def close_session(self):
        """Close session"""
        if self.session:
            await self.session.close()
    
    # ==================== GeckoTerminal (Primary) ====================
    
    async def fetch_geckoterminal_pools(self, network: str, page: int = 1) -> List[Dict]:
        """Fetch pools from GeckoTerminal"""
        try:
            url = f"{self.GECKOTERMINAL_API}/networks/{network}/pools"
            params = {"page": page}
            
            async with self.session.get(url, params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    return data.get('data', [])
                else:
                    logger.debug(f"GeckoTerminal pools error: {response.status} for {network}")
                    return []
        except Exception as e:
            logger.debug(f"GeckoTerminal pools fetch error: {e}")
            return []
    
    def parse_geckoterminal_pool(self, pool: Dict, chain: str) -> Optional[Dict]:
        """Parse GeckoTerminal pool data into standardized format"""
        try:
            attrs = pool.get('attributes', {})
            relationships = pool.get('relationships', {})
            
            # Get base token address (strip network prefix like "eth_0x...")
            base_token_id = relationships.get('base_token', {}).get('data', {}).get('id', '')
            if '_' in base_token_id:
                base_token_id = base_token_id.split('_', 1)[1]
            
            # Get quote token
            quote_token_id = relationships.get('quote_token', {}).get('data', {}).get('id', '')
            if '_' in quote_token_id:
                quote_token_id = quote_token_id.split('_', 1)[1]
            
            # Parse symbol from name (e.g., "WETH / USDT 0.01%" -> "WETH")
            name = attrs.get('name', '')
            symbol = attrs.get('base_token_symbol')
            if not symbol and name:
                # Extract base token from name like "WETH / USDT 0.01%"
                symbol = name.split(' / ')[0] if ' / ' in name else name.split()[0]
            
            # Parse reserves for volume
            reserve_usd = float(attrs.get('reserve_in_usd', 0) or 0)
            volume_h24 = float(attrs.get('volume_usd', {}).get('h24', 0) or 0)
            
            # Get DEX info
            dex_id = attrs.get('dex_id', 'unknown')
            
            # Get price change percentages
            price_change_pct = attrs.get('price_change_percentage', {})
            price_change_5m = float(price_change_pct.get('m5', 0) or 0)
            price_change_1h = float(price_change_pct.get('h1', 0) or 0)
            price_change_24h = float(price_change_pct.get('h24', 0) or 0)
            
            return {
                'token_address': base_token_id,
                'chain': chain,
                'symbol': symbol or 'UNKNOWN',
                'name': name,
                'price': float(attrs.get('base_token_price_usd', 0) or 0),
                'price_change_5m': price_change_5m,
                'price_change_1h': price_change_1h,
                'price_change_24h': price_change_24h,
                'volume_24h': volume_h24,
                'liquidity': reserve_usd,
                'market_cap': float(attrs.get('market_cap_usd', 0) or 0),
                'tx_count_24h': 0,
                'buy_count_5m': 0,
                'sell_count_5m': 0,
                'buy_volume_5m': 0,
                'sell_volume_5m': 0,
                'pair_address': pool.get('id', ''),
                'dex_id': dex_id,
                'token_age_hours': 24,
            }
        except Exception as e:
            logger.debug(f"Error parsing GeckoTerminal pool: {e}")
            return None
    
    # ==================== DexScreener (Primary for pairs with 5m data) ====================
    
    async def fetch_dexscreener_chains(self, chain: str, limit: int = 100) -> List[Dict]:
        """Fetch pairs from DexScreener by chain - provides 5m volume data"""
        # Map our chain names to DexScreener chain IDs
        ds_chain_map = {
            'ethereum': 'ethereum',
            'bsc': 'bsc',
            'base': 'base',
            'arbitrum': 'arbitrum',
            'polygon': 'polygon',
            'optimism': 'optimism',
            'avalanche': 'avalanche',
        }
        ds_chain = ds_chain_map.get(chain, chain)
        
        try:
            # Use the tokens endpoint which returns pairs sorted by liquidity
            url = f"{self.DEXSCREENER_API}/tokens/{ds_chain}"
            async with self.session.get(url) as response:
                if response.status == 200:
                    data = await response.json()
                    pairs = data.get('pairs', [])
                    # Sort by liquidity
                    pairs.sort(key=lambda x: float(x.get('liquidity', {}).get('usd', 0) or 0), reverse=True)
                    return pairs[:limit]
                else:
                    logger.debug(f"DexScreener {chain} error: {response.status}")
                    return []
        except Exception as e:
            logger.debug(f"DexScreener {chain} fetch error: {e}")
            return []
    
    async def fetch_dexscreener_solana(self, limit: int = 100) -> List[Dict]:
        """Fetch Solana pairs from DexScreener"""
        try:
            url = f"{self.DEXSCREENER_API}/tokens/solana"
            async with self.session.get(url) as response:
                if response.status == 200:
                    data = await response.json()
                    pairs = data.get('pairs', [])
                    pairs.sort(key=lambda x: float(x.get('liquidity', {}).get('usd', 0) or 0), reverse=True)
                    return pairs[:limit]
                else:
                    return []
        except Exception as e:
            logger.debug(f"DexScreener Solana fetch error: {e}")
            return []
    
    def parse_dexscreener_pair(self, pair: Dict, chain: str) -> Optional[Dict]:
        """Parse DexScreener pair for Solana fallback"""
        try:
            base_token = pair.get('baseToken', {})
            return {
                'token_address': base_token.get('address'),
                'chain': chain,
                'symbol': base_token.get('symbol', 'UNKNOWN'),
                'name': base_token.get('name'),
                'price': float(pair.get('priceUsd', 0) or 0),
                'price_change_5m': float(pair.get('priceChange', {}).get('m5', 0) or 0),
                'price_change_1h': float(pair.get('priceChange', {}).get('h1', 0) or 0),
                'price_change_24h': float(pair.get('priceChange', {}).get('h24', 0) or 0),
                'volume_24h': float(pair.get('volume', {}).get('h24', 0) or 0),
                'volume_5m': float(pair.get('volume', {}).get('m5', 0) or 0),
                'liquidity': float(pair.get('liquidity', {}).get('usd', 0) or 0),
                'market_cap': float(pair.get('marketCap', 0) or 0),
                'tx_count_24h': 0,
                'buy_count_5m': 0,
                'sell_count_5m': 0,
                'buy_volume_5m': 0,
                'sell_volume_5m': 0,
                'pair_address': pair.get('pairAddress'),
                'dex_id': pair.get('dexId'),
                'token_age_hours': 24,
            }
        except Exception as e:
            logger.debug(f"Error parsing DexScreener pair: {e}")
            return None
    
    # ==================== OHLCV ====================
    
    async def fetch_ohlcv(self, network: str, pool_address: str, timeframe: str = "5m", limit: int = 100) -> List[Dict]:
        """Fetch OHLCV data with caching"""
        cached = self.cache.get_ohlcv(pool_address, timeframe)
        if cached is not None:
            return cached
        
        try:
            url = f"{self.GECKOTERMINAL_API}/networks/{network}/pools/{pool_address}/ohlcv/{timeframe}"
            params = {"limit": limit}
            
            async with self.session.get(url, params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    ohlcv_list = data.get('data', {}).get('attributes', {}).get('ohlcv_list', [])
                    
                    candles = []
                    for candle in ohlcv_list:
                        if len(candle) >= 6:
                            candles.append({
                                'timestamp': candle[0],
                                'open': float(candle[1]),
                                'high': float(candle[2]),
                                'low': float(candle[3]),
                                'close': float(candle[4]),
                                'volume': float(candle[5]),
                            })
                    
                    self.cache.set_ohlcv(pool_address, timeframe, candles)
                    return candles
                else:
                    return []
        except Exception as e:
            logger.debug(f"OHLCV fetch error: {e}")
            return []
    
    async def fetch_multi_timeframe_ohlcv(self, chain: str, pool_address: str) -> Dict[str, List[Dict]]:
        """Fetch OHLCV for multiple timeframes"""
        network = self.GECKO_NETWORK_MAP.get(chain, chain)
        
        timeframes = {
            '1m': {'limit': 60, 'wait': 0.05},
            '5m': {'limit': 60, 'wait': 0.05},
            '15m': {'limit': 48, 'wait': 0.05},
            '1h': {'limit': 24, 'wait': 0.05},
        }
        
        result = {}
        for tf, params in timeframes.items():
            candles = await self.fetch_ohlcv(network, pool_address, tf, params['limit'])
            result[tf] = candles
            await asyncio.sleep(params['wait'])
        
        return result
    
    # ==================== Main Scanning ====================
    
    async def scan_all_chains(self, chains: List[str]) -> List[Dict]:
        """Scan multiple chains using GeckoTerminal (primary) + DexScreener (Solana fallback)"""
        cached_pairs = self.cache.get_pairs_list(chains)
        if cached_pairs is not None:
            logger.info(f"Pairs list cache HIT ({len(cached_pairs)} pairs)")
            return cached_pairs
        
        all_pairs = []
        
        for chain in chains:
            gecko_network = self.GECKO_NETWORK_MAP.get(chain, chain)
            
            # Use GeckoTerminal for all chains (reliable, stable)
            for page in range(1, 3):  # 2 pages per chain
                pools = await self.fetch_geckoterminal_pools(gecko_network, page)
                for pool in pools:
                    parsed = self.parse_geckoterminal_pool(pool, chain)
                    if parsed:
                        all_pairs.append(parsed)
                if len(pools) < 50:
                    break
                await asyncio.sleep(0.2)
            
            # Solana also from DexScreener (for additional coverage)
            if chain == 'solana':
                pairs = await self.fetch_dexscreener_solana(limit=30)
                for raw_pair in pairs:
                    parsed = self.parse_dexscreener_pair(raw_pair, chain)
                    if parsed:
                        all_pairs.append(parsed)
            
            await asyncio.sleep(0.3)
        
        self.cache.set_pairs_list(chains, all_pairs)
        logger.info(f"Fetched + cached {len(all_pairs)} pairs from {len(chains)} chains")
        
        return all_pairs
    
    def filter_tokens(self, pairs: List[Dict]) -> List[Dict]:
        """Filter tokens by liquidity and volume thresholds"""
        filtered = []
        
        for pair in pairs:
            chain = pair.get('chain', 'unknown').lower()
            thresholds = self.get_chain_thresholds(chain)
            
            liquidity = pair.get('liquidity', 0) or 0
            volume_24h = pair.get('volume_24h', 0) or 0
            
            min_liquidity = thresholds.get('min_liquidity', 5000)
            min_volume = thresholds.get('min_volume', 10000)
            
            if liquidity < min_liquidity:
                continue
            if volume_24h < min_volume:
                continue
            
            pair['_thresholds'] = thresholds
            filtered.append(pair)
        
        logger.debug(f"Filtered {len(pairs)} → {len(filtered)} tokens")
        return filtered
