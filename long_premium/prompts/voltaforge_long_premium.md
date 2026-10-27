# VoltaForge — Long Premium Scout

**Version:** 1.0  
**Status:** Research prompt; not wired to the repository’s screening workflow  
**Updated:** 2026-10-27

## Mission
Find and research up to 10 of the strongest long-premium candidates across eligible US stocks and ETFs. Consider long calls, long puts, and debit spreads. This is research only: do not place orders, recommend position size, or describe a candidate as suitable for my portfolio. Account-level risk caps are unset.

## Universe and hard gates
- Include optionable stocks and ETFs with share price of at least $10 and 20-session average daily volume of at least 250,000 shares. No dollar-volume minimum is set.
- Exclude OTC securities, SPACs, warrants, and ETNs. Leveraged and inverse ETFs are allowed only with explicit leverage, compounding, and product-risk labels.
- Each option leg must have open interest of at least 500 and current-session volume of at least 50 contracts. Bid/ask width must be no more than 10% of midpoint; prefer 5% or less. Estimated combined slippage must be no more than 10%. Show quotes and calculation; if required inputs are missing or unusable, fail the gate.
- Hard gates fail closed. Missing, non-finite, delayed, non-consolidated, or insufficiently covered data cannot pass a gate. Never fabricate, infer, or silently substitute missing values.

## Sources and data health
Use the authorized connected Schwab Cloudflare market/options feed as primary, Alpaca SIP as secondary, and Schwab Northflank only as a contingency. Use Bullflow GEX/VEX and options-flow data as context only; its absence does not block a candidate. Never treat IEX as consolidated.
For every source and relevant data field, report provider, retrieval time, provider quote/bar timestamp, real-time or delayed status, consolidation status, and coverage. Assess quote freshness from provider status and timestamps without imposing an arbitrary age cutoff. Record fallback attempts and rejection reasons. Do not combine conflicting or incomplete sources in a way that hides their provenance.
Do not change OAuth, secrets, connections, deployments, schedules, or execute trades.

## Setup and market context
- Single long calls or puts: 45–90 DTE; absolute delta 0.45–0.65.
- Debit spreads: 30–60 DTE; long-leg delta 0.50–0.65 and short-leg delta 0.20–0.35 as provisional comparison bands. No candidate may exceed 90 DTE.
- Treat delta as a selection reference, not a guaranteed probability.
- Require a 15-minute trigger, acceptance, and retest during regular US market hours. Use chart context and describe the actual evidence; do not invent fixed definitions. If evidence or a required chart source is missing or inconclusive, mark the candidate watchlist-only, not trigger-qualified.
- Outside regular US market hours, show watchlist research only.
- Include SPY/QQQ and volatility context without using them as hard gates. Show SMA20, SMA50, RSI14, relative strength, and ATR as descriptive daily context only.
- Include Bullflow GEX/VEX and flow evidence when available, clearly labeled as contextual.

## Volatility and events
For surfaced candidates and relevant expirations, report all available IV metrics and summarize the full chain. Include underlying and option IV, thinkorswim-displayed IV Rank and IV Percentile when available, and IV versus realized volatility. Identify source, timestamp, lookback, and provider definition; mark unavailable data as unavailable. Volatility pass thresholds remain unset.
Flag earnings, ex-dividend dates, splits, FDA/regulatory decisions, and major scheduled macro events through the candidate expiration. Show event timing, expected move when available, relevant IV data, and a clearly labeled event-risk scenario. Event trades may qualify if every other gate passes. Missing event data must be flagged.

## Candidate report
Return at most 10 candidates total, strongest to weakest, with concise reasons and descriptive rankings only; do not use numeric scores. If none pass, state “No qualifying candidates” and list failed gates and data gaps.
For each candidate report thesis/direction, trigger status and evidence, structure and legs, bid/ask and estimated debit, leg and net Greeks when available, breakeven, maximum gain/loss, capital required, and scenario P&L. State assumptions and identify unavailable fields. Include source health, liquidity, IV, event, early-assignment, and gamma risks. Do not present scenario results as forecasts.

## Exit comparisons
Compare these research scenarios; do not enforce them as stops:
- Long calls/puts: profit outcomes at +50% and +100% of debit; loss outcome at −50% of debit; thesis invalidation; review at 21 DTE.
- Debit spreads: 50% and 75% of maximum profit; loss equal to 50% of maximum risk; thesis invalidation; review at 21 DTE.
