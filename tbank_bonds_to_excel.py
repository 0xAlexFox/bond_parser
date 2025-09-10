import os
import asyncio
from datetime import datetime, timezone, timedelta
from typing import Optional, Tuple, Dict, List

import pandas as pd
from dateutil import tz
import aiohttp
import ssl
import certifi

from tinkoff.invest import AsyncClient
from tinkoff.invest.schemas import InstrumentStatus

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; tbank-moex-export/1.3)",
    "Accept": "application/json",
}

RISK_MAP = {0: "UNSPECIFIED", 1: "LOW", 2: "MODERATE", 3: "HIGH"}

def invert_risk_label(label: str) -> str:
    if label == "LOW":
        return "HIGH"
    if label == "HIGH":
        return "LOW"
    return label

def coupon_type_name(floating_flag: bool) -> str:
    return "Плавающий" if floating_flag else "Фиксированный"

def dt_to_local_date_str(dt, tz_local):
    if not dt:
        return ""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(tz_local).date().isoformat()

# ---------- MOEX ISS helpers ----------
async def _get_json(session: aiohttp.ClientSession, url: str) -> Optional[dict]:
    try:
        async with session.get(url, headers=HEADERS, timeout=aiohttp.ClientTimeout(total=20)) as r:
            if r.status != 200:
                return None
            return await r.json()
    except Exception:
        return None

def _parse_table(data: dict, key: str) -> tuple[list, list]:
    if not data or key not in data:
        return [], []
    t = data[key]
    return t.get("data", []) or [], t.get("columns", []) or []

def _parse_secid_from_securities(data: dict, isin: str) -> Optional[str]:
    rows, cols = _parse_table(data, "securities")
    if not rows or "SECID" not in cols or "ISIN" not in cols:
        return None
    i_sid, i_isin = cols.index("SECID"), cols.index("ISIN")
    for r in rows:
        if (r[i_isin] or "").upper() == isin.upper():
            return r[i_sid]
    return None

async def _moex_find_secid_by_isin(session: aiohttp.ClientSession, isin: str) -> Optional[str]:
    url1 = ("https://iss.moex.com/iss/engines/stock/markets/bonds/securities.json"
            f"?isin={isin}&iss.only=securities&iss.meta=off&securities.columns=SECID,ISIN")
    sid = _parse_secid_from_securities(await _get_json(session, url1), isin)
    if sid: return sid

    url2 = ("https://iss.moex.com/iss/engines/stock/markets/bonds/securities.json"
            f"?q={isin}&iss.only=securities&iss.meta=off&securities.columns=SECID,ISIN")
    sid = _parse_secid_from_securities(await _get_json(session, url2), isin)
    if sid: return sid

    url3 = ("https://iss.moex.com/iss/securities.json"
            f"?isin={isin}&iss.only=securities&iss.meta=off&securities.columns=SECID,ISIN")
    sid = _parse_secid_from_securities(await _get_json(session, url3), isin)
    if sid: return sid

    url4 = ("https://iss.moex.com/iss/securities.json"
            f"?q={isin}&iss.only=securities&iss.meta=off&securities.columns=SECID,ISIN")
    return _parse_secid_from_securities(await _get_json(session, url4), isin)

async def _moex_get_meta_for_secid(session: aiohttp.ClientSession, secid: str) -> dict:
    url = (
        "https://iss.moex.com/iss/engines/stock/markets/bonds"
        f"/securities/{secid}.json?iss.only=securities&iss.meta=off"
        "&securities.columns=SECID,SHORTNAME,MATDATE,COUPONPERCENT,COUPONVALUE,COUPONPERIOD,FACEVALUE,ACCRUEDINT"
    )
    data = await _get_json(session, url)
    out = {}
    rows, cols = _parse_table(data, "securities")
    if rows and cols:
        row = rows[0]
        def get(c): return row[cols.index(c)] if c in cols else None
        out["SHORTNAME"]      = get("SHORTNAME")
        out["MATDATE"]        = get("MATDATE")
        out["COUPONPERCENT"]  = float(get("COUPONPERCENT")) if get("COUPONPERCENT") is not None else None
        out["COUPONVALUE"]    = float(get("COUPONVALUE")) if get("COUPONVALUE") is not None else None
        out["COUPONPERIOD"]   = float(get("COUPONPERIOD")) if get("COUPONPERIOD") is not None else None  # дни
        out["FACEVALUE"]      = float(get("FACEVALUE")) if get("FACEVALUE") is not None else None
        out["ACCRUEDINT_SEC"] = float(get("ACCRUEDINT")) if get("ACCRUEDINT") is not None else None
    return out

def _parse_md(data: dict) -> Tuple[Optional[float], Optional[float], Optional[str], Optional[float]]:
    rows, cols = _parse_table(data, "marketdata")
    if not rows or not cols:
        return None, None, None, None
    row = rows[0]
    def get(col): return row[cols.index(col)] if col in cols else None
    board = get("BOARDID") if "BOARDID" in cols else None
    last  = get("LAST")
    yld   = get("YIELD")
    aci   = get("ACCRUEDINT") if "ACCRUEDINT" in cols else None
    return (
        float(yld) if yld is not None else None,
        float(last) if last is not None else None,
        board,
        float(aci) if aci is not None else None
    )

async def _moex_marketdata_agg(session: aiohttp.ClientSession, secid: str):
    url = (
        "https://iss.moex.com/iss/engines/stock/markets/bonds"
        f"/securities/{secid}.json?iss.only=marketdata&iss.meta=off&marketdata.columns=BOARDID,LAST,YIELD,ACCRUEDINT"
    )
    return _parse_md(await _get_json(session, url))

async def _moex_marketdata_board(session: aiohttp.ClientSession, secid: str, board: str):
    url = (
        "https://iss.moex.com/iss/engines/stock/markets/bonds"
        f"/boards/{board}/securities/{secid}.json?iss.only=marketdata&iss.meta=off&marketdata.columns=LAST,YIELD,ACCRUEDINT"
    )
    return _parse_md(await _get_json(session, url))

async def _moex_get_boards_for_secid(session: aiohttp.ClientSession, secid: str) -> list[str]:
    priority = ["TQCB", "TQCBP", "TQOB", "TQO1", "TQIR", "TQOF", "TQOD", "TQCBF"]
    ordered, seen = list(priority), set(priority)
    url = (
        "https://iss.moex.com/iss/engines/stock/markets/bonds"
        f"/securities/{secid}.json?iss.only=boards&iss.meta=off&boards.columns=BOARDID,IS_TRADING"
    )
    data = await _get_json(session, url)
    rows, cols = _parse_table(data, "boards")
    if rows and "BOARDID" in cols:
        i_bid = cols.index("BOARDID")
        for r in rows:
            bid = r[i_bid]
            if bid and bid not in seen:
                ordered.append(bid); seen.add(bid)
    return ordered

async def _moex_history_latest(session: aiohttp.ClientSession, secid: str, board: str, days_back: int = 365):
    date_from = (datetime.utcnow().date() - timedelta(days=days_back)).isoformat()
    url = (
        "https://iss.moex.com/iss/history/engines/stock/markets/bonds"
        f"/boards/{board}/securities/{secid}.json?from={date_from}"
        "&iss.only=history&iss.meta=off&history.columns=TRADEDATE,YIELDCLOSE,LEGALCLOSEPRICE"
    )
    data = await _get_json(session, url)
    rows, cols = _parse_table(data, "history")
    if not rows or not cols:
        return None, None
    i_y = cols.index("YIELDCLOSE") if "YIELDCLOSE" in cols else None
    i_p = cols.index("LEGALCLOSEPRICE") if "LEGALCLOSEPRICE" in cols else None
    i_d = cols.index("TRADEDATE") if "TRADEDATE" in cols else None
    best_dt, best_y, best_p = None, None, None
    for r in rows:
        if i_y is None: continue
        y = r[i_y]
        if y is None: continue
        d = r[i_d] if i_d is not None else None
        if best_dt is None or (d and d > best_dt):
            best_dt, best_y = d, float(y)
            best_p = float(r[i_p]) if (i_p is not None and r[i_p] is not None) else None
    return best_y, best_p

async def _fetch_moex_by_isin(session: aiohttp.ClientSession, isin: str) -> dict:
    secid = await _moex_find_secid_by_isin(session, isin)
    if not secid:
        return {}

    meta = await _moex_get_meta_for_secid(session, secid)

    ytm, last, _, aci_md = await _moex_marketdata_agg(session, secid)
    if (ytm is not None) or (last is not None) or (aci_md is not None):
        return {"SECID": secid, "YTM": ytm, "LAST": last, "ACCRUEDINT": aci_md, **meta}

    boards = await _moex_get_boards_for_secid(session, secid)
    for b in boards:
        y, p, _, aci_b = await _moex_marketdata_board(session, secid, b)
        if (y is not None) or (p is not None) or (aci_b is not None):
            return {"SECID": secid, "YTM": y, "LAST": p, "ACCRUEDINT": aci_b, **meta}

    for b in boards:
        y, p = await _moex_history_latest(session, secid, b, days_back=365)
        if y is not None:
            return {"SECID": secid, "YTM": y, "LAST": p, **meta}

    return {"SECID": secid, **meta}

# ---------- Tinkoff: следующая дата купона ----------
async def _get_next_coupon_date(client: AsyncClient, figi: str, now_utc: datetime) -> Optional[str]:
    try:
        to_dt = now_utc + timedelta(days=365 * 5)
        resp = await client.instruments.get_bond_coupons(figi=figi, from_=now_utc, to=to_dt)
        future = []
        for e in resp.events:
            if e.coupon_date:
                dt = e.coupon_date
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                if dt >= now_utc:
                    future.append(dt)
        if future:
            future.sort()
            return future[0].date().isoformat()
    except Exception:
        return None
    return None

# ---------- Публичная точка (используется из run.py) ----------
async def export_bonds(
    token: str,
    outfile: str,
    only_isins: Optional[List[str]],
    base_only: bool,
    min_ytm: Optional[float],
    max_duration: Optional[float],
):
    tz_local = tz.gettz("Europe/Moscow")
    ssl_context = ssl.create_default_context(cafile=certifi.where())
    now_utc = datetime.now(timezone.utc)

    async with AsyncClient(token) as client, aiohttp.ClientSession(
        connector=aiohttp.TCPConnector(ssl=ssl_context)
    ) as session:

        status = InstrumentStatus.INSTRUMENT_STATUS_BASE if base_only else InstrumentStatus.INSTRUMENT_STATUS_ALL
        bonds_resp = await client.instruments.bonds(instrument_status=status)
        bonds = bonds_resp.instruments

        if only_isins:
            only = {s.strip().upper() for s in only_isins if s.strip()}
            bonds = [b for b in bonds if b.isin in only]

        if not bonds:
            print("Нет облигаций по заданному фильтру.")
            return

        rows = []
        for b in bonds:
            isin = b.isin

            name_ti = b.name
            maturity_ti = getattr(b, "maturity_date", None)
            maturity_str = dt_to_local_date_str(maturity_ti, tz_local) if maturity_ti else ""

            floating = bool(getattr(b, "floating_coupon_flag", False))
            amort    = bool(getattr(b, "amortization_flag", False))
            risk     = invert_risk_label(RISK_MAP.get(getattr(b, "risk_level", 0), "UNSPECIFIED"))

            moex = await _fetch_moex_by_isin(session, isin)
            last_price = moex.get("LAST")
            ytm = moex.get("YTM")

            # фильтр по YTM
            if (min_ytm is not None) and (ytm is not None) and (ytm < min_ytm):
                continue

            aci = moex.get("ACCRUEDINT") or moex.get("ACCRUEDINT_SEC")
            coupon_percent = moex.get("COUPONPERCENT")
            coupon_value   = moex.get("COUPONVALUE")
            face_value     = moex.get("FACEVALUE")
            coupon_period  = moex.get("COUPONPERIOD")  # дни
            coupon_freq    = round(365 / coupon_period) if (coupon_period and coupon_period > 0) else None

            mat_moex = moex.get("MATDATE")
            if (not maturity_str) and mat_moex and mat_moex != "0000-00-00":
                maturity_str = mat_moex

            # грубая “дюрация”: годы до погашения
            duration_years = None
            try:
                if maturity_str:
                    mat_dt = datetime.fromisoformat(maturity_str)
                    if mat_dt.tzinfo is None:
                        mat_dt = mat_dt.replace(tzinfo=tz_local)
                    mat_dt = mat_dt.astimezone(timezone.utc)
                    duration_years = max(0.0, (mat_dt - now_utc).days / 365.25)
            except Exception:
                pass

            # фильтр по дюрации
            if (max_duration is not None) and (duration_years is not None) and (duration_years > max_duration):
                continue

            next_coupon = await _get_next_coupon_date(client, b.figi, now_utc)
            name = moex.get("SHORTNAME") or name_ti

            rows.append({
                "ISIN": isin,
                "Эмитент": name,
                "Текущая цена": last_price,
                "НКД": aci,
                "Купонная ставка, %": coupon_percent,
                "Размер купона (денег)": coupon_value,
                "Частота купонов (в год)": coupon_freq,
                "Номинал": face_value,
                "Следующая дата купона": next_coupon,
                "Дата погашения": maturity_str,
                "Дюрация, лет (грубо)": duration_years,
                "Доходность к погашению (MOEX, % годовых)": ytm,
                "Тип купона": coupon_type_name(floating),
                "Амортизация": amort,
                "Рейтинг": risk,
            })

        df = pd.DataFrame(rows, columns=[
            "ISIN", "Эмитент", "Текущая цена", "НКД",
            "Купонная ставка, %", "Размер купона (денег)", "Частота купонов (в год)",
            "Номинал", "Следующая дата купона",
            "Дата погашения", "Дюрация, лет (грубо)",
            "Доходность к погашению (MOEX, % годовых)",
            "Тип купона", "Амортизация", "Рейтинг"
        ])
        df.to_excel(outfile, index=False)
        print(f"Готово: {outfile} (строк: {len(df)})")