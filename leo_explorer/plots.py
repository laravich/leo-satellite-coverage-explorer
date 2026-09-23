import numpy as np
import plotly.express as px
import plotly.graph_objects as go


class PlotFactory:
    @staticmethod
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

    @staticmethod
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
        return PlotFactory.apply_world_style(figure)

    @staticmethod
    def build_coverage_map(visible_df, location_name, ground_latitude, ground_longitude):
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
        return PlotFactory.apply_world_style(figure)

    

    @staticmethod
    def build_coverage_heatmap(coverage_grid_df, visible_df, location_name, ground_latitude, ground_longitude):
    # heatmap building function
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
        return PlotFactory.apply_world_style(figure)

    @staticmethod
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