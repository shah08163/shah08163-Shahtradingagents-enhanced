---
name: thetaharbor-short-premium
description: Run the locked VER 1.0 research scan for defined-risk credit spreads, iron condors, CSPs, and covered calls.
---

# ThetaHarbor — Short Premium Sentinel

Apply this skill when the user asks to run or interpret the ThetaHarbor short-premium scan. Do not use it for long-premium scans.

## Run the scan

1. Read [the packaged VER 1.0 prompt](references/thetaharbor-ver-1.0.md) before each scan and follow its rules.
2. Use available authorized connected market-data tools. Schwab Cloudflare is primary, Alpaca SIP secondary, and Schwab Northflank is contingency only. Bullflow is contextual. Do not substitute web search, IEX, or estimates for consolidated hard-gate data.
3. Check regular US market hours. During the session, qualify entry triggers only when the required 15-minute trigger, acceptance, and retest are evidenced. Outside the session, return watchlist research only.
4. Preserve source provenance, timestamps, real-time/delayed and consolidation status, coverage, fallbacks, and rejection reasons. Missing or ineligible hard-gate data fails closed. Missing Bullflow context alone does not block a candidate.
5. Consider only defined-risk directional credit spreads and iron condors; do not propose uncovered short options. Include CSPs/covered calls using the reference rules. If no willing-to-own/willing-to-sell list was supplied, label those candidates prominently “approval needed.”
6. Report up to 10 candidates, strongest to weakest, with descriptive reasons and the requested per-structure risk fields and scenario comparisons. Use no numeric ranking scores. If nothing passes, say so and summarize failed gates and data gaps.

This is research only. Do not place orders, size positions, change OAuth/secrets/connections, or alter deployments and schedules. Account-level risk caps remain unset.

## Version lock

VER 1.0 is frozen. Do not edit this skill or its packaged prompt during a scan. If the user asks to change the rules, preserve VER 1.0 and create a new versioned skill and prompt file.

