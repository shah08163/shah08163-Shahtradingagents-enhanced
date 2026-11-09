# Northflank deployment — Shah TradingAgents API

This service is intended to run as a Northflank **combined service** built from GitHub.

## Source

- Repository: `shah08163/shah08163-Shahtradingagents-enhanced`
- Branch while testing: `feature/shah-milestone-1`
- Build type: Dockerfile
- Dockerfile path: `/Dockerfile.service`
- Build context: `/`
- Port: `8000` / HTTP / public

## Runtime variables

Copy the values from `.env.service.example` into Northflank runtime environment variables.

Required:

- `SHAHTRADINGAGENTS_API_TOKEN`: a long random secret used as the Bearer token for `/analyze`
- `TRADINGAGENTS_LLM_PROVIDER=chatgpt`
- `TRADINGAGENTS_QUICK_THINK_LLM=gpt-6-luna`
- `TRADINGAGENTS_DEEP_THINK_LLM=gpt-6-sol`

Recommended persistent paths:

- `TRADINGAGENTS_RESULTS_DIR=/home/appuser/.tradingagents/logs`
- `TRADINGAGENTS_CACHE_DIR=/home/appuser/.tradingagents/cache`
- `TRADINGAGENTS_MEMORY_LOG_PATH=/home/appuser/.tradingagents/memory/trading_memory.md`
- `TRADINGAGENTS_CHECKPOINT_ENABLED=true`

## Persistent volume

Attach a persistent volume at:

`/home/appuser/.tradingagents`

This retains:

- ChatGPT subscription auth (`chatgpt-auth.json`)
- reports
- cache
- checkpoint state
- TradingAgents memory log

Do not expose or copy the auth file outside the service.

## Health checks

Use an HTTP liveness/readiness check against:

- path: `/health`
- port: `8000`

`/health` verifies that the process and configuration can be loaded. It deliberately does not require ChatGPT sign-in so the deployment can become reachable before the one-time login is completed.

After login, inspect `/ready`. For `llm_provider=chatgpt`, it should report:

```json
{
  "ready": true,
  "provider": "chatgpt",
  "api_auth_configured": true,
  "chatgpt_signed_in": true
}
```

## One-time ChatGPT subscription login

Open a shell/terminal inside the running Northflank container and run:

```bash
tradingagents login chatgpt
```

TradingAgents prints an OpenAI sign-in address. Open it in your browser and complete login. For a remote/container environment, follow TradingAgents' prompt to paste the browser's final callback address back into the container session.

The resulting auth file is stored under `/home/appuser/.tradingagents`, so the persistent volume keeps the sign-in across restarts.

## Smoke tests

Replace `SERVICE_URL` and `TOKEN` below.

Liveness:

```bash
curl -sS "$SERVICE_URL/health"
```

Readiness:

```bash
curl -sS "$SERVICE_URL/ready"
```

First real analysis:

```bash
curl -sS \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "ticker": "AMZN",
    "asset_type": "stock",
    "analysts": ["market", "social", "news", "fundamentals"],
    "save_reports": true
  }' \
  "$SERVICE_URL/analyze"
```

## Merge gate

Before merging Milestone 1 into `main`, require all of the following:

1. Docker image builds on Northflank.
2. `/health` returns HTTP 200.
3. `/ready` reports API auth configured and ChatGPT signed in.
4. An unauthenticated `/analyze` request returns HTTP 401.
5. AMZN completes successfully with a valid Bearer token.
6. A report is written to the persistent volume when `save_reports=true`.
