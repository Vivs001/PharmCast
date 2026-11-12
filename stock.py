"""Months of cover, status, suggested order and priority."""
import numpy as np
import pandas as pd
from datetime import date
import config


def usable_by_item(batches, today=None):
    """Stock that is not yet expired."""
    today = today or config.DEMO_DATE
    b = batches.copy()
    b["ExpiryDate"] = pd.to_datetime(b["Expiry"]).dt.date
    ok = b[b["ExpiryDate"] >= today]
    return ok.groupby("Item")["Qty"].sum()


def stock_table(fc_items, items, batches, safety_months=config.SAFETY_MONTHS, review_months=config.REVIEW_MONTHS):
    usable = usable_by_item(batches)
    df = fc_items.merge(items[["Item", "Unit", "UnitCost", "LeadMonths", "VED"]], on="Item")
    df["HasRecord"] = df["Item"].isin(batches["Item"])
    df["Usable"] = df["Item"].map(usable).fillna(0).astype(int)
    f = df["Forecast"]
    df["Cover"] = np.where(f > config.NO_USE_FORECAST, df["Usable"] / f.where(f > 0, np.nan), np.nan)
    need = f * (df["LeadMonths"] + review_months) + safety_months * f
    df["Order"] = np.where(f > config.NO_USE_FORECAST, np.maximum(0, np.ceil(need - df["Usable"])), 0).astype(int)
    df["OrderValue"] = df["Order"] * df["UnitCost"]

    def status(r):
        if r["Forecast"] <= config.NO_USE_FORECAST:
            return "No expected use"
        if not r["HasRecord"]:
            return "No stock record"
        if r["Cover"] < r["LeadMonths"]:
            return "Runs out"
        if r["Cover"] < r["LeadMonths"] + safety_months:
            return "Low"
        if r["Cover"] > config.HIGH_COVER_MONTHS:
            return "High"
        return "OK"
    df["Status"] = df.apply(status, axis=1)
    df["Priority"] = df["Status"].map({"Runs out": "Urgent", "Low": "High"}).fillna("Routine")
    df.loc[df["Order"] == 0, "Priority"] = "-"
    pr = {"Urgent": 0, "High": 1, "Routine": 2, "-": 3}
    ved = {"V": 0, "E": 1, "D": 2}
    df = df.assign(_p=df["Priority"].map(pr), _v=df["VED"].map(ved)).sort_values(["_p", "_v", "UnitCost"], ascending=[True, True, False]).drop(columns=["_p", "_v"])
    return df.reset_index(drop=True)


def projection(usable, monthly, months=6):
    """Stock left at the end of each of the next months at the forecast rate."""
    return [max(0.0, usable - monthly * k) for k in range(0, months + 1)]
