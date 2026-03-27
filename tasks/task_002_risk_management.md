# Task #002: Risk Management — Block Scam Signals

## Status
- [x] Created: 2026-03-27
- [ ] In progress
- [ ] Completed

## Problem (from Max's audit)

Crypto Hunter generates signals but DOES NOT filter scam/pump-dump tokens. Example:
- Token with 0.02% liquidity_ratio (should be >5%)
- Whale Activity + Low Liquidity = MANIPULATION, not opportunity
- Alpha Score contradicts Pump Score (formula bug)
- BSC network = higher scam risk (not weighted)

## Task

Improve `risk_engine.py` and `signal_detectors.py` to BLOCK scam signals:

### 1. Add Liquidity Ratio Check
```python
# Calculate: liquidity / market_cap
liquidity_ratio = token.liquidity / token.market_cap if token.market_cap > 0 else 0

# REJECT if liquidity_ratio < 0.01 (1%)
# This is the critical fix - without it, we trap users
```

### 2. Block Whale + Low Liquidity Combinations
```python
# If whale_activity == True AND liquidity < 10000 USD → SKIP
# Whales in low-liquidity pools = manipulation, not signal
```

### 3. Weight Network Risk
```python
NETWORK_RISK = {
    'ethereum': 0.9,   # Safe
    'base': 0.9,
    'arbitrum': 0.9,
    'optimism': 0.9,
    'bsc': 0.5,        # HIGH RISK - most scams
    'polygon': 0.7,
    'solana': 0.8,
    'avalanche': 0.7,
}
# Multiply final score by network risk
```

### 4. Reject New Tokens
```python
# If token_age_hours < 24 → automatic WEAK_SIGNAL
# New tokens = higher rug pull risk
```

### 5. Fix Alpha Score Formula
Alpha Score should NOT be high when Pump Score is low.
Current bug: Alpha can be 0.79 while Pump Score is 0.49.

Fix formula to make alpha_score <= pump_score when risk-adjusted.

## Files to Modify
- `kimi_crypto_hunter/detectors/signal_detectors.py`
- `kimi_crypto_hunter/detectors/risk_engine.py` (create if missing)
- `kimi_crypto_hunter/.env` (new thresholds)

## Expected Result
- NO signals with liquidity_ratio < 1%
- NO signals with whale_activity=True AND liquidity < $10k
- BSC signals get lower priority
- Alpha Score <= Pump Score (after risk adjustment)

## Review Criteria
1. Code compiles without errors
2. Scanner runs for 1+ hour without crashes
3. Zero scam-like signals generated (liquidity_ratio < 1%)
4. At least 1 legitimate WATCH/STRONG_BUY signal generated

## Reference
User audit: signals with 0.02% liquidity are "traps for beginners"

---

**Assignee:** Kimi
**Reviewer:** Max
**Priority:** HIGH — blocks monetization if not fixed
