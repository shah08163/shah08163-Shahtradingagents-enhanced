#!/usr/bin/env python3
"""Shah Quant v2.1: auditable stock-universe screen. No order submission.

Inputs: Alpaca market-data REST credentials (APCA_API_KEY_ID, APCA_API_SECRET_KEY).
Outputs: universe.json, technical_screen.csv, audit.json in --out.
A completed stock-level screen is NOT certification of Schwab option-chain,
Bullflow, catalyst, entry, portfolio-fit or execution gates.
"""
from __future__ import annotations
import argparse
import csv
import datetime as dt
import json
import math
import os
import pathlib
import random
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from zoneinfo import ZoneInfo

DATA = "https://data.alpaca.markets"
BROKER = "https://api.alpaca.markets"
EXCLUDE = re.compile(r"\b(ETF|ETN|EXCHANGE TRADED|FUND|TRUST|WARRANT|RIGHTS?|UNITS?|SPAC|BLANK CHECK|ACQUISITION CORP(?:ORATION)?|ACQUISITION COMPANY)\b", re.I)
SUFFIX = re.compile(r"(\.WS|\.W|\.U|\.UN|\.R|\.RT)$", re.I)

class ApiError(Exception):
    pass

def request_json(host, route, query, attempts=6):
    url = host + route + "?" + urllib.parse.urlencode(query, doseq=True)
    headers = {"APCA-API-KEY-ID": os.environ["APCA_API_KEY_ID"],
               "APCA-API-SECRET-KEY": os.environ["APCA_API_SECRET_KEY"]}
    for attempt in range(attempts):
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=45) as response:
                return json.loads(response.read())
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, ValueError) as exc:
            status = exc.code if isinstance(exc, urllib.error.HTTPError) else None
            if status not in (429, 500, 502, 503, 504, None) or attempt == attempts-1:
                raise ApiError(f"{route} failed ({status or type(exc).__name__}) after {attempt+1} tries") from exc
            retry_after = exc.headers.get("Retry-After") if isinstance(exc, urllib.error.HTTPError) else None
            wait = min(90, float(retry_after) if retry_after and retry_after.isdigit() else (2**attempt + random.random()))
            time.sleep(wait)
    raise ApiError(route)

def atomic_json(path, value):
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(value, indent=2, sort_keys=True), encoding="utf-8")
    tmp.replace(path)

def chunks(items, size):
    for i in range(0, len(items), size):
        yield i // size, items[i:i+size]

def eligible(asset):
    if asset.get("exchange") in ("OTC", "CRYPTO") or asset.get("status") != "active" or not asset.get("tradable"):
        return False
    if "has_options" not in asset.get("attributes", []):
        return False
    name, symbol = asset.get("name", ""), asset.get("symbol", "")
    if not symbol or EXCLUDE.search(name) or SUFFIX.search(symbol):
        return False
    return True

def get_universe():
    # Direct REST avoids connector Pydantic validation failures on new exchange codes.
    raw = request_json(BROKER, "/v2/assets", {"status": "active", "asset_class": "us_equity"})
    counts = {"retrieved": len(raw), "option_flagged": sum("has_options" in a.get("attributes", []) for a in raw)}
    chosen = {a["symbol"]: a for a in raw if eligible(a)}
    return chosen, counts

def technical(bars):
    # Indicator values use only full, completed DAILY sessions: exclude today's partial candle.
    sorted_bars = sorted(bars, key=lambda v: v["t"])
    today = dt.datetime.now(ZoneInfo('America/New_York')).date().isoformat()
    complete = [b for b in sorted_bars if b["t"][:10] < today]
    if len(complete) < 51:
        return None
    closes = [float(b["c"]) for b in complete]
    highs = [float(b["h"]) for b in complete]
    lows = [float(b["l"]) for b in complete]
    prev = closes[-1]
    moves = [math.log(closes[i] / closes[i-1]) for i in range(1, len(closes)) if closes[i] > 0 and closes[i-1] > 0]
    def rv(n):
        x = moves[-n:]
        if len(x) < n: return None
        mu = sum(x) / n
        return math.sqrt(sum((v-mu)**2 for v in x)/(n-1))*math.sqrt(252)*100
    diffs = [closes[i] - closes[i-1] for i in range(len(closes)-14, len(closes))]
    gains, losses = sum(max(0,z) for z in diffs), sum(max(0,-z) for z in diffs)
    rsi = 100 if losses == 0 else 100 - 100/(1 + gains/losses)
    ranges = [max(highs[i]-lows[i], abs(highs[i]-closes[i-1]), abs(lows[i]-closes[i-1]))
              for i in range(len(closes)-14, len(closes))]
    return {"prev_close":round(prev,4),"sma20":round(sum(closes[-20:])/20,4),
            "sma50":round(sum(closes[-50:])/50,4),"rsi14":round(rsi,2),
            "atr14":round(sum(ranges)/14,4),"rv5":round(rv(5),2),
            "rv10":round(rv(10),2),"rv20":round(rv(20),2),
            "bars":len(complete),"history_asof":complete[-1]["t"]}

def write_csv(path, rows):
    fields = ["symbol","exchange","name","price","iex_day_volume","change_pct","prev_close",
              "sma20","sma50","rsi14","atr14","rv5","rv10","rv20","history_asof",
              "bias","reason"]
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer=csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)

def run(out, limit=None, min_price=10, min_iex_volume=1000):
    out.mkdir(parents=True, exist_ok=True)
    start=dt.datetime.now(dt.timezone.utc).isoformat()
    assets, counts = get_universe()
    universe=sorted(assets)
    if limit is not None: universe=universe[:limit]
    atomic_json(out/"universe.json", {"created_utc":start, "symbols":universe, "counts":counts})
    audit={"started_utc":start, "universe_size":len(universe), "counts":counts,
           "selection":{"min_price":min_price,"min_iex_volume":min_iex_volume},
           "snapshot_success":0,"snapshot_missing":[],"snapshot_batch_failures":[],
           "history_success":0,"history_insufficient":[],"history_batch_failures":[],
           "screened":0,"survivors":0,"status":"RUNNING"}
    atomic_json(out/"audit.json",audit)
    snapshots={}
    for number,batch in chunks(universe,80):
        try:
            response=request_json(DATA,"/v2/stocks/snapshots",{"symbols":",".join(batch),"feed":"iex"})
            snapshots.update(response)
        except ApiError as exc:
            audit["snapshot_batch_failures"].append({"batch":number,"symbols":batch,"error":str(exc)})
        if number%10==0: atomic_json(out/"audit.json",audit)
        time.sleep(.3)
    audit["snapshot_success"]=sum(s in snapshots for s in universe)
    audit["snapshot_missing"]=[s for s in universe if s not in snapshots]
    prelim=[]
    for symbol in universe:
        z=snapshots.get(symbol) or {}
        current=z.get("dailyBar") or {}
        previous=z.get("prevDailyBar") or {}
        price=(z.get("latestTrade") or {}).get("p")
        vol=current.get("v")
        if not price or not vol or not previous.get("c") or not current.get("c"): continue
        if price<min_price or vol<min_iex_volume: continue
        prelim.append((symbol, float(price), int(vol), (current["c"]/previous["c"]-1)*100))
    audit["prelim_count"]=len(prelim)
    bars={}
    now=dt.datetime.now(dt.timezone.utc)
    start_day=(now-dt.timedelta(days=115)).date().isoformat()
    end_day=(now+dt.timedelta(days=1)).date().isoformat()
    # Alpaca multi-symbol bars are paginated; continue until every page is consumed.
    for number,batch in chunks([x[0] for x in prelim],30):
        token=None
        seen=set()
        batch_data={}
        try:
            while True:
                query={"symbols":",".join(batch),"timeframe":"1Day","start":start_day,
                       "end":end_day,"limit":10000,"feed":"iex","adjustment":"split"}
                if token: query["page_token"]=token
                page=request_json(DATA,"/v2/stocks/bars",query)
                for ticker, recs in page.get("bars",{}).items(): batch_data.setdefault(ticker,[]).extend(recs)
                token=page.get("next_page_token")
                if not token: break
                if token in seen: raise ApiError("repeated pagination token")
                seen.add(token)
            bars.update(batch_data)
        except ApiError as exc:
            audit["history_batch_failures"].append({"batch":number,"symbols":batch,"error":str(exc)})
        if number%10==0: atomic_json(out/"audit.json",audit)
        time.sleep(.3)
    result=[]
    for symbol,price,vol,pct in prelim:
        t=technical(bars.get(symbol,[]))
        if not t:
            audit["history_insufficient"].append(symbol)
            continue
        audit["history_success"]+=1
        strong_up=price>t["sma20"] and price>t["sma50"] and 45<=t["rsi14"]<=75
        strong_down=price<t["sma20"] and price<t["sma50"] and 25<=t["rsi14"]<=55
        bias="BULLISH_WATCH" if strong_up else "BEARISH_WATCH" if strong_down else "REJECT"
        # No market-wide option-chain claim; separate handoff.
        if bias=="REJECT": continue
        row={"symbol":symbol,"exchange":assets[symbol].get("exchange"),
             "name":assets[symbol].get("name"),"price":round(price,4),
             "iex_day_volume":vol,"change_pct":round(pct,2),**t,
             "bias":bias,"reason":"Daily trend/RSI preliminary; options/catalysts/flow not checked"}
        result.append(row)
    result.sort(key=lambda z:(z["bias"],-z["iex_day_volume"]))
    write_csv(out/"technical_screen.csv",result)
    audit["screened"]=audit["history_success"]
    audit["survivors"]=len(result)
    audit["finished_utc"]=dt.datetime.now(dt.timezone.utc).isoformat()
    audit["status"]="UNIVERSE_SCREEN_COMPLETE" if (
        len(audit["snapshot_missing"])==0 and not audit["snapshot_batch_failures"]
        and not audit["history_batch_failures"]
        and not audit["history_insufficient"] and limit is None
        ) else "PARTIAL_UNIVERSE_SCREEN"
    audit["full_engine_certified"]=False
    audit["remaining_gates"]=["corporate actions and earnings","Schwab 20-60 DTE contract liquidity",
      "IV/RV and structure","Bullflow first-candidate institutional analysis",
      "15-minute acceptance/retest","portfolio fit","trade execution"]
    atomic_json(out/"audit.json",audit)
    print(json.dumps({"status":audit["status"],"universe":len(universe),
                      "screened":audit["screened"],"survivors":audit["survivors"],
                      "failed_snapshot_batches":len(audit["snapshot_batch_failures"]),
                      "failed_history_batches":len(audit["history_batch_failures"]),
                      "out":str(out)}))

if __name__ == "__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--out",type=pathlib.Path,default=pathlib.Path("long-premium-output"))
    parser.add_argument("--limit",type=int,default=None,help="SMOKE TEST ONLY; partial certification")
    parser.add_argument("--min-price",type=float,default=10)
    parser.add_argument("--min-iex-volume",type=int,default=1000)
    args=parser.parse_args()
    run(args.out,args.limit,args.min_price,args.min_iex_volume)
