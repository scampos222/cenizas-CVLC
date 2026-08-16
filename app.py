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
# 2. FUNCIONES MATEMÁTICAS VECTORIZADAS (NUEVO HPC)
# ==========================================
def operaciones_geoespaciales_vectorizadas(lats, lons):
    """Calcula distancias Haversine y Azimut de manera vectorial en microsegundos"""
    R = 6371.0 
    lat1, lon1, lat2, lon2 = map(np.radians, [LAT_CRATER, LON_CRATER, lats, lons])
    
    # Haversine
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = np.sin(dlat/2)**2 + np.cos(lat1) * np.cos(lat2) * np.sin(dlon/2)**2
    c = 2 * np.arctan2(np.sqrt(a), np.sqrt(1-a))
    distancias = np.round(R * c, 2)
    
    # Azimut / Dirección
    x = np.sin(dlon) * np.cos(lat2)
    y = np.cos(lat1) * np.sin(lat2) - (np.sin(lat1) * np.cos(lat2) * np.cos(dlon))
    initial_bearing = np.arctan2(x, y)
    brng = (np.degrees(initial_bearing) + 360) % 360
    
    dirs = np.array(['N', 'NNE', 'NE', 'ENE', 'E', 'ESE', 'SE', 'SSE', 'S', 'SSW', 'SW', 'WSW', 'W', 'WNW', 'NW', 'NNW'])
    ix = np.round(brng / (360. / len(dirs))).astype(int)
    direcciones = dirs[ix % len(dirs)]
    
    return distancias, direcciones

def clasificar_riesgo_vectorizado(espesores):
    """Clasificación de riesgo usando numpy select para mayor velocidad"""
    condiciones = [
        pd.isna(espesores) | (espesores == 0),
        espesores < 1,
        espesores <= 5,
        espesores > 5
    ]
    opciones = ['⚪ N/A', '🟢 Bajo (< 1mm)', '🟠 Medio (1-5mm)', '🔴 Alto (> 5mm)']
    return np.select(condiciones, opciones, default='⚪ N/A')

def obtener_url_imagen(url_original):
    url_limpia = str(url_original).strip()
    if "|" in url_limpia: url_limpia = url_limpia.split("|")[1].strip()
    if "drive.google.com" in url_limpia:
        match = re.search(r'[-\w]{25,}', url_limpia)
        if match: return f"https://lh3.googleusercontent.com/d/{match.group(0)}"
    return url_limpia

def obtener_nombre_foto(url_original):
    url_limpia = str(url_original).strip()
    if not url_limpia or url_limpia.lower() == "nan": return "Foto de Muestra"
    if "|" in url_limpia: return url_limpia.split("|")[0].strip()
    path = urlparse(url_limpia).path
    nombre_sin_ext = os.path.splitext(os.path.basename(unquote(path)))[0]
    return "Archivo Google Drive" if ("drive.google.com" in url_limpia or not nombre_sin_ext) else nombre_sin_ext

# ==========================================
# 3. MOTOR DE DATOS CACHEADO (OPTIMIZADO)
# ==========================================
@st.cache_data(show_spinner="Descargando y optimizando base de datos...")
def cargar_y_limpiar_datos(archivo, url_gs):
    df_temp = None
    if archivo is not None:
        df_temp = pd.read_csv(archivo) if archivo.name.endswith('.csv') else pd.read_excel(archivo)
    elif url_gs:
        try:
            match = re.search(r'/d/([a-zA-Z0-9-_]+)', url_gs)
            if match: df_temp = pd.read_csv(f"https://docs.google.com/spreadsheets/d/{match.group(1)}/export?format=csv")
        except Exception: pass 
            
    if df_temp is None:
        datos_prueba = {
            'ID_Muestra': ['CAP-01', 'CAP-02', 'CAP-03', 'CAP-04'], 'Vereda': ['Chapio', 'Quintana', 'Coconuco', 'Puracé'],
            'Latitud': [2.443, 2.450, 2.341, 2.355], 'Longitud': [-76.606, -76.610, -76.510, -76.500],
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
        'Localidad': 'Vereda', 'Muestra': 'ID_Muestra', 'ID': 'ID_Muestra', 'Fotos': 'URLs_Fotos', 'Reporte': 'Enlace_Reporte'
    }
    df_temp = df_temp.rename(columns=lambda x: sinonimos.get(str(x).strip(), x))
    
    if 'Fecha_Recoleccion' in df_temp.columns:
        df_temp['Fecha_Recoleccion'] = pd.to_datetime(df_temp['Fecha_Recoleccion'], errors='coerce')

    if 'Latitud' in df_temp.columns and 'Longitud' in df_temp.columns:
        distancias, direcciones = operaciones_geoespaciales_vectorizadas(df_temp['Latitud'].values, df_temp['Longitud'].values)
        df_temp['Distancia_Crater_km'] = distancias
        df_temp['Direccion_Viento'] = direcciones
        
    if 'Espesor_Deposito_mm' in df_temp.columns:
        df_temp['Nivel_Riesgo'] = clasificar_riesgo_vectorizado(df_temp['Espesor_Deposito_mm'])

    cols_info = ['ID_Muestra', 'Vereda', 'Latitud', 'Longitud', 'Tamaño_Promedio_mm', 'Espesor_Deposito_mm', 'URLs_Fotos', 'URL_Microscopio', 'Fecha_Recoleccion', 'Enlace_Reporte', 'Direccion_Viento', 'Distancia_Crater_km', 'Nivel_Riesgo']
    cols_conteo = [col for col in df_temp.columns if col not in cols_info]
    
    for col in cols_conteo + ['Tamaño_Promedio_mm', 'Espesor_Deposito_mm', 'Distancia_Crater_km']:
        if col in df_temp.columns: df_temp[col] = pd.to_numeric(df_temp[col], errors='coerce').fillna(0)

    df_temp['Total_Granos'] = df_temp[cols_conteo].sum(axis=1)
    
    # Vectorización del cálculo de porcentajes
    df_pct_temp = df_temp.copy()
    if not df_temp[cols_conteo].empty:
        df_pct_temp[cols_conteo] = df_temp[cols_conteo].div(df_temp['Total_Granos'].replace(0, 1), axis=0) * 100

    return df_temp, df_pct_temp, cols_conteo

# ==========================================
# 4. MICRO-CACHÉ MATEMÁTICO (NUEVO)
# ==========================================
@st.cache_data(show_spinner="Calculando modelo de interpolación espacial...")
def calcular_modelo_espacial(lon, lat, z, metodo_interp, resolucion):
    """Realiza la matemática pesada solo si cambian los datos o la resolución"""
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
# 5. MÓDULOS MACRO-PESTAÑAS
# ==========================================

def renderizar_kpis(df_fil, cols_conteo):
    try:
        m_count = len(df_fil)
        max_esp = df_fil['Espesor_Deposito_mm'].max() if 'Espesor_Deposito_mm' in df_fil.columns else 0
        min_dom = df_fil[cols_conteo].sum().idxmax() if not df_fil[cols_conteo].empty else "N/A"
        dir_dom = df_fil['Direccion_Viento'].mode()[0] if 'Direccion_Viento' in df_fil.columns and not df_fil['Direccion_Viento'].empty else "N/A"
        
        if not df_fil[cols_conteo].empty and df_fil[cols_conteo].sum().sum() > 0:
            pct_dom = round((df_fil[cols_conteo].sum().max() / df_fil[cols_conteo].sum().sum()) * 100, 1)
        else:
            pct_dom = 0
            
        st.info(f"**📝 Resumen Analítico Automatizado:** Bajo los parámetros actuales, se analizaron **{m_count} muestras** con un espesor máximo de **{max_esp} mm**. La dispersión predominante indica un transporte de ceniza hacia el **{dir_dom}**. Mineralógicamente, el depósito está dominado por **{min_dom}** (aprox. {pct_dom}% del conteo total analizado).")

        st.subheader("📊 Panel de Indicadores (KPIs)")
        k1, k2, k3, k4 = st.columns(4)
        k1.metric("Muestras Analizadas", m_count)
        k2.metric("Espesor Máximo (mm)", max_esp)
        k3.metric("Mineral Dominante", min_dom)
        k4.metric("Dispersión Predominante", dir_dom)
        st.markdown("---")
    except Exception as e: st.error(f"⚠️ Error al renderizar KPIs: {e}")

def renderizar_modulo_espacial(df_fil, archivo_geo):
    try:
        st.subheader("Cartografía y Modelamiento Matemático")
        tipo_mapa = st.radio("Seleccione la vista espacial:", ["📍 Puntos (2D)", "🔥 Calor (2D)", "🌋 Vista 3D (Volumen)", "🎯 Isopacas (Espesor)", "🪨 Isopletas (Tamaño de Grano)"], horizontal=True)
        
        metodo_interp = 'RBF (Recomendado)'
        resolucion = 200
        if "Isopacas" in tipo_mapa or "Isopletas" in tipo_mapa:
            with st.expander("⚙️ Parámetros de Interpolación Geostadística"):
                metodo_interp = st.selectbox("Algoritmo Matemático", ["RBF (Función Base Radial - Recomendado)", "Cúbica (Griddata)", "Lineal (Griddata)"])
                resolucion = st.slider("Resolución de Malla (Grid)", min_value=100, max_value=500, value=250, step=50, help="Mayor resolución mejora la curva pero tarda más en procesar.")
        
        st.markdown("---")
        df_mapa = df_fil.dropna(subset=['Latitud', 'Longitud']).copy()
        if df_mapa.empty: return st.warning("No hay datos con coordenadas válidas.")
        
        c_lat, c_lon = df_mapa['Latitud'].mean(), df_mapa['Longitud'].mean()

        if "3D" in tipo_mapa:
            df_3d = df_mapa.dropna(subset=['Espesor_Deposito_mm']).copy()
            if df_3d.empty: return st.warning("Sin datos de 'Espesor_Deposito_mm' para construir 3D.")
            df_3d['Elev_V'] = df_3d['Espesor_Deposito_mm'] * 150 
            capa = pdk.Layer('ColumnLayer', data=df_3d, get_position='[Longitud, Latitud]', get_elevation='Elev_V', radius=150, get_fill_color='[200, 30, 30, 180]', pickable=True, auto_highlight=True)
            crater_layer = pdk.Layer('ScatterplotLayer', data=[{'lat': LAT_CRATER, 'lon': LON_CRATER}], get_position='[lon, lat]', get_color='[255, 0, 0, 255]', get_radius=500, pickable=True)
            vista = pdk.ViewState(longitude=c_lon, latitude=c_lat, zoom=10.5, pitch=55, bearing=20)
            st.pydeck_chart(pdk.Deck(layers=[capa, crater_layer], initial_view_state=vista, tooltip={"html": "<b>Muestra</b>", "style": {"color": "white"}}, map_style='dark'), use_container_width=True)
            
        else:
            m = folium.Map(location=[c_lat, c_lon], zoom_start=11, tiles='CartoDB positron')
            folium.TileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Topo_Map/MapServer/tile/{z}/{y}/{x}', attr='Esri', overlay=False).add_to(m)
            folium.TileLayer('https://services.arcgis.com/WMSServer', attr='SGC', name='Amenaza (SGC)', overlay=True, opacity=0.7).add_to(m)
            folium.Marker([LAT_CRATER, LON_CRATER], tooltip="🌋 Cráter Volcán Puracé", icon=folium.Icon(color="red", icon="fire")).add_to(m)

            if archivo_geo: folium.GeoJson(json.load(archivo_geo), style_function=lambda f: {'fillColor': '#2980B9', 'color': '#2C3E50', 'weight': 1.5, 'fillOpacity': 0.15}).add_to(m)
            
            if "Puntos" in tipo_mapa:
                mc = MarkerCluster().add_to(m)
                for _, r in df_mapa.iterrows():
                    html = f"<b>{r.get('ID_Muestra', 'N/A')}</b><br>Vereda: {r.get('Vereda', 'N/A')}<br>Espesor: {r.get('Espesor_Deposito_mm', 0)} mm<br>Distancia Cráter: {r.get('Distancia_Crater_km', 0)} km"
                    folium.Marker([r['Latitud'], r['Longitud']], popup=folium.Popup(html, max_width=250), tooltip=str(r.get('ID_Muestra', '')), icon=folium.Icon(color="darkblue", icon="info-sign")).add_to(mc)
            
            elif "Calor" in tipo_mapa:
                h_data = df_mapa.dropna(subset=['Espesor_Deposito_mm'])
                if not h_data.empty: HeatMap([[r['Latitud'], r['Longitud'], r['Espesor_Deposito_mm']*2] for _, r in h_data.iterrows()], radius=25, blur=15).add_to(m)
            
            elif "Isopacas" in tipo_mapa or "Isopletas" in tipo_mapa:
                col_obj = 'Espesor_Deposito_mm' if "Isopacas" in tipo_mapa else 'Tamaño_Promedio_mm'
                df_mod = df_mapa.dropna(subset=['Latitud', 'Longitud', col_obj]).copy()
                df_mod = df_mod.groupby(['Latitud', 'Longitud'], as_index=False).agg({col_obj: 'max', 'ID_Muestra': 'first'})
                
                if len(df_mod) < 4:
                    st.warning(f"⚠️ Se requieren al menos 4 puntos para generar el modelo de {col_obj}.")
                else:
                    lon, lat, z = df_mod['Longitud'].values, df_mod['Latitud'].values, df_mod[col_obj].values
                    
                    # Llamada a la función cacheada
                    grid_lon, grid_lat, grid_z, lim_lon_min, lim_lon_max, lim_lat_min, lim_lat_max = calcular_modelo_espacial(lon, lat, z, metodo_interp, resolucion)
                    
                    # Generación de Imagen Transparente
                    fig = plt.figure(frameon=False)
                    ax = fig.add_axes([0, 0, 1, 1])
                    ax.axis('off')
                    ax.set_xlim(lim_lon_min, lim_lon_max); ax.set_ylim(lim_lat_min, lim_lat_max)
                    cmap_choice = 'Reds' if "Isopacas" in tipo_mapa else 'viridis'
                    ax.contourf(grid_lon, grid_lat, grid_z, alpha=0.55, cmap=cmap_choice, levels=12)
                    ax.contour(grid_lon, grid_lat, grid_z, colors='black', linewidths=0.6, levels=12) 
                    
                    buf = io.BytesIO()
                    plt.savefig(buf, format='png', bbox_inches='tight', pad_inches=0, transparent=True)
                    buf.seek(0)
                    img_url = f"data:image/png;base64,{base64.b64encode(buf.read()).decode('utf-8')}"
                    
                    # Limpieza activa de memoria (Garbage Collection)
                    plt.close(fig)
                    buf.close()

                    folium.raster_layers.ImageOverlay(image=img_url, bounds=[[lim_lat_min, lim_lon_min], [lim_lat_max, lim_lon_max]], opacity=0.8).add_to(m)
                    for _, r in df_mod.iterrows(): folium.CircleMarker([r['Latitud'], r['Longitud']], radius=3, color="black", fill=True, popup=f"{r[col_obj]}").add_to(m)

                    min_val, max_val = float(grid_z.min()), float(grid_z.max())
                    if "Isopacas" in tipo_mapa:
                        colormap = cm.LinearColormap(colors=['#FEE0D2', '#FC9272', '#DE2D26', '#99000D'], vmin=min_val, vmax=max_val)
                        colormap.caption = 'Espesor del Depósito (mm)'
                    else:
                        colormap = cm.LinearColormap(colors=['#440154', '#31688E', '#35B779', '#FDE725'], vmin=min_val, vmax=max_val)
                        colormap.caption = 'Tamaño Promedio de Grano (mm)'
                    m.add_child(colormap)

            folium.LayerControl().add_to(m)
            st_folium(m, width="100%", height=600)

    except Exception as e: st.error(f"⚠️ Error al renderizar el módulo espacial: {e}")

def generar_pdf_reporte(m_sel, vereda, fecha, espesor, tamano, riesgo, df_graf):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", 'B', 16)
    pdf.cell(200, 10, txt="REPORTE OFICIAL - OBSERVATORIO VULCANOLOGICO", ln=True, align='C')
    pdf.set_font("Arial", 'B', 12)
    pdf.cell(200, 10, txt=f"Muestra: {m_sel}", ln=True, align='C')
    pdf.ln(10)
    
    riesgo_limpio = str(riesgo).replace('🟢', '').replace('🟠', '').replace('🔴', '').replace('⚪', '').strip()
    
    pdf.set_font("Arial", '', 12)
    pdf.cell(200, 10, txt=f"Vereda/Localidad: {vereda}", ln=True)
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
    b64 = base64.b64encode(pdf_output).decode()
    return f'<a href="data:application/pdf;base64,{b64}" download="Reporte_{m_sel}.pdf" class="button" style="text-decoration:none;background-color:#2980B9;color:white;padding:8px 12px;border-radius:5px;font-size:14px;font-weight:bold;">📥 Descargar Ficha Técnica (PDF)</a>'

def renderizar_modulo_laboratorio(df_fil, df_pct_fil, cols_conteo, fotos_subidas):
    try:
        # --- 1. COMPOSICIÓN INDIVIDUAL ---
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
                📋 <b>Vereda:</b> {d_crudo.get('Vereda','N/A')} &nbsp;|&nbsp; 📅 <b>Fecha:</b> {f_val} &nbsp;|&nbsp; 📏 <b>Tamaño:</b> {d_crudo.get('Tamaño_Promedio_mm',0)} mm &nbsp;|&nbsp; 🔥 <b>Espesor:</b> {d_crudo.get('Espesor_Deposito_mm',0)} mm<br>
                🚨 <b>Alerta:</b> {d_crudo.get('Nivel_Riesgo', 'N/A')} &nbsp;|&nbsp; 🧭 <b>Viento:</b> {d_crudo.get('Direccion_Viento', 'N/A')}
            </div>""", unsafe_allow_html=True)
            
            if PDF_DISPONIBLE:
                pdf_html = generar_pdf_reporte(m_sel, d_crudo.get('Vereda','N/A'), f_val, f"{d_crudo.get('Espesor_Deposito_mm',0)} mm", f"{d_crudo.get('Tamaño_Promedio_mm',0)} mm", d_crudo.get('Nivel_Riesgo', 'N/A'), d_graf)
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
                    st.image(obtener_url_imagen(links[st.session_state[k_est]]), caption=f"{m_sel} | {obtener_nombre_foto(links[st.session_state[k_est]])}", use_container_width=True)

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
                fig_t = px.scatter_ternary(df_tp, a='V%', b='L%', c='C%', color="Nivel_Riesgo", hover_name="ID_Muestra", size="Tamaño_Promedio_mm", title="Clasificación Petrológica (V-L-C)")
                fig_t.update_layout(ternary=dict(aaxis_title='Vidrio %', baxis_title='Líticos %', caxis_title='Cristales %'), margin=dict(t=40,b=40,l=40,r=40))
                st.plotly_chart(fig_t, use_container_width=True)

        with c2:
            if 'Direccion_Viento' in df_fil.columns:
                df_polar = df_fil.groupby('Direccion_Viento')['Espesor_Deposito_mm'].sum().reset_index()
                fig_p = px.bar_polar(df_polar, r="Espesor_Deposito_mm", theta="Direccion_Viento", color="Espesor_Deposito_mm", template="plotly_white", color_continuous_scale="Reds", title="Rosa de Dispersión (Desde el Cráter)")
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
                    fig_l = px.line(d_t, x="Fecha_Recoleccion", y="Tamaño_Promedio_mm", color="Vereda", markers=True, hover_name="ID_Muestra", color_discrete_sequence=colores_profesionales, title="Seguimiento de Tamaño de Grano")
                    fig_l.update_traces(line=dict(width=3), marker=dict(size=8)); st.plotly_chart(fig_l, use_container_width=True)

        st.markdown("---")
        
        # --- 4. NUEVO: RELACIONES ESPACIALES Y ESTADÍSTICAS ---
        st.subheader("4. Análisis de Decaimiento y Correlación Estadística")
        c_dec, c_cor = st.columns(2)
        
        with c_dec:
            if 'Distancia_Crater_km' in df_fil.columns and 'Espesor_Deposito_mm' in df_fil.columns:
                fig_decay = px.scatter(df_fil, x="Distancia_Crater_km", y="Espesor_Deposito_mm", 
                                       color="Vereda", size="Tamaño_Promedio_mm", hover_name="ID_Muestra",
                                       title="Decaimiento del Espesor vs. Distancia al Cráter",
                                       labels={"Distancia_Crater_km": "Distancia al Cráter (km)", "Espesor_Deposito_mm": "Espesor (mm)"},
                                       color_discrete_sequence=colores_profesionales)
                st.plotly_chart(fig_decay, use_container_width=True)
            else:
                st.info("Faltan datos para calcular el decaimiento espacial.")

        with c_cor:
            cols_to_corr = cols_conteo + ['Espesor_Deposito_mm', 'Tamaño_Promedio_mm', 'Distancia_Crater_km']
            cols_to_corr = [c for c in cols_to_corr if c in df_fil.columns]
            
            if len(cols_to_corr) > 1:
                df_corr = df_fil[cols_to_corr].corr(method='pearson')
                fig_corr = px.imshow(df_corr, text_auto=".2f", aspect="auto", color_continuous_scale="RdBu_r", title="Matriz de Correlación (Pearson)", origin="lower")
                st.plotly_chart(fig_corr, use_container_width=True)
            else:
                st.info("No hay suficientes variables numéricas para la matriz de correlación.")

    except Exception as e: st.error(f"⚠️ Error renderizando el módulo de laboratorio: {e}")

def renderizar_modulo_operativo(df_fil):
    try:
        st.subheader("Semáforo de Gestión del Riesgo y Operaciones")
        
        cols_mostrar = ['ID_Muestra', 'Vereda', 'Distancia_Crater_km', 'Espesor_Deposito_mm', 'Nivel_Riesgo', 'Enlace_Reporte']
        cols_existentes = [c for c in cols_mostrar if c in df_fil.columns]
        df_mostrar = df_fil[cols_existentes].copy()
        
        def color_riesgo(val):
            if 'Alto' in str(val): return 'background-color: #FADBD8; color: #78281F;'
            elif 'Medio' in str(val): return 'background-color: #FDEBD0; color: #7E5109;'
            elif 'Bajo' in str(val): return 'background-color: #D5F5E3; color: #186A3B;'
            return ''
        
        if 'Nivel_Riesgo' in df_mostrar.columns:
            st.dataframe(df_mostrar.style.map(color_riesgo, subset=['Nivel_Riesgo']), hide_index=True, use_container_width=True)
        else:
            st.dataframe(df_mostrar, hide_index=True, use_container_width=True)

        st.markdown("---"); st.subheader("Base de Datos Estructural (Cruda)")
        st.dataframe(df_fil, use_container_width=True)
    except Exception as e: st.error(f"⚠️ Error cargando el módulo operativo: {e}")

# ==========================================
# 5. EJECUCIÓN PRINCIPAL (FLUJO DE UI)
# ==========================================
st.sidebar.title("Panel de Control")
if st.sidebar.button("🔄 Actualizar Datos de Origen", use_container_width=True): st.cache_data.clear(); st.rerun()
st.sidebar.markdown("---")

with st.sidebar.expander("📂 Carga de Datos", expanded=True):
    url_gs = st.text_input("🔗 Link Google Sheets (Público)", placeholder="Pega el link...")
    st.markdown("---")
    a_sub = st.file_uploader("O Excel/CSV Local", type=["xlsx", "csv"])
    a_geo = st.file_uploader("Capa Veredas (.geojson)", type=["geojson", "json"])
    st.markdown("---")
    fotos_subidas = st.file_uploader("📷 Subir Fotos (Multiselección)", type=["jpg", "jpeg", "png"], accept_multiple_files=True)

df_bruto, df_pct_bruto, c_conteo = cargar_y_limpiar_datos(a_sub, url_gs)

if df_bruto.empty:
    st.error("No se detectaron datos válidos.")
    st.stop()

st.sidebar.markdown("---")
with st.sidebar.expander("🗺️ Filtros Espaciales"):
    v_unicas = sorted(df_bruto.get('Vereda', pd.Series()).dropna().unique().tolist())
    if "v_sel" not in st.session_state: st.session_state["v_sel"] = v_unicas
    col1, col2 = st.columns(2)
    if col1.button("Todas", use_container_width=True): st.session_state["v_sel"] = v_unicas
    if col2.button("Limpiar", use_container_width=True): st.session_state["v_sel"] = []
    v_sel = st.multiselect("Vereda:", v_unicas, key="v_sel")

with st.sidebar.expander("📅 Filtros Temporales"):
    m_f = pd.Series(True, index=df_bruto.index)
    if 'Fecha_Recoleccion' in df_bruto.columns and not df_bruto['Fecha_Recoleccion'].isnull().all():
        df_bruto['Anio'] = df_bruto['Fecha_Recoleccion'].dt.year
        df_bruto['Mes'] = df_bruto['Fecha_Recoleccion'].dt.month
        a_sel = st.selectbox("Año:", ["Todos"] + sorted(df_bruto['Anio'].dropna().unique(), reverse=True))
        m_sel = st.selectbox("Mes:", ["Todos"] + [f"Mes {int(m)}" for m in (df_bruto[df_bruto['Anio']==a_sel]['Mes'].dropna().unique() if a_sel != "Todos" else range(1,13))])
        if a_sel != "Todos": m_f &= (df_bruto['Anio'] == a_sel)
        if m_sel != "Todos": m_f &= (df_bruto['Mes'] == int(m_sel.split()[1]))

m_v = df_bruto['Vereda'].isin(v_sel) if v_sel else pd.Series(True, index=df_bruto.index)
df_fil, df_pct_fil = df_bruto[m_v & m_f], df_pct_bruto[m_v & m_f]

if df_fil.empty: st.warning("⚠️ Sin resultados para los filtros aplicados.")
else:
    st.sidebar.download_button("📥 Descargar CSV Filtrado", df_fil.to_csv(index=False).encode('utf-8'), 'cenizas.csv', 'text/csv', use_container_width=True)
    
    renderizar_kpis(df_fil, c_conteo)
    
    t_espacial, t_laboratorio, t_operativo = st.tabs(["🌍 Módulo Espacial (Mapas)", "🔬 Módulo de Laboratorio (Mineralogía y Vientos)", "🗃️ Módulo Operativo (Datos y Riesgos)"])
    
    with t_espacial: renderizar_modulo_espacial(df_fil, a_geo)
    with t_laboratorio: renderizar_modulo_laboratorio(df_fil, df_pct_fil, c_conteo, fotos_subidas)
    with t_operativo: renderizar_modulo_operativo(df_fil)
