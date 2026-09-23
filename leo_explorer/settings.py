import streamlit as st

from .config import CITY_COORDINATES


# -----------------------------------------------------------------------------
# Sidebar controls
# -----------------------------------------------------------------------------

def get_location_settings():
    """Display location controls and return the user's coverage settings."""

    st.sidebar.header("Coverage settings")
    method = st.sidebar.radio(
        "Choose ground location",
        ["Select a city", "Enter custom coordinates"],
    )

    if method == "Select a city":
        location_name = st.sidebar.selectbox(
            "Select a city", list(CITY_COORDINATES)
        )
        latitude, longitude = CITY_COORDINATES[location_name]
    else:
        location_name = "Custom location"
        latitude = st.sidebar.number_input(
            "Latitude",
            min_value=-90.0,
            max_value=90.0,
            value=49.4521,
            step=0.0001,
            format="%.4f",
        )
        longitude = st.sidebar.number_input(
            "Longitude",
            min_value=-180.0,
            max_value=180.0,
            value=11.0767,
            step=0.0001,
            format="%.4f",
        )

    minimum_elevation = st.sidebar.slider(
        "Minimum elevation angle",
        min_value=0,
        max_value=60,
        value=25,
        step=5,
        help=(
            "Only satellites at or above this angle from the local horizon "
            "are counted as visible."
        ),
    )

    return location_name, latitude, longitude, minimum_elevation