"""First-expiring, first-out simulation and expiry flags.

Rule-based simulation, not a trained model. For each item, stock is used
earliest expiry first at the forecast monthly rate. What is left in a batch on
its expiry date is the quantity at risk.
"""
import numpy as np
import pandas as pd
import config


def _left(batches_item, rate):
    """Quantity left at expiry for each batch (batches sorted by expiry)."""
    consumed_before = 0.0
    out = []
    for _, b in batches_item.iterrows():
        months = max(0.0, (b["ExpiryDate"] - config.DEMO_DATE).days / 30.4)
        take = min(b["Qty"], max(0.0, rate * months - consumed_before))
        out.append(b["Qty"] - take)
        consumed_before += take
    return out


def flag(share, days, left, expired):
    if expired:
        return "Expired"
    if left <= 0:
        return "None"
    if share >= config.HIGH_SHARE and days <= config.HIGH_DAYS:
        return "High"
    if share >= config.MEDIUM_SHARE or days <= config.MEDIUM_DAYS:
        return "Medium"
    return "Low"


def watch(batches, fc_items):
    """One row per batch with quantity left at expiry (central and conservative) and a flag."""
    b = batches.copy()
    b["ExpiryDate"] = pd.to_datetime(b["Expiry"]).dt.date
    rate = fc_items.set_index("Item")
    rows = []
    for item, g in b.groupby("Item"):
        g = g.sort_values("ExpiryDate")
        live = g[g["ExpiryDate"] >= config.DEMO_DATE]
        f = float(rate.loc[item, "Forecast"]) if item in rate.index else 0.0
        hi = float(rate.loc[item, "High"]) if item in rate.index else 0.0
        left_c = dict(zip(live.index, _left(live, f)))
        left_h = dict(zip(live.index, _left(live, hi)))
        for idx, r in g.iterrows():
            expired = r["ExpiryDate"] < config.DEMO_DATE
            days = (r["ExpiryDate"] - config.DEMO_DATE).days
            lc = float(r["Qty"]) if expired else float(left_c[idx])
            lh = float(r["Qty"]) if expired else float(left_h[idx])
            share = lc / r["Qty"] if r["Qty"] else 0
            rows.append(dict(Item=item, Batch=r["Batch"], Expiry=r["ExpiryDate"], DaysToExpiry=days, Qty=int(r["Qty"]),
                             Left=int(round(lc)), LeftHigh=int(round(lh)), UnitCost=r["UnitCost"],
                             ValueAtRisk=round(lc * r["UnitCost"], 2), ValueHigh=round(lh * r["UnitCost"], 2),
                             Flag=flag(share, days, lc, expired)))
    if not rows:
        return pd.DataFrame(columns=["Item","Batch","Expiry","DaysToExpiry","Qty","Left","LeftHigh","UnitCost","ValueAtRisk","ValueHigh","Flag"])
    df = pd.DataFrame(rows)
    order = {"Expired": 0, "High": 1, "Medium": 2, "Low": 3, "None": 4}
    return df.assign(_o=df["Flag"].map(order)).sort_values(["_o", "ValueAtRisk"], ascending=[True, False]).drop(columns="_o").reset_index(drop=True)


def summary(w):
    """Batches expiring Oct to Dec and the two rules."""
    q = w[(w["DaysToExpiry"] >= 0) & (pd.to_datetime(w["Expiry"]) <= pd.Timestamp(config.DEMO_DATE) + pd.Timedelta(days=91))]
    cons = q[q["LeftHigh"] > 0]
    cent = q[q["Left"] > 0]
    return dict(expiring=len(q), items_conservative=cons["Item"].nunique(), units_conservative=int(cons["LeftHigh"].sum()),
                value_conservative=float(cons["ValueHigh"].sum()), items_central=cent["Item"].nunique(),
                units_central=int(cent["Left"].sum()), value_central=float(cent["ValueAtRisk"].sum()),
                expired=int((w["Flag"] == "Expired").sum()))
