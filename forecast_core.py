"""
forecast_core.py - compare 7 forecasting methods on monthly consumption.

INPUT  : a wide table, one row per item, one column per month (1..T), values = units consumed.
         Missing = blank. Months that are copies or empty templates must already be removed.
STEPS  : 1) group items by their FIRST `GROUP_MONTHS` months only (no peeking at the test)
         2) rolling one-month-ahead test: for each test month, fit on all earlier months
         3) score 7 methods: WAPE, bias, MASE, skill vs naive - overall and by group
         4) pick the best method per group, forecast the next months, safety stock, order quantity
Nothing here calls an outside service. Only numpy, pandas, scikit-learn.
"""
import numpy as np
import pandas as pd
from sklearn.linear_model import Ridge
from sklearn.ensemble import RandomForestRegressor, GradientBoostingRegressor

METHODS = ["Naive", "Moving average (3)", "Exp. smoothing", "Croston/SBA",
           "Linear regression (pooled)", "Random Forest (pooled)", "Gradient Boosting (pooled)"]
GROUP_MONTHS = 4      # items are grouped by their first 4 months only
MIN_TRAIN = 4         # first forecast is made from 4 months of history
CAP = 5.0             # cap on scaled values used inside the pooled models
Z = 1.65              # ~95% service level for safety stock


# ----------------------------------------------------------------- simple methods
def f_naive(h):
    return h[-1]


def f_ma3(h):
    return h[-3:].mean()


def f_ses(h):
    best, best_sse = 0.3, np.inf
    for a in (0.1, 0.2, 0.3, 0.5, 0.7, 0.9):
        lvl, sse = h[0], 0.0
        for y in h[1:]:
            sse += (y - lvl) ** 2
            lvl = a * y + (1 - a) * lvl
        if sse < best_sse:
            best, best_sse = a, sse
    lvl = h[0]
    for y in h[1:]:
        lvl = best * y + (1 - best) * lvl
    return lvl


def f_croston_sba(h, a=0.2):
    nz = np.flatnonzero(h > 0)
    if len(nz) == 0:
        return 0.0
    z = h[nz[0]]
    p = nz[0] + 1.0
    q = 1
    for y in h[nz[0] + 1:]:
        if y > 0:
            z = a * y + (1 - a) * z
            p = a * q + (1 - a) * p
            q = 1
        else:
            q += 1
    return (1 - a / 2) * z / p


# ----------------------------------------------------------------- pooled ML
def _features(Y, m):
    """features for forecasting month index m (0-based) using months 0..m-1; Y is items x months"""
    hist = Y[:, :m]
    s = hist.mean(axis=1) + 1.0
    lag1 = Y[:, m - 1] / s
    lag2 = Y[:, m - 2] / s
    last3 = Y[:, max(0, m - 3):m].mean(axis=1) / s
    zshare = (hist == 0).mean(axis=1)
    # ratios are capped at CAP so one very large month cannot dominate the fit
    X = np.c_[np.clip(lag1, 0, CAP), np.clip(lag2, 0, CAP), np.clip(last3, 0, CAP), zshare, np.log(s)]
    return X, s


def _ml_models():
    return {
        "Linear regression (pooled)": Ridge(alpha=1.0),
        "Random Forest (pooled)": RandomForestRegressor(n_estimators=200, max_depth=4, min_samples_leaf=5, random_state=0, n_jobs=-1),
        "Gradient Boosting (pooled)": GradientBoostingRegressor(n_estimators=100, max_depth=2, learning_rate=0.05, subsample=0.8, random_state=0),
    }


def ml_forecast(Y, t):
    """fit on rows with target month 2..t-1 (0-based), predict month t. returns {name: array}"""
    Xs, ys = [], []
    for m in range(2, t):
        X, s = _features(Y, m)
        Xs.append(X)
        ys.append(np.clip(Y[:, m] / s, 0, CAP))
    X_tr, y_tr = np.vstack(Xs), np.concatenate(ys)
    X_te, s_te = _features(Y, t)
    out = {}
    for name, mdl in _ml_models().items():
        mdl.fit(X_tr, y_tr)
        out[name] = np.clip(mdl.predict(X_te), 0, None) * s_te
    return out


# ----------------------------------------------------------------- driver
def forecast_all(Y, t):
    """all 7 methods, forecast month index t from months 0..t-1. returns DataFrame items x methods"""
    n = Y.shape[0]
    res = {m: np.zeros(n) for m in METHODS}
    for i in range(n):
        h = Y[i, :t]
        res["Naive"][i] = f_naive(h)
        res["Moving average (3)"][i] = f_ma3(h)
        res["Exp. smoothing"][i] = f_ses(h)
        res["Croston/SBA"][i] = f_croston_sba(h)
    res.update(ml_forecast(Y, t))
    return pd.DataFrame(res)


def run_test(wide, first_test=None):
    """wide: DataFrame items x months (columns in time order). returns (long results, groups, Y)"""
    Y = wide.fillna(0).to_numpy(float)
    T = Y.shape[1]
    first_test = first_test or MIN_TRAIN
    nz = (Y[:, :GROUP_MONTHS] > 0).sum(axis=1)
    groups = pd.Series(np.where(nz >= 3, "Fast-moving", np.where(nz >= 1, "Slow / intermittent", "No use in first 4 months")), index=wide.index)
    rows = []
    for t in range(first_test, T):
        F = forecast_all(Y, t)
        F.index = wide.index
        F["actual"] = Y[:, t]
        F["test_month"] = wide.columns[t]
        rows.append(F.reset_index().rename(columns={"index": "item", wide.index.name or "item": "item"}))
    long = pd.concat(rows, ignore_index=True)
    long["group"] = long["item"].map(groups)
    return long, groups, Y


def score(long, Y, wide, groups, first_test=None):
    first_test = first_test or MIN_TRAIN
    # MASE scale: mean abs one-step change in the first `first_test` months (training only)
    d = np.abs(np.diff(Y[:, :first_test], axis=1)).mean(axis=1)
    scale = pd.Series(d, index=wide.index)
    out = []
    for gname, g in list(long.groupby("group")) + [("All items", long)]:
        for m in METHODS:
            e = g[m] - g["actual"]
            tot = g["actual"].sum()
            wape = e.abs().sum() / tot if tot > 0 else np.nan
            bias = e.sum() / tot if tot > 0 else np.nan
            ab = (g.assign(ae=e.abs()).groupby("item")["ae"].mean())
            sc = scale.reindex(ab.index)
            ok = sc > 0
            mase = (ab[ok] / sc[ok]).mean() if ok.any() else np.nan
            out.append((gname, m, g["item"].nunique(), wape, bias, mase))
    res = pd.DataFrame(out, columns=["group", "method", "items", "WAPE", "bias", "MASE"])
    base = res[res.method == "Naive"].set_index("group")["WAPE"]
    res["skill_vs_naive"] = 1 - res["WAPE"] / res["group"].map(base)
    return res


def final_plan(wide, long, groups, best, horizon=3, onhand=None):
    """refit best method per group on all months; forecast next `horizon` months (flat); safety stock; order"""
    Y = wide.fillna(0).to_numpy(float)
    T = Y.shape[1]
    F = forecast_all(Y, T)
    F.index = wide.index
    rows = []
    err = long.copy()
    for item, g in groups.items():
        m = best.get(g, "Naive")
        fc = float(F.loc[item, m])
        e = err[err["item"] == item]
        rmse = float(np.sqrt(((e[m] - e["actual"]) ** 2).mean())) if len(e) else 0.0
        ss = Z * rmse
        stock = float(onhand.get(item, np.nan)) if onhand is not None else np.nan
        note = ""
        if np.isnan(stock):
            note = "no stock record: check"
        elif stock < 0:
            note = "negative stock balance: check records"
        need = horizon * fc + ss
        order = max(0.0, need - max(0.0, 0 if np.isnan(stock) else stock))
        if g.startswith("No use"):
            note = (note + "; " if note else "") + "little history: manual review"
        rows.append((item, g, m, fc, ss, stock, round(order), note))
    return pd.DataFrame(rows, columns=["item", "group", "method", "forecast_next_month", "safety_stock",
                                       "on_hand", f"suggested_order_{horizon}_months", "note"])


# ----------------------------------------------------------------- stock projection
def stock_projection(plan, horizon=6):
    """Project each item's stock forward using its forecast. Two lines per item:
       no new orders, and with the suggested order arriving at the start of month 1.
       months_of_cover = stock on hand / forecast monthly use."""
    rows = []
    for _, r in plan.iterrows():
        fc = float(r["forecast_next_month"])
        stock = r["on_hand"]
        order = float(r[[c for c in plan.columns if c.startswith("suggested_order")][0]])
        has_stock = not np.isnan(stock) and stock >= 0
        s0 = max(0.0, 0.0 if np.isnan(stock) else float(stock))
        cover = (s0 / fc) if fc > 0.5 else np.inf
        no_ord = [max(0.0, s0 - fc * k) for k in range(1, horizon + 1)]
        with_ord = [max(0.0, s0 + order - fc * k) for k in range(1, horizon + 1)]
        runout = next((k for k in range(1, horizon + 1) if s0 - fc * k <= 0), None) if fc > 0.5 else None
        if np.isnan(stock) or stock < 0:
            cover, runout, no_ord, with_ord = np.nan, None, [np.nan] * horizon, [np.nan] * horizon
        if np.isnan(stock):
            status = "No stock record"
        elif stock < 0:
            status = "Negative balance: check"
        elif fc <= 0.5:
            status = "No expected use" if s0 > 0 else "No stock, no use"
        elif cover < 1:
            status = "Runs out within 1 month"
        elif cover < 3:
            status = "Low (under 3 months)"
        elif cover <= 12:
            status = "OK (3 to 12 months)"
        else:
            status = "High (over 12 months): expiry watch"
        rows.append((r["item"], r["group"], s0 if has_stock else stock, fc, cover, runout, status, no_ord, with_ord))
    out = pd.DataFrame(rows, columns=["item", "group", "on_hand", "forecast_per_month", "months_of_cover",
                                      "runs_out_in_month", "status", "balance_no_order", "balance_with_order"])
    return out


# ----------------------------------------------------------------- demand per item (main output)
def demand_table(wide, long, groups, best, horizon=12):
    """Expected demand per item: per month, likely range, and total for the next `horizon` months."""
    Y = wide.fillna(0).to_numpy(float)
    T = Y.shape[1]
    F = forecast_all(Y, T)
    F.index = wide.index
    rows = []
    for item, g in groups.items():
        m = best.get(g, "Naive")
        fc = float(F.loc[item, m])
        e = long[long["item"] == item]
        rmse = float(np.sqrt(((e[m] - e["actual"]) ** 2).mean())) if len(e) else np.nan
        y = wide.loc[item].fillna(0).to_numpy(float)
        used = int((y > 0).sum())
        avg = float(y.mean())
        rel = rmse / fc if fc > 0.5 and not np.isnan(rmse) else np.inf
        if fc <= 0.5:
            rel_label = "No expected use"
        elif used >= 6 and rel < 0.5:
            rel_label = "Good"
        elif used >= 4 and rel < 1.0:
            rel_label = "Fair"
        else:
            rel_label = "Low: manual review"
        rows.append((item, g, f"{used} of {T}", round(avg, 1), m, round(fc, 1),
                     round(max(0.0, fc - rmse), 1) if not np.isnan(rmse) else np.nan,
                     round(fc + rmse, 1) if not np.isnan(rmse) else np.nan,
                     round(fc * horizon), round(avg * horizon), rel_label))
    return pd.DataFrame(rows, columns=["item", "group", "months_with_use", "avg_monthly_use_so_far", "method",
                                       "forecast_per_month", "likely_low", "likely_high",
                                       f"forecast_next_{horizon}_months", f"same_pace_as_so_far_{horizon}_months",
                                       "reliability"])
