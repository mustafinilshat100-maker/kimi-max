"""
Social Score Module for Crypto Hunter v2
Tracks social media mentions and sentiment for tokens.
MVP Version: Basic Twitter scraping with keyword matching
"""

import asyncio
import logging
from typing import Dict, List, Optional
from datetime import datetime, timezone, timedelta
from collections import defaultdict
import re

logger = logging.getLogger(__name__)


class SocialScorer:
    """
    Calculate social score based on Twitter mentions and sentiment.
    MVP Version - lightweight implementation
    """
    
    def __init__(self):
        # Cache for recent mentions
        self.mentions_cache = defaultdict(lambda: defaultdict(list))
        self.cache_ttl = timedelta(minutes=30)
        
        # Top crypto Twitter accounts to monitor (public data)
        self.influential_accounts = [
            'elonmusk', 'cz_binance', 'saylor', 'VitalikButerin',
            'CryptoWhale', 'WhaleAlert', 'WatcherGuru', 'CryptoRank',
        ]
        
        # Basic sentiment keywords
        self.positive_keywords = [
            'bullish', 'moon', 'pump', 'gem', 'alpha', 'buy', 'long',
            ' breakout', 'surge', 'rally', 'gain', 'profit', '🚀', '🌙',
            'huge', 'massive', 'big news', 'partnership', 'listing',
        ]
        
        self.negative_keywords = [
            'bearish', 'dump', 'crash', 'scam', 'rug', 'sell', 'short',
            'bear', 'loss', 'dip', 'correction', 'panic', 'fear', '😱',
            'avoid', 'stay away', 'red flag', 'danger',
        ]
    
    async def get_social_score(self, symbol: str, name: str, chain: str) -> Dict:
        """
        Get social score for a token.
        
        Returns:
            Dict with social_score, mentions_1m, mentions_5m, mentions_15m, sentiment
        """
        try:
            # Clean symbol for search (remove $ if present)
            clean_symbol = symbol.replace('$', '').upper()
            
            # For MVP, simulate social data collection
            # In production, this would use Twitter API v2
            mentions_data = await self._fetch_mentions(clean_symbol, name, chain)
            
            # Calculate sentiment
            sentiment = self._calculate_sentiment(mentions_data)
            
            # Calculate score (0.0 to 3.0 scale)
            base_score = 1.0  # Neutral
            
            # Boost for mention velocity
            if mentions_data['count_1m'] > 0:
                base_score += 0.2
            if mentions_data['count_5m'] > 5:
                base_score += 0.3
            if mentions_data['count_15m'] > 15:
                base_score += 0.5
            
            # Apply sentiment multiplier
            if sentiment == 'positive':
                base_score *= 1.3
            elif sentiment == 'negative':
                base_score *= 0.7
            
            # Cap at 3.0
            social_score = min(base_score, 3.0)
            
            return {
                'social_score': round(social_score, 3),
                'mentions_1m': mentions_data['count_1m'],
                'mentions_5m': mentions_data['count_5m'],
                'mentions_15m': mentions_data['count_15m'],
                'sentiment': sentiment,
                'sources': mentions_data.get('sources', []),
            }
            
        except Exception as e:
            logger.error(f"Error calculating social score for {symbol}: {e}")
            return {
                'social_score': 1.0,  # Neutral on error
                'mentions_1m': 0,
                'mentions_5m': 0,
                'mentions_15m': 0,
                'sentiment': 'neutral',
                'sources': [],
            }
    
    async def _fetch_mentions(self, symbol: str, name: str, chain: str) -> Dict:
        """
        Fetch mention counts for different time windows.
        MVP: Returns placeholder data.
        Production: Use Twitter API v2 search endpoint.
        """
        # MVP: Return neutral/placeholder data
        # This simulates what real data might look like
        
        # In production, you would:
        # 1. Query Twitter API: search/recent with query=f"${symbol} OR {name}"
        # 2. Filter by time windows (1m, 5m, 15m)
        # 3. Count mentions from influential accounts
        # 4. Analyze sentiment of tweets
        
        return {
            'count_1m': 0,   # Placeholder
            'count_5m': 2,   # Placeholder
            'count_15m': 5,  # Placeholder
            'sources': ['twitter'],  # Placeholder
        }
    
    def _calculate_sentiment(self, mentions_data: Dict) -> str:
        """
        Calculate overall sentiment from mentions.
        MVP: Returns based on placeholder logic.
        """
        # MVP: Return neutral
        # Production: Analyze text of each mention for sentiment
        return 'neutral'
    
    def analyze_text_sentiment(self, text: str) -> Dict:
        """
        Analyze sentiment of a single text.
        
        Args:
            text: Tweet or post text
            
        Returns:
            Dict with sentiment and confidence
        """
        text_lower = text.lower()
        
        positive_count = sum(1 for kw in self.positive_keywords if kw in text_lower)
        negative_count = sum(1 for kw in self.negative_keywords if kw in text_lower)
        
        if positive_count > negative_count:
            return {'sentiment': 'positive', 'confidence': min(positive_count * 0.3, 1.0)}
        elif negative_count > positive_count:
            return {'sentiment': 'negative', 'confidence': min(negative_count * 0.3, 1.0)}
        else:
            return {'sentiment': 'neutral', 'confidence': 0.5}
    
    def extract_token_mentions(self, text: str) -> List[str]:
        """
        Extract token symbols mentioned in text.
        
        Args:
            text: Tweet or post text
            
        Returns:
            List of mentioned symbols
        """
        # Match $SYMBOL pattern
        pattern = r'\$([A-Za-z0-9]{2,10})'
        matches = re.findall(pattern, text)
        return [m.upper() for m in matches]


# Global instance
_social_scorer = None

def get_social_scorer() -> SocialScorer:
    """Get or create global SocialScorer instance"""
    global _social_scorer
    if _social_scorer is None:
        _social_scorer = SocialScorer()
    return _social_scorer
