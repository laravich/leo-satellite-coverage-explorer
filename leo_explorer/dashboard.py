import requests
import streamlit as st

from .config import CONSTELLATIONS
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
        "Explore different LEO constellations using CelesTrak orbital data. "
        "The app shows current positions and geometric visibility "
        "from a selected ground location."
    )

    constellation_name = st.sidebar.selectbox(
        "Satellite constellation",
        list(CONSTELLATIONS),
    )

    constellation = CONSTELLATIONS[constellation_name]
    group = constellation["group"]
    local_path = constellation["local_path"]

    base_url = (
        "https://celestrak.org/NORAD/elements/gp.php"
        f"?GROUP={group}"
    )
    data_url = f"{base_url}&FORMAT=CSV"
    fallback_url = f"{base_url}&FORMAT=JSON"

    try:
        (
            orbital_df,
            satellite_entries,
            timescale,
            load_errors,
            data_source,
        ) = SatelliteService.load_satellite_data(
            str(local_path),
            data_url,
            fallback_url,
        )

    except (requests.RequestException, ValueError) as error:
        st.error(
            f"Could not load {constellation_name} orbital data: {error}"
        )
        st.stop()

    st.caption(
        f"Constellation: {constellation_name} · Data source: {data_source}"
    )

    dataset_key = (
        constellation_name,
        tuple(
            zip(
                orbital_df["NORAD_CAT_ID"].astype(str),
                orbital_df["EPOCH"].astype(str),
            )
        ),
    )

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
            dataset_key,
        )
    )
    # -------------------------------------------------------------------------
    # Dataset overview
    # -------------------------------------------------------------------------

    render_overview(orbital_df, satellite_entries, position_df, load_errors, calculation_errors)
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
