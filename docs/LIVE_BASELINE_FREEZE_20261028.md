# Tested live baseline — October 28, 2026 Pacific

Change ID LIVE-BASELINE-FREEZE-20261028. User requested locking the working code for a different-ticker test tomorrow.

## Pinned source and deployment
- Baseline branch: baseline/live-seven-analyst-20261028
- Exact tested source: 393a4539cecc5b19c20f5f80829612cd8abef28a
- Existing production branch feature/shah-milestone-1 verified at the same SHA.
- Render service srv-db9r5l5g1s2s739ojlu0; confirmed A's workspace tea-db9r4d7avr4c73f4d1q0.
- Deploy dep-dbhck7dg1s2s739ke220 verified live, finished 2026-10-29T04:24:43.669626Z.
- Daily request allowance: 10. Existing single-worker queue retained. Failed requests still count.
- ChatGPT remains the interface; original existing Python graph executes on existing Render service. No new infrastructure. This freeze does not eliminate that execution dependency.
- No branch protections, auto-deploy setting, permissions, credentials, plans or production files changed by this freeze. The checkpoint branch records the baseline; it is not a claim that branch protection was enabled. The commit SHA is the authoritative immutable reference.

## Verified live execution
- GOOGL original four analysts completed: 85-MowaAV0WLrb4YsoexAB0f.
- GOOGL original seven analysts completed: Y9W_Yd8nQ4jvpgxtD166WkMP.
- OpenAI Responses API HTTP 200 observed; all seven original report fields returned.
- Seven-engine result Underweight / evidence score -0.318, not proposed SES certification or a personalized allocation recommendation.
- Local service suite: 1400 passed, 1 skipped (optional langchain_aws), 1 deselected, 100 subtests passed; targeted auth/MCP tests 13 passed, lint passed. These are not substitutes for the two actual live runs.

## Not approved for promotion
PR #14 remains draft/unmerged and its experimental connected-data code is NOT deployed. Do not deploy it merely because the existing original service completed a run.
Research-data validation remains PARTIAL: service Schwab bridge HTTP 502; GEX/VEX inconsistent spots; missing company-news coverage; anomalous/period-mismatched financial data; core market Yahoo path rather than connected Schwab/Alpaca; no live Alpaca fallback verification.

## Next ticker test — October 29 Pacific
Ticker and test time not specified; no scheduled job created. Run when user supplies a ticker.
1. Verify existing service SHA and model_auth status. Normal refresh may be needed; future refresh reliability is not yet proven. Do not expose credentials or silently reset OAuth.
2. Start one seven-analyst request and poll its original run ID to completed/failed. Do not duplicate queued/running jobs; allow for existing single-worker queue.
3. Require seven actual report fields plus evidence and final output. Record source/trading dates and distinguish session close from later quotes.
4. Verify connected flow, OI and exposure coverage; keep missing data unavailable, flag inconsistent spots and provider failures. Missing fields are not zeros.
5. Report execution success separately from data completeness and investment conclusions. No orders or automatic allocations.
6. Repeatability in ChatGPT Desktop remains unverified until exercised there.

## Recovery
Do not redeploy while a research run is active; jobs are process-local and expire after 30 minutes. If a later code release regresses execution, restore this pinned source with an approved deploy. Do not restore/replay old OAuth refresh tokens. Retain the private full-report artifact and repository execution evidence. New corrective work should use a separate branch and explicit release review.
