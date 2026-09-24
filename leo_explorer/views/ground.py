# contains the ground location metrics, coverage maps, charts, and visible-satellite table.
import plotly.express as px
import streamlit as st

from ..coverage import CoverageService
from ..plots import PlotFactory


def render_ground(
    visible_df,
    location_name,
    ground_latitude,
    ground_longitude,
    minimum_elevation,
):
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
