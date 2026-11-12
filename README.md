# PharmCast

Demand forecasting, stock-and-order suggestions and expiry watch for a hospital pharmacy.
A small offline Streamlit app. **All data in this repository is fictional.**

> Built by the author with AI coding assistance. The logic was reviewed and tested by the author.
> This is a pilot/demo tool, not a validated clinical or procurement system. Cut-offs in `config.py` are demo defaults.

## Run it
```
pip install -r requirements.txt
streamlit run app.py
```
Works offline after the one-time install. Telemetry is off (`.streamlit/config.toml`).
Press "Load fictional sample data" on screen 1 first. Run `python tests.py` to check the code.

## Screens
1 Data check, 2 Forecast, 3 Stock and order, 4 Expiry watch, 5 Receive delivery, 6 About and limits.

## What it does
- Compares seven forecasting methods per item with rolling one-month-ahead backtests: four plain-arithmetic methods (repeat last month, 3-month average, exponential smoothing, Croston/SBA) and three scikit-learn models (linear regression, random forest, gradient boosting).
- Suggests an order: forecast over lead time + review period + safety stock, minus usable stock.
- Expiry watch is rule-based (not machine learning): it flags batches likely to expire unused.
- Settings and flag cut-offs are in `config.py`.

## Using your own Excel file
Screen 1 > Data source > "My own Excel file".
- **Monthly report (one sheet per month):** reads every visible month sheet, can recover copied months from hidden "Copy of ORIGINAL" sheets (`hidden_sheets.py`), and reads expiry dates from the latest hidden sheet that has them.
- **Other layout:** pick the columns yourself.

Your file is read on your computer only. Loaded batches are saved to `pharmcast.db` in this folder (git-ignored). Delete it when you are done and never share it.

## Templates (`templates/`)
`PharmCast_Monthly_Template_BLANK.xlsx` is the empty monthly form; `PharmCast_Monthly_Template_SAMPLE_fictional.xlsx` shows it filled with fictional data.

## Data and privacy
Do not commit real inventory, patient or personnel data. `.gitignore` blocks `*.db`, `.env` and `*_REAL*.xlsx`.

## Limitations
Short histories cannot confirm seasonality; past stockouts are not recorded; the expiry watch is a rule, not a trained model; results depend on data quality.
