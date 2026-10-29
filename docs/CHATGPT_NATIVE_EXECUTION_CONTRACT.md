# ChatGPT-native Shah TradingAgents — execution contract (experimental)

Status: SPECIFICATION / NOT PRODUCTION-CERTIFIED
Date: 2026-10-28
Source of truth: this GitHub repository. This document does not imply the repository's Python LangGraph agents run inside ChatGPT.

## Non-negotiable architecture
- ChatGPT orchestrates the analysis through directly connected, read-only tools.
- Source of agent policy, schemas, weights, test expectations, and revisions: GitHub.
- Source of current quotes/options/OI: existing Schwab Cloudflare Web connector.
- Source of institutional flow and GEX/VEX: existing Bullflow connector.
- Equity market backup: existing Alpaca connector, with timestamps, feed labels, and limitations.
- Public news/fundamentals and dated earnings events: verified original/public sources, with source dates.
- No newly hosted research backend, Render, Northflank, new Cloudflare Worker, new OAuth, or additional credentials for orchestration. Existing data connectors may independently use hosted infrastructure.
- No live orders, unattended execution, fabricated prices or Greeks, or silent fallback.

## Invocation
User asks: "Shah TradingAgents <TICKER>".
The ChatGPT orchestrator loads this contract and relevant approved repository rules, invokes connected data tools, and prepares separate evidence-grounded analyst conclusions for:
1. market (daily and intraday price/volume, regime)
2. social (verifiable social sentiment with sample, timeframe and source; otherwise UNAVAILABLE)
3. news (date-specific catalysts and primary-source confirmation)
4. fundamentals (reported figures, filing dates, and explicit uncertainty)
5. flow (single-leg SWEEP/BLOCK directional premiums vs MULTI structural volume; do not treat MULTI as directional)
6. oi (contract-level OI/IV 0-60 DTE; no stale-quote or missing-Greek substitution)
7. dealer (GEX/VEX calculated exposure, never assert true dealer inventory without proof)

## Execution controls and fail-closed outputs
1. Before every run: tool inventory, auth/read access smoke test, timestamp, source, and as-of checks. An online status alone is NOT a successful test.
2. Fetch data independently; distinguish trading-date session close, after-hours, and delayed/IEX quotes.
3. Each analyst returns: status {VERIFIED, PARTIAL, UNAVAILABLE}; as_of; sources; evidence; interpretation; limitations.
4. Report missing analyst results as UNAVAILABLE; never call a seven-analyst output complete unless all seven pass.
5. Do not fabricate the existing proprietary Shah score or replace it with a new weighted system. Calculate only against a reviewed, version-pinned scoring specification; otherwise SHAHSCORE=UNAVAILABLE.
6. Trade posture: actionable only when contemporaneous liquidity, event, market-regime, and risk gates pass. Otherwise WATCH or NO TRADE.
7. Every output records run date, ticker, repository SHA, each tool/source and snapshot time, successful/failed tools, missing fields and whether the conclusion is executable.
8. Read-only run should work without the legacy mcp__Shah_TradingAgents__run_trading_research service. That service remains a separate optional compatibility test, never an unannounced requirement.
9. If a connector fails, retry once, disclose, and continue only with independent permitted sources where completeness permits. Never misstate data provenance.
10. Do not modify external services, connections or credentials without an explicit approved change.

## Acceptance tests (not yet certified)
- AT1: GOOGL all seven analyst records populated with genuine evidence and independent timestamps; unavailable is explicit, never a fabricated pass.
- AT2: Repeat exact workflow on second ticker without ad-hoc repair or user commands.
- AT3: With legacy TradingAgents research endpoint unavailable, direct connected-source run still finishes with honest PARTIAL/NO TRADE results.
- AT4: Verify scoring and risk gates against version-pinned authoritative rules before reporting an official Shah score.
- AT5: Repeat twice on different days, preserving test evidence in the repository; diagnose any drift before changing production.

## Observed checks 2026-10-28 (not certification)
- Legacy Shah research backend: status online; seven- and single-analyst GOOGL calls both failed ChatGPTAuthError.
- Schwab Cloudflare Web GOOGL quote and 0-60 DTE options explorer: successful; quote freshness varies by contract.
- Bullflow GOOGL options profile and GEX: successful.
- Alpaca GOOGL market data: successful IEX feed; not SIP consolidated.
- Social independently sourced analysis: not verified.
- Official Shah scoring rule execution: not verified.
- Original private plugin's MCP endpoint points to onrender.com; active app-backed plugin destination unverified.
Therefore production certification is NOT achieved.

## Release evidence
change_id: CHATGPT-NATIVE-CONTRACT-20261028
objective: preserve target architecture and reproducible acceptance gates
deployment_provider: none
deployment_id: none
deployed_commit: none
auth_check: partial
functional_smoke_test: partial
logs_checked: false
rollback_to: main (unmodified)
status: experimental_specification_only
