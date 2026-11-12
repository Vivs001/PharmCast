"""PharmCast demo interface (fictional data). Run: streamlit run app.py"""
import altair as alt
import numpy as np
import pandas as pd
import streamlit as st
from datetime import date

import checks, config, data_gen, db, expiry, forecast, importer, stock

st.set_page_config(page_title="PharmCast", page_icon="💊", layout="wide")
db.init()

# ---------- look ----------
st.markdown("""
<style>
.block-container {padding-top: 3.2rem; padding-bottom: 4rem; max-width: 1500px;}
.banner {background:#fff4d6; border:1px solid #e6c768; color:#6b4e00; padding:6px 12px; border-radius:6px;
         font-size:0.8rem; font-weight:700; letter-spacing:.06em; margin-bottom:10px;}
.footer {position:fixed; left:0; right:0; bottom:0; text-align:center; font-size:0.78rem; color:#555;
         background:#ffffffee; border-top:1px solid #ddd; padding:5px; z-index:99;}
.tile {background:#f3f5f8; border-radius:10px; padding:12px 16px;}
.tile .v {font-size:1.35rem; font-weight:700; color:#1a1a1a; line-height:1.15;}
.tile .l {font-size:0.8rem; color:#555;}
.note {color:#555; font-size:0.85rem;}
h1 {font-size:1.7rem !important;}
</style>
""", unsafe_allow_html=True)

CHIP = {  # background colours for status chips in tables
    "Good": "#d6f0dc", "Fair": "#fff0c2", "Low": "#fde0c8", "No expected use": "#e6e6e6",
    "Expired": "#f6c7c7", "High": "#fadbd8", "Medium": "#ffe9b3", "None": "#e3f1e6",
    "Urgent": "#f6c7c7", "Routine": "#e3f1e6", "Runs out": "#f6c7c7", "OK": "#e3f1e6",
    "No stock record": "#e6e6e6",
}


def chip(v):
    c = CHIP.get(v)
    return f"background-color: {c}; font-weight: 600;" if c else ""


def tile(col, value, label):
    col.markdown(f'<div class="tile"><div class="v">{value}</div><div class="l">{label}</div></div>', unsafe_allow_html=True)


def peso(x):
    return f"PHP {x:,.0f}"


# ---------- data and computation ----------
@st.cache_data(show_spinner="Running the forecast test...")
def load_demo():
    recovered, raw, items, stock_records, b = data_gen.make_data()
    Y = recovered[config.MONTHS].values
    res = forecast.run(Y, recovered["Item"].tolist())
    return recovered, raw, items, stock_records, b, res


def set_demo():
    recovered, raw, items, sr, b, res = load_demo()
    db.reset_batches(b)
    st.session_state["ds"] = dict(recovered=recovered, raw=raw, items=items, stock_records=sr, res=res,
                                  months=config.MONTHS, fut=config.FORECAST_MONTHS, demo=True,
                                  as_of=config.FIXED_DEMO_DATE, notes=[])
    db.log(ROLE_NOW, "LOAD SAMPLE DATA", "fictional")


ds = st.session_state.get("ds")
loaded = ds is not None
IS_DEMO = ds["demo"] if loaded else True
if loaded:
    config.DEMO_DATE = ds["as_of"]
    MONTHS = ds["months"]
    FUT = ds["fut"]
    recovered, raw, items, stock_records, res = ds["recovered"], ds["raw"], ds["items"], ds["stock_records"], ds["res"]

# ---------- sidebar ----------
st.sidebar.markdown("## 💊 PharmCast")
st.sidebar.caption("Demand forecasting and expiry watch for a hospital pharmacy")
role = st.sidebar.selectbox("Signed in as (demo role)", config.ROLES, index=0)
ROLE_NOW = role
st.sidebar.markdown(f"**{'Demo date' if IS_DEMO else 'As-of date'}:** {config.DEMO_DATE:%d %b %Y}")
PAGES = ["1. Data check", "2. Forecast", "3. Stock and order", "4. Expiry watch", "5. Receive delivery", "6. About and limits"]
page = st.sidebar.radio("Screen", PAGES, label_visibility="collapsed")
if IS_DEMO:
    st.markdown(f'<div class="banner">{config.BANNER}</div>', unsafe_allow_html=True)
    st.markdown(f'<div class="footer">{config.FOOTER}</div>', unsafe_allow_html=True)
else:
    st.markdown('<div class="banner" style="background:#e3eefc;border-color:#9bb8e6;color:#1d3e7a">ACTUAL DATA FROM YOUR FILE · KEEP ON THIS COMPUTER</div>', unsafe_allow_html=True)
    st.markdown('<div class="footer">PharmCast, demo with fictional data</div>', unsafe_allow_html=True)


def need_data():
    st.info("No data loaded yet. Go to **1. Data check** and load the fictional sample data or your own Excel file.")
    st.stop()


def finish_load(out, as_of, label):
    with st.spinner("Running the forecast test..."):
        Y = out["recovered"][out["months"]].values.astype(float)
        res_ = forecast.run(Y, out["recovered"]["Item"].tolist())
    db.reset_batches(out["batches"])
    st.session_state["ds"] = dict(recovered=out["recovered"], raw=out["raw"], items=out["items"], stock_records=out["stock_records"],
                                  res=res_, months=out["months"], fut=["+1", "+2", "+3"], demo=False, as_of=as_of, notes=out["notes"])
    db.log(ROLE_NOW, "LOAD FILE", f"{label} | {len(out['recovered'])} items | {len(out['months'])} months")
    st.rerun()


def import_ui_monthly():
    """A monthly report: one sheet per month with the same columns."""
    up = st.file_uploader("Monthly report workbook (.xlsx)", type=["xlsx", "xlsm"], key="upl_monthly",
                          help="Monthly Accomplishment Report (drugs and medicines) or Monthly Inventory and Consumption Report (supplies).")
    st.caption("Reads every visible month sheet (Jan, Feb, ...). Months with no consumption yet are skipped. Nothing leaves this computer.")
    c = st.columns(4)
    lead = c[0].number_input("Lead time for every item (months)", 0.5, 12.0, 2.0, 0.5, key="cl_ld")
    ved = c[1].selectbox("V/E/D class for every item", ["V", "E", "D"], index=1, key="cl_vd")
    as_of = c[2].date_input("As-of date (today)", value=date(2026, 10, 25), key="cl_ao")
    rec = c[3].checkbox("Recover copied months from the hidden original sheets", value=True, key="cl_rc")
    if not up:
        st.info("Choose the workbook, then press **Use this file**.")
        return
    if st.button("Use this file", type="primary", key="cl_go"):
        try:
            with st.spinner("Reading the workbook..."):
                out = importer.read_monthly_report(up, recover_copies=rec, lead=lead, ved=ved)
        except Exception as e:
            st.error(f"Could not read the workbook: {e}")
            return
        finish_load(out, as_of, up.name)


def import_ui():
    kind = st.radio("File layout", ["Monthly report (one sheet per month)", "Other layout (I choose the columns)"],
                    horizontal=True, key="layout")
    if kind.startswith("Monthly"):
        import_ui_monthly()
    else:
        import_ui_map()


def import_ui_map():
    """Upload the user's own workbook and map its columns."""
    up = st.file_uploader("Your Excel workbook (.xlsx)", type=["xlsx", "xlsm"], key="upl_map")
    if not up:
        st.info("Choose your workbook. It is read on this computer only and nothing is sent anywhere.")
        return
    try:
        xl = pd.ExcelFile(up)
    except Exception as e:
        st.error(f"Could not open the file: {e}")
        return
    st.markdown("**Step 1. Monthly consumption sheet**")
    c = st.columns(3)
    sheet = c[0].selectbox("Sheet", xl.sheet_names, key="sh1")
    hdr = c[1].number_input("Row that holds the column names", 1, 60, 1, key="hd1")
    try:
        df = importer.read_sheet(xl, sheet, int(hdr))
    except Exception as e:
        st.error(f"Could not read that sheet: {e}")
        return
    cols = list(df.columns)
    K1 = f"{sheet}_{int(hdr)}"
    st.dataframe(df.head(6).astype(str), hide_index=True, width="stretch")
    item_col = c[2].selectbox("Item (medicine) column", cols, index=cols.index(importer.guess_item(cols)), key=f"it1_{K1}")
    months = st.multiselect("Month columns, oldest first (at least 6)", cols, default=importer.guess_months(cols), key=f"mo1_{K1}")
    o = st.columns(2)
    unit_col = o[0].selectbox("Unit of measure column (optional)", [importer.NONE] + cols, key=f"un1_{K1}")
    cost_col = o[1].selectbox("Unit cost column (optional)", [importer.NONE] + cols, key=f"co1_{K1}")

    st.markdown("**Step 2. Stock, batch and expiry sheet (optional, needed for orders and expiry watch)**")
    has_stock = st.checkbox("My workbook has stock and expiry dates", value=True, key="hs")
    stock_df, smap = None, None
    if has_stock:
        s = st.columns(3)
        sheet2 = s[0].selectbox("Sheet", xl.sheet_names, index=min(1, len(xl.sheet_names) - 1), key="sh2")
        hdr2 = s[1].number_input("Row that holds the column names", 1, 60, 1, key="hd2")
        try:
            stock_df = importer.read_sheet(xl, sheet2, int(hdr2))
        except Exception as e:
            st.error(f"Could not read the stock sheet: {e}")
            return
        c2 = list(stock_df.columns)
        K2 = f"{sheet2}_{int(hdr2)}"
        st.dataframe(stock_df.head(6).astype(str), hide_index=True, width="stretch")
        g = importer.guess
        def pick(label, pat, key, optional=False):
            opts = ([importer.NONE] if optional else []) + c2
            gv = g(c2, pat)
            idx = opts.index(gv) if gv in opts else 0
            return s2.selectbox(label, opts, index=idx, key=key)
        s2 = st.columns(5)
        i_item = s2[0].selectbox("Item", c2, index=c2.index(importer.guess_item(c2)), key=f"si_{K2}")
        gv = g(c2, r"exp"); i_exp = s2[1].selectbox("Expiry date", c2, index=c2.index(gv) if gv in c2 else 0, key=f"se_{K2}")
        gv = g(c2, r"qty|quant|balance|stock|on.?hand"); i_qty = s2[2].selectbox("Quantity on hand", c2, index=c2.index(gv) if gv in c2 else 0, key=f"sq_{K2}")
        i_bat = s2[3].selectbox("Batch / lot (optional)", [importer.NONE] + c2, index=([importer.NONE] + c2).index(g(c2, r"batch|lot")), key=f"sb_{K2}")
        i_cost = s2[4].selectbox("Unit cost (optional)", [importer.NONE] + c2, index=([importer.NONE] + c2).index(g(c2, r"cost|price")), key=f"sc_{K2}")
        smap = dict(item=i_item, expiry=i_exp, qty=i_qty, batch=None if i_bat == importer.NONE else i_bat,
                    cost=None if i_cost == importer.NONE else i_cost)

    st.markdown("**Step 3. Settings the file does not have**")
    d = st.columns(3)
    lead = d[0].number_input("Lead time for every item (months)", 0.5, 12.0, 2.0, 0.5, key="ld")
    ved = d[1].selectbox("V/E/D class for every item", ["V", "E", "D"], index=1, key="vd")
    as_of = d[2].date_input("As-of date (today)", value=date(2026, 10, 25), key="ao")
    st.caption("Lead time and V/E/D apply to all items until the workbook carries them per item.")
    if st.button("Use this file", type="primary", key="go"):
        try:
            out = importer.build(df, item_col, months, None if unit_col == importer.NONE else unit_col,
                                 None if cost_col == importer.NONE else cost_col, stock_df, smap, lead, ved)
            with st.spinner("Running the forecast test..."):
                Y = out["recovered"][out["months"]].values.astype(float)
                res_ = forecast.run(Y, out["recovered"]["Item"].tolist())
        except Exception as e:
            st.error(f"Could not build the data: {e}")
            return
        db.reset_batches(out["batches"].assign(Qty=out["batches"]["Qty"]))
        fut = [f"+{k}" for k in (1, 2, 3)]
        st.session_state["ds"] = dict(recovered=out["recovered"], raw=out["raw"], items=out["items"], stock_records=out["stock_records"],
                                      res=res_, months=out["months"], fut=fut, demo=False, as_of=as_of, notes=out["notes"])
        db.log(role, "LOAD FILE", f"{up.name} | {len(out['recovered'])} items | {len(out['months'])} months")
        st.rerun()


# ======================= 1. DATA CHECK =======================
if page == PAGES[0]:
    st.title("1. Data check")
    st.caption("Choose where the data comes from. The check lists what is wrong before any month is accepted.")
    src = st.radio("Data source", ["Fictional sample data", "My own Excel file"], horizontal=True,
                   index=0 if IS_DEMO else 1, key="src")
    if src == "Fictional sample data":
        if st.button("Load fictional sample data", type="primary"):
            set_demo()
            st.rerun()
    else:
        import_ui()
    if not loaded:
        st.info("Load the fictional sample data or your own Excel file to run the data check.")
        st.stop()
    st.caption("Showing: " + ("fictional sample data" if IS_DEMO else "your file"))
    for n_ in ds["notes"]:
        st.warning(n_)
    rep = checks.report(raw, stock_records, items)
    cnt = checks.counts(rep)
    t = st.columns(5)
    tile(t[0], len(recovered), "medicines in the file")
    tile(t[1], cnt.get("Copied month", 0), "copied months")
    tile(t[2], cnt.get("Negative balance", 0), "negative balances")
    tile(t[3], cnt.get("No stock record", 0), "items with no stock record")
    tile(t[4], cnt.get("Mixed units", 0), "item with mixed units")
    st.markdown("#### Data check report")
    st.dataframe(rep, width="stretch", hide_index=True, height=370)
    st.markdown("#### Months")
    acc = db.accepted()
    mon = pd.DataFrame({"Month": MONTHS, "Status": ["Accepted" if m in acc else "Waiting for review" for m in MONTHS],
                        "Note": ["Original figures recovered from hidden sheet" if (IS_DEMO and m in ("Apr", "Sep")) else "" for m in MONTHS]})
    cols = st.columns([3, 1])
    cols[0].dataframe(mon.T, width="stretch")
    if cols[1].button("Accept months", width="stretch"):
        if role != "logistics_officer":
            cols[1].warning("Only the logistics officer can accept months.")
        else:
            db.accept_months(role, MONTHS)
            st.rerun()
    st.caption("Accepted months are saved to the local history. The audit log records who accepted them.")

# ======================= 2. FORECAST =======================
elif page == PAGES[1]:
    if not loaded: need_data()
    st.title("2. Forecast: demand per item")
    st.caption(f"Each item is forecast by the method that did best for its group in a test on {MONTHS[config.TEST_START]} to {MONTHS[-1]}.")
    it = res["items"].copy()
    f1, f2, f3 = st.columns([1, 1, 2])
    g = f1.multiselect("Group", forecast.GROUPS, default=forecast.GROUPS)
    r = f2.multiselect("Reliability", ["Good", "Fair", "Low", "No expected use"], default=["Good", "Fair", "Low", "No expected use"])
    it = it[it["Group"].isin(g) & it["Reliability"].isin(r)]
    show = pd.DataFrame({
        "Medicine": it["Item"], "Group": it["Group"], "Method": it["Method"],
        "Forecast / month": it["Forecast"].round(1),
        "Likely range": [f"{a:,.0f} to {b:,.0f}" for a, b in zip(it["Low"], it["High"])],
        "12 months": it["Months12"].round(0).astype(int), "Reliability": it["Reliability"]})
    st.dataframe(show.style.map(chip, subset=["Reliability"]).format({"Forecast / month": "{:,.1f}"}), width="stretch", hide_index=True, height=360)
    st.markdown("#### How the method was chosen: average miss (WAPE) by method and group, lower is better")
    wt = res["wape"].copy()
    wt.columns = [c if c != "No use in first 4 months" else "No use" for c in wt.columns]
    best = {("No use" if k == "No use in first 4 months" else k): v for k, v in res["winners"].items()}

    def hi(col):
        return ["background-color:#d6f0dc; font-weight:700" if (col.name in best and idx == best[col.name]) else "" for idx in col.index]
    st.dataframe((wt * 100).style.apply(hi).format("{:.1f}%", na_rep="-"), width="stretch", height=300)
    st.caption("Shaded = lowest in the group, the method used for every item in that group. Groups come from use in January to April.")

# ======================= 3. STOCK AND ORDER =======================
elif page == PAGES[2]:
    if not loaded: need_data()
    st.title("3. Stock and order")
    saf = st.sidebar.slider("Safety stock (months of forecast)", 0.0, 3.0, config.SAFETY_MONTHS, 0.5,
                            disabled=(role != "logistics_officer"),
                            help="Set by the logistics officer.")
    bt = db.batches()
    st_ = stock.stock_table(res["items"], items, bt, safety_months=saf)
    t = st.columns(4)
    tile(t[0], int((st_["Order"] > 0).sum()), "items to order")
    tile(t[1], int((st_["Priority"] == "Urgent").sum()), "Urgent")
    tile(t[2], peso(st_["OrderValue"].sum()), "total suggested value")
    tile(t[3], int((st_["Status"] == "Runs out").sum()), "items that run out before delivery")
    st.write("")
    view = pd.DataFrame({"Medicine": st_["Item"], "Usable stock": st_["Usable"], "Forecast / month": st_["Forecast"].round(1),
                         "Months of cover": st_["Cover"].round(1), "Lead time (months)": st_["LeadMonths"], "VED": st_["VED"],
                         "Status": st_["Status"], "Suggested order": st_["Order"], "Priority": st_["Priority"]})
    st.dataframe(view.style.map(chip, subset=["Status", "Priority"]).format({"Months of cover": "{:.1f}", "Forecast / month": "{:,.1f}"}, na_rep="-"),
                 width="stretch", hide_index=True, height=330)
    st.caption("Suggested order = forecast over (lead time + review period) + safety stock − usable stock, never below zero. The officer reviews every quantity.")
    st.markdown("#### Two example items")
    names = res["items"].query("Reliability in ['Good','Fair']")["Item"].tolist()
    default = [n for n in ["Amlodipine 10 mg tab", "Amoxicillin 500 mg cap"] if n in names][:2]
    cols = st.columns(2)
    Y = recovered[MONTHS].values
    if not names:
        st.warning("No item has Good or Fair reliability, so there is no example chart.")
    for k, col in enumerate(cols if names else []):
        with col:
            sel = st.selectbox(f"Item {k+1}", names, index=names.index(default[k]) if k < len(default) else min(k, len(names) - 1), key=f"ex{k}")
            i = int(res["items"].index[res["items"]["Item"] == sel][0])
            row = res["items"].loc[i]
            sr = st_[st_["Item"] == sel].iloc[0]
            m = row["Method"]
            btm = res["backtest"][res["backtest"]["item"] == i]
            hist = pd.DataFrame({"Month": MONTHS, "Value": Y[i], "Series": "Actual issuance"})
            test = pd.DataFrame({"Month": MONTHS[config.TEST_START:], "Value": btm[m].values, "Series": f"Test forecast ({m})"})
            fut = pd.DataFrame({"Month": FUT, "Value": [row["Forecast"]] * 3, "Series": "Forecast"})
            band = pd.DataFrame({"Month": FUT, "Low": [row["Low"]] * 3, "High": [row["High"]] * 3})
            order = MONTHS + FUT
            lines = alt.Chart(pd.concat([hist, test, fut])).mark_line(point=True).encode(
                x=alt.X("Month:N", sort=order, title=None), y=alt.Y("Value:Q", title="Units per month"),
                color=alt.Color("Series:N", scale=alt.Scale(domain=["Actual issuance", f"Test forecast ({m})", "Forecast"],
                                                            range=["#555555", "#e08a1e", "#2f6fd6"]), legend=alt.Legend(orient="bottom", title=None)),
                strokeDash=alt.StrokeDash("Series:N", legend=None, scale=alt.Scale(domain=["Actual issuance", f"Test forecast ({m})", "Forecast"],
                                                                                   range=[[1, 0], [4, 3], [1, 0]])))
            area = alt.Chart(band).mark_area(opacity=0.18, color="#2f6fd6").encode(x=alt.X("Month:N", sort=order), y="Low:Q", y2="High:Q")
            st.altair_chart((area + lines).properties(height=210), width="stretch")
            pj = stock.projection(float(sr["Usable"]), float(row["Forecast"]), 6)
            pdf = pd.DataFrame({"Months from now": range(7), "Stock left": pj})
            lead = float(sr["LeadMonths"])
            ln = alt.Chart(pdf).mark_line(point=True, color="#2f6fd6").encode(x=alt.X("Months from now:Q", axis=alt.Axis(tickMinStep=1)), y=alt.Y("Stock left:Q", title="Stock left (units)"))
            rule = alt.Chart(pd.DataFrame({"x": [lead]})).mark_rule(color="#c0392b", strokeDash=[5, 4]).encode(x="x:Q")
            txt = alt.Chart(pd.DataFrame({"x": [lead], "t": [f"lead time ({lead:.0f} mo)"]})).mark_text(align="left", dx=4, dy=-4, color="#c0392b", y=0).encode(x="x:Q", text="t:N")
            st.altair_chart((ln + rule + txt).properties(height=150), width="stretch")
            st.caption(f"{row['Group']} · method {m} · reliability {row['Reliability']} · cover {sr['Cover']:.1f} months · suggested order {int(sr['Order']):,} · {sr['Priority']}")

# ======================= 4. EXPIRY WATCH =======================
elif page == PAGES[3]:
    if not loaded: need_data()
    st.title("4. Expiry watch")
    st.caption("Rule-based simulation, not a trained model. Stock is used earliest expiry first at the forecast rate; what is left on the expiry date is flagged.")
    bt = db.batches()
    w = expiry.watch(bt, res["items"])
    s = expiry.summary(w)
    t = st.columns(5)
    tile(t[0], s["expiring"], "batches expiring in the next 3 months")
    tile(t[1], f'{s["items_conservative"]} / {s["items_central"]}', "items flagged (conservative / central)")
    tile(t[2], f'{s["units_conservative"]:,} / {s["units_central"]:,}', "units at risk (conservative / central)")
    tile(t[3], f'{s["value_conservative"]:,.0f} / {s["value_central"]:,.0f}', "value at risk, PHP (conservative / central)")
    tile(t[4], s["expired"], "batches already expired")
    st.write("")
    f1, f2 = st.columns([1, 3])
    fl = f1.multiselect("Flag", ["Expired", "High", "Medium", "Low", "None"], default=["Expired", "High", "Medium", "Low"])
    v = w[w["Flag"].isin(fl)]
    show = pd.DataFrame({"Medicine": v["Item"], "Batch": v["Batch"], "Expiry date": v["Expiry"].astype(str), "Days": v["DaysToExpiry"],
                         "Quantity": v["Qty"], "Left at expiry": v["Left"], "Value at risk (PHP)": v["ValueAtRisk"], "Flag": v["Flag"]})
    st.dataframe(show.style.map(chip, subset=["Flag"]).format({"Value at risk (PHP)": "{:,.0f}"}), width="stretch", hide_index=True, height=420)
    st.caption("Conservative rule: stock exceeds even the high end of expected use until expiry. Central rule: stock exceeds the central estimate. "
               "Assumes one expiry date per batch, earliest-expiry-first issuing and no later deliveries. Flag levels are the authors' pilot rules, not validated thresholds.")

# ======================= 5. RECEIVE DELIVERY =======================
elif page == PAGES[4]:
    if not loaded: need_data()
    st.title("5. Receive delivery")
    if role != "logistics_officer":
        st.markdown("""
<div style="border:1.5px dashed #999; border-radius:12px; padding:30px; text-align:center; background:#f6f6f6; margin:20px 0;">
<div style="font-size:2.6rem;">🔒</div>
<div style="font-size:1.25rem; font-weight:700;">Delivery entry is locked to the Logistics Officer</div>
<div class="note">You are signed in as <b>%s</b>. Receiving stock changes the numbers every forecast and expiry flag depends on, so it is limited to one accountable role.</div>
</div>""" % role, unsafe_allow_html=True)
    else:
        st.caption("Records new stock and expiry dates. Every entry is written to the audit log.")
        with st.form("recv", clear_on_submit=True):
            c = st.columns(3)
            item = c[0].selectbox("Medicine", items["Item"].tolist())
            batch = c[1].text_input("Batch number", value="B9001")
            exp = c[2].date_input("Expiry date", value=date(2027, 6, 30))
            c2 = st.columns(3)
            qty = c2[0].number_input("Quantity received", min_value=1, value=500, step=10)
            cost = c2[1].number_input("Unit cost (PHP)", min_value=0.0, value=float(items.set_index("Item").loc[item, "UnitCost"]) if item else 0.0)
            c2[2].write("")
            ok = st.form_submit_button("Save delivery", type="primary")
            if ok:
                db.add_delivery(role, item, batch, exp.isoformat(), qty, cost)
                st.success(f"Saved: {qty:,} × {item}, batch {batch}, expiry {exp:%d %b %Y}.")
    st.markdown("#### Audit log (latest entries)")
    st.dataframe(db.audit(8).rename(columns={"When_": "When"}), width="stretch", hide_index=True)
    st.caption("Entries are voided, never deleted. The log shows who changed what and when.")

# ======================= 6. ABOUT AND LIMITS =======================
else:
    st.title("6. About and limits")
    st.markdown("""
**What PharmCast does.** It turns a hospital pharmacy's monthly records into a per-item demand estimate, a stock projection with a suggested order, and an expiry watch. The logistics officer decides every quantity.

**Limits to state plainly**
- **Nine months of data** cannot show seasonality. The October to December forecast is one month ahead repeated flat.
- **Past stockouts and disposals were not recorded**, so unmet demand is understated and expiry risk cannot be validated.
- **Expiry risk is a rule-based simulation**, not a trained model. Flag levels are the authors' pilot rules.
- **Supplies were harder to predict than medicines.** No method clearly beat simple averages on the total.
- **The comparison with current practice is a proxy**, not the unit's actual programmed list.

**Safeguards.** Runs on one local computer with no outside calls and no AI service. Telemetry is off. Delivery entry is locked to one role. Records are voided, never deleted. Demonstrations use fictional data only.
""")
