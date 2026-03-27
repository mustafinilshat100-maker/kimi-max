from typing import Dict, Optional
import os
import math
from dotenv import load_dotenv

load_dotenv()


def safe_value(v):
    """Return 0 if v is None, NaN, or Inf"""
    if v is None:
        return 0
    if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
        return 0
    return v


class PumpDetector:
    """Detect pump signals based on multiple metrics"""
    
    def __init__(self):
        self.buy_pressure_min = float(os.getenv('PUMP_BUY_PRESSURE_MIN', 3.0))
        self.volume_velocity_min = float(os.getenv('PUMP_VOLUME_VELOCITY_MIN', 2.0))
        self.tx_growth_min = float(os.getenv('PUMP_TX_GROWTH_MIN', 3.0))
        self.liquidity_velocity_min = float(os.getenv('PUMP_LIQUIDITY_VELOCITY_MIN', 1.05))
        self.price_change_min = float(os.getenv('PUMP_PRICE_CHANGE_MIN', 0.03))
        self.pump_score_min = float(os.getenv('PUMP_SCORE_MIN', 0.7))
    
    def detect(self, metrics: Dict) -> Optional[Dict]:
        """
        Detect pump signal based on conditions with NaN protection
        """
        # Safe extraction with NaN protection
        buy_pressure = safe_value(metrics.get('buy_pressure', 1.0)) or 1.0
        volume_velocity = safe_value(metrics.get('volume_velocity', 1.0)) or 1.0
        volume_acceleration = safe_value(metrics.get('volume_acceleration', 1.0)) or 1.0
        tx_growth = safe_value(metrics.get('tx_growth', 1.0)) or 1.0
        liquidity_velocity = safe_value(metrics.get('liquidity_velocity', 1.0)) or 1.0
        holders_velocity = safe_value(metrics.get('holders_velocity', 1.0)) or 1.0
        price_change_5m = safe_value(metrics.get('price_change_5m', 0)) / 100
        
        # Check minimum conditions
        if buy_pressure < self.buy_pressure_min:
            return None
        if volume_velocity < self.volume_velocity_min:
            return None
        if tx_growth < self.tx_growth_min:
            return None
        if liquidity_velocity < self.liquidity_velocity_min:
            return None
        if price_change_5m < self.price_change_min:
            return None
        
        # Calculate Pump Score with NaN protection
        pump_score = (
            0.30 * min(volume_acceleration / 3, 2.0) +
            0.25 * min(tx_growth / 5, 2.0) +
            0.20 * min(buy_pressure / 5, 2.0) +
            0.15 * min((liquidity_velocity - 1) * 10, 2.0) +
            0.10 * min(holders_velocity, 2.0)
        )
        
        # Final NaN check
        if math.isnan(pump_score) or math.isinf(pump_score):
            pump_score = 0.0
        
        if pump_score < self.pump_score_min:
            return None
        
        return {
            'signal_type': 'PUMP',
            'pump_score': round(pump_score, 3),
            'metrics': {
                'buy_pressure': round(buy_pressure, 2),
                'volume_velocity': round(volume_velocity, 2),
                'volume_acceleration': round(volume_acceleration, 2),
                'tx_growth': round(tx_growth, 2),
                'liquidity_velocity': round(liquidity_velocity, 3),
                'price_change_5m': round(price_change_5m * 100, 2),
            }
        }


class DipDetector:
    """Detect dip/recovery signals (false dumps)"""
    
    def __init__(self):
        self.price_drop_min = float(os.getenv('DIP_PRICE_DROP_MIN', -0.25))
        self.price_drop_max = float(os.getenv('DIP_PRICE_DROP_MAX', -0.10))
        self.volume_spike_min = float(os.getenv('DIP_VOLUME_SPIKE_MIN', 3.0))
        self.tx_spike_min = float(os.getenv('DIP_TX_SPIKE_MIN', 2.0))
        self.liquidity_outflow_max = float(os.getenv('DIP_LIQUIDITY_OUTFLOW_MAX', 0.05))
        self.dip_score_min = float(os.getenv('DIP_SCORE_MIN', 0.65))
    
    def detect(self, metrics: Dict) -> Optional[Dict]:
        """
        Detect dip recovery signal with NaN protection:
        - price_drop_5m between -10% and -25%
        - volume_spike > 3
        - tx_spike > 2
        - liquidity_outflow < 5%
        """
        # Safe extraction with NaN protection
        price_change_5m = safe_value(metrics.get('price_change_5m', 0)) / 100
        volume_velocity = safe_value(metrics.get('volume_velocity', 1.0)) or 1.0
        tx_growth = safe_value(metrics.get('tx_growth', 1.0)) or 1.0
        liquidity_velocity = safe_value(metrics.get('liquidity_velocity', 1.0)) or 1.0
        
        # Price drop in range
        if not (self.price_drop_min <= price_change_5m <= self.price_drop_max):
            return None
        
        # Volume spike
        if volume_velocity < self.volume_spike_min:
            return None
        
        # Transaction spike
        if tx_growth < self.tx_spike_min:
            return None
        
        # Liquidity outflow check
        liquidity_outflow = 1 - liquidity_velocity if liquidity_velocity < 1 else 0
        if liquidity_outflow > self.liquidity_outflow_max:
            return None
        
        # Calculate Dip Score with NaN protection
        liquidity_stability = 1 - liquidity_outflow
        dip_score = (
            0.4 * min(abs(price_change_5m) * 4, 1.0) +
            0.3 * min(volume_velocity / 5, 1.0) +
            0.2 * min(tx_growth / 5, 1.0) +
            0.1 * liquidity_stability
        )
        
        # Final NaN check
        if math.isnan(dip_score) or math.isinf(dip_score):
            dip_score = 0.0
        
        if dip_score < self.dip_score_min:
            return None
        
        return {
            'signal_type': 'DIP',
            'dip_score': round(dip_score, 3),
            'metrics': {
                'price_drop': round(price_change_5m * 100, 2),
                'volume_spike': round(volume_velocity, 2),
                'tx_spike': round(tx_growth, 2),
                'liquidity_stability': round(liquidity_stability, 3),
            }
        }


class WhaleDetector:
    """Detect whale activity"""
    
    def detect(self, metrics: Dict) -> bool:
        """
        Whale trade > 1% of liquidity pool
        """
        liquidity = metrics.get('liquidity', 0) or 0
        volume_5m = metrics.get('volume_5m', 0) or 0
        
        if liquidity <= 0:
            return False
        
        # Estimate whale trade as significant portion of 5m volume
        # If volume_5m is unusually high compared to average, likely whale activity
        whale_threshold = liquidity * 0.01  # 1% of liquidity
        
        # Consider whale activity if volume spike with high buy pressure
        if volume_5m > whale_threshold * 5:  # 5% of liquidity in 5min
            return True
        
        return False


class RiskEngine:
    """Check token risk factors"""
    
    def __init__(self):
        self.top_holder_max = float(os.getenv('RUG_PULL_TOP_HOLDER_MAX', 0.20))
        self.min_token_age_hours = float(os.getenv('RUG_PULL_MIN_TOKEN_AGE_HOURS', 1))
        self.min_liquidity_ratio = float(os.getenv('MIN_LIQUIDITY_MARKETCAP_RATIO', 0.05))
    
    def check_risk(self, metrics: Dict) -> Dict:
        """
        Check rug pull risk:
        - top_holder_share > 20%
        - token_age < 1 hour
        - liquidity/market_cap < 0.05
        """
        risks = {
            'is_rug_pull_risk': False,
            'is_high_risk': False,
            'risk_factors': [],
            'liquidity_ratio': 0.0,
        }
        
        # Top holder check
        top_holder_share = metrics.get('top_holder_share', 0) or 0
        if top_holder_share > self.top_holder_max:
            risks['is_rug_pull_risk'] = True
            risks['risk_factors'].append(f"Top holder share {top_holder_share:.1%} > {self.top_holder_max:.0%}")
        
        # Token age check
        token_age_hours = metrics.get('token_age_hours', 999) or 999
        if token_age_hours < self.min_token_age_hours:
            risks['is_rug_pull_risk'] = True
            risks['risk_factors'].append(f"Token age {token_age_hours:.1f}h < {self.min_token_age_hours}h")
        
        # Liquidity ratio check
        liquidity = metrics.get('liquidity', 0) or 0
        market_cap = metrics.get('market_cap', 0) or 0
        if market_cap > 0:
            liquidity_ratio = liquidity / market_cap
            risks['liquidity_ratio'] = round(liquidity_ratio, 4)
            if liquidity_ratio < self.min_liquidity_ratio:
                risks['is_high_risk'] = True
                risks['risk_factors'].append(f"Liquidity/MC ratio {liquidity_ratio:.2%} < {self.min_liquidity_ratio:.0%}")
        
        return risks


class AlphaCalculator:
    """Calculate final Alpha Score with multi-timeframe analysis"""
    
    def __init__(self):
        self.weights = {
            'volume_acceleration': float(os.getenv('ALPHA_WEIGHT_VOLUME_ACCEL', 0.20)),
            'tx_growth': float(os.getenv('ALPHA_WEIGHT_TX_GROWTH', 0.15)),
            'buy_pressure': float(os.getenv('ALPHA_WEIGHT_BUY_PRESSURE', 0.15)),
            'liquidity_velocity': float(os.getenv('ALPHA_WEIGHT_LIQUIDITY_VEL', 0.10)),
            'holders_velocity': float(os.getenv('ALPHA_WEIGHT_HOLDERS_VEL', 0.10)),
            'whale': float(os.getenv('ALPHA_WEIGHT_WHALE', 0.10)),
            'timeframe': float(os.getenv('ALPHA_WEIGHT_TIMEFRAME', 0.20)),  # Multi-timeframe weight
        }
        self.strong_buy = float(os.getenv('STRONG_BUY_THRESHOLD', 2.5))
        self.watch = float(os.getenv('WATCH_THRESHOLD', 1.5))
        self.weak = float(os.getenv('WEAK_SIGNAL_THRESHOLD', 0.5))
    
    def calculate(self, metrics: Dict, whale_activity: bool = False, timeframe_strength: Dict = None) -> Dict:
        """
        Calculate Alpha Score with multi-timeframe analysis and NaN protection:
        - Short impulse (1m): 20% of timeframe weight
        - Trend confirmation (5m): 30% of timeframe weight  
        - Sustainability (15m): 30% of timeframe weight
        - Global direction (1h): 20% of timeframe weight
        """
        # Safe extraction with NaN protection
        volume_acceleration = safe_value(metrics.get('volume_acceleration', 1.0)) or 1.0
        tx_growth = safe_value(metrics.get('tx_growth', 1.0)) or 1.0
        buy_pressure = safe_value(metrics.get('buy_pressure', 1.0)) or 1.0
        liquidity_velocity = safe_value(metrics.get('liquidity_velocity', 1.0)) or 1.0
        holders_velocity = safe_value(metrics.get('holders_velocity', 1.0)) or 1.0
        
        # Base alpha score from metrics
        base_score = (
            self.weights['volume_acceleration'] * min(volume_acceleration / 2, 3.0) +
            self.weights['tx_growth'] * min(tx_growth / 3, 3.0) +
            self.weights['buy_pressure'] * min(buy_pressure / 3, 3.0) +
            self.weights['liquidity_velocity'] * min((liquidity_velocity - 1) * 5 + 1, 3.0) +
            self.weights['holders_velocity'] * min(holders_velocity, 3.0) +
            self.weights['whale'] * (2.0 if whale_activity else 0)
        )
        
        # Add timeframe analysis if available
        timeframe_score = 0.0
        if timeframe_strength:
            # Weight timeframe components
            tf_weights = {
                '1m_impulse': 0.20,      # Short impulse
                '5m_trend': 0.30,        # Trend confirmation
                '15m_sustainability': 0.30,  # Sustainability
                '1h_direction': 0.20,    # Global direction
            }
            
            for key, weight in tf_weights.items():
                value = safe_value(timeframe_strength.get(key, 0))
                # Normalize to 0-3 range for consistency
                normalized = min(max(value + 1, 0), 3)  # Shift from -1,1 to 0,2 then cap at 3
                timeframe_score += normalized * weight
            
            # Apply timeframe weight to base score
            timeframe_contribution = timeframe_score * self.weights['timeframe']
            base_score += timeframe_contribution
        
        alpha_score = base_score
        
        # Final NaN check
        if math.isnan(alpha_score) or math.isinf(alpha_score):
            alpha_score = 0.0
        
        # Classify signal
        if alpha_score >= self.strong_buy:
            signal_strength = 'STRONG_BUY'
        elif alpha_score >= self.watch:
            signal_strength = 'WATCH'
        elif alpha_score >= self.weak:
            signal_strength = 'WEAK_SIGNAL'
        else:
            signal_strength = 'NONE'
        
        result = {
            'alpha_score': round(alpha_score, 3),
            'signal_strength': signal_strength,
        }
        
        return result
