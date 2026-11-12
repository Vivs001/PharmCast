"""Builds fictional monthly issuance and batches. Seeded so it is always the same."""
import numpy as np
import pandas as pd
from datetime import date, timedelta
import config

# name, unit, unit_cost (PHP), lead_time (months), VED, pattern, base level
ITEMS = [
    ("Amlodipine 10 mg tab", "tab", 3.5, 3, "E", "steady", 360),
    ("Losartan 50 mg tab", "tab", 4.2, 3, "E", "steady", 480),
    ("Losartan 100 mg tab", "tab", 6.0, 3, "E", "steady", 250),
    ("Metformin 500 mg tab", "tab", 1.8, 3, "V", "trend_up", 520),
    ("Atorvastatin 20 mg tab", "tab", 5.5, 3, "E", "steady", 300),
    ("Simvastatin 40 mg tab", "tab", 4.0, 3, "E", "bursty_fast", 130),
    ("Paracetamol 500 mg tab", "tab", 0.9, 2, "V", "steady", 1500),
    ("Ascorbic acid 500 mg tab", "tab", 1.2, 2, "D", "steady", 270),
    ("Co-amoxiclav 625 mg tab", "tab", 22.0, 3, "V", "steady", 300),
    ("Amoxicillin 500 mg cap", "cap", 3.0, 3, "V", "trend_down", 420),
    ("Cefalexin 500 mg cap", "cap", 6.5, 3, "E", "steady", 240),
    ("Mefenamic acid 500 mg tab", "tab", 2.2, 2, "E", "bursty_fast", 220),
    ("Ibuprofen 400 mg tab", "tab", 1.5, 2, "E", "steady", 330),
    ("Omeprazole 20 mg cap", "cap", 3.8, 3, "E", "steady", 360),
    ("Cetirizine 10 mg tab", "tab", 1.3, 2, "D", "steady", 280),
    ("Multivitamins tab", "tab", 2.0, 2, "D", "steady", 230),
    ("Salbutamol 2 mg tab", "tab", 1.1, 3, "V", "slow", 40),
    ("Prednisone 10 mg tab", "tab", 1.6, 3, "E", "slow", 60),
    ("Methylprednisolone 4 mg tab", "tab", 9.0, 3, "E", "slow", 4),
    ("Azithromycin 500 mg tab", "tab", 28.0, 3, "V", "slow", 36),
    ("Ciprofloxacin 500 mg tab", "tab", 7.5, 3, "E", "slow", 45),
    ("Metronidazole 500 mg tab", "tab", 2.4, 2, "E", "slow", 55),
    ("Furosemide 40 mg tab", "tab", 1.0, 3, "V", "slow", 50),
    ("Captopril 25 mg tab", "tab", 1.4, 3, "E", "slow", 65),
    ("Glibenclamide 5 mg tab", "tab", 1.2, 3, "E", "slow", 48),
    ("Diazepam 5 mg tab", "tab", 3.2, 4, "E", "slow", 20),
    ("Loperamide 2 mg cap", "cap", 2.8, 2, "D", "slow", 24),
    ("Ranitidine 150 mg tab", "tab", 1.9, 2, "D", "late_start", 30),
    ("Tramadol 50 mg cap", "cap", 5.0, 4, "E", "late_start", 28),
    ("Fluconazole 150 mg cap", "cap", 18.0, 3, "E", "late_start", 18),
    ("Hydrocortisone 100 mg vial", "vial", 48.0, 4, "V", "no_use", 0),
    ("Epinephrine 1 mg amp", "amp", 35.0, 4, "V", "no_use", 0),
    ("Atropine 0.6 mg amp", "amp", 22.0, 4, "V", "no_use", 0),
    ("Diclofenac 75 mg amp", "amp", 14.0, 3, "E", "no_use", 0),
    ("Dextrose 5% 500 mL bag", "bag", 62.0, 3, "V", "no_use", 0),
    ("Ceftriaxone 1 g vial", "vial", 38.0, 3, "V", "no_use", 0),
    ("Salbutamol inhaler 100 mcg", "inhaler", 210.0, 4, "V", "no_use", 0),
    ("Warfarin 5 mg tab", "tab", 4.5, 4, "E", "no_use", 0),
    ("Digoxin 0.25 mg tab", "tab", 6.0, 4, "E", "no_use", 0),
    ("Phenytoin 100 mg cap", "cap", 3.1, 4, "E", "no_use", 0),
    ("Oral rehydration salts sachet", "sachet", 8.0, 2, "V", "no_use", 0),
    ("Vitamin B complex tab", "tab", 1.7, 2, "D", "no_use", 0),
]
NO_RECORD = {"Ranitidine 150 mg tab", "Tramadol 50 mg cap", "Fluconazole 150 mg cap"}   # three items with no stock record
NEGATIVE = {"Simvastatin 40 mg tab": -35, "Prednisone 10 mg tab": -12}               # two negative balances
MIXED_UNIT = {"Multivitamins tab": "tab/box"}                                        # one item with mixed units


def _series(rng, pattern, base):
    m = np.arange(9)
    if pattern == "steady":
        y = base * (1 + 0.18 * rng.standard_normal(9))
    elif pattern == "trend_up":
        y = base * (0.7 + 0.07 * m) * (1 + 0.1 * rng.standard_normal(9))
    elif pattern == "trend_down":
        y = base * (1.3 - 0.07 * m) * (1 + 0.1 * rng.standard_normal(9))
    elif pattern == "bursty_fast":
        y = base * (1 + 0.6 * rng.standard_normal(9))
    elif pattern == "slow":
        y = np.where(rng.random(9) < 0.4, base * (0.5 + rng.random(9) * 1.5), 0.0)
        y[:4] = 0.0                           # exactly one or two months of use in Jan to Apr
        for k in rng.choice(4, size=int(rng.integers(1, 3)), replace=False):
            y[k] = base * (0.6 + rng.random())
    elif pattern == "late_start":
        y = np.where(m >= 4, np.where(rng.random(9) < 0.7, base * (0.5 + rng.random(9)), 0.0), 0.0)
    else:  # no_use
        y = np.zeros(9)
        if rng.random() < 0.3:
            y[rng.integers(6, 9)] = rng.integers(1, 4)
    return np.maximum(0, np.round(y)).astype(int)


def make_data(seed=42):
    """Returns recovered (true) monthly issuance, raw visible sheets, stock records, batches."""
    rng = np.random.default_rng(seed)
    rows, meta = [], []
    for name, unit, cost, lead, ved, pat, base in ITEMS:
        y = _series(rng, pat, base)
        rows.append([name] + list(y))
        meta.append([name, MIXED_UNIT.get(name, unit), cost, lead, ved])
    recovered = pd.DataFrame(rows, columns=["Item"] + config.MONTHS)
    items = pd.DataFrame(meta, columns=["Item", "Unit", "UnitCost", "LeadMonths", "VED"])

    # Raw visible sheets: April and September were copied from the previous month.
    raw = recovered.copy()
    raw["Apr"] = raw["Mar"]
    raw["Sep"] = raw["Aug"]
    for m in ["Oct", "Nov", "Dec"]:
        raw[m] = np.nan

    # Batches on hand at the end of September.
    today = config.DEMO_DATE
    fcast_guess = recovered[config.MONTHS[-6:]].mean(axis=1).to_dict()
    batches = []
    bno = 1
    for i, row in items.iterrows():
        name = row["Item"]
        if name in NO_RECORD:
            continue
        monthly = max(1.0, recovered.loc[i, config.MONTHS[-6:]].mean())
        nb = int(rng.integers(1, 4))
        for k in range(nb):
            if k == 0:
                exp = today + timedelta(days=int(rng.integers(100, 400)))
            else:
                exp = today + timedelta(days=int(rng.integers(180, 700)))
            qty = int(max(5, round(monthly * rng.uniform(0.8, 4.0))))
            batches.append([name, f"B{bno:04d}", exp.isoformat(), qty, row["UnitCost"]])
            bno += 1
    b = pd.DataFrame(batches, columns=["Item", "Batch", "Expiry", "Qty", "UnitCost"])

    # Force the expiry story: 19 batches expiring Oct to Dec 2026, two already expired.
    cand = b[b["Batch"].str.endswith(tuple("0123456789"))].index.tolist()
    active = [i for i in b.index if recovered.loc[recovered["Item"] == b.loc[i, "Item"], config.MONTHS[-6:]].values.mean() > 1]
    rng2 = np.random.default_rng(7)
    pick = list(rng2.choice(active, size=min(19, len(active)), replace=False))
    for n, i in enumerate(pick):
        d = [date(2026, 10, 12), date(2026, 10, 28), date(2026, 11, 15), date(2026, 11, 30), date(2026, 12, 14), date(2026, 12, 29)][n % 6]
        b.loc[i, "Expiry"] = d.isoformat()
        monthly = max(1.0, recovered.loc[recovered["Item"] == b.loc[i, "Item"], config.MONTHS[-6:]].values.mean())
        months_left = (d - today).days / 30.4
        # about half of them have more stock than will be used before expiry
        b.loc[i, "Qty"] = int(round(monthly * (months_left * (1.9 if n % 2 == 0 else 0.6)) + 5))
    expired = [i for i in b.index if i not in pick][:2]
    for i in expired:
        b.loc[i, "Expiry"] = date(2026, 9, 18 - 5 * (i % 2)).isoformat()
        b.loc[i, "Qty"] = max(10, int(b.loc[i, "Qty"] // 2))

    # Stock records (end-of-September balance as recorded).
    bal = b.groupby("Item")["Qty"].sum()
    rec = []
    for name in items["Item"]:
        if name in NO_RECORD:
            continue
        v = int(bal.get(name, 0))
        v = NEGATIVE.get(name, v)
        rec.append([name, v])
    stock_records = pd.DataFrame(rec, columns=["Item", "Balance"])
    return recovered, raw, items, stock_records, b
