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


# -----------------------------------------------------------------------------
# App configuration and constants
# -----------------------------------------------------------------------------

# This must be the first Streamlit command in the script.
st.set_page_config(
    page_title="LEO Satellite Explorer",
    page_icon="\U0001F6F0",
    layout="wide",
)

from leo_explorer.config import (
    DATA_PATH,
    DATA_URL,
    FALLBACK_DATA_URL,
    DATA_CACHE_SECONDS,
    POSITION_CACHE_SECONDS,
    C_KM_PER_SECOND,
    NUMERIC_COLUMNS,
    POSITION_COLUMNS,
    VISIBLE_COLUMNS,
    CITY_COORDINATES
)

from leo_explorer.hybrid import HybridRouteSimulator



# -----------------------------------------------------------------------------
# Data preparation
# -----------------------------------------------------------------------------
from leo_explorer.satellites import SatelliteService


# -----------------------------------------------------------------------------
# Coverage calculation
# -----------------------------------------------------------------------------
from leo_explorer.coverage import CoverageService

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


# -----------------------------------------------------------------------------
# Map-building functions
# -----------------------------------------------------------------------------
from leo_explorer.plots import PlotFactory


# -----------------------------------------------------------------------------
# Main application
# -----------------------------------------------------------------------------

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

    st.header("Dataset overview")
    st.caption(
        "These metrics describe the orbital records in the local CelesTrak file."
    )

    overview_col1, overview_col2, overview_col3 = st.columns(3)

    overview_col1.metric(
        "Satellites",
        len(satellite_entries),
    )

    overview_col2.metric(
        "Average inclination",
        f"{oneweb_df['INCLINATION'].mean():.2f}°",
    )

    overview_col3.metric(
        "Average orbits per day",
        f"{oneweb_df['MEAN_MOTION'].mean():.2f}",
    )

    # Keep large diagnostic tables available without crowding the dashboard
    with st.expander("Inspect the data"):
        dataset_tab, position_tab = st.tabs(
            ["Orbital dataset", "Calculated positions"]
        )

        dataset_tab.dataframe(
            oneweb_df,
            use_container_width=True,
        )

        position_tab.dataframe(
            position_df,
            use_container_width=True,
        )

        all_errors = load_errors + calculation_errors

        if all_errors:
            st.warning(
                f"{len(all_errors)} satellite record(s) "
                "could not be processed."
            )

            st.code("\n".join(all_errors[:20]))

    chart_col1, chart_col2 = st.columns(2)

    with chart_col1:
        st.subheader("Orbital inclination distribution")

        st.caption(
            "Shows how the orbital planes are tilted relative to the equator."
        )

        inclination_figure = px.histogram(
            oneweb_df,
            x="INCLINATION",
            nbins=30,
            labels={
                "INCLINATION": "Inclination (degrees)"
            },
            color_discrete_sequence=["#1F77B4"],
        )

        inclination_figure.update_layout(
            yaxis_title="Number of satellites"
        )

        st.plotly_chart(
            inclination_figure,
            use_container_width=True,
        )

    with chart_col2:
        st.subheader("Inclination and mean motion")

        st.caption(
            "Compares orbital tilt with completed orbits per day."
        )

        orbit_figure = px.scatter(
            oneweb_df,
            x="INCLINATION",
            y="MEAN_MOTION",
            hover_name="OBJECT_NAME",
            labels={
                "INCLINATION": "Inclination (degrees)",
                "MEAN_MOTION": "Orbits per day",
            },
        )

        st.plotly_chart(
            orbit_figure,
            use_container_width=True,
        )

    # -------------------------------------------------------------------------
    # Global satellite positions
    # -------------------------------------------------------------------------

    st.header("🌍 Current satellite positions")

    st.caption(
        f"Calculated at {calculation_time}. Each marker is the point on Earth "
        "directly below a satellite, not its full coverage footprint."
    )

    st.plotly_chart(
        PlotFactory.build_world_position_map(position_df),
        use_container_width=True,
    )

    #3D Map
    st.subheader("🌐 3D satellite globe")

    st.caption(
        "Satellites are displayed at their calculated altitude above Earth. "
        "Drag to rotate the globe and scroll to zoom."
    )

    satellite_globe = PlotFactory.build_3d_satellite_globe(position_df)

    st.plotly_chart(
        satellite_globe,
        use_container_width=True,
    )

    # -------------------------------------------------------------------------
    # Ground coverage analysis
    # -------------------------------------------------------------------------

    st.header("📡 Ground coverage analysis")

    st.write(
        f"Location: **{location_name}** "
        f"({ground_latitude:.4f}°, {ground_longitude:.4f}°)"
    )

    st.caption(
        f"Satellites must be at least {minimum_elevation}° above the horizon. "
        "This is geometric visibility, not guaranteed commercial service."
    )

    number_visible = len(visible_df)

    if number_visible:
        best_elevation = visible_df["elevation_deg"].max()

        nearest_row = visible_df.loc[
            visible_df["distance_km"].idxmin()
        ]

        nearest_distance = nearest_row["distance_km"]
        nearest_delay = nearest_row["delay_ms"]

        st.success(
            f"This location currently has geometric coverage from "
            f"{number_visible} satellite(s)."
        )

    else:
        best_elevation = None
        nearest_distance = None
        nearest_delay = None

        st.warning(
            "No satellite currently meets the selected elevation angle."
        )

    metric_col1, metric_col2, metric_col3, metric_col4 = st.columns(4)

    metric_col1.metric(
        "Visible satellites",
        number_visible,
    )

    metric_col2.metric(
        "Best elevation",
        (
            f"{best_elevation:.1f}°"
            if best_elevation is not None
            else "N/A"
        ),
    )

    metric_col3.metric(
        "Nearest satellite",
        (
            f"{nearest_distance:,.0f} km"
            if nearest_distance is not None
            else "N/A"
        ),
    )

    metric_col4.metric(
        "One-way space delay",
        (
            f"{nearest_delay:.2f} ms"
            if nearest_delay is not None
            else "N/A"
        ),
    )

    # -------------------------------------------------------------------------
    # Current coverage map
    # -------------------------------------------------------------------------

    st.subheader("Current coverage map")

    st.caption(
        "Coloured markers meet the selected elevation threshold; the red star "
        "is the ground location."
    )

    st.plotly_chart(
        PlotFactory.build_coverage_map(
            visible_df,
            location_name,
            ground_latitude,
            ground_longitude,
        ),
        use_container_width=True,
    )

    # -------------------------------------------------------------------------
    # Coverage footprint heatmap
    # -------------------------------------------------------------------------

    st.subheader("🌐 Coverage footprint heatmap")

    st.caption(
        f"This map shows the estimated ground coverage of the "
        f"{number_visible} satellites currently visible from "
        f"{location_name}. The colours represent overlapping coverage."
    )

    if not visible_df.empty:

        # Calculate how many satellites cover each global grid point
        coverage_grid_df = CoverageService.calculate_coverage_grid(
            visible_df=visible_df,
            minimum_elevation=minimum_elevation,
            grid_step=2,
        )

        # Create the Plotly geographic coverage heatmap
        coverage_heatmap = PlotFactory.build_coverage_heatmap(
            coverage_grid_df=coverage_grid_df,
            visible_df=visible_df,
            location_name=location_name,
            ground_latitude=ground_latitude,
            ground_longitude=ground_longitude,
        )

        st.plotly_chart(
            coverage_heatmap,
            use_container_width=True,
        )

    else:
        st.info(
            "The heatmap cannot be generated because no satellite "
            "meets the selected minimum elevation angle."
        )

    # -------------------------------------------------------------------------
    # Existing elevation charts and table
    # -------------------------------------------------------------------------

    if not visible_df.empty:
        details_col1, details_col2 = st.columns(2)

        with details_col1:
            st.subheader("Highest visible satellites")

            st.caption(
                "Higher elevation means farther above the local horizon."
            )

            elevation_chart_df = (
                visible_df.nlargest(15, "elevation_deg")
                .sort_values("elevation_deg")
            )

            elevation_figure = px.bar(
                elevation_chart_df,
                x="elevation_deg",
                y="satellite_name",
                orientation="h",
                color="elevation_deg",
                color_continuous_scale="Turbo",
                labels={
                    "elevation_deg": "Elevation angle (degrees)",
                    "satellite_name": "Satellite",
                },
            )

            elevation_figure.update_layout(
                coloraxis_showscale=False
            )

            st.plotly_chart(
                elevation_figure,
                use_container_width=True,
            )

        with details_col2:
            st.subheader("Elevation versus distance")

            st.caption(
                "Satellites higher in the sky generally have a "
                "shorter slant range."
            )

            distance_figure = px.scatter(
                visible_df,
                x="elevation_deg",
                y="distance_km",
                hover_name="satellite_name",
                color="elevation_deg",
                color_continuous_scale="Turbo",
                labels={
                    "elevation_deg": "Elevation angle (degrees)",
                    "distance_km": (
                        "Distance from ground station (km)"
                    ),
                },
            )

            st.plotly_chart(
                distance_figure,
                use_container_width=True,
            )

        st.subheader("Visible satellite details")

        coverage_table = visible_df[
            [
                "satellite_name",
                "norad_id",
                "elevation_deg",
                "azimuth_deg",
                "distance_km",
                "delay_ms",
            ]
        ].copy()

        coverage_table.columns = [
            "Satellite",
            "NORAD ID",
            "Elevation (°)",
            "Azimuth (°)",
            "Distance (km)",
            "One-way delay (ms)",
        ]

        coverage_table = coverage_table.round(
            {
                "Elevation (°)": 2,
                "Azimuth (°)": 2,
                "Distance (km)": 1,
                "One-way delay (ms)": 2,
            }
        )

        st.dataframe(
            coverage_table,
            use_container_width=True,
            hide_index=True,
        )

    # -------------------------------------------------------------------------
    # First hybrid-network step: show an illustrative route and gNB sites.
    # -------------------------------------------------------------------------
    st.header("🚗 Terrestrial–satellite experiment")
    st.caption(
        "Illustrative straight-line route and example gNB locations. "
        "No radio coverage or satellite handovers are calculated yet."
    )
    route_df, gnb_df = HybridRouteSimulator.example_hybrid_route()
    route_map = go.Figure()
    route_map.add_trace(go.Scattergeo(
        lat=route_df["latitude"],
        lon=route_df["longitude"],
        mode="lines",
        line=dict(width=4, color="#2563EB"),
        name="Example route",
    ))
    route_map.add_trace(go.Scattergeo(
        lat=gnb_df["latitude"],
        lon=gnb_df["longitude"],
        text=gnb_df["site"],
        mode="markers+text",
        textposition="top center",
        marker=dict(size=12, color="#DC2626", symbol="circle"),
        name="Example gNBs",
    ))
    route_map.update_geos(
        visible=False,
        resolution=50,
        fitbounds="locations",
        showland=True,
        landcolor="#F1F5F9",
        showlakes=True,
        lakecolor="#BFDBFE",
    )
    route_map.update_layout(height=450, margin=dict(l=10, r=10, t=10, b=10))
    st.plotly_chart(route_map, use_container_width=True)
    st.dataframe(gnb_df, hide_index=True, use_container_width=True)

    # Calculate signal from all three gNBs along the vehicle route.
    all_links_df, strongest_gnb_df = HybridRouteSimulator.calculate_terrestrial_links(
        route_df, gnb_df
    )

    signal_chart = px.line(
        all_links_df,
        x="step",
        y="received_power_dbm",
        color="site",
        title="Estimated terrestrial signal along the route",
        labels={
            "step": "Route point",
            "received_power_dbm": "Estimated received power (dBm)",
        },
    )

    # Black dashed line shows the strongest available gNB.
    signal_chart.add_trace(go.Scatter(
        x=strongest_gnb_df["step"],
        y=strongest_gnb_df["received_power_dbm"],
        mode="lines",
        line=dict(color="black", width=3, dash="dash"),
        name="Strongest gNB",
    ))

    st.plotly_chart(signal_chart, use_container_width=True)

    st.caption(
        "Illustrative model: 3.5 GHz, 46 dBm EIRP and path-loss "
        "exponent 3.0. This is estimated received power, not measured RSRP."
    )

    st.dataframe(
        strongest_gnb_df.round({
            "distance_km": 2,
            "received_power_dbm": 1,
        }),
        hide_index=True,
        use_container_width=True,
    )

    # find best satellite for the ue position
    st.subheader("OneWeb visibility along the vehicle route")

    if "hybrid_experiment_start_time" not in st.session_state:
        st.session_state.hybrid_experiment_start_time = (
            timescale.now().utc_datetime()
        )

    st.caption(
        "Experiment start: "
        f"{st.session_state.hybrid_experiment_start_time:%Y-%m-%d %H:%M UTC}"
    )


    hysteresis_deg = st.slider(
        "Satellite handover margin (degrees)",
        min_value=0,
        max_value=20,
        value=5,
        step=1,
    )

    if st.button("Calculate satellite visibility along route"):
        with st.spinner("Checking OneWeb satellites along the route..."):
            satellite_route_df = HybridRouteSimulator.calculate_satellites_along_route(
                route_df,
                satellite_entries,
                timescale,
                start_time=st.session_state.hybrid_experiment_start_time,
                minimum_elevation_deg=minimum_elevation,
                hysteresis_deg=hysteresis_deg,
            )

        comparison = satellite_route_df[
            ["minutes", "highest_satellite", "satellite_name"]
        ].copy()

        # Count changes between consecutive visible satellites.
        highest_changes = (
            comparison["highest_satellite"]
            .ne(comparison["highest_satellite"].shift())
            & comparison["highest_satellite"].notna()
            & comparison["highest_satellite"].shift().notna()
        ).sum()

        hysteresis_changes = (
            comparison["satellite_name"]
            .ne(comparison["satellite_name"].shift())
            & comparison["satellite_name"].notna()
            & comparison["satellite_name"].shift().notna()
        ).sum()

        st.write(
            f"Satellite changes — highest elevation: {highest_changes}; "
            f"5° hysteresis: {hysteresis_changes}"
        )
        st.dataframe(
            comparison,
            hide_index=True,
            use_container_width=True,
        )

        st.dataframe(
            satellite_route_df.round({
                "elevation_deg": 1,
                "distance_km": 1,
            }),
            hide_index=True,
            use_container_width=True,
        )

        elevation_chart = px.line(
            satellite_route_df,
            x="minutes",
            y="elevation_deg",
            markers=True,
            title="Highest visible OneWeb satellite along the route",
            labels={
                "minutes": "Minutes into journey",
                "elevation_deg": "Elevation angle (degrees)",
            },
        )
        st.plotly_chart(elevation_chart, use_container_width=True)

        #----------------------------------------------------------
        # Keep only terrestrial results for the sampled satellite route points.
        journey_df = satellite_route_df.merge(
            strongest_gnb_df[
                ["step", "site", "received_power_dbm"]
            ],
            on="step",
            how="left",
        )

        # An illustrative threshold chosen to make coverage gaps visible.
        terrestrial_threshold_dbm = -80.0

        def choose_serving_link(row):
            if row["received_power_dbm"] >= terrestrial_threshold_dbm:
                return f"Terrestrial: {row['site']}"

            if pd.notna(row["satellite_name"]):
                return f"Satellite: {row['satellite_name']}"

            return "Outage"

        journey_df["serving_link"] = journey_df.apply(
            choose_serving_link,
            axis=1,
        )

        journey_df["network_type"] = journey_df["serving_link"].apply(
            lambda link: (
                "Outage" if link == "Outage"
                else "Satellite" if link.startswith("Satellite:")
                else "Terrestrial"
            )
        )

        # Count changes between two connected serving links.
        previous_link = journey_df["serving_link"].shift()
        handover = (
            journey_df["serving_link"].ne(previous_link)
            & previous_link.notna()
            & journey_df["serving_link"].ne("Outage")
            & previous_link.ne("Outage")
        )
        handover_count = int(handover.sum())

        transition_df = journey_df.loc[
            handover,
            ["minutes", "serving_link", "network_type"]
        ].copy()

        transition_df["previous_link"] = previous_link[handover].values
        transition_df["previous_type"] = (
            journey_df["network_type"].shift()[handover].values
        )
        transition_df["transition_type"] = (
            transition_df["previous_type"]
            + " → "
            + transition_df["network_type"]
        )

        st.write("Connected-link changes by type")
        st.write(transition_df["transition_type"].value_counts())
        st.dataframe(
            transition_df[
                ["minutes", "previous_link", "serving_link", "transition_type"]
            ],
            hide_index=True,
            use_container_width=True,
        )

        outage_points = int(
            journey_df["network_type"].eq("Outage").sum()
        )
        satellite_points = int(
            journey_df["network_type"].eq("Satellite").sum()
        )

        st.subheader("First terrestrial–satellite selection result")

        col1, col2, col3 = st.columns(3)
        col1.metric("Satellite-served points", satellite_points)
        col2.metric("Outage points", outage_points)
        col3.metric("Connected-link changes", handover_count)

        st.dataframe(
            journey_df[
                [
                    "minutes",
                    "site",
                    "received_power_dbm",
                    "satellite_name",
                    "elevation_deg",
                    "serving_link",
                ]
            ].round({
                "received_power_dbm": 1,
                "elevation_deg": 1,
            }),
            hide_index=True,
            use_container_width=True,
        )

        st.caption(
            "Experimental rule: use terrestrial when estimated power "
            "is at least -80 dBm; otherwise use a satellite above the "
            "selected minimum elevation. Satellite service here means "
            "geometric visibility only, not a verified working link."
        )

if __name__ == "__main__":
    main()