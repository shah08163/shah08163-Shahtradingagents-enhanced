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
- PR #14 remains draft and explicitly experimental. PR #17 merged to main as e5038721c2f31cef1c60428bb614cda14ff8b3d6, adding the first dated GOOGL/SPY OI snapshot archive.
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
| OI history | Dated contract snapshots in GitHub; compare only matching contracts across distinct sessions | Nov. 16 baseline is on main via PR #17; a later comparable snapshot is still needed for OI change |
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
2. GOOGL has a completed ChatGPT-native seven-role role-based run recorded below. SPY has only a connector smoke-check so far; run its full seven-role analysis as the derivatives fixture.
3. Resolve partial roles individually: obtain a reproducible social sample; improve market feed coverage; retain Bullflow's recorded-flow scope; interpret Dealer models with spot/expiry checks; and calculate OI change after a second archived trading-session snapshot.
4. Repeat the same workflow without ad-hoc repair and preserve run evidence without overwriting prior snapshots.
5. Compare the native reports with recorded original outputs and pinned prompts. A similar-looking report is not parity proof. Document differences; do not change original decision rules without user approval.
6. Only after native acceptance is reviewed should the user decide whether to retire the Render web service, Postgres database, and Valkey service. No service retirement or configuration change is authorized by this plan.

## Current acceptance state

- ChatGPT-native seven-role methodology exists: **defined**.
- GOOGL seven-role role-based run: **completed; Flow VERIFIED, six roles PARTIAL; not original graph execution**. SPY: **connector smoke-check only**.
- OI snapshot baseline for GOOGL/SPY: **captured on 2026-11-16; PR #17 merged to main as e5038721c2f31cef1c60428bb614cda14ff8b3d6**.
- Comparable second OI snapshot: **pending**.
- Seven-role all-evidence end-to-end acceptance: **pending**.
- Original graph execution parity: **not certified**.
- Render retirement: **not approved or performed**.


## Preliminary native connector smoke-check — 2026-11-16

This was a direct connector and public-source check in ChatGPT. It was **not** a complete analyst run: no seven-record report, debate, trader synthesis, three risk views, or PM decision was generated. All seven role statuses below remain PARTIAL. Original graph execution is false; parity is not certified.

| Role | Result | Evidence and open limit |
| --- | --- | --- |
| Market | PARTIAL | Schwab returned SPY and GOOGL quotes around 23:11 UTC and full 0–60 DTE chains (5,958 SPY; 2,174 GOOGL). Alpaca IEX daily bars ended Nov 12 for SPY but Nov 16 for GOOGL. Schwab contract quote timestamps were about 1.9 hours old, so chain data supports observation, not trade pricing. |
| Social | PARTIAL | Search surfaced dated Reddit posts and third-party aggregation for both tickers. This was not a systematic source-native sample with a reproducible capture window and complete post counts; sentiment confidence remains low. |
| News | PARTIAL | Search surfaced same-day market coverage and the official Alphabet Q3 2026 results filing. This discovery pass did not build a complete catalyst timeline or corroborate all material events. |
| Fundamentals | PARTIAL | Official SEC results for Alphabet and State Street SPY fund/holdings information were found. The full period-matched financial and ETF exposure/valuation analysis was not run. |
| Flow | PARTIAL | Bullflow returned 2026-11-16 recorded-flow profiles at 21:56:46Z: SPY 2,320,463 contracts and -$8.67M net directional premium; GOOGL 182,393 contracts and +$9.41M. Coverage is recorded flow, not a full-market census; profile totals alone do not validate each SWEEP/BLOCK print. |
| OI | PARTIAL | Schwab returned 5,958 SPY and 2,174 GOOGL contracts over 0–60 DTE. This same-session retrieval does not establish OI change. The Nov 16 archive is one date; a later comparable session is required. |
| Dealer | PARTIAL | Bullflow returned OI-GEX, volume-GEX, and VEX for both underlyings. Spot references were close but not identical (SPY about 740.49–740.55; GOOGL about 284.27–284.38). These remain modeled exposures, not verified dealer positions. |

Observed technical checks: Alpaca IEX returned 29 SPY daily bars ending Nov 12 and 31 GOOGL daily bars ending Nov 16. Calculated GOOGL 20-session SMA was about $300.41 and RSI(14) about 31.55; SPY's corresponding values use stale bars through Nov 12 (SMA about $759.50; RSI(14) about 48.84) and must not be represented as Nov 16 indicators.

Sources used during discovery: Schwab Cloudflare Web, Bullflow Connection, Alpaca IEX, web search, the SEC's Alphabet Q3 results, State Street's SPY page, and dated Reddit/search results. Source references are in the ChatGPT run transcript. **Render calls: 0. Legacy Shah research-service calls: 0.**


## GOOGL seven-role ChatGPT-native run — 2026-11-16

**Execution type:** Seven separate role-based ChatGPT analyses using direct connected read-only sources. Prompt/methodology reference: experimental source snapshot 05e67726dbcdfaffd13a5edd0ce672821288f913 (PR #14). This did not execute the original Python/LangGraph graph. No Render or legacy Shah research-service calls occurred.

**As of:** After-hours, 2026-11-16. Schwab quote retrieved 23:23:04Z; chain underlying snapshot 23:22:47Z; Bullflow profile generated 23:21:20Z (trade cutoff/as-of 21:56:46Z); Bullflow GEX 23:21:20Z; VEX 23:21:21Z; Alpaca IEX daily bar for Nov. 16.

| Role | Status | Evidence and interpretation |
| --- | --- | --- |
| Market | PARTIAL | Schwab after-hours quote about $284.25; Alpaca IEX Nov. 16 daily bar closed $283.795, with high $294.12 and low $282.975. Calculated 20-session SMA $300.41 and RSI(14) 31.55. The IEX bar volume is not consolidated market volume; after-hours quote and regular-session close are different observations. |
| Social | PARTIAL | Public search surfaced current GOOGL Reddit/aggregator discussion, but not a reproducible source-native sample with reliable counts and a defined capture window. Sentiment confidence is low. |
| News | PARTIAL | Latest major company event identified was the Oct. 28 Q3 earnings release. Nov. 16 market coverage reported Alphabet shares lower amid a broad market decline. This was not a complete catalyst or event-calendar review. |
| Fundamentals | PARTIAL | SEC Q3 filing/release: revenue $127.6B (+25% YoY), operating income $40.6B (+30%), operating margin 31.8%, Google Cloud revenue $30.7B (+103%). Q3 operating cash flow was $42.3B, capex $51.4B, free cash flow -$9.1B. Management maintained 2026 capex guidance of $195B–$205B and expected higher 2027 capex. Valuation was not fully reconciled in this run. |
| Flow | VERIFIED (recorded sample scope) | Bullflow historical flow returned 642 rows for 2026-11-16 with hasMore=false: 281 SWEEP, 203 BLOCK, 158 MULTI. Conditional directional premium from qualifying SWEEP/BLOCK rows was +$9.405M across 467 eligible observations. MULTI represented $90.8M premium and was excluded from directional bias. Coverage is recorded activity, not a market-wide census; side does not prove opening/closing intent. |
| OI | PARTIAL | Schwab returned 2,174 contracts across 13 expirations, with OI and IV fields. The Nov. 20 $285 call/put IVs were 46.825%/45.783%, but their quote timestamps were about 7,676 seconds old. No IVR/IVP or OI change is inferred. The Nov. 16 archive is a single-date baseline; this run did not add a second trading date. |
| Dealer | PARTIAL | Bullflow OI GEX summed about -$99.99M across expirations and -$80.87M excluding same-day expiry. Volume GEX was -$426.17M with same-day expiry included, but +$50.52M excluding it; VEX was +$277.46M. The sign change makes the regime mixed and low-confidence. These are model estimates, not verified dealer inventory. |

**Synthesis:** Bull case: strong reported revenue, operating income, and Cloud growth; RSI is low; filtered SWEEP/BLOCK flow was net positive. Bear case: price is below its 20-session average; capex is pressuring free cash flow; dealer exposure changes sign when same-day expiry is removed. Trader posture was cautious/underweight watch, not executable. Aggressive risk view waits for price stabilization; neutral view waits for confirmation from price and flow; conservative view stays out pending better alignment and fresh option quotes. PM conclusion: cautious/underweight research posture, medium-low confidence. No trade, official Shah score, or original-graph output was produced.

**Run gates:** Seven role records present: yes. All seven VERIFIED: no (Flow VERIFIED, six PARTIAL). ORIGINAL_GRAPH_EXECUTED=false; EXECUTION_PARITY=NOT_CERTIFIED; Render calls: 0; legacy Shah service calls: 0.

**Source links:** [Alphabet Q3 2026 release (SEC)](https://www.sec.gov/Archives/edgar/data/1652044/000165204426000080/googexhibit991q32026.htm); [Alphabet Q3 2026 filing (SEC)](https://www.sec.gov/Archives/edgar/data/1652044/000165204426000084/goog-20260930.htm); [Q3 earnings call (Alphabet IR)](https://abc.xyz/investor/events/event-details/2026/2026-Q3-Earnings-Call-2026-Ujou16CTw9/default.aspx); [Nov. 16 market coverage](https://www.marketwatch.com/data-news/alphabet-inc-cl-c-stock-underperforms-monday-when-compared-to-competitors-ef4f0703-9c7bc4f35f64).


## Social analyst implementation decision

The ChatGPT-native Social contract is defined in [CHATGPT_NATIVE_SOCIAL_AGENT.md](CHATGPT_NATIVE_SOCIAL_AGENT.md). ChatGPT owns relevance/stance classification and synthesis for retrieved records; TypeSafe/Jev is not required. Source-native dated counts remain preferred. When only web-search examples are available, Social is PARTIAL and qualitative only—no source-wide ratio, sample denominator, or representativeness claim. If no dated posts can be verified, Social is UNAVAILABLE. This accepted compromise allows the other six analyst roles to proceed and does not certify original graph parity.
