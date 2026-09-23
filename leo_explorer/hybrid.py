import numpy as np
import pandas as pd
from datetime import timedelta
from skyfield.api import wgs84

class HybridRouteSimulator:
    @staticmethod
    def example_hybrid_route():
        """Illustrative straight-line route and example gNB sites near Nuremberg."""
        route = pd.DataFrame({
            "latitude": np.linspace(49.4521, 49.5897, 60),
            "longitude": np.linspace(11.0767, 11.0040, 60),
        })
        route["step"] = np.arange(len(route))
        sites = pd.DataFrame({
            "site": ["Example gNB 1", "Example gNB 2", "Example gNB 3"],
            "latitude": [49.4600, 49.5150, 49.5750],
            "longitude": [11.0750, 11.0470, 11.0120],
        })
        return route, sites

    @staticmethod
    def calculate_terrestrial_links(route, sites):
        """Estimate signal from every example gNB at each route point."""
        results = []

        for position in route.itertuples(index=False):
            for site in sites.itertuples(index=False):
                # Distance between vehicle and gNB using the Haversine formula.
                lat1, lat2 = np.radians([position.latitude, site.latitude])
                delta_lat = lat2 - lat1
                delta_lon = np.radians(site.longitude - position.longitude)

                a = (
                    np.sin(delta_lat / 2) ** 2
                    + np.cos(lat1) * np.cos(lat2) * np.sin(delta_lon / 2) ** 2
                )
                distance_km = 2 * 6371.0 * np.arcsin(
                    np.sqrt(np.clip(a, 0.0, 1.0))
                )

                # Illustrative 3.5 GHz log-distance signal model.
                distance_m = max(distance_km * 1000, 20.0)
                reference_loss_db = (
                    32.45 + 20 * np.log10(3500) - 60
                )
                path_loss_db = (
                    reference_loss_db + 30 * np.log10(distance_m)
                )
                received_power_dbm = 46.0 - path_loss_db

                results.append({
                    "step": position.step,
                    "site": site.site,
                    "distance_km": distance_km,
                    "received_power_dbm": received_power_dbm,
                })

        all_links = pd.DataFrame(results)

        # Select the strongest gNB at each route point.
        strongest = all_links.loc[
            all_links.groupby("step")["received_power_dbm"].idxmax()
        ].sort_values("step").reset_index(drop=True)

        return all_links, strongest

    @staticmethod
    def calculate_satellites_along_route(route, satellite_entries, timescale, start_time, minimum_elevation_deg=10, hysteresis_deg=5,):
        """Find the highest visible satellite at sampled vehicle positions."""
        """Compare highest-elevation and hysteresis satellite selection."""
        results = []
        #start_time = timescale.now().utc_datetime()
        current_satellite_name = None

        # Use every third point: 20 positions from the 60-point example route.
        for sample_number, position in enumerate(route.iloc[::3].itertuples(index=False)):
            # Assume two minutes pass between sampled positions.
            observation_time = timescale.from_datetime(
                start_time + timedelta(minutes=2 * sample_number)
            )
            vehicle = wgs84.latlon(position.latitude, position.longitude)

            #best_satellite = None
            visible = []

            for entry in satellite_entries:
                try:
                    topocentric = (
                        entry["satellite"] - vehicle
                    ).at(observation_time)

                    elevation, azimuth, distance = topocentric.altaz()

                    if elevation.degrees >= minimum_elevation_deg:
                        visible.append({
                            "satellite_name": entry["name"],
                            "elevation_deg": elevation.degrees,
                            "distance_km": distance.km,
                        })
                    
                    # if elevation.degrees < minimum_elevation_deg:
                    #     continue

                    # if (
                    #     best_satellite is None
                    #     or elevation.degrees > best_satellite["elevation_deg"]
                    # ):
                    #     best_satellite = {
                    #         "satellite_name": entry["name"],
                    #         "elevation_deg": elevation.degrees,
                    #         "distance_km": distance.km,
                    #     }

                except (TypeError, ValueError):
                    continue

            # Baseline: choose the satellite highest in the sky.
            highest = max(visible, key=lambda sat: sat["elevation_deg"], default=None)

            # Find the satellite selected at the previous sampled point.
            current = next(
                (
                    sat for sat in visible
                    if sat["satellite_name"] == current_satellite_name
                ),
                None,
            )
            switch_reason = (
                "No satellite visible" if highest is None
                else "Previous satellite below minimum elevation" if current is None
                else "Candidate exceeds margin" if (
                    highest["elevation_deg"]
                    >= current["elevation_deg"] + hysteresis_deg
                )
                else "Keep current satellite"
            )

            if highest is None:
                selected = None

            elif current is None:
                # Current satellite is no longer visible: choose the highest.
                selected = highest

            elif (
                highest["elevation_deg"]
                >= current["elevation_deg"] + hysteresis_deg
            ):
                # Switch only when the candidate is sufficiently higher.
                selected = highest

            else:
                # Keep the current satellite.
                selected = current

            current_satellite_name = (
                selected["satellite_name"] if selected else None
            )


            results.append({
                "step": position.step,
                "minutes": 2 * sample_number,
                "latitude": position.latitude,
                "longitude": position.longitude,
                "highest_satellite": (
                    highest["satellite_name"] if highest else None
                ),
                "highest_elevation_deg": (
                    highest["elevation_deg"] if highest else np.nan
                ),
                # Existing journey code uses these columns.
                "satellite_name": (
                    selected["satellite_name"]
                    if selected else None
                ),
                "elevation_deg": (
                    selected["elevation_deg"]
                    if selected else np.nan
                ),
                "distance_km": (
                    selected["distance_km"]
                    if selected else np.nan
                ),
                "hysteresis_deg": hysteresis_deg,
                "switch_reason": switch_reason,
                "previous_satellite_elevation_deg": (
                    current["elevation_deg"] if current else np.nan
                ),
                "elevation_difference_deg": (
                    highest["elevation_deg"] - current["elevation_deg"]
                    if highest and current else np.nan
                ),
            })

        return pd.DataFrame(results)

