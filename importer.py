"""Turn the user's own Excel workbook into the tables PharmCast needs.

The user picks the sheet and the columns on screen, so the layout of the workbook
does not have to match any template.
"""
import re
import numpy as np
import pandas as pd

MONTH_RE = re.compile(r"^(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)", re.I)
NONE = "(none)"


def read_sheet(xl, sheet, header_row):
    df = xl.parse(sheet, header=header_row - 1)
    df.columns = [str(c).strip() for c in df.columns]
    return df.dropna(how="all")


def guess_item(cols):
    for c in cols:
        if re.search(r"item|description|medicine|generic|drug|name|particular", c, re.I):
            return c
    return cols[0]


def guess_months(cols):
    return [c for c in cols if MONTH_RE.match(c)]


def guess(cols, pattern):
    for c in cols:
        if re.search(pattern, c, re.I):
            return c
    return NONE


def _key(s):
    return re.sub(r"\s+", " ", str(s).strip().lower())


def build(df, item_col, month_cols, unit_col=None, cost_col=None, stock_df=None, smap=None, lead=2.0, ved="E"):
    """Return the dataset dict used by the app, plus a list of plain-language notes."""
    notes = []
    if len(month_cols) < 6:
        raise ValueError("Choose at least 6 month columns (the test needs May-style test months after four training months).")
    month_cols = [str(c) for c in month_cols]
    d = df[[item_col] + month_cols + [c for c in (unit_col, cost_col) if c]].copy()
    d = d[d[item_col].notna() & (d[item_col].astype(str).str.strip() != "")]
    d[item_col] = d[item_col].astype(str).str.strip()
    for m in month_cols:
        d[m] = pd.to_numeric(d[m], errors="coerce")
    # drop months with no figures at all
    empty = [m for m in month_cols if d[m].isna().all()]
    if empty:
        notes.append(f"Months with no figures were left out: {', '.join(empty)}.")
        month_cols = [m for m in month_cols if m not in empty]
    if len(month_cols) < 6:
        raise ValueError("Fewer than 6 months have figures.")
    d["_k"] = d[item_col].map(_key)
    dup = d["_k"].duplicated(keep=False).sum()
    agg = {m: "sum" for m in month_cols}
    if unit_col: agg[unit_col] = "first"
    if cost_col: agg[cost_col] = "first"
    agg[item_col] = "first"
    # sum duplicates only when all values present; keep NaN if every value is NaN
    g = d.groupby("_k", sort=False)
    raw = g.agg({**agg, **{m: (lambda s: s.sum(min_count=1)) for m in month_cols}}).reset_index(drop=True)
    if dup:
        notes.append(f"{dup} rows shared an item name with another row and were added together.")
    raw = raw.rename(columns={item_col: "Item"})
    raw = raw[["Item"] + month_cols + [c for c in (unit_col, cost_col) if c]]
    recovered = raw[["Item"] + month_cols].copy()
    recovered[month_cols] = recovered[month_cols].fillna(0)
    nan_cells = int(raw[month_cols].isna().sum().sum())
    if nan_cells:
        notes.append(f"{nan_cells} blank month cells were treated as zero use.")

    items = pd.DataFrame({"Item": recovered["Item"]})
    items["Unit"] = raw[unit_col].astype(str).fillna("") if unit_col else ""
    cost = pd.to_numeric(raw[cost_col], errors="coerce").fillna(0.0).values if cost_col else np.zeros(len(items))
    items["UnitCost"] = cost
    items["LeadMonths"] = float(lead)
    items["VED"] = ved

    batches = pd.DataFrame(columns=["Item", "Batch", "Expiry", "Qty", "UnitCost"])
    stock_records = None
    if stock_df is not None and smap:
        s = stock_df.copy()
        s["_k"] = s[smap["item"]].map(_key)
        name = dict(zip(recovered["Item"].map(_key), recovered["Item"]))
        s["Item"] = s["_k"].map(name)
        unmatched = s["Item"].isna() & s[smap["item"]].notna()
        if unmatched.any():
            notes.append(f"{int(unmatched.sum())} stock rows had item names not found in the monthly sheet and were ignored.")
        s = s[s["Item"].notna()].copy()
        s["Qty"] = pd.to_numeric(s[smap["qty"]], errors="coerce")
        stock_records = s.groupby("Item", as_index=False)["Qty"].sum().rename(columns={"Qty": "Balance"})
        s["ExpiryD"] = pd.to_datetime(s[smap["expiry"]], errors="coerce")
        bad = s["ExpiryD"].isna() | s["Qty"].isna()
        if bad.any():
            notes.append(f"{int(bad.sum())} stock rows had no readable expiry date or quantity and were left out of the expiry watch.")
        s = s[~bad & (s["Qty"] > 0)].copy()
        s["Batch"] = s[smap["batch"]].astype(str) if smap.get("batch") else [f"B{i+1:04d}" for i in range(len(s))]
        sc = pd.to_numeric(s[smap["cost"]], errors="coerce") if smap.get("cost") else pd.Series(np.nan, index=s.index)
        costmap = sc.groupby(s["Item"]).mean()
        batches = pd.DataFrame({"Item": s["Item"], "Batch": s["Batch"], "Expiry": s["ExpiryD"].dt.strftime("%Y-%m-%d"),
                                "Qty": s["Qty"].astype(int), "UnitCost": sc.fillna(0).values}).reset_index(drop=True)
        if smap.get("cost"):
            fill = items["Item"].map(costmap)
            items["UnitCost"] = np.where(fill.notna(), fill, items["UnitCost"])
    else:
        notes.append("No stock/batch sheet was given, so the expiry watch and suggested orders have no stock to work on.")
    return dict(recovered=recovered, raw=raw[["Item"] + month_cols], items=items, stock_records=stock_records,
                batches=batches, months=month_cols, notes=notes)


# ---------------------------------------------------------------------------
# Monthly report format: one sheet per month, same columns on every sheet
# ---------------------------------------------------------------------------
import difflib
import openpyxl

_MON = ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"]


def _match(key0, names):
    """Exact name first. Otherwise a close name, but only if every number in it (strength, volume) is the same,
    so that 20MG is never matched to 40MG."""
    if key0 in names:
        return key0
    nums = lambda t: re.findall(r"\d+(?:\.\d+)?", t)
    for m in difflib.get_close_matches(key0, list(names), n=5, cutoff=0.85):
        if nums(m) == nums(key0):
            return m
    return None


def _num(x):
    return float(x) if isinstance(x, (int, float)) and not isinstance(x, bool) else None


def _month_of(title):
    t = title.lower()
    if t.startswith("copy of") or "template" in t:
        return None
    for i, m in enumerate(_MON):
        if re.search(m, t):
            return i, m.capitalize()
    return None


def _parse_month_sheet(ws):
    """Rows of one month sheet: name, unit, price, begin, procured, consumption, ending."""
    rows, hdr = [], None
    for i, r in enumerate(ws.iter_rows(values_only=True)):
        a = str(r[0]).strip().upper() if r and r[0] is not None else ""
        if hdr is None:
            if a in ("NOMENCLATURE", "MEDICINES"):
                hdr = i
            continue
        if not a or a.startswith("TOTAL") or a.startswith("GRAND"):
            continue
        cons = _num(r[7]) if len(r) > 7 else None
        beg = _num(r[3]) if len(r) > 3 else None
        if cons is None and beg is None:
            continue  # section title or signature line
        rows.append(dict(name=str(r[0]).strip(), unit=str(r[1] or "").strip(), price=_num(r[2]) or 0.0,
                         begin=beg or 0.0, proc=_num(r[5]) or 0.0, cons=cons, end=_num(r[9]) if len(r) > 9 else None))
    return rows


def _unique(rows):
    """Make duplicate names unique within a sheet by order of appearance."""
    seen, out = {}, []
    for r in rows:
        k = _key(r["name"])
        seen[k] = seen.get(k, 0) + 1
        r = dict(r, key=k if seen[k] == 1 else f"{k} #{seen[k]}")
        out.append(r)
    return out


def _hidden_original(wb, mon):
    for ws in wb.worksheets:
        t = ws.title.lower()
        if t.startswith("copy of original") and mon in t:
            hdr, ci_c, ci_e, rows = None, None, None, {}
            for r in ws.iter_rows(values_only=True):
                a = str(r[0]).strip().upper() if r and r[0] is not None else ""
                if hdr is None:
                    if a == "MEDICINES":
                        H = [str(h).upper() if h else "" for h in r]
                        ci_c = next((i for i, h in enumerate(H) if h == "CONSUMPTION"), None)
                        ci_e = next((i for i, h in enumerate(H) if "EXPIRY" in h), None)
                        hdr = True
                    continue
                if a and ci_c is not None:
                    rows[_key(a)] = (_num(r[ci_c]), r[ci_e] if ci_e is not None else None)
            return rows
    return {}


def _read_visible(file, recover_copies=True, lead=2.0, ved="E"):
    """Fallback reader: visible month sheets only (used when the workbook has no hidden ORIGINAL sheets)."""
    wb = openpyxl.load_workbook(file, data_only=True)
    notes = []
    months = []  # (order, label, rows)
    for ws in wb.worksheets:
        if ws.sheet_state != "visible":
            continue
        mo = _month_of(ws.title)
        if not mo:
            continue
        rows = _unique(_parse_month_sheet(ws))
        if not rows or sum((r["cons"] or 0) for r in rows) <= 0:
            continue  # empty future month
        months.append((mo[0], mo[1], rows, ws.title))
    months.sort(key=lambda x: x[0])
    if len(months) < 6:
        raise ValueError(f"Found only {len(months)} month sheets with consumption; need at least 6. Is this the monthly report workbook?")
    labels = [m[1] for m in months]
    # item order and master list: union in order of first appearance
    keys, disp, unit, price = [], {}, {}, {}
    for _, _, rows, _ in months:
        for r in rows:
            if r["key"] not in disp:
                keys.append(r["key"]); disp[r["key"]] = r["name"] if r["key"] == _key(r["name"]) else r["name"] + " (2)"
            unit[r["key"]] = r["unit"] or unit.get(r["key"], "")
            if r["price"]:
                price[r["key"]] = r["price"]
    raw = pd.DataFrame({"Item": [disp[k] for k in keys]})
    for _, lab, rows, _ in months:
        d = {r["key"]: r["cons"] for r in rows}
        raw[lab] = [d.get(k, np.nan) for k in keys]
    recovered = raw.copy()
    # copied months: same as the month before for >=95% of items
    for j in range(1, len(labels)):
        a, b = labels[j - 1], labels[j]
        both = raw[[a, b]].dropna()
        if len(both) and (both[a] == both[b]).mean() >= 0.95:
            orig = _hidden_original(wb, _MON[months[j][0]]) if recover_copies else {}
            if orig:
                names = list(orig)
                got = 0
                vals = []
                for k, cur in zip(keys, recovered[b]):
                    key0 = k.split(" #")[0]
                    mk_ = _match(key0, orig)
                    hit = orig[mk_] if mk_ else None
                    if hit is not None and hit[0] is not None:
                        got += 1; vals.append(hit[0])
                    else:
                        vals.append(cur)
                recovered[b] = vals
                notes.append(f"{b} was a copy of {a}. Original figures were recovered from the hidden original sheet for {got} of {len(keys)} items.")
            else:
                notes.append(f"{b} looks like a copy of {a} and no hidden original sheet was found. It was used as it is.")
    recovered[labels] = recovered[labels].fillna(0)

    items = pd.DataFrame({"Item": raw["Item"], "Unit": [unit.get(k, "") for k in keys],
                          "UnitCost": [price.get(k, 0.0) for k in keys], "LeadMonths": float(lead), "VED": ved})
    # stock: ending balance of the latest month
    last = months[-1]
    end = {r["key"]: r["end"] for r in last[2] if r["end"] is not None}
    stock_records = pd.DataFrame({"Item": [disp[k] for k in keys if k in end], "Balance": [end[k] for k in keys if k in end]})
    # expiry: the latest hidden original sheet that has expiry dates (one date per item)
    exp = {}
    for mi in range(11, -1, -1):
        o = _hidden_original(wb, _MON[mi])
        got = {k: v[1] for k, v in o.items() if v[1] not in (None, "")}
        if got:
            exp, exp_mon = got, _MON[mi].capitalize()
            break
    brows = []
    if exp:
        names = list(exp)
        for n_, k in enumerate(keys):
            if k not in end or end[k] <= 0:
                continue
            key0 = k.split(" #")[0]
            mk_ = _match(key0, exp)
            e = exp[mk_] if mk_ else None
            d = pd.to_datetime(e, errors="coerce")
            if pd.isna(d):
                continue
            brows.append(dict(Item=disp[k], Batch=f"E{n_+1:04d}", Expiry=d.strftime("%Y-%m-%d"), Qty=int(end[k]), UnitCost=price.get(k, 0.0)))
        notes.append(f"Expiry dates come from the hidden {exp_mon} original sheet, the latest one that has them. Each item is treated as one batch holding its latest ending balance ({last[1]}). Treat the expiry flags as indicative until current batch dates are entered.")
        notes.append(f"{len(brows)} items have both stock on hand and an expiry date.")
    else:
        notes.append("No expiry dates were found in the workbook, so the expiry watch is empty.")
    batches = pd.DataFrame(brows, columns=["Item", "Batch", "Expiry", "Qty", "UnitCost"])
    notes.insert(0, f"Read {len(labels)} month sheets ({labels[0]} to {labels[-1]}) and {len(keys)} items from {'the workbook'}.")
    return dict(recovered=recovered, raw=raw, items=items, stock_records=stock_records, batches=batches,
                months=labels, notes=notes)


def _jan_prices(file):
    wb = openpyxl.load_workbook(file, data_only=True)
    ws = [w for w in wb.worksheets if "JANUARY" in w.title.upper() and w.sheet_state == "visible"]
    out = {}
    if ws:
        for r in range(1, ws[0].max_row + 1):
            n, p = ws[0].cell(r, 1).value, ws[0].cell(r, 3).value
            if isinstance(n, str) and n.strip():
                try:
                    out[re.sub(r"\s+", " ", n).strip().upper()] = float(str(p).replace(",", ""))
                except ValueError:
                    pass
    return out


def read_monthly_report(file, recover_copies=True, lead=2.0, ved="E"):
    """Read a monthly medicine workbook the same way the analysis notebook does.

    The visible April and September sheets can be copies of the month before, so the real monthly figures
    are read from the hidden 'Copy of ORIGINAL' sheets (keyed by item name). Stock is the quantity on hand in
    the latest hidden sheet; expiry is the January date. If the workbook has no hidden sheets the visible
    sheets are read instead."""
    import hidden_sheets as ch
    try:
        _, info, mo = ch.load_weekly(file)
    except Exception:
        mo = pd.DataFrame()
    if mo is None or len(mo) == 0 or not recover_copies:
        return _read_visible(file, recover_copies, lead, ved)
    tot = mo.groupby("month")["cons"].sum()
    used = [int(m) for m in sorted(tot.index) if tot[m] > 0]
    if len(used) < 6:
        return _read_visible(file, recover_copies, lead, ved)
    mo = mo[mo.month.isin(used)]
    wide = mo.pivot_table(index="item", columns="month", values="cons", aggfunc="first")
    wide = wide[wide.notna().any(axis=1)]
    labels = [_MON[m - 1].capitalize() for m in used]
    wide = wide[used]
    wide.columns = labels
    recovered = wide.fillna(0).reset_index().rename(columns={"item": "Item"})
    raw = wide.reset_index().rename(columns={"item": "Item"})
    prices = _jan_prices(file)
    price = {k: prices.get(k, 0.0) for k in wide.index}
    items = pd.DataFrame({"Item": wide.index, "Unit": "", "UnitCost": [price[k] for k in wide.index],
                          "LeadMonths": float(lead), "VED": ved})
    last = mo[mo.month == max(used)].drop_duplicates("item").set_index("item").reindex(wide.index)
    has = last["onhand"].notna()
    stock_records = pd.DataFrame({"Item": wide.index[has], "Balance": last.loc[has, "onhand"].clip(lower=0).values})
    exp = mo[mo.month == 1].drop_duplicates("item").set_index("item")["expiry"].reindex(wide.index)
    brows = []
    for n_, k in enumerate(wide.index):
        q, e = last.loc[k, "onhand"], pd.to_datetime(exp.loc[k], errors="coerce")
        if pd.isna(q) or q <= 0 or pd.isna(e):
            continue
        brows.append(dict(Item=k, Batch=f"E{n_+1:04d}", Expiry=e.strftime("%Y-%m-%d"), Qty=int(q), UnitCost=price[k]))
    batches = pd.DataFrame(brows, columns=["Item", "Batch", "Expiry", "Qty", "UnitCost"])
    notes = [f"Read {len(labels)} months ({labels[0]} to {labels[-1]}) and {len(wide)} items from the hidden original sheets.",
             f"{int((~has).sum())} items have no stock record in {labels[-1]}; they are left out of stock and order.",
             f"Negative balances were set to zero for {int((last['onhand'] < 0).sum())} item(s).",
             "Expiry dates come from the January sheet (one date per item). Treat the expiry flags as indicative until current batch dates are entered."]
    return dict(recovered=recovered, raw=raw, items=items, stock_records=stock_records, batches=batches,
                months=labels, notes=notes)
