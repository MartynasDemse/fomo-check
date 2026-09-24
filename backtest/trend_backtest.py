#!/usr/bin/env python3
"""
trend_backtest.py - strategija "Trendo filtras v1": pasaulio akciju ETF + BTC + ETH.
Sprendimas kartą per menesi. Tik istorinis testas, jokiu sandoriu.

TAISYKLES (uzrasytos PRIES testa; pagal rezultatus nekeiciamos):
  1. Tiksliniai svoriai: pasaulio akcijos 70 %, BTC 20 %, ETH 10 %.
  2. Paskutine menesio prekybos diena kiekvienam turtui:
       kaina > 200 dienu slankusis vidurkis -> laikyti tikslini svori,
       kitaip ta dalis -> grynieji (trumpalaikes JAV obligacijos, BIL).
  3. Sandoris ivykdomas KITOS prekybos dienos uzdarymo kaina (jokio zvilgsnio i ateiti).
  4. Kastai: 0,10 % ETF, 0,30 % kripto nuo apyvartos.

PALYGINIMAS:
  - tas pats 70/20/10 portfelis BE filtro (perbalansuojamas kas menesi)
  - vien pasaulio akcijos (pirk ir laikyk)
  Laikotarpis dalijamas: iki 2022-01-01 ir nuo 2022-01-01 (apima 2022 m. kripto kracha).
  Atsparumo testas: tas pats filtras su 100/150/200/250 dienu vidurkiu. Jei rezultatas
  stipriai priklauso nuo vieno skaiciaus, strategija trapi.

PASTABOS:
  - ACWI (JAV listinguojamas) naudojamas kaip ilgos istorijos pakaitalas. ES investuotojas
    realiai pirktu UCITS atitikmeni (pvz. akumuliacini pasaulio akciju ETF) - rezultatai panasus,
    bet ne identiski. Viskas skaiciuojama USD; EUR/USD kurso itaka neitraukta. Mokesciai neitraukti.

PALEIDIMAS:
  pip install yfinance pandas numpy matplotlib
  python trend_backtest.py
  python trend_backtest.py --synthetic      # testas be interneto (atsitiktiniai duomenys)
"""
import argparse
import sys

import numpy as np
import pandas as pd

ASSETS = {"equity": "ACWI", "btc": "BTC-USD", "eth": "ETH-USD"}
CASH = "BIL"
TARGET = {"equity": 0.70, "btc": 0.20, "eth": 0.10}
COSTS = {"equity": 0.0010, "btc": 0.0030, "eth": 0.0030}
SPLIT = "2022-01-01"
DEFAULT_SMA = 200


def load_prices(synthetic):
    if synthetic:
        rng = np.random.default_rng(7)
        idx = pd.bdate_range("2017-01-02", "2026-09-01")
        spec = {"equity": (0.08, 0.16), "btc": (0.40, 0.70), "eth": (0.40, 0.90), "cash": (0.02, 0.005)}
        data = {}
        for k, (mu, vol) in spec.items():
            r = rng.normal(mu / 252, vol / np.sqrt(252), len(idx))
            data[k] = 100 * np.exp(np.cumsum(r))
        return pd.DataFrame(data, index=idx)
    try:
        import yfinance as yf
    except ImportError:
        sys.exit("Idiek: pip install yfinance")
    tickers = list(ASSETS.values()) + [CASH]
    raw = yf.download(tickers, start="2017-01-01", auto_adjust=True, progress=False)["Close"]
    px = raw.rename(columns={**{v: k for k, v in ASSETS.items()}, CASH: "cash"})
    days = px["equity"].dropna().index            # akciju prekybos kalendorius
    px = px.reindex(days).ffill().dropna()
    return px[["equity", "btc", "eth", "cash"]]


def simulate(px, weights, use_filter, sma_days):
    risky = list(weights)
    cols = risky + ["cash"]
    rets = px[cols].pct_change().fillna(0.0)
    sma = px[risky].rolling(sma_days).mean()
    start = sma.dropna().index[0]
    dates = px.index[px.index >= start]
    month_ends = set(px.index.to_series().groupby(px.index.to_period("M")).max())

    w = pd.Series(0.0, index=cols)
    w["cash"] = 1.0
    value, pending = 1.0, None
    values, invested, trades = [], [], 0
    for i, d in enumerate(dates):
        if i > 0:
            grown = w * (1 + rets.loc[d, cols])
            value *= grown.sum()
            w = grown / grown.sum()
        if pending is not None:
            delta = (pending - w).abs()
            value *= 1 - sum(delta[a] * COSTS[a] for a in risky)
            trades += int((delta[risky] > 0.005).sum())
            w, pending = pending, None
        if d in month_ends:
            tgt = pd.Series(0.0, index=cols)
            for a in risky:
                on = px.at[d, a] > sma.at[d, a] if use_filter else True
                tgt[a] = weights[a] if on else 0.0
            tgt["cash"] = 1.0 - tgt[risky].sum()
            pending = tgt
        values.append(value)
        invested.append(w[risky].sum())
    out = pd.DataFrame({"value": values, "invested": invested}, index=dates)
    out.attrs["trades"] = trades
    return out


def metrics(res, start=None, end=None):
    s = res.loc[start:end]
    v = s["value"] / s["value"].iloc[0]
    years = (v.index[-1] - v.index[0]).days / 365.25
    r = v.pct_change().dropna()
    dd = (v / v.cummax() - 1).min()
    cagr = v.iloc[-1] ** (1 / years) - 1 if years > 0 else np.nan
    vol = r.std() * np.sqrt(252)
    return {
        "CAGR": cagr,
        "Volat.": vol,
        "Max DD": dd,
        "Sharpe~": (r.mean() * 252) / vol if vol else np.nan,
        "CAGR/|DD|": cagr / abs(dd) if dd else np.nan,
        "Investuota": s["invested"].mean(),
    }


def fmt(df):
    out = df.copy()
    for c in ["CAGR", "Volat.", "Max DD", "Investuota"]:
        out[c] = out[c].map(lambda x: f"{x:6.1%}")
    for c in ["Sharpe~", "CAGR/|DD|"]:
        out[c] = out[c].map(lambda x: f"{x:5.2f}")
    return out.to_string()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--synthetic", action="store_true")
    args = ap.parse_args()

    px = load_prices(args.synthetic)
    print(f"Duomenys: {px.index[0].date()} - {px.index[-1].date()}  ({len(px)} prekybos dienu)"
          + ("  [SINTETINIAI]" if args.synthetic else ""))

    strategies = {
        "Trendo filtras 200d": simulate(px, TARGET, True, DEFAULT_SMA),
        "70/20/10 be filtro": simulate(px, TARGET, False, DEFAULT_SMA),
        "Tik akcijos": simulate(px, {"equity": 1.0}, False, DEFAULT_SMA),
    }
    # vienoda pradzia visiems
    common = max(r.index[0] for r in strategies.values())
    strategies = {k: v.loc[common:] for k, v in strategies.items()}

    lines = []
    for title, (a, b) in {"VISAS LAIKOTARPIS": (None, None),
                          f"IKI {SPLIT}": (None, SPLIT),
                          f"NUO {SPLIT} (kontrolinis)": (SPLIT, None)}.items():
        tbl = pd.DataFrame({k: metrics(v, a, b) for k, v in strategies.items()}).T
        lines += [f"\n=== {title} ===", fmt(tbl)]

    years = (strategies["Trendo filtras 200d"].index[-1] - common).days / 365.25
    t = strategies["Trendo filtras 200d"].attrs.get("trades", 0)
    lines.append(f"\nFiltro sandoriu: ~{t / years:.1f} per metus (atskiru turto pakeitimu)")

    rob = {}
    for n in (100, 150, 200, 250):
        r = simulate(px, TARGET, True, n).loc[common:]
        m_all, m_oos = metrics(r), metrics(r, SPLIT, None)
        rob[f"SMA {n}"] = {"CAGR": m_all["CAGR"], "Max DD": m_all["Max DD"],
                           "CAGR nuo 2022": m_oos["CAGR"], "Max DD nuo 2022": m_oos["Max DD"]}
    rob = pd.DataFrame(rob).T.apply(lambda c: c.map(lambda x: f"{x:6.1%}"))
    lines += ["\n=== ATSPARUMAS (vidurkio ilgis) ===", rob.to_string()]

    lines.append("\nKaip skaityti: filtras vertingas, jei ZENGIAI mazina Max DD ir to nepraranda\n"
                 "kontroliniame laikotarpyje bei su kitais vidurkio ilgiais. Didesnis CAGR - premija, ne tikslas.")
    report = "\n".join(lines)
    print(report)
    with open("trend_backtest_report.txt", "w", encoding="utf-8") as f:
        f.write(report)

    curves = pd.DataFrame({k: v["value"] for k, v in strategies.items()})
    curves.to_csv("trend_backtest_curves.csv")
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        fig, ax = plt.subplots(2, 1, figsize=(10, 7), sharex=True, gridspec_kw={"height_ratios": [2, 1]})
        curves.plot(ax=ax[0], logy=True, title="Portfelio verte (log skale)")
        (curves / curves.cummax() - 1).plot(ax=ax[1], legend=False, title="Kritimas nuo piko")
        ax[1].axvline(pd.Timestamp(SPLIT), color="gray", ls="--")
        ax[0].axvline(pd.Timestamp(SPLIT), color="gray", ls="--")
        fig.tight_layout()
        fig.savefig("trend_backtest.png", dpi=120)
        print("\nIssaugota: trend_backtest_report.txt, trend_backtest_curves.csv, trend_backtest.png")
    except ImportError:
        print("\n(matplotlib neidiegtas - grafikas praleistas)")


if __name__ == "__main__":
    main()
