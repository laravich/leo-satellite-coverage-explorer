# 🛰️ LEO Satellite Coverage Explorer

An interactive Streamlit dashboard for exploring OneWeb LEO satellite
positions and instantaneous geometric visibility from selected ground
locations.

This mini project combines satellite communications, orbital-data analysis,
geospatial visualization and interactive dashboard development.

## Features

- Calculates current satellite positions from CelesTrak orbital elements
- Displays OneWeb satellites on an interactive world map
- Provides predefined cities and custom coordinates
- Filters visible satellites by minimum elevation angle
- Calculates elevation, azimuth, distance and propagation delay
- Visualizes visible-satellite elevation and distance
- Displays detailed coverage metrics and satellite information

## Technology Stack

- Python
- Streamlit
- pandas
- Plotly
- Skyfield

## Data Source

Orbital data comes from
[CelesTrak](https://celestrak.org/NORAD/elements/).

CSV datasets are intentionally excluded from this repository. Use
`download_satellite_data.ipynb` to download the current OneWeb orbital data
before running the dashboard.

The notebook should create:

```text
data/oneweb_satellites.csv
```

## Project Structure

```text
leo-satellite-coverage-explorer/
├── data/                              # Locally downloaded data
├── app.py                             # Streamlit application
├── download_satellite_data.ipynb      # Dataset download notebook
├── .gitignore
├── README.md
└── requirements.txt
```

## Installation

Clone the repository:

```bash
git clone git@github.com:rlavanya11993@gmail.com/leo-satellite-coverage-explorer.git
```

Move into the project:

```bash
cd leo-satellite-coverage-explorer
```

Create a virtual environment:

```bash
python -m venv .venv
```

Activate it on Linux or WSL:

```bash
source .venv/bin/activate
```

Install the required packages:

```bash
pip install -r requirements.txt
```

## Download the Data

Open:

```text
download_satellite_data.ipynb
```

Run the notebook to create the local dataset inside the `data` directory.

## Run the Dashboard

```bash
streamlit run app.py
```

Then open the local Streamlit address, normally:

```text
http://localhost:8501
```

## Coverage Definition

A satellite is considered geometrically visible when its elevation angle from
the selected ground location is greater than or equal to the selected minimum
elevation angle.

This analysis represents theoretical geometric visibility, not guaranteed
commercial OneWeb service. Actual service depends on satellite beams, gateways,
capacity, spectrum authorization, terrain and network operation.

The displayed propagation delay is the theoretical one-way free-space delay.
It does not include routing, processing or terrestrial-network delays.

## Planned Improvements

- Automatic cached download from CelesTrak
- Satellite coverage-footprint heatmap
- Twenty-four-hour coverage analysis
- Satellite-pass prediction
- Comparison with Starlink and Iridium NEXT

## Author

**Lavanya Ravichandran**

Wireless communications researcher with experience in 5G/6G, V2X,
radio-resource management, channel modelling and system-level simulation.