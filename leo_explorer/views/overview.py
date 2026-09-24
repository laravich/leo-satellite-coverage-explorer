import plotly.express as px
import streamlit as st


def render_overview(
    oneweb_df,
    satellite_entries,
    position_df,
    load_errors,
    calculation_errors,
):
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
