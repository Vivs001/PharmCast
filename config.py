"""All settings and cut-offs for PharmCast in one place.

Everything here is a pilot rule chosen by the authors. None of these cut-offs
is a validated statistical threshold. Change them here and the whole app follows.
"""
from datetime import date

APP_NAME = "PharmCast"
FOOTER = "PharmCast, demo with fictional data"
BANNER = "FICTIONAL DEMONSTRATION DATA"
DB_PATH = "pharmcast.db"

# Fixed demo date so screenshots are always the same.
FIXED_DEMO_DATE = date(2026, 10, 1)
DEMO_DATE = FIXED_DEMO_DATE      # the app changes this to the as-of date when a real file is loaded

MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep"]
GROUP_MONTHS = 4                 # Jan to Apr decide the group
TEST_START = 4                   # May is the first test month (index 4)
FORECAST_MONTHS = ["Oct", "Nov", "Dec"]

# Stock and order
SAFETY_MONTHS = 1.0              # safety stock, in months of forecast (officer's setting)
REVIEW_MONTHS = 1.0              # review period added to lead time
HIGH_COVER_MONTHS = 6.0          # more than this many months of cover = "High"

# Reliability rule (see README)
GOOD_MIN_MONTHS_USED = 6
FAIR_MIN_MONTHS_USED = 4
NO_USE_FORECAST = 0.5

# Expiry flag cut-offs: the authors' pilot rules, not validated.
# DEFAULTS FOR THE DEMO. Replace with the real tool's values.
HIGH_SHARE = 0.50                # at least this share of the batch left at expiry...
HIGH_DAYS = 90                   # ...and expiry within this many days
MEDIUM_SHARE = 0.20
MEDIUM_DAYS = 180

ROLES = ["logistics_officer", "pharmacist", "pharmacy_staff"]
