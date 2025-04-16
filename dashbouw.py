# --- Imports and Setup ---
import os
import requests
import pandas as pd
import numpy as np
import json
import logging
from dotenv import load_dotenv
from pyproj import Transformer
import dash
from dash import dcc, html, Output, Input
import plotly.express as px
import dash_bootstrap_components as dbc

# Configure console logging (so Render captures it)
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s %(levelname)s: %(message)s'
    # no filename, so logs go to stdout/stderr
)

# --- API call ---
load_dotenv()
api_key = os.getenv("GEMEENTE_API_KEY")
api_url = "https://api.data.amsterdam.nl/v1/nieuwbouwplannen/woningbouwplannen_openbaar/"
headers = {"X-Api-Key": api_key}

try:
    response = requests.get(api_url, headers=headers)
    response.raise_for_status()
    data = response.json()['_embedded']['woningbouwplannen_openbaar']
    logging.debug("Successfully fetched API data; records: %s", len(data))
except Exception as e:
    logging.error("Error fetching API data: %s", e)
    data = []

df = pd.json_normalize(data)

# --- Geometrie voorbereiden ---
def safe_load(x):
    try:
        return json.loads(x) if isinstance(x, str) else x
    except Exception as e:
        logging.error("safe_load error: %s", e)
        return None

df['geometrie.coordinates'] = df['geometrie.coordinates'].apply(safe_load)

def extract_centroid(multipolygon):
    try:
        coords = np.array(multipolygon[0][0])
        lon = coords[:, 0].mean()
        lat = coords[:, 1].mean()
        return pd.Series({'lon': lon, 'lat': lat})
    except Exception as e:
        logging.error("extract_centroid error: %s", e)
        return pd.Series({'lon': None, 'lat': None})

df[['lon', 'lat']] = df['geometrie.coordinates'].apply(extract_centroid)

# --- RD naar WGS84 ---
transformer = Transformer.from_crs("EPSG:28992", "EPSG:4326", always_xy=True)
def convert_rd_to_wgs84(row):
    try:
        lon, lat = transformer.transform(row['lon'], row['lat'])
        return pd.Series({'lon': lon, 'lat': lat})
    except Exception as e:
        logging.error("convert_rd_to_wgs84 error: %s", e)
        return pd.Series({'lon': None, 'lat': None})

df[['lon', 'lat']] = df[['lon', 'lat']].apply(convert_rd_to_wgs84, axis=1)

# --- Kolommen voorbereiden ---
woningtypes = ["socialeHuurZelfstPerm", "middeldureHuur", "vrijeSectorKoop"]
df[woningtypes] = df[woningtypes].apply(pd.to_numeric, errors="coerce")

# Preserve raw date strings, then parse explicitly as ISO
df['startBouwGepland_raw'] = df.get("startBouwGepland", None)
df['startBouwGepland'] = pd.to_datetime(
    df['startBouwGepland_raw'],
    errors="coerce",
    utc=True
)
parsed = df['startBouwGepland'].notna().sum()
total = len(df)
logging.debug("Dates parsed: %s non‑NaT out of %s rows", parsed, total)

df["projectnaamAfkorting"] = df["projectnaamAfkorting"].apply(
    lambda x: x.split('/')[1].split('-')[0] if isinstance(x, str) and '/' in x else x
)
df = df.dropna(subset=['lon', 'lat'])
logging.debug("DataFrame after preprocessing: %s rows", len(df))

# --- Labels & kleuren ---
color_palette = ['#008080', '#66b2b2', '#FF6F61', '#F4E1D2', '#2E3A59']
label_map = {
    "socialeHuurZelfstPerm": "Sociale Huur",
    "middeldureHuur": "Middeldure Huur",
    "vrijeSectorKoop": "Vrije Sector Koop"
}

# --- Dash setup ---
app = dash.Dash(__name__, external_stylesheets=[dbc.themes.BOOTSTRAP])
server = app.server

sidebar_cards = html.Div([
    dbc.Card([...your sidebar code...]),
    html.Br(),
    dbc.Card([...your year filter code...])
])

app.layout = html.Div([
    # Your header, KPI block, sidebar and main panel layout
    # (omitted for brevity; use the same layout as before)
])

# --- Callback for all graphs and KPIs ---
@app.callback(
    Output('map', 'figure'),
    Output('pie-chart', 'figure'),
    Output('bar-chart', 'figure'),
    Output('line-chart', 'figure'),
    Output('top10-chart', 'figure'),
    Output('kpi-totaal', 'children'),
    Output('kpi-projecten', 'children'),
    Output('kpi-buurten', 'children'),
    Output('kpi-gemjaar', 'children'),
    Input('map-type-toggle', 'value'),
    Input('woningtype-checklist', 'value'),
    Input('jaar-slider', 'value')
)
def update_all_graphs(map_type, selected_types, selected_year):
    # ... initial filtering and melt logic (same as before) ...

    # --- Map figure with px.density_map instead of density_mapbox ---
    if map_type == "heatmap":
        map_fig = px.density_map(
            melted,
            lat="lat",
            lon="lon",
            z="value",
            radius=10,
            center=dict(lat=52.37, lon=4.89),
            zoom=11,
            mapbox_style="open-street-map",
            title="<b>Woningbouw Dichtheid (Heatmap)</b>",
            color_continuous_scale="Teal"
        )
    else:
        map_fig = px.scatter_mapbox(
            melted,
            lat="lat",
            lon="lon",
            color="woningtype_label",
            hover_name="projectnaamAfkorting",
            hover_data=["stadsdeelNaam", "startBouwGepland"],
            mapbox_style="open-street-map",
            zoom=11,
            height=500,
            color_discrete_sequence=color_palette
        )
        map_fig.update_traces(marker=dict(size=15))

    map_fig.update_layout(
        margin={"r": 0, "t": 50, "l": 0, "b": 0},
        font=dict(family="system-ui", size=16)
    )

    # ... pie, bar, line, top10 chart code unchanged ...

    return map_fig, pie_fig, bar_fig, line_fig, top10_fig, \
           f"{totaal_woningen}", f"{aantal_projecten}", f"{unieke_buurten}", f"{gemiddeld_jaar}"

# --- Server starten for Render ---
if __name__ == '__main__':
    app.run_server(
        debug=False,
        host='0.0.0.0',
        port=int(os.environ.get("PORT", 8050))
    )
