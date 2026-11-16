# Render-free Shah TradingAgents migration plan

Date: 2026-11-16
Status: migration in progress; no Render services changed
Scope: personal research workflow in ChatGPT Web, with GitHub as versioned methodology and archive

## Decision

The hosted Shah application can be replaced for the user's personal research workflow by a ChatGPT-native, seven-role orchestration using the existing connected Schwab Cloudflare Web, Bullflow, Alpaca, issuer/SEC, and public-source tools. ChatGPT's signed-in session supplies model access. The ChatGPT workflow does not need the hosted app's model OAuth token, custom MCP OAuth server, or Postgres auth database.

This is a workflow replacement, not execution of the original Python/LangGraph graph. GitHub stores and versions prompts, contracts, and selected dated evidence; GitHub does not run Python or act as a live database. No new runtime, hosting, API key, computer dependency, or Render call is part of the target.

## Evidence reviewed

- The user's Render screenshots show a suspended PostgreSQL service named `shah-tradingagents-auth-db`, a deployed Docker web service named `shah-tradingagents`, and an available Valkey 8 service named `shah-tradingagents-auth`.
- The repository's recorded deployed source SHA is `393a4539cecc5b19c20f5f80829612cd8abef28a`. At that SHA, `tradingagents/service/auth_store.py` stores the hosted ChatGPT OAuth token record as AES-GCM ciphertext in Postgres; its encryption key is derived from `SHAHTRADINGAGENTS_API_TOKEN`.
- At the same source SHA, `tradingagents/service/web_access.py` stores invite, browser-session, owner-session, and daily-use records in Postgres. The browser session is 12 hours; the configured research quota is 10 runs per identity per date.
- `tradingagents/service/mcp_oauth.py` stores OAuth client/flow/code/access-token/refresh-token records in Postgres for the hosted MCP endpoint.
- `tradingagents/service/mcp_tools.py` reserves quota before queueing research. Research run state is held in process memory and expires after 30 minutes; it is not persisted in Postgres.
- The source audit records a rejected ChatGPT OAuth refresh grant and failed hosted model authentication. It does not establish the exact current Render deployment revision or the purpose of the separate Valkey service.
- PR #14 is still draft and explicitly experimental; PR #17 is a separate draft containing the first dated OI snapshot archive. Neither is merged.
- The current ChatGPT-native skill defines all seven roles and evidence gates, but it is a role-based ChatGPT orchestration, not the original Python graph.

## Replacement map

| Existing hosted function | Native handling | Status |
| --- | --- | --- |
| Hosted ChatGPT OAuth credential storage/refresh | Use the user's signed-in ChatGPT session; keep no model token in GitHub | Replaced for personal in-ChatGPT runs |
| Hosted MCP OAuth state and tokens | Use the ChatGPT-native skill and direct connected data tools; no custom MCP endpoint required | Replaced for personal in-ChatGPT runs |
| Invite, browser-session, and owner-session database | ChatGPT account access identifies this user | Replaced for one user; no team invite/role administration |
| Custom 10-run daily quota | ChatGPT plan limits apply | No exact custom quota equivalent |
| In-memory background run IDs and 30-minute polling | Run research in the ChatGPT conversation and retain the result there | No independent service/API job queue |
| Durable research methodology and version history | Versioned GitHub documents and reviewed commits | Replaced as versioned file storage, not as a queryable database |
| OI history | Dated contract snapshots in GitHub; compare only matching contracts across distinct sessions | First baseline exists in draft PR #17; second comparable snapshot is still needed for OI change |
| Valkey auth service | Purpose not proven by repository evidence reviewed | Unknown; not required by the target design |

Do not place access tokens, refresh tokens, bearer secrets, OAuth callback URLs/codes, or provider credentials in GitHub.

## Seven-role acceptance gates

A research run must return seven separate records, each with status, as-of time, evidence, source, interpretation, and limits:

1. **Market:** Schwab quote and options snapshot; Alpaca bars with feed and timestamp labels; explain feed/session discrepancies.
2. **Social:** dated, sampled Stocktwits/Reddit evidence or explicitly UNAVAILABLE. Do not infer social sentiment from news or price.
3. **News:** dated company, sector, and macro catalysts; separate publication date from event date.
4. **Fundamentals:** company filings and issuer evidence; for ETFs use holdings/exposures, not fictional issuer financials.
5. **Flow:** Bullflow coverage and timestamps; qualifying SWEEP/BLOCK direction separated from MULTI structure.
6. **OI:** Schwab 0–60 DTE full-strike snapshot, validated contract identifiers, IV/OI availability, and archived prior-session comparison when claiming change.
7. **Dealer:** Bullflow OI/volume GEX and VEX with timestamps and spot checks; call these modeled exposures, not actual dealer inventory.

A role may be PARTIAL or UNAVAILABLE where evidence is missing. Report all seven roles without asserting all seven are VERIFIED unless their evidence gates pass. Separate bull/bear debate, trader synthesis, three risk views, and PM conclusion. Mark `ORIGINAL_GRAPH_EXECUTED=false` and `EXECUTION_PARITY=NOT_CERTIFIED` until separately proven.

## Work sequence

1. Freeze the native contract, record the repository SHA, and confirm that no Render/legacy Shah backend is called.
2. Run the native workflow on SPY as the derivatives integration fixture and GOOGL as the company-fundamentals fixture. Capture each role's actual source/status and fail-closed behavior.
3. Resolve partial roles individually: social sample availability; stable market feed/price discrepancy reporting; Bullflow coverage; Dealer spot alignment; and OI change after a second archived trading-session snapshot.
4. Repeat the same workflow without ad-hoc repair and preserve run evidence without overwriting prior snapshots.
5. Compare the native reports with recorded original outputs and pinned prompts. A similar-looking report is not parity proof. Document differences; do not change original decision rules without user approval.
6. Only after native acceptance is reviewed should the user decide whether to retire the Render web service, Postgres database, and Valkey service. No service retirement or configuration change is authorized by this plan.

## Current acceptance state

- ChatGPT-native seven-role methodology exists: **defined**.
- Current connected source evidence exists for SPY/GOOGL: **partial; prior runs are not certification**.
- OI snapshot baseline for GOOGL/SPY: **captured on 2026-11-16; draft PR #17**.
- Comparable second OI snapshot: **pending**.
- Seven-role all-evidence end-to-end acceptance: **pending**.
- Original graph execution parity: **not certified**.
- Render retirement: **not approved or performed**.
