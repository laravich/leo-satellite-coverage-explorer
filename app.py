"""Interactive OneWeb satellite position and ground-coverage explorer."""

from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from skyfield.api import EarthSatellite, load, wgs84
#for live data
from io import StringIO
import requests


# -----------------------------------------------------------------------------
# App configuration and constants
# -----------------------------------------------------------------------------

# This must be the first Streamlit command in the script.
st.set_page_config(
    page_title="LEO Satellite Explorer",
    page_icon="\U0001F6F0",
    layout="wide",
)

DATA_PATH = Path("data/oneweb_satellites.csv")

DATA_URL = ("https://celestrak.org/NORAD/elements/gp.php?GROUP=ONEWEB&FORMAT=CSV")
DATA_CACHE_SECONDS = 6 * 60 * 60 #6 hours cache the data downloaded
POSITION_CACHE_SECONDS = 60

C_KM_PER_SECOND = 299_792.458 #speed of light
#CACHE_SECONDS = 60

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


# -----------------------------------------------------------------------------
# Data preparation
# -----------------------------------------------------------------------------

@st.cache_resource(ttl=DATA_CACHE_SECONDS)
def load_satellite_data(csv_path: str, data_url: str):
    """
    Load the local CSV when available.

    If the local CSV does not exist, download current orbital
    data from CelesTrak and cache it for six hours.

    and build reusable Skyfield satellite objects.
    """

    local_path = Path(csv_path)

    if local_path.exists():
        # Use the previously downloaded local dataset.
        raw_df = pd.read_csv(
            local_path,
            dtype=str,
            keep_default_na=False
        )

        data_source = f"Local file: {local_path}"

    else:
        # Used during cloud deployment when data/ is not on GitHub.
        response = requests.get(
            data_url,
            timeout=30
        )

        response.raise_for_status()

        raw_df = pd.read_csv(
            StringIO(response.text),
            dtype=str,
            keep_default_na=False
        )

        data_source = "Live CelesTrak data"

    # Create a numeric copy for metrics and visualizations.
    analysis_df = raw_df.copy()

    for column in NUMERIC_COLUMNS:
        if column in analysis_df.columns:
            analysis_df[column] = pd.to_numeric(
                analysis_df[column],
                errors="coerce"
            )

    timescale = load.timescale()
    satellite_entries = []
    load_errors = []

    # Construct every Skyfield satellite object once.
    for record in raw_df.to_dict(orient="records"):
        try:
            satellite_entries.append(
                {
                    "satellite": EarthSatellite.from_omm(
                        timescale,
                        record
                    ),
                    "name": record["OBJECT_NAME"],
                    "norad_id": record["NORAD_CAT_ID"],
                    "inclination": float(
                        record["INCLINATION"]
                    ),
                    "mean_motion": float(
                        record["MEAN_MOTION"]
                    )
                }
            )

        except (KeyError, TypeError, ValueError) as error:
            satellite_name = record.get(
                "OBJECT_NAME",
                "Unknown satellite"
            )

            load_errors.append(
                f"{satellite_name}: {error}"
            )

    return (
        analysis_df,
        satellite_entries,
        timescale,
        load_errors,
        data_source
    )


@st.cache_data(ttl=POSITION_CACHE_SECONDS)
def calculate_snapshot(
    _satellite_entries, #only inside the function
    _timescale,
    ground_latitude: float,
    ground_longitude: float,
    minimum_elevation: int,
):
    """Calculate all world positions and local visibility in one loop.

    Parameters beginning with ``_`` are intentionally excluded from Streamlit's
    cache hashing. The result refreshes every 60 seconds or when an input changes.
    """

    current_time = _timescale.now()
    ground_station = wgs84.latlon(ground_latitude, ground_longitude)
    all_positions = []
    visible_satellites = []
    calculation_errors = []

    for entry in _satellite_entries:
        satellite = entry["satellite"]

        try:
            # Compute the orbital position once and reuse its subpoint.
            geocentric = satellite.at(current_time)
            subpoint = wgs84.subpoint(geocentric)

            position = {
                "satellite_name": entry["name"],
                "norad_id": entry["norad_id"],
                "latitude": subpoint.latitude.degrees,
                "longitude": subpoint.longitude.degrees,
                "altitude_km": subpoint.elevation.km,
                "inclination": entry["inclination"],
                "mean_motion": entry["mean_motion"],
            }
            all_positions.append(position)

            # Calculate elevation, azimuth and distance from the ground location.
            topocentric = (satellite - ground_station).at(current_time)
            elevation, azimuth, distance = topocentric.altaz()

            if elevation.degrees >= minimum_elevation:
                visible_satellites.append(
                    {
                        "satellite_name": entry["name"],
                        "norad_id": entry["norad_id"],
                        "elevation_deg": elevation.degrees,
                        "azimuth_deg": azimuth.degrees,
                        "distance_km": distance.km,
                        # One-way free-space delay; network delay is not included.
                        "delay_ms": distance.km / C_KM_PER_SECOND * 1_000,
                        "satellite_latitude": position["latitude"],
                        "satellite_longitude": position["longitude"],
                        "satellite_altitude_km": position["altitude_km"],
                    }
                )
        except (TypeError, ValueError) as error:
            calculation_errors.append(f"{entry['name']}: {error}")

    position_df = pd.DataFrame(all_positions, columns=POSITION_COLUMNS)
    visible_df = pd.DataFrame(visible_satellites, columns=VISIBLE_COLUMNS)

    if not visible_df.empty:
        visible_df = visible_df.sort_values(
            "elevation_deg", ascending=False
        ).reset_index(drop=True)

    calculation_time = current_time.utc_strftime("%Y-%m-%d %H:%M:%S UTC")
    return position_df, visible_df, calculation_time, calculation_errors


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

def apply_world_style(figure):
    """Apply one consistent geographic style to both world maps."""

    figure.update_geos(
        projection_type="natural earth",
        showland=True,
        landcolor="#B6BB85",
        showocean=True,
        oceancolor="#1D9CB8",
        showcountries=True,
        countrycolor="white",
        showcoastlines=True,
        coastlinecolor="gray",
    )
    return figure


def build_world_position_map(position_df):
    """Create a map of the point on Earth directly below every satellite."""

    figure = px.scatter_geo(
        position_df,
        lat="latitude",
        lon="longitude",
        color="altitude_km",
        hover_name="satellite_name",
        hover_data={
            "norad_id": True,
            "latitude": ":.2f",
            "longitude": ":.2f",
            "altitude_km": ":.2f",
            "inclination": ":.2f",
            "mean_motion": ":.2f",
        },
        color_continuous_scale="Turbo",
        labels={
            "altitude_km": "Altitude (km)",
            "norad_id": "NORAD ID",
            "latitude": "Latitude",
            "longitude": "Longitude",
            "inclination": "Inclination (°)",
            "mean_motion": "Orbits/day",
        },
    )
    figure.update_traces(
        marker={
            "size": 6,
            "opacity": 0.8,
            "line": {"width": 0.3, "color": "white"},
        }
    )
    figure.update_layout(
        height=650,
        margin={"l": 0, "r": 0, "t": 10, "b": 0},
    )
    return apply_world_style(figure)


def build_coverage_map(
    visible_df,
    location_name,
    ground_latitude,
    ground_longitude,
):
    """Map a ground point and all satellites currently visible from it."""

    figure = go.Figure()

    if not visible_df.empty:
        hover_text = visible_df.apply(
            lambda row: (
                f"<b>{row['satellite_name']}</b><br>"
                f"NORAD ID: {row['norad_id']}<br>"
                f"Elevation: {row['elevation_deg']:.2f}°<br>"
                f"Azimuth: {row['azimuth_deg']:.2f}°<br>"
                f"Distance: {row['distance_km']:,.0f} km<br>"
                f"Altitude: {row['satellite_altitude_km']:,.0f} km"
            ),
            axis=1,
        )
        figure.add_trace(
            go.Scattergeo(
                lat=visible_df["satellite_latitude"],
                lon=visible_df["satellite_longitude"],
                mode="markers",
                name="Visible satellites",
                marker={
                    "size": 7,
                    "color": visible_df["elevation_deg"],
                    "colorscale": "Turbo",
                    "showscale": True,
                    "colorbar": {"title": "Elevation<br>(degrees)"},
                    "line": {"width": 0.5, "color": "white"},
                },
                text=hover_text,
                hoverinfo="text",
            )
        )

    # Always display the user's ground location, even with no coverage.
    figure.add_trace(
        go.Scattergeo(
            lat=[ground_latitude],
            lon=[ground_longitude],
            mode="markers+text",
            name="Ground location",
            text=[location_name],
            textposition="top center",
            marker={
                "size": 13,
                "color": "red",
                "symbol": "star",
                "line": {"width": 1, "color": "white"},
            },
            hovertemplate=(
                f"<b>{location_name}</b><br>"
                f"Latitude: {ground_latitude:.4f}°<br>"
                f"Longitude: {ground_longitude:.4f}°"
                "<extra></extra>"
            ),
        )
    )
    figure.update_layout(
        height=520,
        legend={
            "orientation": "h",
            "yanchor": "top",
            "y": -0.06,
            "xanchor": "center",
            "x": 0.5,
            "title": None,
        },
        # Reserve space below the map for its horizontal legend.
        margin={"l": 0, "r": 0, "t": 10, "b": 70},
    )
    return apply_world_style(figure)


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

    # loading data
    try:
        (oneweb_df, satellite_entries, timescale, load_errors, data_source) = load_satellite_data(str(DATA_PATH), DATA_URL)

    except requests.RequestException as error:
        st.error(
        "The local CSV was not found and the orbital data "
        f"could not be downloaded from CelesTrak: {error}"
        )
        st.stop()
    # show which source the app used
    st.caption(f"Data source: {data_source}")
    #if not DATA_PATH.exists():
    #    st.error(f"Dataset not found: {DATA_PATH}")
    #    st.stop()

    # Load the CSV and construct Skyfield objects only once.
    #oneweb_df, satellite_entries, timescale, load_errors = (
    #    load_satellite_data(str(DATA_PATH))
    #)
    location_name, ground_latitude, ground_longitude, minimum_elevation = (
        get_location_settings()
    )

    # Refresh time-dependent positions without reloading the dataset.
    if st.sidebar.button("🔄 Update satellite positions"):
        calculate_snapshot.clear()
        st.rerun()

    position_df, visible_df, calculation_time, calculation_errors = (
        calculate_snapshot(
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
    overview_col1.metric("Satellites", len(satellite_entries))
    overview_col2.metric(
        "Average inclination", f"{oneweb_df['INCLINATION'].mean():.2f}°"
    )
    overview_col3.metric(
        "Average orbits per day", f"{oneweb_df['MEAN_MOTION'].mean():.2f}"
    )

    # Keep large diagnostic tables available without crowding the dashboard.
    with st.expander("Inspect the data"):
        dataset_tab, position_tab = st.tabs(
            ["Orbital dataset", "Calculated positions"]
        )
        dataset_tab.dataframe(oneweb_df, use_container_width=True)
        position_tab.dataframe(position_df, use_container_width=True)

        all_errors = load_errors + calculation_errors
        if all_errors:
            st.warning(f"{len(all_errors)} satellite record(s) could not be processed.")
            st.code("\n".join(all_errors[:20]))

    chart_col1, chart_col2 = st.columns(2)

    with chart_col1:
        st.subheader("Orbital inclination distribution")
        st.caption("Shows how the orbital planes are tilted relative to the equator.")
        inclination_figure = px.histogram(
            oneweb_df,
            x="INCLINATION",
            nbins=30,
            labels={"INCLINATION": "Inclination (degrees)"},
            color_discrete_sequence=["#1F77B4"],
        )
        inclination_figure.update_layout(yaxis_title="Number of satellites")
        st.plotly_chart(inclination_figure, use_container_width=True)

    with chart_col2:
        st.subheader("Inclination and mean motion")
        st.caption("Compares orbital tilt with completed orbits per day.")
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
        st.plotly_chart(orbit_figure, use_container_width=True)

    # -------------------------------------------------------------------------
    # Global satellite positions
    # -------------------------------------------------------------------------

    st.header("🌍 Current satellite positions")
    st.caption(
        f"Calculated at {calculation_time}. Each marker is the point on Earth "
        "directly below a satellite, not its full coverage footprint."
    )
    st.plotly_chart(
        build_world_position_map(position_df), use_container_width=True
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
        nearest_row = visible_df.loc[visible_df["distance_km"].idxmin()]
        nearest_distance = nearest_row["distance_km"]
        nearest_delay = nearest_row["delay_ms"]
        st.success(
            f"This location currently has geometric coverage from "
            f"{number_visible} satellite(s)."
        )
    else:
        best_elevation = nearest_distance = nearest_delay = None
        st.warning("No satellite currently meets the selected elevation angle.")

    metric_col1, metric_col2, metric_col3, metric_col4 = st.columns(4)
    metric_col1.metric("Visible satellites", number_visible)
    metric_col2.metric(
        "Best elevation",
        f"{best_elevation:.1f}°" if best_elevation is not None else "N/A",
    )
    metric_col3.metric(
        "Nearest satellite",
        f"{nearest_distance:,.0f} km" if nearest_distance is not None else "N/A",
    )
    metric_col4.metric(
        "One-way space delay",
        f"{nearest_delay:.2f} ms" if nearest_delay is not None else "N/A",
    )

    st.subheader("Current coverage map")
    st.caption(
        "Coloured markers meet the selected elevation threshold; the red star "
        "is the ground location."
    )
    st.plotly_chart(
        build_coverage_map(
            visible_df,
            location_name,
            ground_latitude,
            ground_longitude,
        ),
        use_container_width=True,
    )

    # The remaining charts and table require at least one visible satellite.
    if not visible_df.empty:
        details_col1, details_col2 = st.columns(2)

        with details_col1:
            st.subheader("Highest visible satellites")
            st.caption("Higher elevation means farther above the local horizon.")
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
            elevation_figure.update_layout(coloraxis_showscale=False)
            st.plotly_chart(elevation_figure, use_container_width=True)

        with details_col2:
            st.subheader("Elevation versus distance")
            st.caption(
                "Satellites higher in the sky generally have a shorter slant range."
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
                    "distance_km": "Distance from ground station (km)",
                },
            )
            st.plotly_chart(distance_figure, use_container_width=True)

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


if __name__ == "__main__":
    main()
