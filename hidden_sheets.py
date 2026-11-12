import openpyxl, re, pandas as pd, numpy as np, sys
def num(v):
    if v is None: return np.nan
    if isinstance(v,(int,float)): return float(v)
    s=str(v).strip().replace(',','')
    try: return float(s)
    except: return np.nan
def clean(s): return re.sub(r"\s+"," ",str(s)).strip().upper()
MON=['JAN','FEB','MAR','APR','MAY','JUN','JUL','AUG','SEP','OCT','NOV','DEC']
def load_weekly(path):
    wb=openpyxl.load_workbook(path,data_only=True)
    rows=[];info=[];monthly=[]
    for ws in wb:
        if not ws.title.upper().startswith('COPY OF ORIGINAL'): continue
        m=[i for i,x in enumerate(MON) if x in ws.title.upper()][0]+1
        # header row
        hr=None
        for r in range(1,8):
            if str(ws.cell(r,1).value).strip().upper()=='MEDICINES': hr=r;break
        if hr is None: continue
        hdr={clean(ws.cell(hr,c).value):c for c in range(1,ws.max_column+1) if ws.cell(hr,c).value}
        wk=[c for h,c in hdr.items() if h.startswith('CONSUMPTION') and 'WEEK' in h]
        cc=[c for h,c in hdr.items() if h=='CONSUMPTION'][0]
        ex=[c for h,c in hdr.items() if h=='EXPIRY']
        oh=[c for h,c in hdr.items() if h=='QUANTITY ON HAND']
        pv=[c for h,c in hdr.items() if h.startswith('PREVIOUS BALANCE')]
        rc=[c for h,c in hdr.items() if h in ('QTY RECEIVED TOTAL','QUANTITY RECEIVED')]
        seen=set(); recs=[]
        for r in range(hr+1,ws.max_row+1):
            nm=ws.cell(r,1).value
            if not isinstance(nm,str) or not nm.strip(): continue
            nm=clean(nm)
            if nm in seen or nm.startswith('TOTAL'): continue
            seen.add(nm)
            w=[num(ws.cell(r,c).value) for c in wk]
            recs.append((nm,num(ws.cell(r,cc).value),w,ws.cell(r,ex[0]).value if ex else None,num(ws.cell(r,oh[0]).value) if oh else np.nan,num(ws.cell(r,pv[0]).value) if pv else np.nan,num(ws.cell(r,rc[0]).value) if rc else np.nan))
        for nm,cons,w,e,o,pb,rv in recs: monthly.append((m,nm,cons,e,o,pb,rv))
        if not wk:
            info.append((ws.title,m,len(recs),0,None)); continue
        W=np.array([x[2] for x in recs]) if recs else np.zeros((0,5))
        present=[j for j in range(W.shape[1]) if np.isfinite(W[:,j]).any()]
        nweeks=max(present)+1 if present else 0
        agree=np.mean([np.nansum(x[2])==(x[1] if np.isfinite(x[1]) else 0) for x in recs]) if recs else np.nan
        info.append((ws.title,m,len(recs),nweeks,round(float(agree),3)))
        for nm,cons,w,e,o,pb,rv in recs:
            for j in range(nweeks):
                rows.append((m,j+1,nm,0.0 if np.isnan(w[j]) else w[j],cons,e))
    df=pd.DataFrame(rows,columns=['month','week','item','cons_w','cons_month','expiry'])
    mo=pd.DataFrame(monthly,columns=['month','item','cons','expiry','onhand','prev','recv'])
    return df,pd.DataFrame(info,columns=['sheet','month','items','weeks','weeks_sum_matches_month']),mo
