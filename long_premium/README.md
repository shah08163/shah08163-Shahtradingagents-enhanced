# Shah Quant Long Premium — auditable universe layer

This is an **isolated, read-only screening module** for the v2.1 engine.
It does not alter the current trading agents, place orders, access or change OAuth credentials, or deploy Workers.

## Research prompt specifications

Two separate research-only prompt drafts are versioned here:
- [VoltaForge — Long Premium Scout](prompts/voltaforge_long_premium.md)
- [ThetaHarbor — Short Premium Sentinel](prompts/thetaharbor_short_premium.md)

These are user-approved prompt specifications, not runtime configuration. Their $10 share-price and 250,000-share ADV thresholds and other rules are not yet wired into this screening module. The workflow's implemented and documented source gates remain as described below.

## Source health and fallback

`source_health.py` defines the fail-closed runtime contract for market and option data:

1. Schwab Cloudflare is primary.
2. Alpaca SIP is the automatic secondary.
3. Schwab Northflank is a contingency and is excluded unless the caller explicitly enables it.
4. Bullflow GEX and VEX are separately validated flow evidence; they do not replace quote or option-chain sources.

Every attempted source records its name, provider and retrieval timestamps, delay status,
consolidation status, quote and option-contract coverage counts, and rejection reasons. A
source is eligible only when it is real-time, consolidated, fresh, and complete for the
requested coverage. IEX is marked
preselection-only and can never satisfy those market-data gates. The $20 price, consolidated
20-session volume, option open-interest, contract-volume, and spread checks fail closed when
any value is absent. Trade readiness also requires fresh Bullflow GEX and VEX rows.
Northflank does not enter the fallback sequence by default.

The source-health module accepts provider callables from the runtime that owns the connected
authorizations. The manual GitHub Actions workflow has no Schwab/Bullflow adapter credentials
and does not access the user's connections; its existing Alpaca IEX output remains a
preselection artifact. It now labels itself explicitly as non-consolidated and uncertified.
The live connected-adapter wiring remains a separate integration requirement; this PR does
not copy, rotate, or request any OAuth token or secret.

## Workflow
Run GitHub Actions **Long Premium Universe Screen (manual)**.
It defaults to a 30-symbol smoke test. Uncheck \`smoke_test\` for the full universe.
Repository Actions secrets required:
- \`ALPACA_API_KEY_ID\`
- \`ALPACA_API_SECRET_KEY\`

Outputs are uploaded as an Actions artifact: \`universe.json\` (every provisional eligible symbol),
\`technical_screen.csv\` (daily trend/RSI survivors), and \`audit.json\`
(universe counts, missing symbols, failed batches, excluded/insufficient history and completion status).
No trading secrets need to be changed.

## Validation boundaries

Universe source: current active Alpaca U.S. equities with \`has_options\` attribute, filtered to recognized U.S. listed exchanges.
Stocks and ETFs are included; name/symbol-based removal of warrants, SPACs and units is **heuristic**.
Review edge cases before certifying instrument eligibility. Some exclusion categories cannot be verified
definitively from Alpaca metadata alone. No claim is made that a symbol with \`has_options\` has liquid spreads.

Snapshots and bars use **IEX-only stock data**, which is not consolidated U.S. equity volume.
The minimum-volume filter is therefore **IEX-traded volume**, not the production engine's
true consolidated $250k/large-cap turnover/liquidity criterion.
Daily indicators use the 51+ most recent completed sessions, with current partial-day bar omitted.

Requests use 80-symbol stock-snapshot batches and 30-symbol history batches, paginate all history,
retry 429/5xx, and save audit checkpoints. A failure never counts as a technical rejection.
When any batch is missing, audit status is \`PARTIAL_UNIVERSE_SCREEN\`.
Smoke-test runs are always partial. This module sets \`full_engine_certified: false\` for **every** run,
even if all stock-history batches finish. This is intentional: passing a stock screen is not a
validated long-premium option trade.

## Required subsequent v2.1 stages

1. Confirm all survivors' stock eligibility and **consolidated** liquidity.
2. Verify earnings, macro events and issuer catalysts (the FOMC meeting Oct 27–28, 2026 is relevant).
3. Run the 20–60 DTE **Schwab Cloudflare** option-chain/liquidity/Greeks/IV screen for
   qualifying survivors; do not infer fills from stock prices.
4. Full Bullflow directional-flow/option OI profile for first provisional candidate;
   GEX/VEX on additional candidates only as needed. Exclude MULTI from directional bias.
5. Run real-time 15-minute trigger/acceptance/retest and portfolio exposure checks.
6. Produce at most five recommendations. Setup ≥80, Entry ≥75 and all hard gates or NO TRADE.

This implementation is purposefully a **pull-request-only foundation**. The GitHub workflow
is manual; no production deployment, secrets, Schwab OAuth or existing schedules are modified.

## Highly liquid stock mandate (October 27 update)

For both optionable stocks and ETFs, the **production hard gate** is at least 1,000,000 **consolidated** average daily shares
AND $100,000,000 consolidated average daily dollar volume over 20 sessions, stock
price >= $20, and liquid option legs (>= 500 OI and >= 50 current-session contracts
per leg; prefer leg bid/ask <=5% of mid; combined spread slippage <=10%, prefer <=5%).
These consolidated-volume/option-chain criteria are **not yet implemented or certified**
by the free IEX-only stock screener. The implemented early-rejection proxy instead
requires >=25,000 IEX average daily shares AND >=$2,500,000 IEX average daily dollar
volume across 20 completed sessions; these are **preselection heuristics, not substitutes**
for the stricter consolidated liquidity hard gates. Missing/insufficient records never
count as qualifying or passed, and audit continues to report partial completion.

After shortlist generation, use verified consolidated market volume and the Schwab
Cloudflare option chain to enforce production hard gates before any trade is marked ARMED
or TRIGGERED. Keep special cases where split/adjusted bars are inconsistent under review.

## ETFs included

Eligible optionable ETFs (broad-market, sector, industry, thematic, commodity and leveraged/inverse ETFs) are included when they pass underlying and option-chain liquidity gates. ETF-specific suitability, leverage decay, corporate action/issuer structure and settlement/contract deliverables must be checked downstream. No ETF inclusion bypasses option-leg OI/volume/spread or catalyst/entry requirements. Exclude ETNs unless separately approved, because their issuer-credit and structural risks differ.
