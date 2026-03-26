# Task #001: Crypto Hunter — Improve Signal Quality

## Status
- [x] Created: 2026-03-27
- [ ] Completed

## Problem
Crypto Hunter generates 6 signals in 3 hours, but ALL are WEAK (alpha < 1.0).
Need stronger signals for monetization.

## Current Data Flow
1. GeckoTerminal → pairs list (120 tokens)
2. DexScreener → 5m volume (enriches ~14 tokens/cycle)
3. Metrics calculated → signals generated

## Issue Identified
DexScreener returns 5m volume = 0 for most tokens. Algorithm relies on `volume_velocity` which is always 1.0.

## Task for Kimi
Improve the signal detection algorithm:

1. **Use price_change_5m as primary indicator** (not volume)
   - When `|price_change_5m| > 2%` AND `|price_change_1h| > 5%` → potential signal
   
2. **Add liquidity spike detection**
   - Compare current liquidity vs 1h ago
   - If `liquidity_velocity > 1.1` → bullish

3. **Improve Pump Detection thresholds**
   - Current: `PUMP_VOLUME_VELOCITY_MIN=1.0` (too low, always triggers)
   - Change to check `price_change_5m >= 2.0` AND `buy_pressure >= 1.2`

4. **Add more data sources**
   - Try Binance API for price ticker (free, no auth needed for basic data)
   - GET `https://api.binance.com/api/v3/ticker/24hr`

## Files to Modify
- `/root/.openclaw/workspace/crypto_hunter/scanner/metrics_engine.py`
- `/root/.openclaw/workspace/crypto_hunter/detectors/signal_detectors.py`
- `/root/.openclaw/workspace/crypto_hunter/.env` (thresholds)

## Expected Result
- Generate 1-2 signals per hour
- Alpha score > 1.0 for meaningful signals
- At least 30% of signals should be STRONG_BUY or WATCH

## Review Criteria
1. Code compiles without errors
2. Scanner runs without crashes for 1+ hour
3. At least 1 STRONG signal generated
4. No NaN/Inf values in metrics

---

**Assignee:** Kimi
**Reviewer:** Max
