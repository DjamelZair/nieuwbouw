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
    
    # --- Pie Chart: verdeling per wijk ---
    wijk_data = melted.groupby(['wijkNaam', 'woningtype_label'])['value'].sum().reset_index()
    pie_fig = px.pie(
        wijk_data,
        names='wijkNaam',
        values='value',
        #title="<b>Verdeling per Wijk</b>",
        color_discrete_sequence=color_palette
    )
    pie_fig.update_layout(
        legend=dict(font=dict(size=18)),
        font=dict(family="system-ui", size=16),
        title_font=dict(family="system-ui", size=22)
    )

    # --- Bar Chart: verhouding woningtypes per wijk ---
    bar_data = melted.groupby(['wijkNaam', 'woningtype_label'])['value'].sum().reset_index()
    bar_fig = px.bar(
        bar_data,
        x="wijkNaam",
        y="value",
        color="woningtype_label",
        barmode="group",
        #title="<b>Verdeling Woningtypen per Wijk</b>",
        color_discrete_sequence=color_palette,
        labels={"value": "Aantal woningen", "wijkNaam": "Wijk", "woningtype_label": "Woningtype"}
    )
    bar_fig.update_layout(
        font=dict(family="system-ui", size=16),
        title_font=dict(family="system-ui", size=22),
        xaxis_tickangle=-45,
        legend_font=dict(size=14),
        margin={"r": 0, "t": 50, "l": 0, "b": 0}
    )
        # --- Line Chart: geplande woningen per jaar (robust via ‘melted’) ---
    # 1) Use the same melted DataFrame you’ve already filtered for value > 0
    melted_line = melted.copy()
    melted_line['jaar'] = melted_line['startBouwGepland'].dt.year

    # 2) Aggregate by year and woningtype
    grouped_line = (
        melted_line
        .groupby(['jaar', 'woningtype_label'])['value']
        .sum()
        .reset_index()
    )

    # 3) Ensure we cover every year in the slider range (fill missing with 0)
    min_year = int(df['startBouwGepland'].dt.year.min())
    max_year = int(selected_year)
    all_years = pd.DataFrame({'jaar': list(range(min_year, max_year + 1))})
    # Cross‑join to get every (jaar, woningtype_label) combo
    types = pd.DataFrame({'woningtype_label': melted_line['woningtype_label'].unique()})
    full_idx = all_years.merge(types, how='cross')
    grouped_line = (
        full_idx
        .merge(grouped_line, on=['jaar','woningtype_label'], how='left')
        .fillna({'value': 0})
    )

    # 4) Build the figure
    line_fig = px.line(
        grouped_line,
        x='jaar',
        y='value',
        color='woningtype_label',
        markers=True,
        labels={
            'jaar': 'Jaar',
            'value': 'Aantal Woningen',
            'woningtype_label': 'Woningtype'
        },
        color_discrete_sequence=color_palette
    )
    line_fig.update_layout(
        margin={"r":0, "t":50, "l":0, "b":0},
        font=dict(family="system-ui", size=16),
        title_font=dict(family="system-ui", size=22),
        legend_font=dict(size=18),
        xaxis=dict(dtick=1)
    )

    # --- Top 10 Buurten met meeste geplande woningen per type ---
    buurt_type_data = melted.groupby(['buurtNaam', 'woningtype_label'])['value'].sum().reset_index()
    top_buurten = (
        buurt_type_data.groupby('buurtNaam')['value']
        .sum()
        .sort_values(ascending=False)
        .head(10)
        .index.tolist()
    )
    top10_data = buurt_type_data[buurt_type_data['buurtNaam'].isin(top_buurten)]

    top10_fig = px.bar(
        top10_data,
        x='value',
        y='buurtNaam',
        color='woningtype_label',
        orientation='h',
        #title="<b>Top 10 Buurten met Meeste Geselecteerde Woningen (per Type)</b>",
        labels={'value': 'Aantal Woningen', 'buurtNaam': 'Buurt', 'woningtype_label': 'Woningtype'},
        color_discrete_sequence=color_palette
    )
    top10_fig.update_layout(
        yaxis=dict(categoryorder='total ascending'),
        font=dict(family="system-ui", size=16),
        title_font=dict(family="system-ui", size=22),
        margin={"r": 0, "t": 50, "l": 0, "b": 0},
        legend_title_text=""
    )
    totaal_woningen = int(melted["value"].sum())
    aantal_projecten = melted["projectnaamAfkorting"].nunique()
    unieke_buurten = melted["buurtNaam"].nunique()
    gemiddeld_jaar = int(melted["startBouwGepland"].dt.year.mean())

    return map_fig, pie_fig, bar_fig, line_fig, top10_fig, \
           f"{totaal_woningen}", f"{aantal_projecten}", f"{unieke_buurten}", f"{gemiddeld_jaar}"

# --- Server starten for Render ---
if __name__ == '__main__':
    app.run_server(
        debug=False,
        host='0.0.0.0',
        port=int(os.environ.get("PORT", 8050))
    )
