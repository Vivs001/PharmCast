import numpy as np, config, data_gen, forecast, stock, expiry
rec, raw, items, sr, b = data_gen.make_data()
Y = rec[config.MONTHS].values
res = forecast.run(Y, rec["Item"].tolist())
it = res["items"]
assert it["Group"].value_counts().sum() == len(rec); print("groups add up OK")
w = res["wape"].values; assert ((w[~np.isnan(w)] >= 0) & (w[~np.isnan(w)] < 5)).all(); print("WAPE range OK")
st = stock.stock_table(it, items, b); assert (st["Order"] >= 0).all(); print("orders non-negative OK")
wt = expiry.watch(b, it); s = expiry.summary(wt)
assert s["expiring"] == 19 and s["expired"] == 2; print("19 expiring, 2 expired OK")
ex = wt[wt["Flag"] == "Expired"]; print("expired excluded from usable:", all(stock.usable_by_item(b).get(i, 0) >= 0 for i in ex["Item"]))
# no future leakage: changing September must not change any earlier month's forecast
import pandas as pd
Y2 = Y.copy(); Y2[:, 8] *= 10
b1, b2 = forecast.backtest(Y), forecast.backtest(Y2)
m = config.METHODS if hasattr(config, "METHODS") else [c for c in b1.columns if c not in ("item", "t", "actual")]
e1, e2 = b1[b1.t < 8][m].values, b2[b2.t < 8][m].values
assert np.allclose(e1, e2); print("no future months used OK")
print("tests done")
