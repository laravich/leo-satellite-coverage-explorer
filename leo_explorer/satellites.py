from pathlib import Path
from io import StringIO

import pandas as pd
import requests
import streamlit as st
from skyfield.api import EarthSatellite, load
from skyfield.api import wgs84

from .config import DATA_CACHE_SECONDS, FALLBACK_DATA_URL, NUMERIC_COLUMNS
from .config import (
    C_KM_PER_SECOND,
    POSITION_CACHE_SECONDS,
    POSITION_COLUMNS,
    VISIBLE_COLUMNS,
)
# -----------------------------------------------------------------------------
# Data preparation
# -----------------------------------------------------------------------------

class SatelliteService:
    @staticmethod
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

        return (analysis_df, satellite_entries, timescale, load_errors, data_source)

    @staticmethod
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
