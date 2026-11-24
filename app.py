import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import folium
from folium.plugins import MarkerCluster, HeatMap
from streamlit_folium import st_folium
import re
import json
import pydeck as pdk
import numpy as np
from scipy.interpolate import griddata, Rbf
import matplotlib.pyplot as plt
import io
import base64
import math
import requests
import branca.colormap as cm

try:
    from sklearn.ensemble import RandomForestRegressor
    ML_DISPONIBLE = True
except ImportError:
    ML_DISPONIBLE = False

try:
    from fpdf import FPDF
    PDF_DISPONIBLE = True
except ImportError:
    PDF_DISPONIBLE = False

try:
    from pykrige.ok import OrdinaryKriging
    KRIGING_DISPONIBLE = True
except ImportError:
    KRIGING_DISPONIBLE = False

# ==========================================
# 1. CONFIGURACIÓN Y CONSTANTES
# ==========================================
st.set_page_config(page_title="AshViewer-CVLC", layout="wide")

st.markdown("""
    <style>
    .main {background-color: transparent;}
    div[data-testid="metric-container"] {
        background-color: #FFFFFF !important;
        border: 1px solid #EAEAEA !important;
        padding: 15px !important;
        border-radius: 10px !important;
        box-shadow: 2px 2px 5px rgba(0,0,0,0.05) !important;
    }
    div[data-testid="metric-container"] * { color: #2C3E50 !important; }
    </style>
    """, unsafe_allow_html=True)

# PALETA SEMÁNTICA OFICIAL
color_map_paper = {
    "Fragmentos vesiculados frescos": "#A9C1D9",
    "Fragmentos vesiculados alterados": "#E68A8A",
    "Cristales": "#FCF5D8",
    "Líticos volcánicos frescos": "#8E8E8E",
    "Líticos volcánicos alterados": "#7CB342",
    "Líticos no volcánicos frescos": "#8E44AD",
    "Líticos no volcánicos alterados": "#C0392B",
    "Otros": "#2980B9"
}

ORDEN_APILADO_MACRO = [
    "Fragmentos vesiculados frescos",
    "Fragmentos vesiculados alterados",
    "Cristales",
    "Líticos volcánicos frescos",
    "Líticos volcánicos alterados",
    "Líticos no volcánicos frescos",
    "Líticos no volcánicos alterados",
    "Otros"
]

colores_profesionales = px.colors.qualitative.Pastel
LAT_CRATER = 2.313377
LON_CRATER = -76.395088
DIRECCIONES_BRUJULA = [
    'N', 'NNE', 'NE', 'ENE', 'E', 'ESE', 'SE', 'SSE',
    'S', 'SSW', 'SW', 'WSW', 'W', 'WNW', 'NW', 'NNW'
]

# ==========================================
# 2. FUNCIONES MATEMÁTICAS Y AUXILIARES
# ==========================================
def limpiar_coordenada(valor):
    if pd.isna(valor):
        return np.nan
    val_str = str(valor).strip().upper().replace(',', '.')
    try:
        return float(val_str)
    except ValueError:
        pass
    numeros = re.findall(r"[\d\.]+", val_str)
    if not numeros:
        return np.nan
    dec = float(numeros[0])
    if len(numeros) > 1:
        dec += float(numeros[1]) / 60.0
    if len(numeros) > 2:
        dec += float(numeros[2]) / 3600.0
    if any(signo in val_str for signo in ['-', 'S', 'W', 'O']):
        dec = -dec
    return dec

def operaciones_geoespaciales_vectorizadas(lats, lons):
    R = 6371.0
    lat1, lon1 = np.radians(LAT_CRATER), np.radians(LON_CRATER)
    lat2, lon2 = np.radians(lats.astype(float)), np.radians(lons.astype(float))
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = np.sin(dlat / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin(dlon / 2) ** 2
    c = 2 * np.arctan2(np.sqrt(a), np.sqrt(1 - a))
    distancias = np.round(R * c, 2)

    x = np.sin(dlon) * np.cos(lat2)
    y = np.cos(lat1) * np.sin(lat2) - (np.sin(lat
