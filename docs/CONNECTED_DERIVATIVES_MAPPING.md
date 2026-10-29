# Connected derivatives integration mapping
Date: 2026-10-28 Pacific. Experimental PR #14; no deployment.

Correction to the earlier execution report: finding three pre-existing Python analyst implementations is not a prerequisite. The user confirms the existing Bullflow, Schwab and Alpaca connections provide the required inputs. Add thin flow/OI/dealer analysis extensions around the original four-analyst graph, preserving original prompts, debate and risk logic. Do not rebuild the original analysts or require new hosted infrastructure.

| Extension | Connected input |
| --- | --- |
| Flow | Bullflow recorded trades/profile; qualifying single-leg SWEEP/BLOCK direction, MULTI separated |
| OI | Schwab full-strike 0–60 DTE contracts; historical observations where actually available; Bullflow corroboration |
| Dealer | Bullflow modeled OI/volume GEX and VEX; Schwab chain/spot cross-check |
| Market context | Schwab primary quotes; Alpaca price-history/quote fallback with feed and timestamps |

## Actual GOOGL connection checks
2026-10-29T03:39Z:
- Schwab explorer returned 1860 contracts for requested 0–60 DTE. This is a returned snapshot count, not independent proof of exhaustive coverage. Quote ages and missing Greeks are explicit. A snapshot alone does not establish OI change.
- Bullflow OI-weighted GEX returned HTTP 200, 2047 strike/expiration rows, as_of 2026-10-29T03:39:05.939Z, spot 292.50.
- Bullflow VEX returned HTTP 200, 2142 rows, as_of 2026-10-29T03:39:07.202Z, spot 318.22.
- Material spot-reference disagreement between GEX and VEX must be flagged. Recent calculation timestamps do not establish synchronized underlying inputs. Do not blend into a verified dealer conclusion.
- Bullflow flow and Alpaca IEX quote succeeded in the preceding recorded attempt.
These are real connected-source responses, not model analyst outputs.

## Execution order
1. Establish model execution for original graph; current direct initialization fails for missing provider credential and connected research service returns daily-limit 429.
2. Validate original four analysts live.
3. Add the three extensions with connected evidence handoff and explicit missing/stale/conflicting-data handling. Registration, state fields and downstream report consumption must be integrated and tested together; data retrieval alone is not integration.
4. Validate seven reports and source provenance through ChatGPT Web/Desktop.

No analyst nodes were added in this documentation change. No model execution succeeded. No production, OAuth, secrets or infrastructure changes.
Change ID: CONNECTED-DERIVATIVES-MAPPING-20261028
Starting source SHA: 181140e3e24b6beccb102d652c6e5f3dc2f87337
Parent execution-evidence commit: 27ba6bb514bf2e030fb13c44293cad7c50dc0a50
Validation: actual read-only connector requests above; no simulated live success.
Deployment: none. Rollback: remove documentation-only commit.
