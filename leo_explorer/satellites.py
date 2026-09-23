from pathlib import Path
from io import StringIO

import pandas as pd
import requests
import streamlit as st
from skyfield.api import EarthSatellite, load

from .config import DATA_CACHE_SECONDS, FALLBACK_DATA_URL, NUMERIC_COLUMNS

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