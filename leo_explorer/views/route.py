import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from ..hybrid import HybridRouteSimulator


def render_route(satellite_entries, timescale, minimum_elevation):
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