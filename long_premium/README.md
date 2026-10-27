# Shah Quant Long Premium — auditable universe layer

This is an **isolated, read-only stock-screening module** for the v2.1 engine.
It does not alter the current trading agents, place orders, access Schwab OAuth, or deploy Workers.

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

Universe source: current active Alpaca U.S. equities with \`has_options\` attribute.
Name/symbol-based removal of obvious ETFs, funds, warrants, SPACs and units is **heuristic**.
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

The **production hard gate** is at least 1,000,000 **consolidated** average daily shares
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
