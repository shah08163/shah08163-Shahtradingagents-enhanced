"""Executable entrypoint for the Shah TradingAgents HTTP service."""

import os


def run() -> None:
    import uvicorn

    uvicorn.run(
        "tradingagents.service.api:app",
        host="0.0.0.0",
        port=int(os.environ.get("PORT", "8000")),
        proxy_headers=True,
    )


if __name__ == "__main__":
    run()
