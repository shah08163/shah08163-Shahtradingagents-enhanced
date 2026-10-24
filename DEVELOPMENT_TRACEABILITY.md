# Development Traceability Standard (v1.0)

Effective: 2026-10-23. Applies to changes made to this repository and its hosted integrations.

## Release evidence (required)
For every change, record in the pull request or release notes:
- Change ID, date, request/chat reference (if available), objective, owner, and affected services.
- Starting branch and commit SHA; files changed and relevant dependency/configuration changes (never secrets).
- Automated tests executed, exact commands, results, and CI run URLs; mark unavailable or not run explicitly.
- Deployment environment, provider, release ID, immutable Git commit SHA, timestamp (UTC), and deployment/job URL.
- Post-deployment verification: remote URL, authentication check, functional smoke test, log/health check, and observed result. Redact credentials and sensitive data.
- Rollback instructions, known-good commit/deployment ID, trigger conditions, and outcome if exercised.
- Known defects, residual risks, user action needed, and final status (proposed / committed / CI-passed / deployed / verified / failed / rolled back).

**Do not claim deployed or working from a commit or CI pass alone.** Never invent evidence; use `unknown` or `not verified` when missing. Historic chat provenance may be incomplete.

## Architecture rules
- Prefer remote HTTPS MCP endpoints and cloud-hosted workloads; no desktop/localhost runtime dependencies without explicit approval.
- Prefer Cloudflare/serverless where suitable; Northflank/Railway require explicit approval for new usage.
- Do not change existing deployments, tokens, grants, tools, or hosting as part of documentation-only updates.
- Always inspect current code/configuration first; stage risky changes, test them end-to-end, and retain a rollback path.
- Continuous SSE collectors need durable orchestration/storage: do not assume a stateless request handler alone can keep a persistent stream alive.

## Change record template
```yaml
change_id: TBD
requested_at_utc: TBD
request_reference: unknown
objective: TBD
repository: TBD
base_commit: unknown
change_commit: unknown
changed_files: []
test_commands: []
test_results: not_run
ci_url: unknown
deployment_provider: unknown
deployment_environment: unknown
deployment_id: unknown
deployed_commit: unknown
deployed_at_utc: unknown
health_check: not_verified
auth_check: not_verified
functional_smoke_test: not_verified
logs_checked: false
rollback_to: unknown
status: proposed
known_issues: []
```

## Operational rule
A GitHub pull request is the source of the change record; the hosting platform is the source of deployment proof. Reconcile the two before marking production verified. Prefer protected branches, reviewed PRs, and required CI checks when supported. Do not record tokens or secrets in tickets, commits, or logs.
