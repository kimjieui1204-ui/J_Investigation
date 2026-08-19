#!/usr/bin/env python3
"""
SEC XBRL frames → fundamentals.json

왜 여기(GitHub Actions)에서 도는가
──────────────────────────────────
Apps Script 에서 SEC 를 직접 부르면 403 "Request Rate Threshold Exceeded" 가 납니다.
구글이 전 세계 Apps Script 사용자에게 같은 IP 를 나눠 주는데, SEC 의 초당 10회 제한이
그 IP 단위로 걸리기 때문입니다. 우리가 아니라 남들이 이미 다 쓴 것입니다.

GitHub Actions 러너는 자기 IP 를 씁니다. 그래서 여기서 긁고, 결과 JSON 만
저장소에 커밋합니다. Apps Script 는 raw.githubusercontent.com 에서 그 파일만 읽습니다.

계산 규칙은 20_Screener.gs 의 scrDerive() 와 한 글자도 다르지 않게 맞췄습니다.
한쪽만 고치면 두 결과가 조용히 갈라집니다. 고칠 때는 반드시 둘 다 고치세요.
"""

import json
import math
import os
import sys
import time
import urllib.request
import urllib.error

UA = os.environ.get("SEC_CONTACT", "").strip()
YEARS_BACK = 4
NEED_YEARS = 3
OUT = os.environ.get("OUT_PATH", "fundamentals.json")

TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
FRAMES = "https://data.sec.gov/api/xbrl/frames/us-gaap/"

# 앞의 태그가 없으면 뒤의 태그로 넘어갑니다.
TAGS = {
    "equity": ("USD", True, [
        "StockholdersEquity",
        "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest"]),
    "liab":   ("USD", True, ["Liabilities"]),
    # Liabilities 를 따로 안 적는 회사가 절반쯤 됩니다. 총자산 − 자기자본으로 냅니다.
    "lse":    ("USD", True, ["LiabilitiesAndStockholdersEquity", "Assets"]),
    "ni":     ("USD", False, ["NetIncomeLoss", "ProfitLoss"]),
    "ocf":    ("USD", False, [
        "NetCashProvidedByUsedInOperatingActivities",
        "NetCashProvidedByUsedInOperatingActivitiesContinuingOperations"]),
    "capex":  ("USD", False, [
        "PaymentsToAcquirePropertyPlantAndEquipment",
        "PaymentsToAcquireProductiveAssets",
        "PaymentsForCapitalImprovements",
        "PaymentsToAcquireOtherPropertyPlantAndEquipment",
        "PaymentsToAcquireMachineryAndEquipment"]),
    "rev":    ("USD", False, [
        "RevenueFromContractWithCustomerExcludingAssessedTax",
        "Revenues",
        "RevenueFromContractWithCustomerIncludingAssessedTax"]),
    "eps":    ("USD-per-shares", False, [
        "EarningsPerShareDiluted", "EarningsPerShareBasic"]),
}


def get(url, tries=4):
    """SEC 는 초당 10회를 넘기면 403 을 줍니다. 넉넉히 쉬고, 막히면 더 쉽니다."""
    last = None
    for i in range(tries):
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        try:
            with urllib.request.urlopen(req, timeout=90) as r:
                return json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            last = f"HTTP {e.code}"
            if e.code == 404:
                return None          # 그 개념·그 기간의 자료가 없는 것뿐입니다
            time.sleep(2 ** i)
        except Exception as e:
            last = str(e)
            time.sleep(2 ** i)
    print(f"  · 실패 {last}: {url}", file=sys.stderr)
    return None


# ── 파생 계산 — 20_Screener.gs 의 scrDerive() 와 같은 규칙 ────────────

def cagr(series):
    """series = [(연도, 값)] 오름차순.
       시작이 적자면 CAGR 은 의미가 없어 None,
       끝이 적자면 최악값 -1 로 둡니다."""
    if len(series) < 2:
        return None
    (y0, a), (y1, b) = series[0], series[-1]
    n = y1 - y0
    if n <= 0 or a <= 0:
        return None
    if b <= 0:
        return -1.0
    return (b / a) ** (1.0 / n) - 1.0


def stdev(vals):
    if len(vals) < 2:
        return None
    m = sum(vals) / len(vals)
    return math.sqrt(sum((v - m) ** 2 for v in vals) / (len(vals) - 1))


def pick(raw, metric):
    o = raw.get(metric, {})
    ys = sorted(int(y) for y in o)
    return [(y, o[y]) for y in ys[-NEED_YEARS:]]


def derive(raw):
    """SEC 원자료 한 종목분 → 최종 지표. 못 구한 것은 None 이고, 사유를 남깁니다."""
    out, miss = {}, []

    eq, ni = pick(raw, "equity"), pick(raw, "ni")
    ocf, cap = pick(raw, "ocf"), pick(raw, "capex")
    rev, eps = pick(raw, "rev"), pick(raw, "eps")
    lb, lse = pick(raw, "liab"), pick(raw, "lse")
    lsed = dict(lse)
    eqd = dict(eq)
    revd = dict(rev)
    capd = dict(cap)

    # ROE — 같은 해끼리만 짝지어 평균
    roes = [v / eqd[y] for y, v in ni if eqd.get(y, 0) > 0]
    out["roe"] = sum(roes) / len(roes) if roes else None
    if out["roe"] is None:
        miss.append("ROE")

    # FCF = 영업현금흐름 − 설비투자. capex 가 없으면 0 으로 보지 않고 결측 처리
    fcfs = [(y, v - abs(capd[y])) for y, v in ocf if y in capd]
    out["fcf"] = fcfs[-1][1] if fcfs else None
    out["fcfPos"] = sum(1 for _, v in fcfs if v > 0)
    if out["fcf"] is None:
        miss.append("FCF")

    margins = [v / revd[y] for y, v in fcfs if revd.get(y, 0) > 0]
    out["fcfm"] = sum(margins) / len(margins) if margins else None

    out["epsCagr"] = cagr(eps)
    out["revCagr"] = cagr(rev)
    if out["epsCagr"] is None:
        miss.append("EPS성장률")

    last_eq_row = eq[-1] if eq else None
    last_eq = last_eq_row[1] if last_eq_row else None
    last_lb = lb[-1][1] if lb else None
    if last_lb is None and last_eq_row and last_eq_row[0] in lsed:
        last_lb = lsed[last_eq_row[0]] - last_eq_row[1]   # 총자산 − 자기자본
    out["debt"] = (last_lb / last_eq) if (last_eq and last_eq > 0
                                          and last_lb is not None) else None

    ev = [v for _, v in eps]
    sd = stdev(ev)
    mean = sum(ev) / len(ev) if ev else 0.0
    out["epsVol"] = (sd / abs(mean)) if (sd is not None and abs(mean) > 1e-9) else None

    out["years"] = "·".join(str(y) for y, _ in eq)
    out["reason"] = (
        "·".join(miss) + " 없음 — SEC 미국 회계기준 공시에서 찾지 못했습니다"
        if miss else "")
    return out


# ── 수집 ──────────────────────────────────────────────────────────

def main():
    if "@" not in UA:
        print("환경변수 SEC_CONTACT 에 이메일이 들어간 연락처가 필요합니다. "
              "예: JIEUI OS you@example.com", file=sys.stderr)
        return 1

    print(f"User-Agent: {UA}")
    tick = get(TICKERS_URL)
    if not tick:
        print("SEC 종목 목록을 못 받았습니다.", file=sys.stderr)
        return 1

    cik2tick = {}
    for v in tick.values():
        cik2tick.setdefault(str(v["cik_str"]), str(v["ticker"]).upper())
    print(f"종목 목록 {len(cik2tick)}건")

    this_year = time.gmtime().tm_year
    years = [this_year - i for i in range(1, YEARS_BACK + 1)]

    store = {}          # ticker → metric → {year: value}
    for metric, (unit, inst, tags) in TAGS.items():
        for y in years:
            hit = 0
            for tag in tags:
                period = f"CY{y}Q4I" if inst else f"CY{y}"
                data = get(f"{FRAMES}{tag}/{unit}/{period}.json")
                time.sleep(0.2)                      # 초당 10회 제한 아래로
                if not data:
                    continue
                for d in data.get("data", []):
                    tk = cik2tick.get(str(d["cik"]))
                    if not tk:
                        continue
                    slot = store.setdefault(tk, {}).setdefault(metric, {})
                    if y not in slot:
                        slot[y] = d["val"]
                        hit += 1
                # ★ 여기서 break 하면 안 됩니다. 회사마다 쓰는 태그가 다릅니다.
                #   설비투자를 69종목 중 48곳만 찾다가, 전부 훑게 바꾸니 63곳이 됐습니다.
            print(f"  {metric} CY{y} → {hit}건")

    rows = {}
    for tk, raw in store.items():
        d = derive(raw)
        # 품질·성장을 둘 다 못 채운 종목은 실을 이유가 없습니다. 파일만 커집니다.
        if d["roe"] is None and d["epsCagr"] is None:
            continue
        rows[tk] = d

    payload = {
        "generated": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()),
        "years": years,
        "count": len(rows),
        "note": "20_Screener.gs 의 scrDerive() 와 같은 규칙으로 계산했습니다.",
        "data": rows,
    }
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, separators=(",", ":"))
    size = os.path.getsize(OUT) / 1024
    print(f"저장 {OUT} · {len(rows)}종목 · {size:.0f}KB")
    return 0


if __name__ == "__main__":
    sys.exit(main())

