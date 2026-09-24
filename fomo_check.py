#!/usr/bin/env python3
"""
fomo_check.py - kasdien atnaujinamas atsakymas i klausima "ar verta prekiauti?"

Kiekviena menesi visos strategijos gauna ta pacia suma (MONTHLY EUR) ir lygina, kiek is jos liko:
  1. DCA 80/20      - 80 % pasaulio akciju ETF + 20 % BTC, perkama kas menesi, niekada neparduodama
  2. DCA tik ETF
  3. DCA tik BTC
  4. Trendo filtras - 80/20, bet turtas laikomas tik kai kaina > ~200 prekybos d. vidurkio
  5. Aktyvus prekiautojas BTC - 1000 atsitiktiniu scenariju. Jis NEBLOGESNIS uz monetos metima
     (jokio blogo iprociu, jokios panikos) - tik daznai perka/parduoda ir moka realius kastus.
     Tai dosnus prielaida prekiautojo naudai: tyrimai rodo, kad realus prekiautojai vidutiniskai
     pasirodo dar blogiau nei atsitiktinumas.

Rezultatas: docs/index.html (GitHub Pages). Paleidimas: python fomo_check.py [--synthetic]
Visi skaiciai hipotetiniai; tai ne investavimo rekomendacija.
"""
import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

# ---------------- NUSTATYMAI (keisk cia) ----------------
TICKERS = {"etf": "VWCE.DE", "btc": "BTC-EUR"}   # Yahoo: pasaulio akciju UCITS ETF (EUR) ir BTC EUR
BINANCE_URL = "https://data-api.binance.vision/api/v3/klines"  # viesi Binance rinkos duomenys, be rakto
BINANCE_SYMBOL = "BTCEUR"  # tie patys duomenys, kuriuos rodo TradingView Binance grafikai
MIX = {"etf": 0.80, "btc": 0.20}
MONTHLY = 100.0            # EUR per menesi
SMA_DAYS = 290             # kalendorines dienos ~ 200 prekybos dienu
BUY_COST = {"etf": 0.001, "btc": 0.005}   # DCA pirkimo kastai (mokestis + spredas)
TRADE_COST = {"etf": 0.001, "btc": 0.002} # trendo filtro perbalansavimo kastai
TRADER_SWITCH_PROB = 0.30  # tikimybe per diena pakeisti pozicija (~9 sandoriai per menesi)
TRADER_COST = 0.0015       # vieno sandorio kastai (0,1 % mokestis + ~0,05 % spredas/slippage)
TRADER_PATHS = 1000
ROOT = Path(__file__).parent
# ---------------------------------------------------------


def binance_daily(symbol=BINANCE_SYMBOL, start="2019-01-01") -> pd.Series:
    """Dienos uzdarymo kainos is Binance. Puslapiuojama po 1000 zvakiu; nebaigta siandienos zvake atmetama."""
    import json as _json
    import urllib.request
    start_ms = int(pd.Timestamp(start).timestamp() * 1000)
    now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    rows = []
    for _ in range(20):
        url = f"{BINANCE_URL}?symbol={symbol}&interval=1d&startTime={start_ms}&limit=1000"
        req = urllib.request.Request(url, headers={"User-Agent": "fomo-check"})
        with urllib.request.urlopen(req, timeout=20) as r:
            batch = _json.load(r)
        if not batch:
            break
        rows += [k for k in batch if k[6] < now_ms]   # k[6] = zvakes uzdarymo laikas
        if len(batch) < 1000:
            break
        start_ms = batch[-1][0] + 86_400_000
    if not rows:
        raise RuntimeError("Binance negrazino duomenu")
    s = pd.Series([float(k[4]) for k in rows],
                  index=pd.to_datetime([k[0] for k in rows], unit="ms").normalize(), name="btc")
    return s[~s.index.duplicated(keep="last")]


def load_prices(synthetic: bool):
    """Grazina (kainos, saltiniai). ETF - Yahoo. BTC - Binance, o laikotarpis pries Binance
    BTCEUR pradzia ir gedimo atveju - Yahoo BTC-EUR."""
    if synthetic:
        rng = np.random.default_rng(11)
        idx = pd.date_range("2019-08-01", pd.Timestamp.today().normalize(), freq="D")
        out = {}
        for k, (mu, vol) in {"etf": (0.09, 0.16), "btc": (0.45, 0.65)}.items():
            r = rng.normal(mu / 365, vol / np.sqrt(365), len(idx))
            out[k] = 100 * np.exp(np.cumsum(r))
        return pd.DataFrame(out, index=idx), {"etf": "sintetiniai", "btc": "sintetiniai"}
    import yfinance as yf
    raw = yf.download(list(TICKERS.values()), start="2019-01-01", auto_adjust=True,
                      progress=False)["Close"]
    raw = raw.rename(columns={v: k for k, v in TICKERS.items()})
    raw.index = pd.to_datetime(raw.index).tz_localize(None).normalize()
    etf = raw["etf"].dropna() if "etf" in raw else pd.Series(dtype=float)
    ybtc = raw["btc"].dropna() if "btc" in raw else pd.Series(dtype=float)
    if etf.empty:
        raise RuntimeError("Yahoo negrazino ETF kainu")
    sources = {"etf": f"Yahoo {TICKERS['etf']}"}

    try:
        b = binance_daily()
        early = ybtc[ybtc.index < b.index[0]]
        btc = pd.concat([early, b])
        sources["btc"] = f"Binance {BINANCE_SYMBOL} nuo {b.index[0].date()}" + \
            (f", anksčiau Yahoo {TICKERS['btc']}" if len(early) else "")
        common = b.index.intersection(ybtc.index)[-30:]
        if len(common):
            gap = float((b[common] / ybtc[common] - 1).abs().median())
            print(f"Binance vs Yahoo BTC skirtumas (30 d. mediana): {gap:.2%}")
            if gap > 0.03:
                sources["warning"] = f"Binance ir Yahoo BTC kainos skiriasi {gap:.1%}"
    except Exception as e:
        if ybtc.empty:
            raise RuntimeError(f"Nei Binance ({e}), nei Yahoo negrazino BTC kainu")
        print(f"Binance nepasiekiamas ({e}), naudojamas Yahoo")
        btc = ybtc
        sources["btc"] = f"Yahoo {TICKERS['btc']} (Binance nepasiekiamas)"

    px = pd.concat({"etf": etf, "btc": btc}, axis=1)
    full = pd.date_range(px.index.min(), px.index.max(), freq="D")   # BTC kalendorius: kasdien
    px = px.reindex(full).ffill().dropna()
    if len(px) < SMA_DAYS + 60:
        raise RuntimeError("Per mazai duomenu")
    return px[["etf", "btc"]], sources


def month_starts(index):
    s = index.to_series()
    return set(s.groupby(index.to_period("M")).min())


def nav_stats(nav: np.ndarray, dates) -> dict:
    nav = np.asarray(nav)
    dd = float((nav / np.maximum.accumulate(nav) - 1).min())
    years = (dates[-1] - dates[0]).days / 365.25
    twr = float(nav[-1] / nav[0])
    return {"maxdd": dd, "twr": twr, "cagr": twr ** (1 / years) - 1 if years > 0 else 0.0}


def run_dca(px, mix, contrib_days):
    """Perka kas menesi pagal proporcijas, niekada neparduoda."""
    rets = px.pct_change().fillna(0.0)
    hold = {a: 0.0 for a in mix}
    units, invested, trades = 0.0, 0.0, 0
    values, navs, inv = [], [], []
    for d in px.index:
        for a in hold:
            hold[a] *= 1 + rets.at[d, a]
        value = sum(hold.values())
        nav = value / units if units else 1.0
        if d in contrib_days:
            units += MONTHLY / nav
            invested += MONTHLY
            for a, w in mix.items():
                hold[a] += MONTHLY * w * (1 - BUY_COST[a])
                trades += 1
            value = sum(hold.values())
        values.append(value)
        navs.append(value / units if units else 1.0)
        inv.append(invested)
    return np.array(values), np.array(navs), np.array(inv), trades


def run_trend(px, mix, contrib_days, sma):
    """80/20, bet kiekviena dalis laikoma tik kai kaina > slankiojo vidurkio; kitaip - grynieji."""
    rets = px.pct_change().fillna(0.0)
    hold = {"etf": 0.0, "btc": 0.0, "cash": 0.0}
    units, invested, trades = 0.0, 0.0, 0
    values, navs = [], []
    for d in px.index:
        for a in mix:
            hold[a] *= 1 + rets.at[d, a]
        value = sum(hold.values())
        nav = value / units if units else 1.0
        if d in contrib_days:
            units += MONTHLY / nav
            invested += MONTHLY
            hold["cash"] += MONTHLY
            total = sum(hold.values())
            for a, w in mix.items():
                target = total * w if px.at[d, a] > sma.at[d, a] else 0.0
                delta = target - hold[a]
                if abs(delta) > 0.01:
                    cost = abs(delta) * TRADE_COST[a]
                    hold[a] += delta
                    hold["cash"] -= delta + cost
                    trades += 1
            value = sum(hold.values())
        values.append(value)
        navs.append(value / units if units else 1.0)
    return np.array(values), np.array(navs), trades


def run_trader(px, contrib_days, seed=3):
    """Atsitiktinis BTC prekiautojas be pranasumo, bet su realiais kastais."""
    rng = np.random.default_rng(seed)
    r = px["btc"].pct_change().fillna(0.0).to_numpy()
    T, P = len(r), TRADER_PATHS
    contrib = np.array([MONTHLY if d in contrib_days else 0.0 for d in px.index])
    switch = rng.random((P, T)) < TRADER_SWITCH_PROB
    state = (rng.random(P)[:, None] < 0.5) ^ (np.cumsum(switch, axis=1) % 2 == 1)
    v = np.zeros(P)
    p10, p50, p90 = np.empty(T), np.empty(T), np.empty(T)
    for t in range(T):
        v = v * (1 + r[t] * state[:, t])
        v = v * (1 - TRADER_COST * switch[:, t])
        v = v + contrib[t]
        p10[t], p50[t], p90[t] = np.percentile(v, [10, 50, 90])
    months = max(1, len(contrib_days))
    return v, p10, p50, p90, float(switch.sum(axis=1).mean() / months)


def build(px, sources=None, stale=False):
    sma = px.rolling(SMA_DAYS).mean()
    px = px.loc[sma.dropna().index[0]:]
    sma = sma.loc[px.index]
    cd = month_starts(px.index)
    dates = px.index

    mix_v, mix_nav, invested, mix_tr = run_dca(px, MIX, cd)
    etf_v, etf_nav, _, etf_tr = run_dca(px[["etf"]], {"etf": 1.0}, cd)
    btc_v, btc_nav, _, btc_tr = run_dca(px[["btc"]], {"btc": 1.0}, cd)
    tr_v, tr_nav, tr_tr = run_trend(px, MIX, cd, sma)
    final, p10, p50, p90, switches_m = run_trader(px, cd)

    inv = float(invested[-1])
    beat_btc = float((final > btc_v[-1]).mean())
    beat_mix = float((final > mix_v[-1]).mean())

    def row(key, name, values, nav, trades, note=""):
        st = nav_stats(nav, dates)
        return {"key": key, "name": name, "value": float(values[-1]),
                "gain": float(values[-1] / inv - 1), "maxdd": st["maxdd"], "cagr": st["cagr"],
                "twr": st["twr"], "trades": int(trades), "note": note}

    table = [
        row("dca_mix", "DCA 80/20", mix_v, mix_nav, mix_tr, "kas mėnesį perka, niekada neparduoda"),
        row("dca_etf", "DCA tik ETF", etf_v, etf_nav, etf_tr),
        row("dca_btc", "DCA tik BTC", btc_v, btc_nav, btc_tr),
        row("trend", "Trendo filtras 80/20", tr_v, tr_nav, tr_tr, "laiko tik tai, kas virš 200 d. vidurkio"),
        {"key": "trader", "name": "Aktyvus BTC prekiautojas (mediana)", "value": float(np.median(final)),
         "gain": float(np.median(final) / inv - 1), "maxdd": None, "cagr": None, "twr": None,
         "trades": int(round(switches_m * len(cd))),
         "note": f"{TRADER_PATHS} atsitiktinių scenarijų"},
    ]

    step = 7  # savaitiniai taskai grafikui
    idx = list(range(0, len(dates), step))
    if idx[-1] != len(dates) - 1:
        idx.append(len(dates) - 1)
    pick = lambda a: [round(float(a[i]), 2) for i in idx]

    hype_path = ROOT / "hype.json"
    try:
        hype = json.loads(hype_path.read_text(encoding="utf-8")) if hype_path.exists() else []
    except json.JSONDecodeError:
        hype = [{"data": "", "saltinis": "hype.json", "teiginys": "Failas sugadintas",
                 "verdiktas": "Klaida", "pastaba": "Patikrink JSON sintaksę."}]

    years = (dates[-1] - dates[0]).days / 365.25
    return {
        "updated": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "data_until": dates[-1].strftime("%Y-%m-%d"),
        "start": dates[0].strftime("%Y-%m-%d"),
        "years": round(years, 1),
        "stale": stale,
        "sources": sources or {},
        "invested": inv,
        "params": {"monthly": MONTHLY, "etf": TICKERS["etf"], "btc": TICKERS["btc"],
                   "switches_per_month": round(switches_m, 1), "trader_cost": TRADER_COST,
                   "paths": TRADER_PATHS},
        "trader": {"beat_btc": beat_btc, "beat_mix": beat_mix,
                   "p10": float(np.percentile(final, 10)), "p50": float(np.median(final)),
                   "p90": float(np.percentile(final, 90))},
        "table": table,
        "chart": {"dates": [dates[i].strftime("%Y-%m-%d") for i in idx],
                  "invested": pick(invested), "dca_mix": pick(mix_v), "dca_etf": pick(etf_v),
                  "dca_btc": pick(btc_v), "trend": pick(tr_v),
                  "trader_p10": pick(p10), "trader_p50": pick(p50), "trader_p90": pick(p90)},
        "hype": hype,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--synthetic", action="store_true", help="atsitiktiniai duomenys testui be interneto")
    args = ap.parse_args()
    try:
        px, sources = load_prices(args.synthetic)
    except Exception as e:
        # Nesugadiname veikiancio puslapio: klaida -> iseinam be pakeitimu
        sys.exit(f"Nepavyko gauti kainu: {e}. Puslapis nepakeistas.")
    data = build(px, sources)
    if args.synthetic:
        data["synthetic"] = True
    template = (ROOT / "template.html").read_text(encoding="utf-8")
    html = template.replace("__DATA__", json.dumps(data, ensure_ascii=False))
    out = ROOT / "docs" / "index.html"
    out.parent.mkdir(exist_ok=True)
    out.write_text(html, encoding="utf-8")
    (ROOT / "docs" / "data.json").write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    t = data["trader"]
    print(f"Atnaujinta iki {data['data_until']}. Įnešta {data['invested']:.0f} EUR. "
          f"Prekiautojas lenkia BTC DCA {t['beat_btc']:.0%} scenarijų.")


if __name__ == "__main__":
    main()
