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
from scipy.interpolate import griddata

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

# ==========================================
# 2. FUNCIONES AUXILIARES (IMÁGENES)
# ==========================================
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
# 3. MOTOR DE DATOS CACHEADO
# ==========================================
@st.cache_data(show_spinner="Descargando, limpiando y optimizando base de datos...")
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
            'ID_Muestra': ['CAP-01', 'CAP-02', 'CAP-03'], 'Vereda': ['Chapio', 'Quintana', 'Coconuco'],
            'Latitud': [2.443, 2.450, 2.341], 'Longitud': [-76.606, -76.610, -76.510],
            'Tamaño_Promedio_mm': [0.5, 0.8, 2.1], 'Espesor_Deposito_mm': [10, 5, 2],
            'Fecha_Recoleccion': ['2026-08-01', '2026-08-05', '2026-08-10'],
            'LV1': [50, 20, 10], 'LVA1': [28, 15, 5], 'Plagioclasa': [69, 40, 10], 'FV1': [20, 50, 80], 'Cuarzo': [2, 5, 0],
            'URLs_Fotos': ['', '', ''], 'Enlace_Reporte': ['https://docs.google.com/', '', '']
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

    cols_info = ['ID_Muestra', 'Vereda', 'Latitud', 'Longitud', 'Tamaño_Promedio_mm', 'Espesor_Deposito_mm', 'URLs_Fotos', 'URL_Microscopio', 'Fecha_Recoleccion', 'Enlace_Reporte']
    cols_conteo = [col for col in df_temp.columns if col not in cols_info]
    
    for col in cols_conteo + ['Tamaño_Promedio_mm', 'Espesor_Deposito_mm']:
        if col in df_temp.columns: df_temp[col] = pd.to_numeric(df_temp[col], errors='coerce').fillna(0)

    df_temp['Total_Granos'] = df_temp[cols_conteo].sum(axis=1)
    
    df_pct_temp = df_temp.copy()
    for col in cols_conteo:
        df_pct_temp[col] = (df_temp[col] / df_temp['Total_Granos'].replace(0, 1)) * 100 

    return df_temp, df_pct_temp, cols_conteo

# ==========================================
# 4. MÓDULOS DE RENDERIZADO (VISTAS AISLADAS)
# ==========================================

def renderizar_kpis(df_fil, cols_conteo):
    try:
        st.subheader("📊 Resumen Ejecutivo")
        k1, k2, k3 = st.columns(3)
        k1.metric("Muestras Analizadas", len(df_fil))
        k2.metric("Espesor Máximo (mm)", df_fil['Espesor_Deposito_mm'].max() if 'Espesor_Deposito_mm' in df_fil.columns else "N/A")
        k3.metric("Mineral Dominante Global", df_fil[cols_conteo].sum().idxmax() if not df_fil[cols_conteo].empty else "N/A")
        st.markdown("---")
    except Exception as e: st.error(f"⚠️ Error al renderizar KPIs: {e}")

def renderizar_mapa(df_fil, archivo_geo):
    try:
        st.subheader("Distribución Espacial Base")
        tipo_mapa = st.radio("Seleccione la vista espacial:", ["📍 Puntos (2D)", "🔥 Calor (2D)", "🌋 Vista 3D (Volumen)"], horizontal=True)
        st.markdown("---")
        
        df_mapa = df_fil.dropna(subset=['Latitud', 'Longitud']).copy()
        if df_mapa.empty: return st.warning("No hay datos con coordenadas válidas.")
        
        c_lat, c_lon = df_mapa['Latitud'].mean(), df_mapa['Longitud'].mean()

        if "3D" in tipo_mapa:
            df_3d = df_mapa.dropna(subset=['Espesor_Deposito_mm']).copy()
            if df_3d.empty: return st.warning("Sin datos de 'Espesor_Deposito_mm' para 3D.")
            st.info("Arrastra con botón derecho (o Shift + clic) para rotar el 3D.")
            df_3d['Elev_V'] = df_3d['Espesor_Deposito_mm'] * 150 
            capa = pdk.Layer('ColumnLayer', data=df_3d, get_position='[Longitud, Latitud]', get_elevation='Elev_V', radius=150, get_fill_color='[200, 30, 30, 180]', pickable=True, auto_highlight=True)
            vista = pdk.ViewState(longitude=c_lon, latitude=c_lat, zoom=10.5, pitch=55, bearing=20)
            st.pydeck_chart(pdk.Deck(layers=[capa], initial_view_state=vista, tooltip={"html": "<b>{ID_Muestra}</b><br>Espesor: {Espesor_Deposito_mm} mm", "style": {"color": "white"}}, map_style='dark'), use_container_width=True)
            
        else:
            m = folium.Map(location=[c_lat, c_lon], zoom_start=11, tiles='CartoDB positron')
            folium.TileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Topo_Map/MapServer/tile/{z}/{y}/{x}', attr='Esri', name='Relieve Topográfico', overlay=False).add_to(m)
            folium.TileLayer('https://services.arcgis.com/WMSServer', attr='SGC', name='Amenaza (SGC)', overlay=True, opacity=0.7).add_to(m)
            if archivo_geo: folium.GeoJson(json.load(archivo_geo), name="Veredas", style_function=lambda f: {'fillColor': '#2980B9', 'color': '#2C3E50', 'weight': 1.5, 'fillOpacity': 0.15}).add_to(m)
            
            if "Puntos" in tipo_mapa:
                mc = MarkerCluster().add_to(m)
                for _, r in df_mapa.iterrows():
                    html = f"<b>{r.get('ID_Muestra', 'N/A')}</b><br>Vereda: {r.get('Vereda', 'N/A')}<br>Espesor: {r.get('Espesor_Deposito_mm', 0)} mm"
                    folium.Marker([r['Latitud'], r['Longitud']], popup=html, tooltip=str(r.get('ID_Muestra', '')), icon=folium.Icon(color="darkblue", icon="info-sign")).add_to(mc)
            elif "Calor" in tipo_mapa:
                h_data = df_mapa.dropna(subset=['Espesor_Deposito_mm'])
                if not h_data.empty: HeatMap([[r['Latitud'], r['Longitud'], r['Espesor_Deposito_mm']*2] for _, r in h_data.iterrows()], radius=25, blur=15).add_to(m)
            folium.LayerControl().add_to(m)
            st_folium(m, width="100%", height=550)
    except Exception as e: st.error(f"⚠️ Error al renderizar el mapa espacial: {e}")

# --- EL NUEVO MÓDULO ROBUSTO PARA EL OVSPO ---
def renderizar_modelamiento(df_fil):
    try:
        st.subheader("Modelamiento Espacial Volcánico")
        st.write("Generación de curvas de isovalores mediante interpolación matemática de datos de campo.")
        
        tipo_modelo = st.radio("Seleccione el modelo a generar:", ["🌋 Isopacas (Espesor del Depósito)", "🪨 Isopletas (Tamaño Máximo/Promedio de Grano)"], horizontal=True)
        st.markdown("---")
        
        columna_objetivo = 'Espesor_Deposito_mm' if 'Isopacas' in tipo_modelo else 'Tamaño_Promedio_mm'
        
        # Limpieza rigurosa para modelos matemáticos
        df_mod = df_fil.dropna(subset=['Latitud', 'Longitud', columna_objetivo]).copy()
        
        # Agrupar coordenadas exactas tomando el valor máximo (enfoque conservador para amenazas volcánicas)
        df_mod = df_mod.groupby(['Latitud', 'Longitud'], as_index=False).agg({columna_objetivo: 'max', 'ID_Muestra': 'first'})
        
        if len(df_mod) < 4:
            return st.warning(f"⚠️ Se requieren al menos 4 muestras con datos válidos de '{columna_objetivo}' y coordenadas distintas para garantizar una interpolación matemática segura.")

        x, y, z = df_mod['Longitud'].values, df_mod['Latitud'].values, df_mod[columna_objetivo].values
        
        # Generar grilla de alta resolución con márgenes adaptables
        margen_x = (x.max() - x.min()) * 0.2 if x.max() != x.min() else 0.05
        margen_y = (y.max() - y.min()) * 0.2 if y.max() != y.min() else 0.05
        
        grid_x, grid_y = np.mgrid[x.min()-margen_x:x.max()+margen_x:200j, y.min()-margen_y:y.max()+margen_y:200j]
        
        # Algoritmo de interpolación: Intentar Cúbico (más suave), sino Lineal
        try:
            grid_z = griddata((x, y), z, (grid_x, grid_y), method='cubic')
        except:
            grid_z = griddata((x, y), z, (grid_x, grid_y), method='linear')
            
        fig_iso = go.Figure()
        
        # Curvas de nivel
        fig_iso.add_trace(go.Contour(
            x=grid_x[:,0], y=grid_y[0,:], z=grid_z.T,
            colorscale='Reds' if 'Isopacas' in tipo_modelo else 'Viridis',
            contours=dict(showlabels=True, labelfont=dict(size=12, color='white')),
            name=f'{columna_objetivo} interpolado',
            opacity=0.85
        ))
        
        # Puntos reales
        fig_iso.add_trace(go.Scatter(
            x=x, y=y, mode='markers+text', text=df_mod['ID_Muestra'],
            textposition='top center', marker=dict(size=9, color='#1C2833', symbol='x'),
            name='Estaciones de Muestreo'
        ))
        
        fig_iso.update_layout(
            xaxis_title="Longitud", yaxis_title="Latitud",
            plot_bgcolor='#FAFAFA', height=600, margin=dict(l=0, r=0, t=30, b=0)
        )
        st.plotly_chart(fig_iso, use_container_width=True)
        st.caption("*Nota: La interpolación en los bordes del área muestreada puede presentar alta incertidumbre matemática.*")
        
    except Exception as e: st.error(f"⚠️ Error matemático en el modelamiento espacial: {e}")

def renderizar_composicion(df_fil, df_pct_fil, cols_conteo, fotos_subidas):
    try:
        st.subheader("Caracterización Mineralógica Individual")
        lista = df_fil["ID_Muestra"].tolist()
        if "idx_muestra" not in st.session_state or st.session_state["idx_muestra"] >= len(lista): st.session_state["idx_muestra"] = 0

        st.markdown("**🔍 Seleccione la Muestra a Analizar:**")
        c_prev, c_sel, c_next = st.columns([0.5, 4, 0.5])
        with c_prev:
            if st.button("⬅️", use_container_width=True): st.session_state["idx_muestra"] = (st.session_state["idx_muestra"] - 1) % len(lista); st.rerun()
        with c_sel:
            m_sel = st.selectbox("ID", options=lista, index=st.session_state["idx_muestra"], label_visibility="collapsed")
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
                📋 <b>Vereda:</b> {d_crudo.get('Vereda','N/A')} &nbsp;|&nbsp; 📅 <b>Fecha:</b> {f_val} &nbsp;|&nbsp; 📏 <b>Tamaño:</b> {d_crudo.get('Tamaño_Promedio_mm',0)} mm &nbsp;|&nbsp; 🔥 <b>Espesor:</b> {d_crudo.get('Espesor_Deposito_mm',0)} mm &nbsp;|&nbsp; 🔬 <b>Granos:</b> {d_crudo.get('Total_Granos',0)}
            </div>""", unsafe_allow_html=True)

        with col_f:
            # INTEGRACIÓN DEL CARGADOR DE FOTOS LOCALES
            fotos_locales_muestra = [f for f in fotos_subidas if m_sel.lower() in f.name.lower()]
            
            if fotos_locales_muestra:
                st.write("📷 **Fotografías Locales Cargadas:**")
                k_est = f"foto_loc_{m_sel}"
                if k_est not in st.session_state: st.session_state[k_est] = 0
                
                # Filtrar si se clickea un mineral
                if min_clic:
                    for i, f_obj in enumerate(fotos_locales_muestra):
                        if min_clic.lower() in f_obj.name.lower(): st.session_state[k_est] = i; break
                
                b1, tx, b2 = st.columns([1, 2, 1])
                if b1.button("⬅️ Anterior", key=f"pl_{m_sel}"): st.session_state[k_est] = (st.session_state[k_est] - 1) % len(fotos_locales_muestra)
                tx.markdown(f"<div style='text-align:center; margin-top:8px;'>Foto {st.session_state[k_est]+1}/{len(fotos_locales_muestra)}</div>", unsafe_allow_html=True)
                if b2.button("Siguiente ➡️", key=f"nl_{m_sel}"): st.session_state[k_est] = (st.session_state[k_est] + 1) % len(fotos_locales_muestra)
                
                foto_act = fotos_locales_muestra[st.session_state[k_est]]
                st.image(foto_act, caption=f"Archivo: {foto_act.name}", use_container_width=True)

            elif "URLs_Fotos" in d_crudo and pd.notna(d_crudo["URLs_Fotos"]):
                links = [u.strip() for u in str(d_crudo["URLs_Fotos"]).split(",") if u.strip().lower() != "nan"]
                if links:
                    st.write("🔗 **Registro Fotográfico en la Nube:**")
                    k_est = f"foto_url_{m_sel}"
                    if k_est not in st.session_state: st.session_state[k_est] = 0
                    if min_clic:
                        for i, l in enumerate(links):
                            if min_clic.lower() in l.lower(): st.session_state[k_est] = i; break
                    
                    b1, tx, b2 = st.columns([1, 2, 1])
                    if b1.button("⬅️ Anterior", key=f"pu_{m_sel}"): st.session_state[k_est] = (st.session_state[k_est] - 1) % len(links)
                    tx.markdown(f"<div style='text-align:center; margin-top:8px;'>Foto {st.session_state[k_est]+1}/{len(links)}</div>", unsafe_allow_html=True)
                    if b2.button("Siguiente ➡️", key=f"nu_{m_sel}"): st.session_state[k_est] = (st.session_state[k_est] + 1) % len(links)
                    
                    l_act = links[st.session_state[k_est]]
                    st.image(obtener_url_imagen(l_act), caption=f"{m_sel} | {obtener_nombre_foto(l_act)}", use_container_width=True)
                else: st.info("Sube las fotos en el menú lateral o pega los enlaces en la base de datos.")
            else: st.info("Sube las fotos en el menú lateral o pega los enlaces en la base de datos.")
    except Exception as e: st.error(f"⚠️ Error renderizando composición de muestra: {e}")

def renderizar_analisis(df_fil, df_pct_fil, cols_conteo):
    try:
        st.subheader("⚖️ Comparativa de Distribución Mineralógica")
        c1, c2 = st.columns(2)
        m1 = c1.selectbox("Muestra A:", df_fil['ID_Muestra'], key="c1")
        m2 = c2.selectbox("Muestra B:", df_fil['ID_Muestra'], index=1 if len(df_fil)>1 else 0, key="c2")
        
        d1 = df_pct_fil[df_pct_fil['ID_Muestra']==m1][cols_conteo].iloc[0].reset_index(); d1.columns, d1['Muestra'] = ['Componente','Porcentaje'], m1
        d2 = df_pct_fil[df_pct_fil['ID_Muestra']==m2][cols_conteo].iloc[0].reset_index(); d2.columns, d2['Muestra'] = ['Componente','Porcentaje'], m2
        
        f_bar = px.bar(pd.concat([d1[d1['Porcentaje']>0], d2[d2['Porcentaje']>0]]), x="Muestra", y="Porcentaje", color="Componente", text="Porcentaje", color_discrete_map=color_map_oficial)
        f_bar.update_traces(texttemplate='%{text:.1f}%', textposition='inside')
        st.plotly_chart(f_bar, use_container_width=True)

        st.markdown("---")
        st.subheader("🔺 Clasificación Petrológica de Cenizas (V-L-C)")
        c_v = [c for c in cols_conteo if 'FV' in c.upper() or 'VIDRIO' in c.upper()]
        c_l = [c for c in cols_conteo if 'LV' in c.upper() or 'LITICO' in c.upper() or 'LÍTICO' in c.upper()]
        c_c = [c for c in cols_conteo if c not in c_v + c_l]

        df_t = df_fil.copy()
        df_t['Vidrio'] = df_t[c_v].sum(axis=1) if c_v else 0
        df_t['Líticos'] = df_t[c_l].sum(axis=1) if c_l else 0
        df_t['Cristales'] = df_t[c_c].sum(axis=1) if c_c else 0
        df_t['Suma'] = df_t['Vidrio'] + df_t['Líticos'] + df_t['Cristales']
        df_tp = df_t[df_t['Suma'] > 0].copy()
        
        if not df_tp.empty:
            df_tp['V%'], df_tp['L%'], df_tp['C%'] = df_tp['Vidrio']/df_tp['Suma']*100, df_tp['Líticos']/df_tp['Suma']*100, df_tp['Cristales']/df_tp['Suma']*100
            fig_t = px.scatter_ternary(df_tp, a='V%', b='L%', c='C%', color="Vereda", hover_name="ID_Muestra", size="Tamaño_Promedio_mm", color_discrete_sequence=colores_profesionales)
            fig_t.update_layout(ternary=dict(aaxis_title='Vidrio %', baxis_title='Líticos %', caxis_title='Cristales %'), margin=dict(t=40,b=40,l=40,r=40))
            st.plotly_chart(fig_t, use_container_width=True)

        st.markdown("---")
        st.subheader("📊 Evolución Mineralógica Temporal (Área Apilada)")
        if 'Fecha_Recoleccion' in df_fil.columns and not df_fil['Fecha_Recoleccion'].dropna().empty:
            df_a = df_pct_fil.copy(); df_a['Fecha'] = df_fil['Fecha_Recoleccion']
            df_a = df_a.dropna(subset=['Fecha']).groupby('Fecha')[cols_conteo].mean().reset_index().melt(id_vars='Fecha', value_vars=cols_conteo, var_name='Componente', value_name='Porcentaje')
            fig_a = px.area(df_a, x="Fecha", y="Porcentaje", color="Componente", color_discrete_map=color_map_oficial)
            fig_a.update_layout(yaxis=dict(range=[0, 100]), margin=dict(t=20, b=20, l=10, r=10))
            st.plotly_chart(fig_a, use_container_width=True)
        else: st.info("Requiere datos temporales para visualizar la evolución.")
    except Exception as e: st.error(f"⚠️ Error renderizando gráficos avanzados: {e}")

def renderizar_tamano(df_fil, df_pct_fil, cols_conteo):
    try:
        st.subheader("📈 Evolución Temporal del Tamaño de Grano")
        if 'Fecha_Recoleccion' in df_fil.columns and 'Tamaño_Promedio_mm' in df_fil.columns:
            d_t = df_fil.dropna(subset=['Fecha_Recoleccion', 'Tamaño_Promedio_mm']).sort_values('Fecha_Recoleccion')
            if not d_t.empty:
                fig_l = px.line(d_t, x="Fecha_Recoleccion", y="Tamaño_Promedio_mm", color="Vereda", markers=True, hover_name="ID_Muestra", color_discrete_sequence=colores_profesionales)
                fig_l.update_traces(line=dict(width=3), marker=dict(size=8)); st.plotly_chart(fig_l, use_container_width=True)
            else: st.info("Datos temporales insuficientes.")
            
            st.markdown("---")
            st.subheader("🔬 Relación: Tamaño vs. Mineralogía")
            min_sel = st.selectbox("Seleccione componente:", cols_conteo)
            d_sc = df_fil[['ID_Muestra', 'Vereda', 'Tamaño_Promedio_mm']].copy(); d_sc['%'] = df_pct_fil[min_sel]
            fig_s = px.scatter(d_sc, x="Tamaño_Promedio_mm", y="%", color="Vereda", hover_name="ID_Muestra", size="Tamaño_Promedio_mm", trendline="ols", color_discrete_sequence=colores_profesionales, labels={"%": f"% {min_sel}"})
            st.plotly_chart(fig_s, use_container_width=True)
        else: st.warning("Faltan columnas de fecha o tamaño de grano.")
    except Exception as e: st.error(f"⚠️ Error renderizando sección de tamaño: {e}")

def renderizar_datos(df_fil):
    try:
        st.subheader("Verificación Operativa")
        if 'Enlace_Reporte' in df_fil.columns: st.dataframe(df_fil[['ID_Muestra', 'Vereda', 'Fecha_Recoleccion', 'Enlace_Reporte']], column_config={"Enlace_Reporte": st.column_config.LinkColumn("Reporte")}, hide_index=True, use_container_width=True)
        st.markdown("---"); st.subheader("Consolidado (Base Cruda)")
        st.dataframe(df_fil, use_container_width=True)
    except Exception as e: st.error(f"⚠️ Error cargando la base de datos: {e}")

# ==========================================
# 5. EJECUCIÓN PRINCIPAL (DISEÑO LIMPIO)
# ==========================================
st.sidebar.title("Panel de Control")
if st.sidebar.button("🔄 Actualizar Datos de Origen", use_container_width=True): st.cache_data.clear(); st.rerun()
st.sidebar.markdown("---")

with st.sidebar.expander("📂 Carga de Datos", expanded=True):
    url_gs = st.text_input("🔗 Link Google Sheets (Público)", placeholder="Pega el link...")
    a_sub = st.file_uploader("O Excel/CSV Local", type=["xlsx", "csv"])
    a_geo = st.file_uploader("Capa Veredas (.geojson)", type=["geojson", "json"])
    st.markdown("---")
    st.markdown("<small><i>Sube varias fotos a la vez y se asignarán automáticamente según el ID en su nombre.</i></small>", unsafe_allow_html=True)
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
        df_bruto['Anio'], df_bruto['Mes'] = df_bruto['Fecha_Recoleccion'].dt.year, df_bruto['Fecha_Recoleccion'].dt.month
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
    
    # NUEVA PESTAÑA AÑADIDA: Modelamiento (Isopacas/Isopletas)
    t1, t2, t3, t4, t5, t6 = st.tabs(["Distribución", "Composición", "Análisis Avanzado", "Tamaño", "🗺️ Modelamiento", "➕ Datos Crudos"])
    
    with t1: renderizar_mapa(df_fil, a_geo)
    with t2: renderizar_composicion(df_fil, df_pct_fil, c_conteo, fotos_subidas)
    with t3: renderizar_analisis(df_fil, df_pct_fil, c_conteo)
    with t4: renderizar_tamano(df_fil, df_pct_fil, c_conteo)
    with t5: renderizar_modelamiento(df_fil)
    with t6: renderizar_datos(df_fil)
