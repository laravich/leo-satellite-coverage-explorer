from pathlib import Path

DATA_PATH = Path("../data/oneweb_satellites.csv")
DATA_URL = "https://celestrak.org/NORAD/elements/gp.php?GROUP=ONEWEB&FORMAT=CSV"
FALLBACK_DATA_URL = "https://raw.githubusercontent.com/satvisorcom/satvisor-data/master/celestrak/json/oneweb.json"