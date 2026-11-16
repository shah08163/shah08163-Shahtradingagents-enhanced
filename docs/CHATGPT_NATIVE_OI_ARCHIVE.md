# ChatGPT-native open-interest snapshot archive

This archive stores read-only Schwab 0–60 DTE option-chain snapshots for contract-level open-interest comparisons in ChatGPT Web. It adds no runtime, API key, or hosting dependency.

## Daily procedure

1. During a ChatGPT Web research run, retrieve the full 0–60 DTE chain for each ticker being analyzed.
2. Save the returned contracts by trading date and expiration under `data/oi_archive/YYYY-MM-DD/TICKER/EXPIRATION.json`.
3. Record the source, retrieval time, underlying quote time, contract quote time, and quote age. Preserve zero OI as zero; leave missing OI null.
4. Compare contract OI only when the exact contract symbol appears in both dated snapshots. Report absolute and percentage change and the two dates. New contracts and expired contracts have no matched comparison.
5. OI change does not identify opening versus closing transactions or bullish versus bearish intent. Use flow evidence separately.
6. If the fetch fails or rows are incomplete, record the failure in that date's manifest; never mark coverage complete.

## Snapshot details

- One JSON file per ticker and expiration keeps each file small enough for the GitHub contents API.
- `manifest.json` records coverage, the underlying quote, and limitations.
- Option bid/ask values are not archived; the archive is for OI/IV context and is not a pricing source.
- Snapshots captured after the session retain individual provider quote timestamps and ages. Stale prices remain unsuitable for execution.
