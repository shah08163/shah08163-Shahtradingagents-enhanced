# Original runner source audit
Experimental PR #14. Change ID ORIGINAL-RUNNER-AUDIT-20261028.
Parent fa5e2dd25f73c3272dbcc918270d1cd9712f6f7e.

## Verified repository source
Branch fix/mcp-async-research-jobs at b3b1df5762f3f712fa7f07c4ecf8125bc727cdf9 contains the ORIGINAL enhanced analysts:
- tradingagents/agents/analysts/flow_analyst.py
- tradingagents/agents/analysts/oi_analyst.py
- tradingagents/agents/analysts/dealer_positioning_analyst.py
Its analyst_execution.py registers all seven. Main lacked those files. Earlier claims that no original three implementations existed were incorrect.

This change copies those three analysts from that pinned source, adapting only fetch-function dependency injection and lint. The connected wrapper delegates to these original factories instead of its newly-written generic analysis prompt. The user's stricter MULTI/OI interpretation and evidence/status instructions are appended to instrument context; original analyst reasoning prompts are preserved. Dealer legacy report key is translated at the wrapper boundary.
No REST clients, API keys or credential copying added.

## Actual quota source
In that service source, service/mcp_tools.py calls web_access.consume_quota(identity) BEFORE AnalyzeRequest validation and before queuing model execution.
service/web_access.py defines DAILY_LIMIT = 3 and atomically increments shah_web_usage before execution. Failure after reservation still consumes the request. Therefore 429 Daily analysis limit reached is the application's quota, NOT evidence of an OpenAI plan/provider limit or working model authentication. CURRENT_DATE is database-defined; reset timezone has not been verified.
This audit does NOT change or circumvent quotas or production access controls.

## Actual execution evidence this turn
- Direct original four-analyst bridge invocation retried after source reconciliation: failed in TradingAgentsGraph initialization with missing OPENAI_API_KEY; no analyst/model execution occurred.
- Existing known Render URL /ready GET timed out after 20 seconds with zero bytes. No readiness/auth conclusion from timeout.
- Render MCP list_services returned no selected workspace; no workspace selected, service logs read or configuration changed. Deployment-to-source parity remains unverified.
- Installed personal-plugin discovery could not resolve an editable integration; no plugin edits performed.
- 1437 local tests passed, 1 skipped (optional langchain_aws), 1 deselected, 100 subtests passed. Nine connector tests are mock/compile tests, not live research. Ruff passed for changed analyst files.

## Boundaries and next executable prerequisite
No new infrastructure, deployment, OAuth, production, quotas or secrets changed.
The model-access test cannot complete from the currently available local credential state and quota-blocked service call. Need an authorized existing runner that can accept a real model request; neither dependency installation nor more feature work resolves that requirement.
Original stock-market data tools still need connected-source adapters; seven-analyst live validation and Web/Desktop repeatability remain incomplete.
Rollback: revert this draft-only commit; no production rollback needed.
