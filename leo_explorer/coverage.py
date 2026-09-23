import numpy as np
import pandas as pd
import streamlit as st


class CoverageService:
    @staticmethod
    @st.cache_data
    def calculate_coverage_grid(visible_df, minimum_elevation, grid_step=2):
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