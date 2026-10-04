import requests
import streamlit as st
import pandas as pd
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
        [*CONSTELLATIONS, "All constellations"],
    )

    if constellation_name == "All constellations":
        selected_names = list(CONSTELLATIONS)
    else:
        selected_names = [constellation_name]

    orbital_frames = []
    satellite_entries = []
    load_errors = []
    data_sources = []

    with st.spinner("Loading satellite orbital data..."):
        for name in selected_names:
            constellation = CONSTELLATIONS[name]
            group = constellation["group"]
            local_path = constellation["local_path"]

            base_url = (
                "https://celestrak.org/NORAD/elements/gp.php"
                f"?GROUP={group}"
            )

            try:
                (
                    frame,
                    entries,
                    loaded_timescale,
                    errors,
                    source,
                ) = SatelliteService.load_satellite_data(
                    str(local_path),
                    f"{base_url}&FORMAT=CSV",
                    f"{base_url}&FORMAT=JSON",
                )

            except (requests.RequestException, ValueError) as error:
                st.error(f"Could not load {name} orbital data: {error}")
                st.stop()

            # Copy before adding a column to the cached dataframe.
            frame = frame.copy()
            frame["constellation"] = name

            orbital_frames.append(frame)
            satellite_entries.extend(entries)
            load_errors.extend(
                f"{name}: {error}" for error in errors
            )
            data_sources.append(f"{name}: {source}")

            # All datasets use the same time system.
            timescale = loaded_timescale

    orbital_df = pd.concat(
        orbital_frames,
        ignore_index=True,
    )

    # Avoid counting a satellite twice if datasets overlap.
    orbital_df = orbital_df.drop_duplicates(
        subset="NORAD_CAT_ID",
    ).reset_index(drop=True)

    satellite_entries = list({
        str(entry["norad_id"]): entry
        for entry in satellite_entries
    }.values())

    st.caption(f"Selection: {constellation_name}")

    with st.expander("Data sources"):
        for source in data_sources:
            st.write(source)

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
    render_route(satellite_entries, timescale, minimum_elevation, constellation_name)
