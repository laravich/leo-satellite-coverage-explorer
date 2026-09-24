import streamlit as st

from ..plots import PlotFactory


def render_positions(position_df, calculation_time):
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
