# Security Services for Contract Verification

## 1. Token Sniffer (tokensniffer.com)
**What it does:** Anti-virus for smart contracts. Smell Test 0-100.

**Key checks:**
- **Fee Check:** Buy/Sell Tax. Scam tokens can have 99% sell tax
- **Contract Analysis:** Renounced Ownership? If not → creator can modify code
- **Liquidity Check:** Locked/Burned? If not → Rug Pull possible

## 2. Honeypot.is
**What it does:** Simulates buy/sell transactions to detect honeypots.

**Red flags:**
- "Yikes! It's a honeypot"
- "Transfer From Failed"
- These mean ONLY creator can sell → 100% scam

## 3. De.Fi Scanner (de.fi/scanner)
**What it does:** Deep scan for hidden vulnerabilities and backdoors.

**What it finds:**
- Blacklist functions (block specific wallets)
- Mint functions (creator can print unlimited tokens)
- Other backdoors

## 4. BscScan (bscscan.com)
**What it does:** Raw blockchain data for BSC network.

**Key checks:**
- **Holders tab:** Top 5 wallets (excluding pool/burn) holding >20-30% = HIGH RISK
- **Contract tab:** Green checkmark = code is public. Closed code = 100% RED FLAG

## Integration Plan for Crypto Hunter

### API Endpoints to Add:
```python
# Token Sniffer
GET https://tokensniffer.com/api/v2/token/{address}

# Honeypot
GET https:// honeypot.is/api/token/{address}

# De.Fi
GET https://api.de.fi/v1/token/{address}/security
```

### Decision Logic:
```
IF honeypot_detected → REJECT
IF sell_tax > 10% → REJECT  
IF ownership_not_renounced → flag as RISKY
IF top_holders > 25% → flag as RISKY
IF liquidity_not_locked → flag as RISKY
```

---

**Priority:** Task #002 (Risk Management) must be completed first, THEN add these API checks.
