# --- Imports en setup ---
import os
import requests
import pandas as pd
import numpy as np
import json
from dotenv import load_dotenv
from pyproj import Transformer
import dash
from dash import dcc, html, Output, Input
import plotly.express as px

# --- API call ---
load_dotenv()
api_key = os.getenv("GEMEENTE_API_KEY")
api_url = "https://api.data.amsterdam.nl/v1/nieuwbouwplannen/woningbouwplannen_openbaar/"
headers = {"X-Api-Key": api_key}
response = requests.get(api_url, headers=headers)
data = response.json()['_embedded']['woningbouwplannen_openbaar']
df = pd.json_normalize(data)

# --- Geometrie voorbereiden ---
def safe_load(x):
    try:
        return json.loads(x) if isinstance(x, str) else x
    except:
        return None

df['geometrie.coordinates'] = df['geometrie.coordinates'].apply(safe_load)

def extract_centroid(multipolygon):
    try:
        coords = np.array(multipolygon[0][0])
        lon = coords[:, 0].mean()
        lat = coords[:, 1].mean()
        return pd.Series({'lon': lon, 'lat': lat})
    except:
        return pd.Series({'lon': None, 'lat': None})

df[['lon', 'lat']] = df['geometrie.coordinates'].apply(extract_centroid)

# --- RD naar WGS84 ---
transformer = Transformer.from_crs("EPSG:28992", "EPSG:4326", always_xy=True)
def convert_rd_to_wgs84(row):
    try:
        lon, lat = transformer.transform(row['lon'], row['lat'])
        return pd.Series({'lon': lon, 'lat': lat})
    except:
        return pd.Series({'lon': None, 'lat': None})
df[['lon', 'lat']] = df[['lon', 'lat']].apply(convert_rd_to_wgs84, axis=1)

# --- Kolommen voorbereiden ---
woningtypes = ["socialeHuurZelfstPerm", "middeldureHuur", "vrijeSectorKoop"]
df[woningtypes] = df[woningtypes].apply(pd.to_numeric, errors="coerce")
df["startBouwGepland"] = pd.to_datetime(df["startBouwGepland"], errors="coerce")
df["projectnaamAfkorting"] = df["projectnaamAfkorting"].apply(
    lambda x: x.split('/')[1].split('-')[0] if isinstance(x, str) and '/' in x else x)
df = df.dropna(subset=['lon', 'lat'])

# --- Labels & kleuren ---
color_palette = ['#008080', '#66b2b2', '#FF6F61', '#F4E1D2', '#2E3A59']
label_map = {
    "socialeHuurZelfstPerm": "Sociale Huur",
    "middeldureHuur": "Middeldure Huur",
    "vrijeSectorKoop": "Vrije Sector Koop"
}

# --- Dash setup ---
app = dash.Dash(__name__)
server = app.server
app.layout = html.Div([
    # HEADER
    html.Div([
    html.Div([
        html.Img(
            src=app.get_asset_url('LogoSite.drawio.png'),
            style={"height": "60px"}
        )
    ], style={"flex": "1", "textAlign": "left"}),

    html.Div([
        html.H1("Woningbouw Plannen Amsterdam: Dashboard", style={
            'color': '#008080',
            'font-family': 'system-ui',
            'padding': '20px',
            'textAlign': 'center',
            'fontSize': '36px',
            'margin': '0'
        })
    ], style={"flex": "2", "textAlign": "center"}),

    html.Div([], style={"flex": "1"})  # spacer div to balance the layout
], style={"display": "flex", "alignItems": "center", "justifyContent": "center", "backgroundColor": "#FFFFFF"}),


    # KPI BLOK
    html.Div([
        html.Div([
            html.Div([
                html.H5("🏗️ Totaal Woningen", style={"textAlign": "center"}),
                html.P(id='kpi-totaal', style={
                    "textAlign": "center", "fontSize": "30px", "color": "#008080"
                })
            ], style={"width": "24%"}),

            html.Div([
                html.H5("📁 Aantal Projecten", style={"textAlign": "center"}),
                html.P(id='kpi-projecten', style={
                    "textAlign": "center", "fontSize": "30px", "color": "#008080"
                })
            ], style={"width": "24%"}),

            html.Div([
                html.H5("📍 Unieke Buurten", style={"textAlign": "center"}),
                html.P(id='kpi-buurten', style={
                    "textAlign": "center", "fontSize": "30px", "color": "#008080"
                })
            ], style={"width": "24%"}),

            html.Div([
                html.H5("📅 Gem. Startjaar", style={"textAlign": "center"}),
                html.P(id='kpi-gemjaar', style={
                    "textAlign": "center", "fontSize": "30px", "color": "#008080"
                })
            ], style={"width": "24%"})
        ], style={"display": "flex", "justifyContent": "space-around", "padding": "1px 2px", "marginBottom": "2px"})
    ]),

    # MAIN BODY
    html.Div([
        # SIDEBAR
        html.Div([
            html.H4("Selecteer woningtype:", style={
                "fontSize": "30px", 'textAlign': 'center', "color": "#005354"
            }),
            dcc.Checklist(
                id='woningtype-checklist',
                options=[{"label": label_map[k], "value": k} for k in woningtypes],
                value=woningtypes,
                labelStyle={
                    "display": "block",
                    "marginBottom": "12px",
                    "padding": "8px 12px",
                    "border": "1px solid #008080",
                    "borderRadius": "8px",
                    "backgroundColor": "#f2fdfa",
                    "cursor": "pointer"
                },
                inputStyle={
                    "marginRight": "12px",
                    "height": "18px",
                    "width": "18px"
                },
                style={
                    "fontSize": "18px",
                    "color": "#005354",
                    "fontFamily": "system-ui",
                    "padding": "12px"
                }
            ),

            html.H4("Filter op geplande startdatum (t/m jaar):", style={
                "fontSize": "30px", 'textAlign': 'center', "color": "#005354", "marginTop": "20px"
            }),

        html.Div([
            html.Div("Jaar filter", style={
                "textAlign": "center",
                "fontWeight": "bold",
                "fontSize": "18px",
                "color": "#005354",
                "marginBottom": "10px"
            }),
            dcc.Slider(
                id='jaar-slider',
                min=df["startBouwGepland"].dt.year.min(),
                max=df["startBouwGepland"].dt.year.max(),
                step=1,
                value=df["startBouwGepland"].dt.year.max(),
                marks={str(year): str(year) for year in sorted(df["startBouwGepland"].dt.year.dropna().unique())},
                tooltip={"placement": "bottom", "always_visible": True},
                included=False
            )
        ], style={
            "padding": "20px",
            "backgroundColor": "#f9f9f9",
            "border": "1px solid #ccc",
            "borderRadius": "10px",
            "marginBottom": "30px"
        }),

            html.Hr(style={"borderTop": "1px solid #ddd", "margin": "20px 0"}),

            html.H4("Verdeling per Wijk", style={
                "fontSize": "25px", 'textAlign': 'center', "color": "#005354"
            }),
            dcc.Graph(id='pie-chart'),

            html.H4("Verdeling Woontypen per Wijk", style={
                "fontSize": "25px", 'textAlign': 'center', "color": "#005354"
            }),
            dcc.Graph(id='bar-chart', style={"marginTop": "30px"})
        ], style={
            "width": "30%", "padding": "20px",
            "border": "1px solid #008080", "borderRadius": "12px", "margin": "10px",
            "boxShadow": "0 2px 10px rgba(0, 0, 0, 0.05)", "backgroundColor": "#fff"
        }),

        # MAIN PANEL
        html.Div([
            html.H4("GeoLocatie Presentatie Nieuwbouw Plannen:", style={
                "fontSize": "30px", 'textAlign': 'center', "color": "#005354"
            }),
            dcc.RadioItems(
                id='map-type-toggle',
                options=[
                    {'label': '📍 Puntenkaart', 'value': 'scatter'},
                    {'label': '🔥 Heatmap', 'value': 'heatmap'}
                ],
                value='heatmap',
                labelStyle={'marginRight': '15px', 'fontSize': '18px'},
                inputStyle={'marginRight': '6px'},
                style={'display': 'flex', 'justifyContent': 'center', 'marginBottom': '10px'}
            ),
            dcc.Graph(id='map'),
            html.H4("Aantal Woningen per Jaar (Gepland):", style={
                "fontSize": "24px",
                "textAlign": "center",
                "color": "#005354",
                "marginBottom": "6px",
                "marginTop": "16px"
            }),
            dcc.Graph(id='line-chart'),

            html.H4("Top 10 Buurten per Type:", style={
                "fontSize": "24px", 
                'textAlign': 'center', 
                "color": "#005354",
                "marginBottom": "2px",  # kleiner maken
                "marginTop": "20px"
            }),
            dcc.Graph(id='top10-chart')
        ], style={
            "width": "70%", "padding": "20px",
            "border": "1px solid #008080", "borderRadius": "12px", "margin": "10px",
            "boxShadow": "0 2px 10px rgba(0, 0, 0, 0.05)", "backgroundColor": "#fff"
        })
    ], style={"display": "flex", "flexDirection": "row", "alignItems": "start"})
])



# --- Callback voor map, pie en line chart ---
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
        return dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update

    # --- FILTER DATA OP GEKOZEN JAAR ---
    filtered_df = df[df["startBouwGepland"].dt.year <= selected_year].copy()

    # --- Melt op basis van selectie ---
    id_vars = ["lat", "lon", "projectnaamAfkorting", "stadsdeelNaam", "wijkNaam", "buurtNaam", "startBouwGepland"]
    melted = filtered_df.melt(id_vars=id_vars, value_vars=selected_types)
    melted = melted[melted["value"] > 0]
    melted["woningtype_label"] = melted["variable"].map(label_map)
    if map_type == "heatmap":
        map_fig = px.density_mapbox(
            melted,
            lat="lat",
            lon="lon",
            z="value",
            radius=25,
            center=dict(lat=52.37, lon=4.89),
            zoom=11,
            mapbox_style="carto-positron",
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
        font=dict(family="system-ui", size=16),
        title_font=dict(family="system-ui", size=22),
        legend_font=dict(size=18)
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

    # --- Line Chart: geplande woningen per jaar ---
    data = filtered_df.dropna(subset=["startBouwGepland"]).copy()
    data['jaar'] = data["startBouwGepland"].dt.year
    grouped = data.groupby('jaar')[selected_types].sum().reset_index()

    if len(selected_types) == 1:
        line_fig = px.line(
            grouped,
            x='jaar',
            y=selected_types[0],
            markers=True,
            #title=f"<b>Aantal {label_map[selected_types[0]]} per Jaar (Gepland)</b>",
            labels={'jaar': 'Jaar', selected_types[0]: 'Aantal Woningen'},
            color_discrete_sequence=[color_palette[woningtypes.index(selected_types[0])]]
        )
    else:
        melted_line = grouped.melt(id_vars='jaar', value_vars=selected_types,
                                   var_name='woningtype', value_name='aantal')
        melted_line['woningtype_label'] = melted_line['woningtype'].map(label_map)

        line_fig = px.line(
            melted_line,
            x='jaar',
            y='aantal',
            color='woningtype_label',
            markers=True,
            #title="<b>Aantal Woningen per Jaar (Gepland)</b>",
            labels={'jaar': 'Jaar', 'aantal': 'Aantal Woningen'},
            color_discrete_sequence=color_palette
        )

    line_fig.update_layout(
        margin={"r": 0, "t": 50, "l": 0, "b": 0},
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
           f"{totaal_woningen:,}", \
           f"{aantal_projecten}", \
           f"{unieke_buurten}", \
           f"{gemiddeld_jaar}"


# --- Server starten ---
if __name__ == '__main__':
    app.run_server(debug=False, host='0.0.0.0', port=int(os.environ.get("PORT", 8050)))

