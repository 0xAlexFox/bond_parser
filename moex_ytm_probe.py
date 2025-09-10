#!/usr/bin/env python3
import argparse, asyncio, ssl, certifi, aiohttp
from datetime import datetime, timedelta

HEADERS = {"User-Agent": "Mozilla/5.0 (moex-ytm-probe/1.3)", "Accept": "application/json"}

async def gj(session, url):
    try:
        async with session.get(url, headers=HEADERS, timeout=aiohttp.ClientTimeout(total=20)) as r:
            if r.status != 200: return None
            return await r.json()
    except Exception:
        return None

def tab(data, key):
    if not data or key not in data: return [], []
    t = data[key]
    return t.get("data", []) or [], t.get("columns", []) or []

def parse_sid(data, isin):
    rows, cols = tab(data, "securities")
    if not rows or "SECID" not in cols or "ISIN" not in cols: return None
    i_sid, i_isin = cols.index("SECID"), cols.index("ISIN")
    for r in rows:
        if (r[i_isin] or "").upper() == isin.upper():
            return r[i_sid]
    return None

async def find_sid(session, isin):
    urls = [
        f"https://iss.moex.com/iss/engines/stock/markets/bonds/securities.json?isin={isin}&iss.only=securities&iss.meta=off&securities.columns=SECID,ISIN",
        f"https://iss.moex.com/iss/engines/stock/markets/bonds/securities.json?q={isin}&iss.only=securities&iss.meta=off&securities.columns=SECID,ISIN",
        f"https://iss.moex.com/iss/securities.json?isin={isin}&iss.only=securities&iss.meta=off&securities.columns=SECID,ISIN",
        f"https://iss.moex.com/iss/securities.json?q={isin}&iss.only=securities&iss.meta=off&securities.columns=SECID,ISIN"
    ]
    for u in urls:
        sid = parse_sid(await gj(session, u), isin)
        if sid: return sid
    return None

async def meta(session, sid):
    u = f"https://iss.moex.com/iss/engines/stock/markets/bonds/securities/{sid}.json?iss.only=securities&iss.meta=off&securities.columns=SECID,SHORTNAME,MATDATE"
    d = await gj(session, u)
    rows, cols = tab(d, "securities")
    sn, md = "", ""
    if rows and cols:
        i_sn = cols.index("SHORTNAME") if "SHORTNAME" in cols else None
        i_md = cols.index("MATDATE") if "MATDATE" in cols else None
        row = rows[0]
        sn = row[i_sn] if i_sn is not None else ""
        md = row[i_md] if i_md is not None else ""
    return sn, md

async def md_agg(session, sid):
    u = f"https://iss.moex.com/iss/engines/stock/markets/bonds/securities/{sid}.json?iss.only=marketdata&iss.meta=off&marketdata.columns=BOARDID,LAST,YIELD"
    d = await gj(session, u); rows, cols = tab(d, "marketdata")
    if not rows or not cols: return None, None, None
    r = rows[0]
    def g(c): return r[cols.index(c)] if c in cols else None
    return g("YIELD"), g("LAST"), g("BOARDID")

async def main_async(isins):
    ssl_ctx = ssl.create_default_context(cafile=certifi.where())
    async with aiohttp.ClientSession(connector=aiohttp.TCPConnector(ssl=ssl_ctx)) as s:
        print("ISIN\tSECID\tSHORTNAME\tMATDATE\tBOARD\tLAST\tYTM")
        for isin in isins:
            sid = await find_sid(s, isin)
            if not sid:
                print(f"{isin}\t\t\t\t\t\t"); continue
            sn, md = await meta(s, sid)
            y, p, b = await md_agg(s, sid)
            print(f"{isin}\t{sid}\t{sn}\t{md}\t{b or ''}\t{'' if p is None else float(p)}\t{'' if y is None else float(y)}")

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("isins", nargs="+")
    a = ap.parse_args()
    asyncio.run(main_async(a.isins))

if __name__ == "__main__":
    main()