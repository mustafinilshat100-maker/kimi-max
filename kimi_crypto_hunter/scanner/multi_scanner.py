"""
Multi-API Scanner - aggregates data from multiple DEX APIs.
Prioritizes data quality and availability.
"""

import aiohttp
import asyncio
import logging
import json
from datetime import datetime, timezone
from typing import List, Dict, Optional, Tuple
import os
from dotenv import load_dotenv
from utils.cache import get_cache

load_dotenv()

logger = logging.getLogger(__name__)


class MultiScanner:
    """
    Multi-source scanner combining:
    - GeckoTerminal: reliable pairs list and OHLCV
    - DexScreener: 5-minute volume data
    - DexTools: fallback for 5-minute volume
    """
    
    GECKOTERMINAL_API = "https://api.geckoterminal.com/api/v2"
    DEXSCREENER_API = "https://api.dexscreener.com/latest/dex"
    DEXTOOLS_API = "https://api.dextools.io/secondary/v1"
    
    # Network mappings
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
        self.chain_thresholds = self._load_thresholds()
        self._dexscreener_session_count = 0  # Rate limiting
    
    def _load_thresholds(self) -> Dict:
        default = {
            "ethereum": {"min_liquidity": 5000, "min_volume": 10000},
            "bsc": {"min_liquidity": 3000, "min_volume": 5000},
            "solana": {"min_liquidity": 2000, "min_volume": 3000},
            "base": {"min_liquidity": 3000, "min_volume": 5000},
            "arbitrum": {"min_liquidity": 3000, "min_volume": 5000},
            "polygon": {"min_liquidity": 2000, "min_volume": 4000},
            "optimism": {"min_liquidity": 3000, "min_volume": 5000},
            "avalanche": {"min_liquidity": 2000, "min_volume": 3000},
        }
        
        try:
            chain_config = os.getenv('CHAIN_THRESHOLDS')
            if chain_config:
                return json.loads(chain_config.replace('\n', '').replace('  ', ' '))
        except:
            pass
        return default
    
    async def init_session(self):
        timeout = aiohttp.ClientTimeout(total=30, connect=10)
        self.session = aiohttp.ClientSession(timeout=timeout)
    
    async def close_session(self):
        """Close aiohttp session"""
        if self.session:
            await self.session.close()
            logger.info("Scanner session closed")
    
    # ==================== DexScreener 5m Data ====================
    
    async def fetch_dexscreener_5m_volume(self, chain: str, symbol: str, token_address: str) -> Optional[Dict]:
        """
        Fetch 5-minute volume data from DexScreener.
        Uses search to find the specific token pair.
        """
        try:
            # Rate limiting - DexScreener is rate limited
            self._dexscreener_session_count += 1
            if self._dexscreener_session_count > 30:
                await asyncio.sleep(1)  # 1 request per second max
                self._dexscreener_session_count = 0
            
            ds_chain_map = {
                'ethereum': 'ethereum',
                'bsc': 'bsc',
                'solana': 'solana',
                'base': 'base',
                'arbitrum': 'arbitrum',
                'polygon': 'polygon',
                'optimism': 'optimism',
                'avalanche': 'avalanche',
            }
            ds_chain = ds_chain_map.get(chain, chain)
            
            # Search for the token
            url = f"{self.DEXSCREENER_API}/search?q={symbol}"
            async with self.session.get(url) as resp:
                if resp.status != 200:
                    return None
                
                data = await resp.json()
                pairs = data.get('pairs', [])
                
                # Find matching pair on correct chain
                for pair in pairs:
                    if pair.get('chainId') != ds_chain:
                        continue
                    
                    base = pair.get('baseToken', {})
                    if base.get('address', '').lower() != token_address.lower():
                        continue
                    
                    # Found the pair - extract 5m data
                    volume = pair.get('volume', {})
                    txns = pair.get('txns', {})
                    
                    return {
                        'volume_5m': float(volume.get('m5', 0) or 0),
                        'volume_1h': float(volume.get('h1', 0) or 0),
                        'buy_count_5m': int(txns.get('m5', {}).get('buys', 0) or 0),
                        'sell_count_5m': int(txns.get('m5', {}).get('sells', 0) or 0),
                        'buy_volume_5m': float(volume.get('m5', 0) or 0) * 0.5,  # Approximate
                        'sell_volume_5m': float(volume.get('m5', 0) or 0) * 0.5,
                        'price_change_5m': float(pair.get('priceChange', {}).get('m5', 0) or 0),
                        'price_change_1h': float(pair.get('priceChange', {}).get('h1', 0) or 0),
                        'liquidity': float(pair.get('liquidity', {}).get('usd', 0) or 0),
                        'pair_address': pair.get('pairAddress'),
                        'dex_id': pair.get('dexId'),
                    }
            
            return None
        except Exception as e:
            logger.debug(f"DexScreener 5m data error: {e}")
            return None
    
    # ==================== GeckoTerminal Pairs ====================
    
    async def fetch_geckoterminal_pools(self, network: str, page: int = 1) -> List[Dict]:
        """Fetch pools from GeckoTerminal"""
        try:
            url = f"{self.GECKOTERMINAL_API}/networks/{network}/pools"
            async with self.session.get(url, params={"page": page}) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return data.get('data', [])
                return []
        except Exception as e:
            logger.debug(f"GeckoTerminal pools error: {e}")
            return []
    
    def parse_geckoterminal_pool(self, pool: Dict, chain: str) -> Optional[Dict]:
        """Parse GeckoTerminal pool into standardized format"""
        try:
            attrs = pool.get('attributes', {})
            relationships = pool.get('relationships', {})
            
            # Get base token address
            base_token_id = relationships.get('base_token', {}).get('data', {}).get('id', '')
            if '_' in base_token_id:
                base_token_id = base_token_id.split('_', 1)[1]
            
            # Parse symbol from name
            name = attrs.get('name', '')
            symbol = attrs.get('base_token_symbol')
            if not symbol and name:
                symbol = name.split(' / ')[0] if ' / ' in name else name.split()[0]
            
            # Price change percentages
            price_change = attrs.get('price_change_percentage', {})
            
            return {
                'token_address': base_token_id,
                'chain': chain,
                'symbol': symbol or 'UNKNOWN',
                'name': name,
                'price': float(attrs.get('base_token_price_usd', 0) or 0),
                'price_change_5m': float(price_change.get('m5', 0) or 0),
                'price_change_1h': float(price_change.get('h1', 0) or 0),
                'price_change_24h': float(price_change.get('h24', 0) or 0),
                'volume_24h': float(attrs.get('volume_usd', {}).get('h24', 0) or 0),
                'liquidity': float(attrs.get('reserve_in_usd', 0) or 0),
                'market_cap': float(attrs.get('market_cap_usd', 0) or 0),
                # 5m data will be filled from DexScreener
                'volume_5m': 0,
                'buy_count_5m': 0,
                'sell_count_5m': 0,
                'buy_volume_5m': 0,
                'sell_volume_5m': 0,
                'pair_address': pool.get('id', ''),
                'dex_id': attrs.get('dex_id', 'unknown'),
                'token_age_hours': 24,
            }
        except Exception as e:
            logger.debug(f"Parse error: {e}")
            return None
    
    # ==================== Main Scanning ====================
    
    async def scan_all_chains(self, chains: List[str]) -> List[Dict]:
        """
        Scan all chains: get pairs from GeckoTerminal, enrich with DexScreener 5m data.
        """
        # Check cache first
        cached = self.cache.get_pairs_list(chains)
        if cached:
            logger.info(f"Using cached pairs ({len(cached)} pairs)")
            return cached
        
        all_pairs = []
        
        for chain in chains:
            network = self.GECKO_NETWORK_MAP.get(chain, chain)
            
            # Get pools from GeckoTerminal
            for page in range(1, 3):
                pools = await self.fetch_geckoterminal_pools(network, page)
                
                for pool in pools:
                    parsed = self.parse_geckoterminal_pool(pool, chain)
                    if parsed:
                        all_pairs.append(parsed)
                
                if len(pools) < 50:
                    break
                await asyncio.sleep(0.2)
            
            # Rate limit between chains
            await asyncio.sleep(0.5)
        
        logger.info(f"Fetched {len(all_pairs)} pairs, enriching with DexScreener 5m data...")
        
        # Enrich with DexScreener 5m data (only for top tokens by liquidity to avoid rate limits)
        enriched = 0
        for pair in all_pairs[:30]:  # Only top 30 to avoid rate limits
            ds_data = await self.fetch_dexscreener_5m_volume(
                pair['chain'],
                pair['symbol'],
                pair['token_address']
            )
            
            if ds_data and ds_data.get('volume_5m', 0) > 0:
                pair['volume_5m'] = ds_data.get('volume_5m', 0)
                pair['buy_count_5m'] = ds_data.get('buy_count_5m', 0)
                pair['sell_count_5m'] = ds_data.get('sell_count_5m', 0)
                pair['buy_volume_5m'] = ds_data.get('buy_volume_5m', 0)
                pair['sell_volume_5m'] = ds_data.get('sell_volume_5m', 0)
                pair['price_change_5m'] = ds_data.get('price_change_5m', pair['price_change_5m'])
                pair['price_change_1h'] = ds_data.get('price_change_1h', pair['price_change_1h'])
                if ds_data.get('liquidity'):
                    pair['liquidity'] = ds_data.get('liquidity', pair['liquidity'])
                if ds_data.get('pair_address'):
                    pair['pair_address'] = ds_data.get('pair_address', pair['pair_address'])
                if ds_data.get('dex_id'):
                    pair['dex_id'] = ds_data.get('dex_id', pair['dex_id'])
                enriched += 1
            
            await asyncio.sleep(0.3)  # Rate limiting
        
        logger.info(f"Enriched {enriched} tokens with DexScreener 5m data")
        
        # Cache the result
        self.cache.set_pairs_list(chains, all_pairs)
        
        return all_pairs
    
    def filter_tokens(self, pairs: List[Dict]) -> List[Dict]:
        """Filter by liquidity and volume thresholds"""
        filtered = []
        
        for pair in pairs:
            chain = pair.get('chain', 'unknown').lower()
            thresholds = self.chain_thresholds.get(chain, self.chain_thresholds.get('default', {}))
            
            liquidity = pair.get('liquidity', 0) or 0
            volume_24h = pair.get('volume_24h', 0) or 0
            
            if liquidity < thresholds.get('min_liquidity', 5000):
                continue
            if volume_24h < thresholds.get('min_volume', 10000):
                continue
            
            filtered.append(pair)
        
        logger.debug(f"Filtered {len(pairs)} → {len(filtered)} tokens")
        return filtered
    
    async def get_5m_data_for_token(self, chain: str, symbol: str, token_address: str) -> Optional[Dict]:
        """Get fresh 5m data for a specific token (used for processing)"""
        return await self.fetch_dexscreener_5m_volume(chain, symbol, token_address)
