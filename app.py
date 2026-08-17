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
import os
from urllib.parse import unquote, urlparse
import numpy as np
from scipy.interpolate import griddata, Rbf
import matplotlib.pyplot as plt
import io
import base64
import math
import branca.colormap as cm
import requests

# Importación de Machine Learning
try:
    from sklearn.ensemble import RandomForestRegressor
    ML_DISPONIBLE = True
except ImportError:
    ML_DISPONIBLE = False

# Importar FPDF de forma segura
try:
    from fpdf import FPDF
    PDF_DISPONIBLE = True
except ImportError:
    PDF_DISPONIBLE = False

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

color_map_oficial = {
    "LV1": "#555555", "LVA1": "#8B4513", "Plagioclasa": "#D3D3D3", 
    "Cuarzo": "#F5F5F5", "FV1": "#FF8C00", "Epidotas": "#9ACD32", "Otros_Cristales": "#9370DB"
}
colores_profesionales = px.colors.qualitative.Pastel

LAT_CRATER = 2.313377
LON_CRATER = -76.395088

# ==========================================
# 2. FUNCIONES MATEMÁTICAS, APIs Y AUXILIARES
# ==========================================

# NUEVA FUNCIÓN: Traductor Universal de Coordenadas de Google Earth a Decimal
def limpiar_coordenada(valor):
    if pd.isna(valor): return np.nan
    val_str = str(valor).strip().upper().replace(',', '.')
    
    # Si ya es un número decimal, pasarlo directamente
    try: return float(val_str)
    except ValueError: pass
    
    # Extraer los números (Grados, Minutos, Segundos)
    numeros = re.findall(r"[\d\.]+", val_str)
    if not numeros: return np.nan
    
    dec = float(numeros[0])
    if len(numeros) > 1: dec += float(numeros[1]) / 60.0
    if len(numeros) > 2: dec += float(numeros[2]) / 3600.0
    
    # Si tiene S (Sur), W (West), O (Oeste) o un guión, es negativo
    if '-' in val_str or 'S' in val_str or 'W' in val_str or 'O' in val_str:
        dec = -dec
        
    return dec

def operaciones_geoespaciales_vectorizadas(lats, lons):
    R = 6371.0 
    lat1, lon1, lat2, lon2 = map(np.radians, [LAT_CRATER, LON_CRATER, lats, lons])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = np.sin(dlat/2)**2 + np.cos(lat1) * np.cos(lat2) * np.sin(dlon/2)**2
    c = 2 * np.arctan2(np.sqrt(a), np.sqrt(1-a))
    distancias = np.round(R * c, 2)
    
    x = np.sin(dlon) * np.cos(lat2)
    y = np.cos(lat1) * np.sin(lat2) - (np.sin(lat1) * np.cos(lat2) * np.cos(dlon))
    initial_bearing = np.arctan2(x, y)
    brng = (np.degrees(initial_bearing) + 360) % 360
    
    dirs = np.array(['N', 'NNE', 'NE', 'ENE', 'E', 'ESE', 'SE', 'SSE', 'S', 'SSW', 'SW', 'WSW', 'W', 'WNW', 'NW', 'NNW'])
    ix = np.round(brng / (360. / len(dirs))).astype(int)
    direcciones = dirs[ix % len(dirs)]
    
    return distancias, direcciones

def clasificar_riesgo_vectorizado(espesores):
    condiciones = [pd.isna(espesores) | (espesores == 0), espesores < 1, espesores <= 5, espesores > 5]
    opciones = ['⚪ N/A', '🟢 Bajo (< 1mm)', '🟠 Medio (1-5mm)', '🔴 Alto (> 5mm)']
    return np.select(condiciones, opciones, default='⚪ N/A')

@st.cache_data(ttl=600, show_spinner=False)
def obtener_clima_crater_actual():
    try:
        url = f"https://api.open-meteo.com/v1/forecast?latitude={LAT_CRATER}&longitude={LON_CRATER}&current=wind_speed_10m,wind_direction_10m"
        r = requests.get(url, timeout=5)
        if r.status_code == 200:
            data = r.json()['current']
            velocidad = data['wind_speed_10m']
            grados = data['wind_direction_10m']
            dirs = ['N', 'NNE', 'NE', 'ENE', 'E', 'ESE', 'SE', 'SSE', 'S', 'SSW', 'SW', 'WSW', 'W', 'WNW', 'NW', 'NNW']
            ix = int(round(grados / (360. / len(dirs))))
            direccion = dirs[ix % len(dirs)]
            return velocidad, direccion
    except:
        return None, None
    return None, None

def obtener_url_imagen(url_original):
    url_limpia = str(url_original).strip()
    if "|" in url_limpia: url_limpia = url_limpia.split("|")[1].strip()
    if "drive.google.com" in url_limpia:
        match = re.search(r'[-\w]{25,}', url_limpia)
        if match: return f"https://lh3.googleusercontent.com/d/{match.group(0)}"
    return url_limpia

# ==========================================
# 3. MOTOR DE DATOS CLOUD & CACHÉ
# ==========================================
@st.cache_data(show_spinner="Descargando y optimizando base de datos...")
def cargar_y_limpiar_datos(archivo, url_gs, usar_sql=False):
    df_temp = None
    
    if usar_sql:
        try:
            conn = st.connection("sql")
            df_temp = conn.query("SELECT * FROM muestras_ceniza;", ttl="10m")
            st.toast("Conectado a Base de Datos SQL exitosamente.", icon="✅")
        except Exception:
            st.toast("No se detectó configuración SQL. Usando métodos alternativos.", icon="⚠️")
    
    if df_temp is None:
        if archivo is not None:
            df_temp = pd.read_csv(archivo) if archivo.name.endswith('.csv') else pd.read_excel(archivo)
        elif url_gs:
            try:
                match = re.search(r'/d/([a-zA-Z0-9-_]+)', url_gs)
                if match: df_temp = pd.read_csv(f"https://docs.google.com/spreadsheets/d/{match.group(1)}/export?format=csv")
            except Exception: pass 
            
    if df_temp is None:
        datos_prueba = {
            'ID_Muestra': ['CAP-01', 'CAP-02', 'CAP-03', 'CAP-04'], 'Localizacion': ['Chapio', 'Quintana', 'Coconuco', 'Puracé'],
            'Latitud': ["2°18'48\"N", "2.450", "2.341", "2.355"], 'Longitud': ["76°23'42\"W", "-76.610", "-76.510", "-76.500"],
            'Tamaño_Promedio_mm': [0.5, 0.8, 2.1, 1.5], 'Espesor_Deposito_mm': [0.5, 3, 8, 12],
            'Fecha_Recoleccion': ['2026-08-01', '2026-08-05', '2026-08-10', '2026-08-11'],
            'LV1': [50, 20, 10, 30], 'LVA1': [28, 15, 5, 20], 'Plagioclasa': [69, 40, 10, 25], 'FV1': [20, 50, 80, 15], 'Cuarzo': [2, 5, 0, 10],
            'URLs_Fotos': ['', '', '', ''], 'Enlace_Reporte': ['', '', '', '']
        }
        df_temp = pd.DataFrame(datos_prueba)

    sinonimos = {
        'Lat': 'Latitud', 'LATITUD': 'Latitud', 'lat': 'Latitud', 'Lon': 'Longitud', 'LONGITUD': 'Longitud', 'lng': 'Longitud',
        'Fecha': 'Fecha_Recoleccion', 'fecha': 'Fecha_Recoleccion', 'Date': 'Fecha_Recoleccion',
        'Tamaño': 'Tamaño_Promedio_mm', 'Tamano': 'Tamaño_Promedio_mm', 'Espesor': 'Espesor_Deposito_mm',
        'Localidad': 'Localizacion', 'Vereda': 'Localizacion', 'Localizacion': 'Localizacion', 'Muestra': 'ID_Muestra', 'ID': 'ID_Muestra', 'Fotos': 'URLs_Fotos', 'Reporte': 'Enlace_Reporte'
    }
    df_temp = df_temp.rename(columns=lambda x: sinonimos.get(str(x).strip(), x))
    
    if 'Fecha_Recoleccion' in df_temp.columns:
        df_temp['Fecha_Recoleccion'] = pd.to_datetime(df_temp['Fecha_Recoleccion'], errors='coerce')

    # LIMPIEZA DE COORDENADAS ANTES DE MATEMÁTICAS
    if 'Latitud' in df_temp.columns:
        df_temp['Latitud'] = df_temp['Latitud'].apply(limpiar_coordenada)
    if 'Longitud' in df_temp.columns:
        df_temp['Longitud'] = df_temp['Longitud'].apply(limpiar_coordenada)

    # Forzar a numérico y borrar nulos de coordenadas (filtro vital)
    if 'Latitud' in df_temp.columns and 'Longitud' in df_temp.columns:
        df_temp['Latitud'] = pd.to_numeric(df_temp['Latitud'], errors='coerce')
        df_temp['Longitud'] = pd.to_numeric(df_temp['Longitud'], errors='coerce')
        
        df_temp = df_temp.dropna(subset=['Latitud', 'Longitud'])

        distancias, direcciones = operaciones_geoespaciales_vectorizadas(df_temp['Latitud'].values, df_temp['Longitud'].values)
        df_temp['Distancia_Crater_km'] = distancias
        df_temp['Direccion_Viento'] = direcciones
        
    if 'Espesor_Deposito_mm' in df_temp.columns:
        df_temp['Nivel_Riesgo'] = clasificar_riesgo_vectorizado(df_temp['Espesor_Deposito_mm'])

    cols_info = ['ID_Muestra', 'Localizacion', 'Latitud', 'Longitud', 'Tamaño_Promedio_mm', 'Espesor_Deposito_mm', 'URLs_Fotos', 'URL_Microscopio', 'Fecha_Recoleccion', 'Enlace_Reporte', 'Direccion_Viento', 'Distancia_Crater_km', 'Nivel_Riesgo']
    cols_conteo = [col for col in df_temp.columns if col not in cols_info]
    
    for col in cols_conteo + ['Tamaño_Promedio_mm', 'Espesor_Deposito_mm', 'Distancia_Crater_km']:
        if col in df_temp.columns: df_temp[col] = pd.to_numeric(df_temp[col], errors='coerce').fillna(0)

    df_temp['Total_Granos'] = df_temp[cols_conteo].sum(axis=1)
    
    df_pct_temp = df_temp.copy()
    if not df_temp[cols_conteo].empty:
        df_pct_temp[cols_conteo] = df_temp[cols_conteo].div(df_temp['Total_Granos'].replace(0, 1), axis=0) * 100

    return df_temp, df_pct_temp, cols_conteo

@st.cache_data(show_spinner="Calculando modelo de interpolación espacial...")
def calcular_modelo_espacial(lon, lat, z, metodo_interp, resolucion):
    margen_lon, margen_lat = (lon.max() - lon.min()) * 0.2 if lon.max() != lon.min() else 0.05, (lat.max() - lat.min()) * 0.2 if lat.max() != lat.min() else 0.05
    lim_lon_min, lim_lon_max = lon.min() - margen_lon, lon.max() + margen_lon
    lim_lat_min, lim_lat_max = lat.min() - margen_lat, lat.max() + margen_lat
    
    grid_lon, grid_lat = np.mgrid[lim_lon_min:lim_lon_max:complex(0, resolucion), lim_lat_min:lim_lat_max:complex(0, resolucion)]
    
    if "RBF" in metodo_interp:
        rbf_func = Rbf(lon, lat, z, function='multiquadric', smooth=0.1)
        grid_z = rbf_func(grid_lon, grid_lat)
    elif "Cúbica" in metodo_interp:
        try: grid_z = griddata((lon, lat), z, (grid_lon, grid_lat), method='cubic')
        except: grid_z = griddata((lon, lat), z, (grid_lon, grid_lat), method='linear')
    else:
        grid_z = griddata((lon, lat), z, (grid_lon, grid_lat), method='linear')
    
    grid_z = np.clip(grid_z, 0, z.max() * 1.2)
    return grid_lon, grid_lat, grid_z, lim_lon_min, lim_lon_max, lim_lat_min, lim_lat_max

# ==========================================
# 4. MÓDULOS MACRO-PESTAÑAS
# ==========================================

def renderizar_kpis(df_fil, cols_conteo):
    try:
        m_count = len(df_fil)
        max_esp = df_fil['Espesor_Deposito_mm'].max() if 'Espesor_Deposito_mm' in df_fil.columns else 0
        min_dom = df_fil[cols_conteo].sum().idxmax() if not df_fil[cols_conteo].empty else "N/A"
        dir_dom = df_fil['Direccion_Viento'].mode()[0] if 'Direccion_Viento' in df_fil.columns and not df_fil['Direccion_Viento'].empty else "N/A"
        
        if not df_fil[cols_conteo].empty and df_fil[cols_conteo].sum().sum() > 0:
            pct_dom = round((df_fil[cols_conteo].sum().max() / df_fil[cols_conteo].sum().sum()) * 100, 1)
        else: pct_dom = 0
            
        st.info(f"**📝 Resumen Analítico Automatizado:** Bajo los parámetros actuales, se analizaron **{m_count} muestras** con un espesor máximo de **{max_esp} mm**. La dispersión predominante indica un transporte de ceniza hacia el **{dir_dom}**. Mineralógicamente, el depósito está dominado por **{min_dom}** (aprox. {pct_dom}% del total analizado).")

        k1, k2, k3, k4 = st.columns(4)
        k1.metric("Muestras Analizadas", m_count)
        k2.metric("Espesor Máximo (mm)", max_esp)
        k3.metric("Mineral Dominante", min_dom)
        k4.metric("Dispersión Predominante", dir_dom)
        st.markdown("---")
    except Exception as e: st.error(f"⚠️ Error al renderizar KPIs: {e}")

def renderizar_modulo_espacial(df_fil, archivo_geo):
    try:
        st.subheader("Análisis Geoespacial y Predictivo")
        st.markdown("<small><i>Navega por las pestañas para ver las diferentes capas y modelos generados.</i></small>", unsafe_allow_html=True)
        
        df_mapa = df_fil.dropna(subset=['Latitud', 'Longitud']).copy()
        if df_mapa.empty: return st.warning("No hay datos con coordenadas válidas.")
        c_lat, c_lon = df_mapa['Latitud'].mean(), df_mapa['Longitud'].mean()

        tab_base, tab_geo, tab_sim = st.tabs(["🗺️ Cartografía Base", "📐 Modelos (Isopacas/Isopletas)", "🤖 Simulaciones (IA/Tiempo)"])
        
        with tab_base:
            tipo_mapa_base = st.radio("Capa a visualizar:", ["📍 Puntos (2D)", "🔥 Dispersión (2D)", "🌋 Vista 3D (Volumen)"], horizontal=True)
            
            if "3D" in tipo_mapa_base:
                df_3d = df_mapa.dropna(subset=['Espesor_Deposito_mm']).copy()
                if df_3d.empty: st.warning("Sin datos de 'Espesor_Deposito_mm' para construir 3D.")
                else:
                    df_3d['Elev_V'] = df_3d['Espesor_Deposito_mm'] * 150 
                    capa = pdk.Layer('ColumnLayer', data=df_3d, get_position='[Longitud, Latitud]', get_elevation='Elev_V', radius=150, get_fill_color='[200, 30, 30, 180]', pickable=True, auto_highlight=True)
                    crater_layer = pdk.Layer('ScatterplotLayer', data=[{'lat': LAT_CRATER, 'lon': LON_CRATER}], get_position='[lon, lat]', get_color='[255, 0, 0, 255]', get_radius=500, pickable=True)
                    vista = pdk.ViewState(longitude=c_lon, latitude=c_lat, zoom=10.5, pitch=55, bearing=20)
                    st.pydeck_chart(pdk.Deck(layers=[capa, crater_layer], initial_view_state=vista, tooltip={"html": "<b>Muestra</b>", "style": {"color": "white"}}, map_style='dark'), use_container_width=True)
            else:
                m_base = folium.Map(location=[c_lat, c_lon], zoom_start=11, tiles='CartoDB positron')
                folium.TileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Topo_Map/MapServer/tile/{z}/{y}/{x}', attr='Esri', overlay=False).add_to(m_base)
                folium.Marker([LAT_CRATER, LON_CRATER], tooltip="🌋 Cráter Volcán Puracé", icon=folium.Icon(color="red", icon="fire")).add_to(m_base)
                
                if archivo_geo: folium.GeoJson(json.load(archivo_geo), style_function=lambda f: {'fillColor': '#2980B9', 'color': '#2C3E50', 'weight': 1.5, 'fillOpacity': 0.15}).add_to(m_base)
                
                if "Puntos" in tipo_mapa_base:
                    mc = MarkerCluster().add_to(m_base)
                    for _, r in df_mapa.iterrows():
                        html = f"<b>{r.get('ID_Muestra', 'N/A')}</b><br>Espesor: {r.get('Espesor_Deposito_mm', 0)} mm<br>Distancia: {r.get('Distancia_Crater_km', 0)} km"
                        folium.Marker([r['Latitud'], r['Longitud']], popup=folium.Popup(html, max_width=250), tooltip=str(r.get('ID_Muestra', '')), icon=folium.Icon(color="darkblue", icon="info-sign")).add_to(mc)
                
                elif "Dispersión" in tipo_mapa_base:
                    h_data = df_mapa.dropna(subset=['Espesor_Deposito_mm'])
                    if not h_data.empty:
                        HeatMap([[r['Latitud'], r['Longitud'], r['Espesor_Deposito_mm']*2] for _, r in h_data.iterrows()], radius=25, blur=15).add_to(m_base)
                        min_v, max_v = float(h_data['Espesor_Deposito_mm'].min()), float(h_data['Espesor_Deposito_mm'].max())
                        colormap = cm.LinearColormap(colors=['blue', 'cyan', 'lime', 'yellow', 'red'], vmin=min_v, vmax=max_v)
                        colormap.caption = 'Intensidad de Dispersión (Espesor en mm)'
                        m_base.add_child(colormap)

                st_folium(m_base, width="100%", height=600, key="mapa_base")

        with tab_geo:
            tipo_mapa_geo = st.radio("Modelo Matemático:", ["🎯 Isopacas (Espesor)", "🪨 Isopletas (Tamaño)"], horizontal=True)
            with st.expander("⚙️ Parámetros de Interpolación Geostadística"):
                metodo_interp = st.selectbox("Algoritmo Matemático", ["RBF (Función Base Radial - Recomendado)", "Cúbica (Griddata)", "Lineal (Griddata)"], key="geo_algo")
                resolucion = st.slider("Resolución de Malla (Grid)", min_value=100, max_value=500, value=250, step=50, key="geo_res")
            
            col_obj = 'Espesor_Deposito_mm' if "Isopacas" in tipo_mapa_geo else 'Tamaño_Promedio_mm'
            df_mod = df_mapa.dropna(subset=['Latitud', 'Longitud', col_obj]).copy()
            df_mod = df_mod.groupby(['Latitud', 'Longitud'], as_index=False).agg({col_obj: 'max', 'ID_Muestra': 'first'})
            
            if len(df_mod) < 4: st.warning(f"⚠️ Se requieren al menos 4 puntos para {col_obj}.")
            else:
                lon, lat, z = df_mod['Longitud'].values, df_mod['Latitud'].values, df_mod[col_obj].values
                grid_lon, grid_lat, grid_z, l_lon_min, l_lon_max, l_lat_min, l_lat_max = calcular_modelo_espacial(lon, lat, z, metodo_interp, resolucion)
                
                fig = plt.figure(frameon=False)
                ax = fig.add_axes([0, 0, 1, 1])
                ax.axis('off'); ax.set_xlim(l_lon_min, l_lon_max); ax.set_ylim(l_lat_min, l_lat_max)
                cmap_choice = 'Reds' if "Isopacas" in tipo_mapa_geo else 'viridis'
                ax.contourf(grid_lon, grid_lat, grid_z, alpha=0.55, cmap=cmap_choice, levels=12)
                ax.contour(grid_lon, grid_lat, grid_z, colors='black', linewidths=0.6, levels=12) 
                
                buf = io.BytesIO()
                plt.savefig(buf, format='png', bbox_inches='tight', pad_inches=0, transparent=True)
                buf.seek(0)
                img_url = f"data:image/png;base64,{base64.b64encode(buf.read()).decode('utf-8')}"
                plt.close(fig); buf.close()

                m_geo = folium.Map(location=[c_lat, c_lon], zoom_start=11, tiles='CartoDB positron')
                folium.Marker([LAT_CRATER, LON_CRATER], tooltip="🌋 Cráter Volcán Puracé", icon=folium.Icon(color="red", icon="fire")).add_to(m_geo)
                folium.raster_layers.ImageOverlay(image=img_url, bounds=[[l_lat_min, l_lon_min], [l_lat_max, l_lon_max]], opacity=0.8).add_to(m_geo)
                for _, r in df_mod.iterrows(): folium.CircleMarker([r['Latitud'], r['Longitud']], radius=3, color="black", fill=True).add_to(m_geo)

                colormap = cm.LinearColormap(colors=['#FEE0D2', '#FC9272', '#DE2D26', '#99000D'] if "Isopacas" in tipo_mapa_geo else ['#440154', '#31688E', '#35B779', '#FDE725'], vmin=float(grid_z.min()), vmax=float(grid_z.max()))
                colormap.caption = f"{col_obj} (mm)"
                m_geo.add_child(colormap)
                
                st_folium(m_geo, width="100%", height=600, key="mapa_geo")

        with tab_sim:
            tipo_mapa_sim = st.radio("Motor de Simulación:", ["⏳ Time-Lapse (Animación Histórica)", "🤖 IA: Predicción (Random Forest)"], horizontal=True)
            
            if "Time-Lapse" in tipo_mapa_sim:
                df_time = df_mapa.dropna(subset=['Fecha_Recoleccion', 'Espesor_Deposito_mm']).copy()
                if df_time.empty: st.warning("No hay datos de fecha para animar.")
                else:
                    df_time = df_time.sort_values('Fecha_Recoleccion')
                    df_time['Fecha_Str'] = df_time['Fecha_Recoleccion'].dt.strftime('%Y-%m-%d')
                    
                    fig_tl = px.scatter_mapbox(df_time, lat="Latitud", lon="Longitud", 
                                            color="Espesor_Deposito_mm", size="Espesor_Deposito_mm",
                                            animation_frame="Fecha_Str", hover_name="ID_Muestra",
                                            color_continuous_scale="Reds", size_max=25, zoom=10,
                                            mapbox_style="carto-positron", center={"lat": LAT_CRATER, "lon": LON_CRATER},
                                            title="Evolución Espacio-Temporal del Depósito de Ceniza")
                    fig_tl.update_layout(margin={"r":0,"t":40,"l":0,"b":0}, height=600)
                    st.plotly_chart(fig_tl, use_container_width=True)

            elif "IA: Predicción" in tipo_mapa_sim:
                if not ML_DISPONIBLE: st.error("⚠️ La librería scikit-learn no está instalada. Añádela al requirements.txt")
                else:
                    st.info("🧠 **Red Neuronal / Random Forest:** La IA simula el espesor de la ceniza en zonas sin muestreo.")
                    df_ml = df_mapa.dropna(subset=['Espesor_Deposito_mm', 'Distancia_Crater_km']).copy()
                    if len(df_ml) < 4: st.warning("Se requieren al menos 4 muestras para entrenar la Inteligencia Artificial.")
                    else:
                        X = df_ml[['Latitud', 'Longitud', 'Distancia_Crater_km']]
                        y = df_ml['Espesor_Deposito_mm']
                        
                        modelo_rf = RandomForestRegressor(n_estimators=100, random_state=42)
                        modelo_rf.fit(X, y)
                        
                        lon_min, lon_max = df_ml['Longitud'].min() - 0.05, df_ml['Longitud'].max() + 0.05
                        lat_min, lat_max = df_ml['Latitud'].min() - 0.05, df_ml['Latitud'].max() + 0.05
                        grid_lon, grid_lat = np.mgrid[lon_min:lon_max:100j, lat_min:lat_max:100j]
                        
                        distancias_grid, _ = operaciones_geoespaciales_vectorizadas(grid_lat.flatten(), grid_lon.flatten())
                        X_pred = pd.DataFrame({'Latitud': grid_lat.flatten(), 'Longitud': grid_lon.flatten(), 'Distancia_Crater_km': distancias_grid})
                        
                        predicciones = modelo_rf.predict(X_pred)
                        grid_z_rf = predicciones.reshape(grid_lon.shape)
                        
                        fig_rf = go.Figure(data=go.Contour(z=grid_z_rf.T, x=grid_lon[:,0], y=grid_lat[0,:], colorscale='Reds', contours=dict(showlabels=True), name="Espesor Previsto"))
                        fig_rf.add_trace(go.Scatter(x=df_ml['Longitud'], y=df_ml['Latitud'], mode='markers', marker=dict(color='black', symbol='x', size=8), name='Datos Entrenamiento'))
                        fig_rf.add_trace(go.Scatter(x=[LON_CRATER], y=[LAT_CRATER], mode='markers', marker=dict(color='red', symbol='triangle-up', size=14), name='Cráter'))
                        fig_rf.update_layout(height=600, xaxis_title="Longitud", yaxis_title="Latitud", plot_bgcolor='#FAFAFA')
                        st.plotly_chart(fig_rf, use_container_width=True)

    except Exception as e: st.error(f"⚠️ Error al renderizar el módulo espacial: {e}")

def renderizar_modulo_comparativo(df_fil, df_pct_fil, cols_conteo):
    try:
        st.subheader("⚖️ Análisis Comparativo Multi-Muestra")
        col_f1, col_f2 = st.columns(2)
        with col_f1:
            locs_disponibles = sorted(df_fil['Localizacion'].dropna().unique().tolist())
            filtro_v = st.multiselect("Filtrar opciones por Localización:", locs_disponibles, default=[])
        with col_f2:
            if 'Fecha_Recoleccion' in df_fil.columns and not df_fil['Fecha_Recoleccion'].dropna().empty:
                fechas_disponibles = sorted(df_fil['Fecha_Recoleccion'].dt.strftime('%Y-%m-%d').dropna().unique().tolist(), reverse=True)
                filtro_f = st.multiselect("Filtrar opciones por Fecha:", fechas_disponibles, default=[])
            else: filtro_f = []

        df_opciones = df_fil.copy()
        if filtro_v: df_opciones = df_opciones[df_opciones['Localizacion'].isin(filtro_v)]
        if filtro_f and 'Fecha_Recoleccion' in df_opciones.columns:
            df_opciones = df_opciones[df_opciones['Fecha_Recoleccion'].dt.strftime('%Y-%m-%d').isin(filtro_f)]

        muestras_disponibles = df_opciones['ID_Muestra'].tolist()
        muestras_seleccionadas = st.multiselect("Seleccione las muestras a comparar:", muestras_disponibles, default=muestras_disponibles[:3] if len(muestras_disponibles) >= 3 else muestras_disponibles)

        if not muestras_seleccionadas: return st.info("Seleccione al menos una muestra para iniciar la comparativa.")

        st.markdown("---")
        st.subheader("📊 Comparativa de Distribución Mineralógica")
        df_comp_pct = df_pct_fil[df_pct_fil['ID_Muestra'].isin(muestras_seleccionadas)].copy()
        df_melted = df_comp_pct.melt(id_vars=['ID_Muestra'], value_vars=cols_conteo, var_name='Componente', value_name='Porcentaje')
        df_melted = df_melted[df_melted['Porcentaje'] > 0] 
        
        fig_bar = px.bar(df_melted, x="ID_Muestra", y="Porcentaje", color="Componente", text="Porcentaje", color_discrete_map=color_map_oficial, barmode="stack")
        fig_bar.update_traces(texttemplate='%{text:.1f}%', textposition='inside')
        fig_bar.update_layout(height=450)
        st.plotly_chart(fig_bar, use_container_width=True)

        st.markdown("---")
        st.subheader("📏 Comparativa Físico-Espacial")
        cols_fisicas = ['ID_Muestra', 'Localizacion', 'Fecha_Recoleccion', 'Tamaño_Promedio_mm', 'Espesor_Deposito_mm', 'Distancia_Crater_km', 'Nivel_Riesgo']
        df_fisico = df_fil[df_fil['ID_Muestra'].isin(muestras_seleccionadas)][[c for c in cols_fisicas if c in df_fil.columns]].copy()
        if 'Fecha_Recoleccion' in df_fisico.columns: df_fisico['Fecha_Recoleccion'] = df_fisico['Fecha_Recoleccion'].dt.strftime('%Y-%m-%d')
        st.dataframe(df_fisico, hide_index=True, use_container_width=True)
        
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df_fisico.to_excel(writer, index=False, sheet_name='Datos_Fisicos_Geo')
            df_comp_pct.to_excel(writer, index=False, sheet_name='Quimica_Porcentajes')
            
        st.download_button(label="📥 Descargar Comparativa Excel (.xlsx)", data=output.getvalue(), file_name="comparativa_cvlc.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

    except Exception as e: st.error(f"⚠️ Error renderizando el módulo comparativo: {e}")

def generar_pdf_reporte(m_sel, localizacion, fecha, espesor, tamano, riesgo, df_graf):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", 'B', 16)
    pdf.cell(200, 10, txt="REPORTE OFICIAL - OBSERVATORIO VULCANOLOGICO", ln=True, align='C')
    pdf.set_font("Arial", 'B', 12)
    pdf.cell(200, 10, txt=f"Muestra: {m_sel}", ln=True, align='C')
    pdf.ln(10)
    riesgo_limpio = str(riesgo).replace('🟢', '').replace('🟠', '').replace('🔴', '').replace('⚪', '').strip()
    pdf.set_font("Arial", '', 12)
    pdf.cell(200, 10, txt=f"Localizacion: {localizacion}", ln=True)
    pdf.cell(200, 10, txt=f"Fecha de Recoleccion: {fecha}", ln=True)
    pdf.cell(200, 10, txt=f"Espesor del Deposito: {espesor}", ln=True)
    pdf.cell(200, 10, txt=f"Nivel de Riesgo Local: {riesgo_limpio}", ln=True)
    pdf.ln(10)
    pdf.set_font("Arial", 'B', 14)
    pdf.cell(200, 10, txt="Composicion Mineralogica (%)", ln=True)
    pdf.set_font("Arial", '', 12)
    for index, row in df_graf.iterrows():
        comp_limpio = str(row['Componente']).encode('latin-1', 'ignore').decode('latin-1')
        pdf.cell(200, 10, txt=f"- {comp_limpio}: {round(row['Porcentaje'], 2)}%", ln=True)
    
    pdf_output = pdf.output(dest='S').encode('latin-1', 'ignore')
    return f'<a href="data:application/pdf;base64,{base64.b64encode(pdf_output).decode()}" download="Reporte_{m_sel}.pdf" class="button" style="text-decoration:none;background-color:#2980B9;color:white;padding:8px 12px;border-radius:5px;font-size:14px;font-weight:bold;">📥 Descargar Ficha Técnica (PDF)</a>'

def renderizar_modulo_laboratorio(df_fil, df_pct_fil, cols_conteo, fotos_subidas):
    try:
        st.subheader("1. Caracterización Mineralógica Individual")
        lista = df_fil["ID_Muestra"].tolist()
        if "idx_muestra" not in st.session_state or st.session_state["idx_muestra"] >= len(lista): st.session_state["idx_muestra"] = 0

        c_prev, c_sel, c_next = st.columns([0.5, 4, 0.5])
        with c_prev:
            if st.button("⬅️", use_container_width=True): st.session_state["idx_muestra"] = (st.session_state["idx_muestra"] - 1) % len(lista); st.rerun()
        with c_sel:
            m_sel = st.selectbox("ID de Muestra", options=lista, index=st.session_state["idx_muestra"], label_visibility="collapsed")
            st.session_state["idx_muestra"] = lista.index(m_sel)
        with c_next:
            if st.button("➡️", use_container_width=True): st.session_state["idx_muestra"] = (st.session_state["idx_muestra"] + 1) % len(lista); st.rerun()

        d_crudo = df_fil[df_fil["ID_Muestra"] == m_sel].iloc[0]
        d_pct = df_pct_fil[df_pct_fil["ID_Muestra"] == m_sel][cols_conteo].iloc[0]
        d_graf = d_pct[d_pct > 0].reset_index(); d_graf.columns = ["Componente", "Porcentaje"]

        col_g, col_f = st.columns([1.3, 1])
        min_clic = None
        with col_g:
            fig = px.pie(d_graf, names="Componente", values="Porcentaje", hole=0.35, color="Componente", color_discrete_map=color_map_oficial)
            fig.update_traces(textposition="inside", textinfo="percent+label")
            fig.update_layout(margin=dict(t=20, b=20, l=10, r=10), height=350)
            ev = st.plotly_chart(fig, use_container_width=True, on_select="rerun", key=f"pie_{m_sel}")
            if ev and ev.get("selection") and ev["selection"]["points"]: min_clic = ev["selection"]["points"][0]["label"]

            f_val = pd.to_datetime(d_crudo['Fecha_Recoleccion']).strftime('%Y-%m-%d') if pd.notna(d_crudo.get('Fecha_Recoleccion')) else 'N/A'
            st.markdown(f"""
            <div style="background-color:#EBF5FB; padding:10px 14px; border-radius:8px; margin-top:10px; font-size: 13px; border-left: 5px solid #2980B9; color:#1C2833; white-space: nowrap; overflow-x: auto;">
                📋 <b>Localización:</b> {d_crudo.get('Localizacion','N/A')} &nbsp;|&nbsp; 📅 <b>Fecha:</b> {f_val} &nbsp;|&nbsp; 📏 <b>Tamaño:</b> {d_crudo.get('Tamaño_Promedio_mm',0)} mm &nbsp;|&nbsp; 🔥 <b>Espesor:</b> {d_crudo.get('Espesor_Deposito_mm',0)} mm<br>
                🚨 <b>Alerta:</b> {d_crudo.get('Nivel_Riesgo', 'N/A')} &nbsp;|&nbsp; 🧭 <b>Viento Histórico:</b> {d_crudo.get('Direccion_Viento', 'N/A')}
            </div>""", unsafe_allow_html=True)
            
            if PDF_DISPONIBLE:
                pdf_html = generar_pdf_reporte(m_sel, d_crudo.get('Localizacion','N/A'), f_val, f"{d_crudo.get('Espesor_Deposito_mm',0)} mm", f"{d_crudo.get('Tamaño_Promedio_mm',0)} mm", d_crudo.get('Nivel_Riesgo', 'N/A'), d_graf)
                st.markdown(f"<div style='margin-top: 15px;'>{pdf_html}</div>", unsafe_allow_html=True)

        with col_f:
            fotos_locales = [f for f in fotos_subidas if m_sel.lower() in f.name.lower()]
            if fotos_locales:
                k_est = f"foto_loc_{m_sel}"
                if k_est not in st.session_state: st.session_state[k_est] = 0
                st.session_state[k_est] = st.session_state[k_est] % max(1, len(fotos_locales))
                b1, tx, b2 = st.columns([1, 2, 1])
                if b1.button("⬅️", key=f"pl_{m_sel}"): st.session_state[k_est] = (st.session_state[k_est] - 1) % len(fotos_locales)
                tx.markdown(f"<div style='text-align:center; margin-top:8px;'>Foto {st.session_state[k_est]+1}/{len(fotos_locales)}</div>", unsafe_allow_html=True)
                if b2.button("➡️", key=f"nl_{m_sel}"): st.session_state[k_est] = (st.session_state[k_est] + 1) % len(fotos_locales)
                st.image(fotos_locales[st.session_state[k_est]], caption=f"Archivo: {fotos_locales[st.session_state[k_est]].name}", use_container_width=True)

            elif "URLs_Fotos" in d_crudo and pd.notna(d_crudo["URLs_Fotos"]):
                links = [u.strip() for u in str(d_crudo["URLs_Fotos"]).split(",") if u.strip().lower() != "nan"]
                if links:
                    k_est = f"foto_url_{m_sel}"
                    if k_est not in st.session_state: st.session_state[k_est] = 0
                    st.session_state[k_est] = st.session_state[k_est] % max(1, len(links))
                    b1, tx, b2 = st.columns([1, 2, 1])
                    if b1.button("⬅️", key=f"pu_{m_sel}"): st.session_state[k_est] = (st.session_state[k_est] - 1) % len(links)
                    tx.markdown(f"<div style='text-align:center; margin-top:8px;'>Foto {st.session_state[k_est]+1}/{len(links)}</div>", unsafe_allow_html=True)
                    if b2.button("➡️", key=f"nu_{m_sel}"): st.session_state[k_est] = (st.session_state[k_est] + 1) % len(links)
                    st.image(obtener_url_imagen(links[st.session_state[k_est]]), caption=f"{m_sel}", use_container_width=True)

        st.markdown("---")
        
        # --- 2. ROSA DE VIENTOS Y TERNARIO ---
        st.subheader("2. Petrología y Rosa de Dispersión Atmosférica")
        c1, c2 = st.columns(2)
        with c1:
            c_v = [c for c in cols_conteo if 'FV' in c.upper() or 'VIDRIO' in c.upper()]
            c_l = [c for c in cols_conteo if 'LV' in c.upper() or 'LITICO' in c.upper() or 'LÍTICO' in c.upper()]
            c_c = [c for c in cols_conteo if c not in c_v + c_l]
            df_t = df_fil.copy()
            df_t['Vidrio'], df_t['Líticos'], df_t['Cristales'] = df_t[c_v].sum(axis=1) if c_v else 0, df_t[c_l].sum(axis=1) if c_l else 0, df_t[c_c].sum(axis=1) if c_c else 0
            df_t['Suma'] = df_t['Vidrio'] + df_t['Líticos'] + df_t['Cristales']
            df_tp = df_t[df_t['Suma'] > 0].copy()
            if not df_tp.empty:
                df_tp['V%'], df_tp['L%'], df_tp['C%'] = df_tp['Vidrio']/df_tp['Suma']*100, df_tp['Líticos']/df_tp['Suma']*100, df_tp['Cristales']/df_tp['Suma']*100
                fig_t = px.scatter_ternary(df_tp, a='V%', b='L%', c='C%', color="Nivel_Riesgo", hover_name="ID_Muestra", size="Tamaño_Promedio_mm", title="Clasificación Petrológica")
                st.plotly_chart(fig_t, use_container_width=True)

        with c2:
            v_vel, v_dir = obtener_clima_crater_actual()
            clima_txt = f"Viento Actual (Satélite): **{v_vel} km/h hacia el {v_dir}**" if v_vel else "Viento Actual (Satélite): No disponible"
            if 'Direccion_Viento' in df_fil.columns:
                df_polar = df_fil.groupby('Direccion_Viento')['Espesor_Deposito_mm'].sum().reset_index()
                fig_p = px.bar_polar(df_polar, r="Espesor_Deposito_mm", theta="Direccion_Viento", color="Espesor_Deposito_mm", template="plotly_white", color_continuous_scale="Reds", title=f"Rosa de Dispersión<br><sup style='font-size:12px'>{clima_txt}</sup>")
                st.plotly_chart(fig_p, use_container_width=True)

        st.markdown("---")
        
        # --- 3. EVOLUCIÓN TEMPORAL ---
        st.subheader("3. Evolución Temporal (Cenizas y Tamaño)")
        col_t1, col_t2 = st.columns(2)
        with col_t1:
            if 'Fecha_Recoleccion' in df_fil.columns and not df_fil['Fecha_Recoleccion'].dropna().empty:
                df_a = df_pct_fil.copy(); df_a['Fecha'] = df_fil['Fecha_Recoleccion']
                df_a = df_a.dropna(subset=['Fecha']).groupby('Fecha')[cols_conteo].mean().reset_index().melt(id_vars='Fecha', value_vars=cols_conteo, var_name='Componente', value_name='Porcentaje')
                fig_a = px.area(df_a, x="Fecha", y="Porcentaje", color="Componente", color_discrete_map=color_map_oficial, title="Evolución Mineralógica")
                fig_a.update_layout(yaxis=dict(range=[0, 100]), margin=dict(t=30, b=20, l=10, r=10))
                st.plotly_chart(fig_a, use_container_width=True)
            
        with col_t2:
            if 'Fecha_Recoleccion' in df_fil.columns and 'Tamaño_Promedio_mm' in df_fil.columns:
                d_t = df_fil.dropna(subset=['Fecha_Recoleccion', 'Tamaño_Promedio_mm']).sort_values('Fecha_Recoleccion')
                if not d_t.empty:
                    fig_l = px.line(d_t, x="Fecha_Recoleccion", y="Tamaño_Promedio_mm", color="Localizacion", markers=True, hover_name="ID_Muestra", color_discrete_sequence=colores_profesionales, title="Seguimiento de Tamaño de Grano")
                    fig_l.update_traces(line=dict(width=3), marker=dict(size=8)); st.plotly_chart(fig_l, use_container_width=True)

        st.markdown("---")
        
        # --- 4. RELACIONES ESPACIALES Y ESTADÍSTICAS ---
        st.subheader("4. Análisis de Decaimiento, Volumen Magmático y Correlación")
        c_dec, c_cor = st.columns(2)
        
        with c_dec:
            if 'Distancia_Crater_km' in df_fil.columns and 'Espesor_Deposito_mm' in df_fil.columns:
                df_vol = df_fil.dropna(subset=['Distancia_Crater_km', 'Espesor_Deposito_mm'])
                df_vol = df_vol[df_vol['Espesor_Deposito_mm'] > 0]
                if len(df_vol) > 3:
                    try:
                        x_val = df_vol['Distancia_Crater_km'].values
                        y_val = df_vol['Espesor_Deposito_mm'].values / 1e6 
                        slope, intercept = np.polyfit(x_val, np.log(y_val), 1)
                        k = -slope
                        y0 = np.exp(intercept)
                        if k > 0:
                            vol_km3 = (2 * np.pi * y0) / (k**2)
                            vei = 1 if vol_km3 < 0.0001 else 2 if vol_km3 < 0.001 else 3 if vol_km3 < 0.01 else 4 if vol_km3 < 0.1 else 5 if vol_km3 < 1 else "6+"
                            st.success(f"🌋 **Estimación Magmática (Modelo Exponencial):** Volumen: **~{vol_km3:.6f} km³** | VEI Estimado: **{vei}**")
                    except: pass
                
                fig_decay = px.scatter(df_fil, x="Distancia_Crater_km", y="Espesor_Deposito_mm", color="Localizacion", size="Tamaño_Promedio_mm", hover_name="ID_Muestra", title="Decaimiento del Espesor vs. Distancia")
                st.plotly_chart(fig_decay, use_container_width=True)

        with c_cor:
            cols_to_corr = cols_conteo + ['Espesor_Deposito_mm', 'Tamaño_Promedio_mm', 'Distancia_Crater_km']
            cols_to_corr = [c for c in cols_to_corr if c in df_fil.columns]
            if len(cols_to_corr) > 1:
                df_corr = df_fil[cols_to_corr].corr(method='pearson')
                fig_corr = px.imshow(df_corr, text_auto=".2f", aspect="auto", color_continuous_scale="RdBu_r", title="Matriz de Correlación", origin="lower")
                st.plotly_chart(fig_corr, use_container_width=True)

    except Exception as e: st.error(f"⚠️ Error renderizando el módulo de laboratorio: {e}")

def renderizar_modulo_operativo(df_fil):
    try:
        st.subheader("🛡️ Control de Calidad (QA/QC) Automático")
        errores = []
        fuera_limites = df_fil[(df_fil['Latitud'] > 5) | (df_fil['Latitud'] < -5) | (df_fil['Longitud'] > -70) | (df_fil['Longitud'] < -80)]
        if not fuera_limites.empty: errores.append(f"{len(fuera_limites)} muestras con coordenadas anómalas.")
        esp_cero = df_fil[df_fil['Espesor_Deposito_mm'] <= 0]
        if not esp_cero.empty: errores.append(f"{len(esp_cero)} muestras tienen espesor 0 o negativo.")
        sin_minerales = df_fil[df_fil['Total_Granos'] == 0]
        if not sin_minerales.empty: errores.append(f"{len(sin_minerales)} muestras sin conteo mineralógico.")

        if errores:
            for err in errores: st.error(f"🔴 ALERTA QA/QC: {err}")
        else: st.success("🟢 ¡QA/QC Aprobado! Integridad total de datos confirmada.")

        st.markdown("---")
        st.subheader("Semáforo de Gestión del Riesgo y Operaciones")
        cols_mostrar = ['ID_Muestra', 'Localizacion', 'Distancia_Crater_km', 'Espesor_Deposito_mm', 'Nivel_Riesgo', 'Enlace_Reporte']
        cols_existentes = [c for c in cols_mostrar if c in df_fil.columns]
        df_mostrar = df_fil[cols_existentes].copy()
        
        def color_riesgo(val):
            if 'Alto' in str(val): return 'background-color: #FADBD8; color: #78281F;'
            elif 'Medio' in str(val): return 'background-color: #FDEBD0; color: #7E5109;'
            elif 'Bajo' in str(val): return 'background-color: #D5F5E3; color: #186A3B;'
            return ''
        
        if 'Nivel_Riesgo' in df_mostrar.columns: st.dataframe(df_mostrar.style.map(color_riesgo, subset=['Nivel_Riesgo']), hide_index=True, use_container_width=True)
        else: st.dataframe(df_mostrar, hide_index=True, use_container_width=True)
        
        st.markdown("---"); st.subheader("Base de Datos Estructural (Cruda)")
        st.dataframe(df_fil, use_container_width=True)
    except Exception as e: st.error(f"⚠️ Error cargando el módulo operativo: {e}")

# ==========================================
# 5. EJECUCIÓN PRINCIPAL (FLUJO DE UI)
# ==========================================
st.sidebar.title("Panel de Control")
usar_sql = st.sidebar.checkbox("🗄️ Habilitar Base de Datos SQL")
if st.sidebar.button("🔄 Actualizar Datos de Origen", use_container_width=True): st.cache_data.clear(); st.rerun()
st.sidebar.markdown("---")

with st.sidebar.expander("📂 Carga de Datos y Nube", expanded=not usar_sql):
    url_gs = st.text_input("🔗 Link Google Sheets (Público)", placeholder="Pega el link...", disabled=usar_sql)
    a_sub = st.file_uploader("O Excel/CSV Local", type=["xlsx", "csv"], disabled=usar_sql)
    a_geo = st.file_uploader("Capa Veredas (.geojson)", type=["geojson", "json"])
    fotos_subidas = st.file_uploader("📷 Subir Fotos Locales (Multiselección)", type=["jpg", "jpeg", "png"], accept_multiple_files=True)

df_bruto, df_pct_bruto, c_conteo = cargar_y_limpiar_datos(a_sub, url_gs, usar_sql)

if df_bruto.empty:
    st.error("No se detectaron datos válidos.")
    st.stop()

st.sidebar.markdown("---")
with st.sidebar.expander("🗺️ Filtros Espaciales"):
    v_unicas = sorted(df_bruto.get('Localizacion', pd.Series()).dropna().unique().tolist())
    if "v_sel" not in st.session_state: st.session_state["v_sel"] = v_unicas
    col1, col2 = st.columns(2)
    if col1.button("Todas", use_container_width=True): st.session_state["v_sel"] = v_unicas
    if col2.button("Limpiar", use_container_width=True): st.session_state["v_sel"] = []
    v_sel = st.multiselect("Localización:", v_unicas, key="v_sel")

with st.sidebar.expander("📅 Filtros Temporales"):
    m_f = pd.Series(True, index=df_bruto.index)
    if 'Fecha_Recoleccion' in df_bruto.columns and not df_bruto['Fecha_Recoleccion'].isnull().all():
        df_bruto['Anio'] = df_bruto['Fecha_Recoleccion'].dt.year
        df_bruto['Mes'] = df_bruto['Fecha_Recoleccion'].dt.month
        a_sel = st.selectbox("Año:", ["Todos"] + sorted(df_bruto['Anio'].dropna().unique(), reverse=True))
        m_sel = st.selectbox("Mes:", ["Todos"] + [f"Mes {int(m)}" for m in (df_bruto[df_bruto['Anio']==a_sel]['Mes'].dropna().unique() if a_sel != "Todos" else range(1,13))])
        if a_sel != "Todos": m_f &= (df_bruto['Anio'] == a_sel)
        if m_sel != "Todos": m_f &= (df_bruto['Mes'] == int(m_sel.split()[1]))

m_v = df_bruto['Localizacion'].isin(v_sel) if v_sel else pd.Series(True, index=df_bruto.index)
df_fil, df_pct_fil = df_bruto[m_v & m_f], df_pct_bruto[m_v & m_f]

if df_fil.empty: st.warning("⚠️ Sin resultados para los filtros aplicados.")
else:
    renderizar_kpis(df_fil, c_conteo)
    
    t_espacial, t_laboratorio, t_comparativo, t_operativo = st.tabs([
        "🌍 Módulo Espacial (Mapas)", 
        "🔬 Módulo de Laboratorio (IA y Química)", 
        "⚖️ Módulo Comparativo (Multi-Muestra)",
        "🗃️ Módulo Operativo (QA/QC)"
    ])
    
    with t_espacial: renderizar_modulo_espacial(df_fil, a_geo)
    with t_laboratorio: renderizar_modulo_laboratorio(df_fil, df_pct_fil, c_conteo, fotos_subidas)
    with t_comparativo: renderizar_modulo_comparativo(df_fil, df_pct_fil, c_conteo)
    with t_operativo: renderizar_modulo_operativo(df_fil)
