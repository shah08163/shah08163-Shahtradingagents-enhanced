# Shah TradingAgents native market-data source priority

Effective policy for Render-free ChatGPT research. Do not call Render or the legacy Shah research backend.

## Historical price data

1. **Primary: Schwab Web through the existing Cloudflare connection.** Use Schwab historical price bars for daily and intraday OHLCV whenever the connected endpoint returns the requested symbol, interval, date range, and session coverage.
2. **Fallback: Alpaca IEX.** Use Alpaca only when Schwab historical bars fail, omit the required interval/date coverage, or return unusable data. State explicitly that the run fell back to Alpaca IEX and include its timestamp, interval, date coverage, and feed.
3. Do not silently substitute or blend feeds. If both sources were checked and disagree, retain Schwab as primary and report the discrepancy. If Schwab is unavailable and Alpaca is used, label all resulting prices/indicators as IEX-derived; IEX volume is not consolidated market volume.
4. If neither source provides valid bars, report historical price data as unavailable. Do not fabricate or infer bars.

## Other market data

- Schwab Web through Cloudflare remains authoritative for the underlying quote and options chain, including option quote, IV, and OI snapshots. Parse quote timestamps and retrieval timestamps separately.
- Keep historical bars distinct from current quotes and option-chain snapshots. Record each source's as-of time, session, interval, and coverage; do not combine observations as if they were simultaneous.
- This bar-source priority does not change Bullflow's role for recorded options flow and modeled GEX/VEX.

## Acceptance record

For every run, show the historical price source actually used, endpoint/feed, interval, date range, retrieval/as-of timestamps, and whether a fallback occurred. Mark the market role PARTIAL if the selected source cannot support the requested period or if significant coverage limitations remain.
