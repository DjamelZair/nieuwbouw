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
    errors="coerce",  # fallback to NaT if parse fails
    utc=True         # ensure consistent timezone handling
)
# Log how many dates parsed successfully
parsed = df['startBouwGepland'].notna().sum()
total = len(df)
logging.debug("Dates parsed: %s non-NaT out of %s rows", parsed, total)

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
    dbc.Card([
        dbc.CardHeader("Selecteer woningtype", style={
            "fontSize": "24px", "textAlign": "center", "color": "#005354",
            "backgroundColor": "#e6f2f2", "fontWeight": "bold"
        }),
        dbc.CardBody([
            dbc.Checklist(
                id='woningtype-checklist',
                options=[{"label": label_map[k], "value": k} for k in woningtypes],
                value=woningtypes,
                switch=True,
                style={"fontSize": "18px", "color": "#005354"}
            )
        ])
    ], style={
        "marginBottom": "30px",
        "border": "1px solid #008080",
        "borderRadius": "12px",
        "boxShadow": "0 2px 8px rgba(0,0,0,0.05)",
        "backgroundColor": "#ffffff"
    }),
    html.Br(),
    dbc.Card([
        dbc.CardHeader("Filter op geplande startdatum (t/m jaar)", style={
            "fontSize": "24px", "textAlign": "center", "color": "#005354",
            "backgroundColor": "#e6f2f2", "fontWeight": "bold"
        }),
        dbc.CardBody([
            dbc.Label("Jaarfilter", html_for="jaar-slider", style={
                "textAlign": "center", "width": "100%", "fontSize": "18px", "color": "#005354", "marginBottom": "10px"
            }),
            dcc.Slider(
                id='jaar-slider',
                min=int(df["startBouwGepland"].dt.year.min()),
                max=int(df["startBouwGepland"].dt.year.max()),
                step=1,
                value=int(df["startBouwGepland"].dt.year.max()),
                marks={str(year): str(year) for year in sorted(df["startBouwGepland"].dt.year.dropna().unique())},
                tooltip={"placement": "bottom", "always_visible": True},
                included=False
            )
        ])
    ], style={
        "marginBottom": "30px",
        "border": "1px solid #008080",
        "borderRadius": "12px",
        "boxShadow": "0 2px 8px rgba(0,0,0,0.05)",
        "backgroundColor": "#ffffff"
    })
])

app.layout = html.Div([
    # HEADER
    html.Div([
        html.Div([html.Img(src=app.get_asset_url('LogoSite.drawio.png'), style={"height": "60px"})],
                 style={"flex": "1", "textAlign": "left"}),
        html.Div([html.H1("Woningbouw Plannen Amsterdam: Dashboard", style={
            'color': '#008080', 'font-family': 'system-ui',
            'padding': '20px', 'textAlign': 'center', 'fontSize': '36px', 'margin': '0'
        })], style={"flex": "2", "textAlign": "center"}),
        html.Div([], style={"flex": "1"})
    ], style={"display": "flex", "alignItems": "center", "justifyContent": "center", "backgroundColor": "#FFFFFF"}),

    # KPI BLOCK
    html.Div([
        html.Div([
            html.Div([html.H5("🏗️ Totaal Woningen"), html.P(id='kpi-totaal')], style={"width": "24%"}),
            html.Div([html.H5("📁 Aantal Projecten"), html.P(id='kpi-projecten')], style={"width": "24%"}),
            html.Div([html.H5("📍 Unieke Buurten"), html.P(id='kpi-buurten')], style={"width": "24%"}),
            html.Div([html.H5("📅 Gem. Startjaar"), html.P(id='kpi-gemjaar')], style={"width": "24%"})
        ], style={"display": "flex", "justifyContent": "space-around", "marginBottom": "10px"})
    ]),

    # MAIN BODY
    html.Div([
        # SIDEBAR
        html.Div([
            sidebar_cards,
            html.Hr(style={"borderTop": "1px solid #ddd", "margin": "20px 0"}),
            html.H4("Verdeling per Wijk"), dcc.Graph(id='pie-chart'),
            html.H4("Verdeling Woontypen per Wijk"), dcc.Graph(id='bar-chart')
        ], style={"width": "30%", "padding": "20px", "border": "1px solid #008080",
                  "borderRadius": "12px", "margin": "10px", "boxShadow": "0 2px 10px rgba(0,0,0,0.05)",
                  "backgroundColor": "#fff"}),

        # MAIN PANEL
        html.Div([
            html.H4("GeoLocatie Presentatie Nieuwbouw Plannen:"),
            dcc.RadioItems(
                id='map-type-toggle',
                options=[
                    {'label': '📍 Puntenkaart', 'value': 'scatter'},
                    {'label': '🔥 Heatmap', 'value': 'heatmap'}
                ],
                value='heatmap', labelStyle={'marginRight': '15px'}
            ),
            dcc.Graph(id='map'),
            html.H4("Aantal Woningen per Jaar (Gepland):"), dcc.Graph(id='line-chart'),
            html.H4("Top 10 Buurten per Type:"), dcc.Graph(id='top10-chart')
        ], style={"width": "70%", "padding": "20px", "border": "1px solid #008080",
                  "borderRadius": "12px", "margin": "10px", "boxShadow": "0 2px 10px rgba(0,0,0,0.05)",
                  "backgroundColor": "#fff"})
    ], style={"display": "flex", "flexDirection": "row", "alignItems": "start"})
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
    if not selected_types:
        return tuple(dash.no_update for _ in range(9))

    # Filter by year, after ensuring date parsing
    filtered_df = df[df["startBouwGepland"].dt.year <= int(selected_year)].copy()
    logging.debug("Filtered by year <= %s: %s rows", selected_year, len(filtered_df))

    # If no valid dates remain, bail early
    if filtered_df["startBouwGepland"].notna().sum() == 0:
        logging.warning("All dates are NaT after filtering by year in production")
        empty_fig = px.line()
        empty_fig.add_annotation(text="No valid dates", xref="paper", yref="paper", showarrow=False)
        return (empty_fig, empty_fig, empty_fig, empty_fig, empty_fig, "0", "0", "0", "0")

    # Melt and filter values
    id_vars = ["lat", "lon", "projectnaamAfkorting", "stadsdeelNaam",
               "wijkNaam", "buurtNaam", "startBouwGepland"]
    melted = filtered_df.melt(id_vars=id_vars, value_vars=selected_types)
    melted = melted[melted["value"] > 0]
    melted["woningtype_label"] = melted["variable"].map(label_map)
    logging.debug("After melt & >0 filter: %s rows", len(melted))

    if melted.empty:
        logging.warning("Melted DataFrame is empty after value filter")
        empty_fig = px.bar()
        empty_fig.add_annotation(text="No data for selected filters",
                                 xref="paper", yref="paper", showarrow=False)
        return (empty_fig, empty_fig, empty_fig, empty_fig, empty_fig, "0", "0", "0", "0")

    # Map figure
    if map_type == "heatmap":
        try:
            map_fig = px.density_mapbox(
                melted, lat="lat", lon="lon", z="value", radius=25,
                center=dict(lat=52.37, lon=4.89), zoom=11,
                mapbox_style="carto-positron", title="Woningbouw Dichtheid",
                color_continuous_scale="Teal"
            )
        except Exception as e:
            logging.error("density_mapbox error: %s", e)
            map_fig = px.scatter_mapbox()
            map_fig.add_annotation(text="Heatmap error", xref="paper", yref="paper", showarrow=False)
    else:
        map_fig = px.scatter_mapbox(
            melted, lat="lat", lon="lon", color="woningtype_label",
            hover_name="projectnaamAfkorting", hover_data=["stadsdeelNaam", "startBouwGepland"],
            mapbox_style="open-street-map", zoom=11, height=500,
            color_discrete_sequence=color_palette
        )
        map_fig.update_traces(marker=dict(size=15))

    map_fig.update_layout(margin={"r":0,"t":50,"l":0,"b":0}, font=dict(size=16))

    # Pie chart
    wijk_data = melted.groupby(['wijkNaam','woningtype_label'])['value'].sum().reset_index()
    pie_fig = px.pie(wijk_data, names='wijkNaam', values='value',
                     color_discrete_sequence=color_palette)
    pie_fig.update_layout(font=dict(size=16))

    # Bar chart
    bar_data = melted.groupby(['wijkNaam','woningtype_label'])['value'].sum().reset_index()
    bar_fig = px.bar(bar_data, x="wijkNaam", y="value", color="woningtype_label",
                     barmode="group", color_discrete_sequence=color_palette,
                     labels={"value":"Aantal woningen","wijkNaam":"Wijk"})
    bar_fig.update_layout(font=dict(size=16), xaxis_tickangle=-45)

    # Line chart
    data = filtered_df.dropna(subset=["startBouwGepland"]).copy()
    data['jaar'] = data["startBouwGepland"].dt.year
    grouped = data.groupby('jaar')[selected_types].sum().reset_index()
    logging.debug("Grouped line data shape: %s", grouped.shape)
    if grouped.empty:
        line_fig = px.line()
        line_fig.add_annotation(text="No data for line chart", xref="paper", yref="paper", showarrow=False)
    else:
        if len(selected_types) == 1:
            line_fig = px.line(grouped, x='jaar', y=selected_types[0],
                               markers=True, labels={'jaar':'Jaar', selected_types[0]:'Aantal'})
        else:
            ml = grouped.melt(id_vars='jaar', value_vars=selected_types,
                              var_name='woningtype', value_name='aantal')
            ml['woningtype_label'] = ml['woningtype'].map(label_map)
            line_fig = px.line(ml, x='jaar', y='aantal', color='woningtype_label',
                               markers=True, labels={'jaar':'Jaar','aantal':'Aantal'})
    line_fig.update_layout(font=dict(size=16), xaxis=dict(dtick=1))

    # Top 10 buurten
    buurt_data = melted.groupby(['buurtNaam','woningtype_label'])['value'].sum().reset_index()
    top_b = buurt_data.groupby('buurtNaam')['value'].sum().nlargest(10).index
    top10 = buurt_data[buurt_data['buurtNaam'].isin(top_b)]
    top10_fig = px.bar(top10, x='value', y='buurtNaam', color='woningtype_label',
                       orientation='h', labels={'value':'Aantal','buurtNaam':'Buurt'},
                       color_discrete_sequence=color_palette)
    top10_fig.update_layout(font=dict(size=16), yaxis=dict(categoryorder='total ascending'))

    # KPIs
    totaal = int(melted['value'].sum())
    projecten = melted['projectnaamAfkorting'].nunique()
    buurten = melted['buurtNaam'].nunique()
    gemjaar = int(melted['startBouwGepland'].dt.year.mean())

    return map_fig, pie_fig, bar_fig, line_fig, top10_fig, f"{totaal}", f"{projecten}", f"{buurten}", f"{gemjaar}"

# --- Server starten for Render ---
if __name__ == '__main__':
    app.run_server(
        debug=False,
        host='0.0.0.0',
        port=int(os.environ.get("PORT", 8050))
    )
