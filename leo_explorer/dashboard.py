import requests
import streamlit as st

from .config import DATA_PATH, DATA_URL
from .satellites import SatelliteService
from .settings import get_location_settings
from .views.overview import render_overview
from .views.positions import render_positions
from .views.ground import render_ground
from .views.route import render_route

def main():
    """Load the data, calculate one snapshot and render the application."""

    st.title("🛰️ LEO Satellite Coverage Explorer")
    st.write(
        "Explore the OneWeb constellation using CelesTrak orbital data. "
        "The app shows current positions and instantaneous geometric visibility "
        "from a selected ground location."
    )

    # Loading data
    try:
        (oneweb_df, satellite_entries, timescale, load_errors, data_source) = SatelliteService.load_satellite_data(str(DATA_PATH), DATA_URL)

    except requests.RequestException as error:
        st.error(
            "The local CSV was not found and the orbital data "
            f"could not be downloaded from CelesTrak: {error}"
        )
        st.stop()

    # Show which source the app used
    st.caption(f"Data source: {data_source}")

    location_name, ground_latitude, ground_longitude, minimum_elevation = (
        get_location_settings()
    )

    # Refresh time-dependent positions without reloading the dataset
    if st.sidebar.button("🔄 Update satellite positions"):
        SatelliteService.calculate_snapshot.clear()
        st.rerun()

    position_df, visible_df, calculation_time, calculation_errors = (
        SatelliteService.calculate_snapshot(
            satellite_entries,
            timescale,
            ground_latitude,
            ground_longitude,
            minimum_elevation,
        )
    )
    # -------------------------------------------------------------------------
    # Dataset overview
    # -------------------------------------------------------------------------

    render_overview(oneweb_df, satellite_entries, position_df, load_errors, calculation_errors)
    # -------------------------------------------------------------------------
    # Global satellite positions
    # -------------------------------------------------------------------------
    render_positions(position_df, calculation_time)

    # -------------------------------------------------------------------------
    # Ground coverage analysis
    # -------------------------------------------------------------------------

    render_ground(visible_df, location_name, ground_latitude, ground_longitude, minimum_elevation)

    # -------------------------------------------------------------------------
    # First hybrid-network step: show an illustrative route and gNB sites.
    # -------------------------------------------------------------------------
    render_route(satellite_entries, timescale, minimum_elevation)
