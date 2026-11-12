"""Local SQLite storage. Records are voided, never deleted."""
import sqlite3
from datetime import datetime
import pandas as pd
import config


def conn():
    c = sqlite3.connect(config.DB_PATH)
    c.row_factory = sqlite3.Row
    return c


def init():
    with conn() as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS accepted_months (month TEXT PRIMARY KEY, accepted_at TEXT, role TEXT);
        CREATE TABLE IF NOT EXISTS batches (id INTEGER PRIMARY KEY AUTOINCREMENT, item TEXT, batch TEXT, expiry TEXT,
            qty INTEGER, unit_cost REAL, source TEXT, void INTEGER DEFAULT 0);
        CREATE TABLE IF NOT EXISTS audit_log (id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT, role TEXT, action TEXT, detail TEXT);
        """)


def log(role, action, detail=""):
    with conn() as c:
        c.execute("INSERT INTO audit_log (ts, role, action, detail) VALUES (?,?,?,?)",
                  (datetime.now().strftime("%Y-%m-%d %H:%M"), role, action, detail))


def reset_batches(df):
    """Load the fictional batches (demo only)."""
    with conn() as c:
        c.execute("DELETE FROM batches")
        for r in df.itertuples():
            c.execute("INSERT INTO batches (item,batch,expiry,qty,unit_cost,source) VALUES (?,?,?,?,?,?)",
                      (r.Item, r.Batch, r.Expiry, int(r.Qty), float(r.UnitCost), "sample"))


def batches():
    with conn() as c:
        df = pd.read_sql_query("SELECT item AS Item, batch AS Batch, expiry AS Expiry, qty AS Qty, unit_cost AS UnitCost, source AS Source "
                               "FROM batches WHERE void=0", c)
    return df


def add_delivery(role, item, batch, expiry, qty, unit_cost):
    with conn() as c:
        c.execute("INSERT INTO batches (item,batch,expiry,qty,unit_cost,source) VALUES (?,?,?,?,?,?)",
                  (item, batch, expiry, int(qty), float(unit_cost), "delivery"))
    log(role, "RECEIVE DELIVERY", f"{item} | {batch} | exp {expiry} | qty {qty}")


def accept_months(role, months):
    with conn() as c:
        for m in months:
            c.execute("INSERT OR REPLACE INTO accepted_months VALUES (?,?,?)", (m, datetime.now().strftime("%Y-%m-%d %H:%M"), role))
    log(role, "ACCEPT MONTHS", ", ".join(months))


def accepted():
    with conn() as c:
        return [r["month"] for r in c.execute("SELECT month FROM accepted_months ORDER BY rowid")]


def audit(n=15):
    with conn() as c:
        return pd.read_sql_query("SELECT ts AS When_, role AS Role, action AS Action, detail AS Detail FROM audit_log ORDER BY id DESC LIMIT ?", c, params=(n,))
