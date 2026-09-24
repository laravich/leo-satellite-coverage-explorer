"""Interactive OneWeb satellite position and ground-coverage explorer."""

from pathlib import Path
import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from skyfield.api import EarthSatellite, load, wgs84
#for live data
from io import StringIO
import requests
from datetime import timedelta
from leo_explorer.config import (DATA_PATH, DATA_URL, FALLBACK_DATA_URL, DATA_CACHE_SECONDS, POSITION_CACHE_SECONDS, C_KM_PER_SECOND, NUMERIC_COLUMNS, POSITION_COLUMNS, VISIBLE_COLUMNS, CITY_COORDINATES)
from leo_explorer.hybrid import HybridRouteSimulator
from leo_explorer.satellites import SatelliteService
from leo_explorer.coverage import CoverageService
from leo_explorer.settings import get_location_settings
from leo_explorer.plots import PlotFactory
from leo_explorer.views.overview import render_overview
from leo_explorer.views.positions import render_positions
from leo_explorer.views.ground import render_ground
from leo_explorer.views.route import render_route
from leo_explorer.dashboard import main  # noqa: E402


# -----------------------------------------------------------------------------
# App configuration and constants
# -----------------------------------------------------------------------------

# This must be the first Streamlit command in the script.
st.set_page_config(page_title="LEO Satellite Explorer", page_icon="\U0001F6F0", layout="wide")

if __name__ == "__main__":
    main()