"""Data check report: what is wrong with the uploaded monthly files."""
import numpy as np
import pandas as pd
import config


def report(raw, stock_records, items):
    rows = []
    n = len(raw)
    cols = [c for c in raw.columns if c != "Item"]
    # copied months
    for i in range(1, len(cols)):
        a, b = cols[i - 1], cols[i]
        same = (raw[a] == raw[b]).sum()
        if same / n >= 0.95:
            rows.append(("Copied month", f"{b}", f"{b} equals {a} for {same} of {n} items ({same/n:.0%})",
                         "Recover the original figures from the hidden original sheet and confirm with the data owner"))
    # empty months
    empty = [m for m in cols if raw[m].isna().all()]
    if empty:
        rows.append(("Empty months", ", ".join(empty), "No consumption entered (empty template)", "Not used in the forecast"))
    # negative balances
    if stock_records is None:
        rows.append(("No stock sheet", "-", "No stock or batch sheet was loaded", "Add stock, batch and expiry data to use the expiry watch"))
        stock_records = pd.DataFrame({"Item": [], "Balance": []})
        skip_missing = True
    else:
        skip_missing = False
    neg = stock_records[stock_records["Balance"] < 0]
    for r in neg.itertuples():
        rows.append(("Negative balance", r.Item, f"Recorded balance {r.Balance}", "Check the last count and receipts"))
    # items with no stock record
    miss = [] if skip_missing else sorted(set(raw["Item"]) - set(stock_records["Item"]))
    for it in miss:
        rows.append(("No stock record", it, "Issued in the monthly sheet but no balance or batch on file", "Add the batch and expiry date"))
    # mixed units
    mixed = items[items["Unit"].astype(str).str.contains("/")]
    for r in mixed.itertuples():
        rows.append(("Mixed units", r.Item, f"Unit recorded as {r.Unit}", "Use one unit of measure per item"))
    return pd.DataFrame(rows, columns=["Finding", "Where", "Detail", "What to do"])


def counts(rep):
    return rep["Finding"].value_counts().to_dict()
