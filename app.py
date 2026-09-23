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
        # First try downloading CSV data directly from CelesTrak.
        try:
            response = requests.get(
             data_url,
             timeout=(10, 60)
            )

            response.raise_for_status()

            raw_df = pd.read_csv(
                StringIO(response.text),
                dtype=str,
               keep_default_na=False
            )

            data_source = "Live CelesTrak data"

        # Use the GitHub mirror if CelesTrak cannot be reached.
        except requests.RequestException:
            fallback_response = requests.get(
               FALLBACK_DATA_URL,
               timeout=(10, 60)
            )

            fallback_response.raise_for_status()

            raw_df = pd.DataFrame(
                fallback_response.json()
            )

            # Replace missing values and preserve OMM fields as strings.
            raw_df = raw_df.fillna("").astype(str)

            data_source = "CelesTrak data through backup mirror"

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
# Coverage calculation
# -----------------------------------------------------------------------------
@st.cache_data
def calculate_coverage_grid(
    visible_df,
    minimum_elevation,
    grid_step=2
):
    """
    This calculates the maximum coverage radius of one satellite, expressed as an angle measured from the centre of Earth.

    Calculate how many visible satellites cover each point
    on a global latitude-longitude grid.

    Coverage is based on:
    - satellite altitude
    - spherical Earth geometry
    - selected minimum elevation angle
    """

    grid_columns = [
        "latitude",
        "longitude",
        "coverage_count"
    ]

    if visible_df.empty:
        return pd.DataFrame(columns=grid_columns)

    earth_radius_km = 6371.0

    # Create ground locations every two degrees.
    latitudes = np.arange(
        -90,
        90 + grid_step,
        grid_step
    )

    longitudes = np.arange(
        -180,
        180,
        grid_step
    )

    longitude_grid, latitude_grid = np.meshgrid(
        longitudes,
        latitudes
    )

    latitude_grid_rad = np.radians(latitude_grid)
    longitude_grid_rad = np.radians(longitude_grid)

    coverage_count = np.zeros(
        latitude_grid.shape,
        dtype=int
    )

    elevation_rad = np.radians(minimum_elevation)

    for _, satellite in visible_df.iterrows():

        satellite_latitude_rad = np.radians(
            satellite["satellite_latitude"]
        )

        satellite_longitude_rad = np.radians(
            satellite["satellite_longitude"]
        )

        satellite_altitude_km = satellite[
            "satellite_altitude_km"
        ]

        orbital_radius_km = (
            earth_radius_km +
            satellite_altitude_km
        )

        # Maximum Earth-centred angle reached by the footprint.
        footprint_angle = (
            np.arccos( #This converts the geometric relationship into an angle.
                np.clip( # arccos accepts only -1 to +1
                    (
                        earth_radius_km /
                        orbital_radius_km
                    ) *
                    np.cos(elevation_rad),
                    -1,
                    1
                )
            )
            -
            elevation_rad
        )

        # Great-circle angle between the satellite subpoint
        # and every point in the global grid.
        cosine_distance = (
            np.sin(latitude_grid_rad) *
            np.sin(satellite_latitude_rad)
            +
            np.cos(latitude_grid_rad) *
            np.cos(satellite_latitude_rad) *
            np.cos(
                longitude_grid_rad -
                satellite_longitude_rad
            )
        )

        angular_distance = np.arccos(
            np.clip(cosine_distance, -1, 1)
        )

        # Add one when this satellite covers the grid point.
        coverage_count += (
            angular_distance <= footprint_angle
        ).astype(int)

    coverage_grid_df = pd.DataFrame(
        {
            "latitude": latitude_grid.ravel(),
            "longitude": longitude_grid.ravel(),
            "coverage_count": coverage_count.ravel()
        }
    )

    # Remove locations not covered by any selected satellite.
    coverage_grid_df = coverage_grid_df[
        coverage_grid_df["coverage_count"] > 0
    ].copy()

    return coverage_grid_df


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

# heatmap building function
def build_coverage_heatmap(
    coverage_grid_df,
    visible_df,
    location_name,
    ground_latitude,
    ground_longitude
):
    """
    Create a geographic heatmap showing coverage overlap.

    The colour at each grid point indicates how many of the
    currently visible satellites cover that location.
    """

    figure = go.Figure()

    # Coverage grid
    if not coverage_grid_df.empty:

        hover_text = coverage_grid_df.apply(
            lambda row: (
                f"<b>Coverage location</b><br>"
                f"Latitude: {row['latitude']:.1f}°<br>"
                f"Longitude: {row['longitude']:.1f}°<br>"
                f"Covering satellites: "
                f"{int(row['coverage_count'])}"
            ),
            axis=1
        )

        figure.add_trace(
            go.Scattergeo(
                lat=coverage_grid_df["latitude"],
                lon=coverage_grid_df["longitude"],
                mode="markers",
                name="Coverage area",
                marker={
                    "size": 6,
                    "symbol": "square",
                    "opacity": 0.75,
                    "color": coverage_grid_df[
                        "coverage_count"
                    ],
                    "colorscale": "Turbo",
                    "cmin": 1,
                    "cmax": coverage_grid_df[
                        "coverage_count"
                    ].max(),
                    "showscale": True,
                    "colorbar": {
                        "title": "Covering<br>satellites"
                    },
                    "line": {
                        "width": 0
                    }
                },
                text=hover_text,
                hoverinfo="text"
            )
        )

    # Locations of the satellites creating the coverage.
    figure.add_trace(
        go.Scattergeo(
            lat=visible_df["satellite_latitude"],
            lon=visible_df["satellite_longitude"],
            mode="markers",
            name="Visible satellites",
            marker={
                "size": 7,
                "symbol": "diamond",
                "color": "white",
                "line": {
                    "width": 1,
                    "color": "black"
                }
            },
            text=visible_df["satellite_name"],
            hovertemplate=(
                "<b>%{text}</b>"
                "<extra></extra>"
            )
        )
    )

    # User-selected city or custom location.
    figure.add_trace(
        go.Scattergeo(
            lat=[ground_latitude],
            lon=[ground_longitude],
            mode="markers+text",
            name="Ground location",
            text=[location_name],
            textposition="top center",
            marker={
                "size": 14,
                "symbol": "star",
                "color": "red",
                "line": {
                    "width": 1,
                    "color": "white"
                }
            },
            hovertemplate=(
                f"<b>{location_name}</b><br>"
                f"Latitude: {ground_latitude:.4f}°<br>"
                f"Longitude: {ground_longitude:.4f}°"
                "<extra></extra>"
            )
        )
    )

    figure.update_layout(
        height=650,
        legend={
            "orientation": "h",
            "yanchor": "top",
            "y": -0.05,
            "xanchor": "center",
            "x": 0.5,
            "title": None
        },
        margin={
            "l": 0,
            "r": 0,
            "t": 10,
            "b": 70
        }
    )

    # Reuse your existing world-map styling function.
    return apply_world_style(figure)

# create 3d map of the earth
def build_3d_satellite_globe(position_df):
    """
    Create an interactive 3D globe showing satellites at their
    calculated altitude above Earth.
    """

    earth_radius_km = 6371.0

    # -------------------------------------------------------------------------
    # Convert satellite latitude, longitude and altitude to 3D coordinates
    # -------------------------------------------------------------------------
    latitude_rad = np.radians(position_df["latitude"])
    longitude_rad = np.radians(position_df["longitude"])

    satellite_radius = (
        earth_radius_km + position_df["altitude_km"]
    )

    satellite_x = (
        satellite_radius
        * np.cos(latitude_rad)
        * np.cos(longitude_rad)
    )

    satellite_y = (
        satellite_radius
        * np.cos(latitude_rad)
        * np.sin(longitude_rad)
    )

    satellite_z = (
        satellite_radius
        * np.sin(latitude_rad)
    )

    # -------------------------------------------------------------------------
    # Create the Earth sphere
    # -------------------------------------------------------------------------
    earth_longitude = np.linspace(0, 2 * np.pi, 120)
    earth_latitude = np.linspace(-np.pi / 2, np.pi / 2, 60)

    earth_longitude_grid, earth_latitude_grid = np.meshgrid(
        earth_longitude,
        earth_latitude,
    )

    earth_x = (
        earth_radius_km
        * np.cos(earth_latitude_grid)
        * np.cos(earth_longitude_grid)
    )

    earth_y = (
        earth_radius_km
        * np.cos(earth_latitude_grid)
        * np.sin(earth_longitude_grid)
    )

    earth_z = (
        earth_radius_km
        * np.sin(earth_latitude_grid)
    )

    figure = go.Figure()

    # Add Earth
    figure.add_trace(
        go.Surface(
            x=earth_x,
            y=earth_y,
            z=earth_z,
            surfacecolor=np.sin(earth_latitude_grid),
            colorscale=[
                [0.0, "#0B3D91"],
                [0.5, "#1D9CB8"],
                [1.0, "#78C7E8"],
            ],
            showscale=False,
            opacity=0.9,
            name="Earth",
            hoverinfo="skip",
        )
    )

    # -------------------------------------------------------------------------
    # Create satellite hover information
    # -------------------------------------------------------------------------
    hover_text = position_df.apply(
        lambda row: (
            f"<b>{row['satellite_name']}</b><br>"
            f"NORAD ID: {row['norad_id']}<br>"
            f"Latitude: {row['latitude']:.2f}°<br>"
            f"Longitude: {row['longitude']:.2f}°<br>"
            f"Altitude: {row['altitude_km']:,.1f} km"
        ),
        axis=1,
    )

    # Add satellites
    figure.add_trace(
        go.Scatter3d(
            x=satellite_x,
            y=satellite_y,
            z=satellite_z,
            mode="markers",
            name="Satellites",
            marker={
                "size": 3.5,
                "color": position_df["altitude_km"],
                "colorscale": "Turbo",
                "showscale": True,
                "colorbar": {
                    "title": "Altitude<br>(km)"
                },
                "line": {
                    "width": 0.3,
                    "color": "white",
                },
            },
            text=hover_text,
            hoverinfo="text",
        )
    )

    # -------------------------------------------------------------------------
    # Format the 3D scene
    # -------------------------------------------------------------------------
    figure.update_layout(
        height=750,
        scene={
            "aspectmode": "data",
            "xaxis": {
                "visible": False,
            },
            "yaxis": {
                "visible": False,
            },
            "zaxis": {
                "visible": False,
            },
            "camera": {
                "eye": {
                    "x": 1.5,
                    "y": 1.5,
                    "z": 1.0,
                }
            },
            "bgcolor": "#050B18",
        },
        paper_bgcolor="#050B18",
        margin={
            "l": 0,
            "r": 0,
            "t": 20,
            "b": 0,
        },
        legend={
            "orientation": "h",
            "yanchor": "top",
            "y": -0.02,
            "xanchor": "center",
            "x": 0.5,
        },
    )

    return figure

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
        (
            oneweb_df,
            satellite_entries,
            timescale,
            load_errors,
            data_source,
        ) = load_satellite_data(
            str(DATA_PATH),
            DATA_URL,
        )

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
        build_world_position_map(position_df),
        use_container_width=True,
    )

    #3D Map
    st.subheader("🌐 3D satellite globe")

    st.caption(
        "Satellites are displayed at their calculated altitude above Earth. "
        "Drag to rotate the globe and scroll to zoom."
    )

    satellite_globe = build_3d_satellite_globe(position_df)

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
        build_coverage_map(
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
        coverage_grid_df = calculate_coverage_grid(
            visible_df=visible_df,
            minimum_elevation=minimum_elevation,
            grid_step=2,
        )

        # Create the Plotly geographic coverage heatmap
        coverage_heatmap = build_coverage_heatmap(
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