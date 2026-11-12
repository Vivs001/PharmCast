"""Grouping, seven forecasting methods, backtest, method selection, reliability.

The arithmetic lives in forecast_core.py, the same code the two analysis notebooks run
(so the app gives the same numbers as the analysis notebooks). This file only connects it to the app:
it renames the methods, keeps the table layout the screens expect and applies the
reliability rule from config.py. Every forecast for month t uses only months before t.
"""
import numpy as np
import pandas as pd
import forecast_core as core
import config

METHODS = ["Repeat last month", "3-month average", "Exponential smoothing", "Croston/SBA",
           "Linear regression", "Random forest", "Gradient boosting"]
GROUPS = ["Fast-moving", "Slow / intermittent", "No use in first 4 months"]
_MAP = dict(zip(core.METHODS, METHODS))      # core name -> app name


def make_groups(Y):
    """Fast: used in 3 or 4 of Jan to Apr. Slow: 1 or 2. No use: 0."""
    nz = (Y[:, :config.GROUP_MONTHS] > 0).sum(axis=1)
    return np.where(nz >= 3, GROUPS[0], np.where(nz >= 1, GROUPS[1], GROUPS[2]))


def forecast_all(Y, t):
    """Forecast month index t for every item, with all seven methods."""
    F = core.forecast_all(np.asarray(Y, float), t).rename(columns=_MAP)
    return F[METHODS].clip(lower=0)


def backtest(Y):
    """Forecast May to September one month ahead. Long table: item, t, actual, one column per method."""
    Y = np.asarray(Y, float)
    rows = []
    for t in range(config.TEST_START, Y.shape[1]):
        F = forecast_all(Y, t)
        F.insert(0, "item", np.arange(Y.shape[0]))
        F.insert(1, "t", t)
        F.insert(2, "actual", Y[:, t])
        rows.append(F)
    return pd.concat(rows, ignore_index=True)


def wape_table(bt, groups):
    """WAPE by method and group (lower is better). DataFrame indexed by method."""
    bt = bt.copy()
    bt["group"] = np.asarray(groups)[bt["item"].values]
    cols = {}
    for g in GROUPS + ["All items"]:
        sub = bt if g == "All items" else bt[bt["group"] == g]
        denom = sub["actual"].sum()
        cols[g] = {m: (np.abs(sub[m] - sub["actual"]).sum() / denom if denom > 0 else np.nan) for m in METHODS}
    return pd.DataFrame(cols)


def choose(wt):
    """Best method per group = lowest WAPE. A group with no use in the test falls back to Repeat last month."""
    best = {}
    for g in GROUPS:
        col = wt[g].dropna()
        best[g] = col.idxmin() if len(col) else "Repeat last month"
    return best


def reliability(nz_months, rmse, f):
    if f <= config.NO_USE_FORECAST:
        return "No expected use"
    if nz_months >= config.GOOD_MIN_MONTHS_USED and rmse < 0.5 * f:
        return "Good"
    if nz_months >= config.FAIR_MIN_MONTHS_USED and rmse < f:
        return "Fair"
    return "Low"


def run(Y, names):
    """Full pipeline. Returns dict with item table, WAPE table, winners, backtest."""
    Y = np.asarray(Y, float)
    groups = make_groups(Y)
    bt = backtest(Y)
    wt = wape_table(bt, groups)
    winners = choose(wt)
    final = forecast_all(Y, Y.shape[1])          # next month, from all months so far
    rows = []
    for i, name in enumerate(names):
        g = groups[i]
        m = winners[g]
        f = float(final.loc[i, m])
        err = bt[bt["item"] == i]
        rmse = float(np.sqrt(((err[m] - err["actual"]) ** 2).mean()))
        nz = int((Y[i] > 0).sum())
        rows.append(dict(Item=name, Group=g, Method=m, Forecast=f, Low=max(0.0, f - rmse), High=f + rmse, RMSE=rmse,
                         Months12=f * 12, MonthsUsed=nz, Reliability=reliability(nz, rmse, f)))
    return dict(items=pd.DataFrame(rows), wape=wt, winners=winners, backtest=bt, groups=groups, final=final)
