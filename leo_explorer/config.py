from pathlib import Path

DATA_PATH = Path("../data/oneweb_satellites.csv")
DATA_URL = "https://celestrak.org/NORAD/elements/gp.php?GROUP=ONEWEB&FORMAT=CSV"
FALLBACK_DATA_URL = "https://raw.githubusercontent.com/satvisorcom/satvisor-data/master/celestrak/json/oneweb.json"

DATA_CACHE_SECONDS = 6 * 60 * 60 #6 hours cache the data downloaded
POSITION_CACHE_SECONDS = 60
C_KM_PER_SECOND = 299_792.458 #speed of light

NUMERIC_COLUMNS = [
    "INCLINATION",
    "ECCENTRICITY",
    "MEAN_MOTION",
    "RA_OF_ASC_NODE",
    "ARG_OF_PERICENTER",
    "MEAN_ANOMALY",
    "BSTAR",
]

POSITION_COLUMNS = [
    "satellite_name",
    "norad_id",
    "latitude",
    "longitude",
    "altitude_km",
    "inclination",
    "mean_motion",
]

VISIBLE_COLUMNS = [
    "satellite_name",
    "norad_id",
    "elevation_deg",
    "azimuth_deg",
    "distance_km",
    "delay_ms",
    "satellite_latitude",
    "satellite_longitude",
    "satellite_altitude_km",
]

# Ready-to-use ground locations for the coverage analysis.
CITY_COORDINATES = {
    "Nuremberg, Germany": (49.4521, 11.0767),
    "Munich, Germany": (48.1351, 11.5820),
    "Zürich, Switzerland": (47.3769, 8.5417),
    "Bangalore, India": (12.9716, 77.5946),
    "New York, USA": (40.7128, -74.0060),
    "Sydney, Australia": (-33.8688, 151.2093),
}
