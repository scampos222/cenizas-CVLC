import streamlit as st
import pandas as pd
import plotly.express as px
import folium
from folium.plugins import MarkerCluster
from streamlit_folium import st_folium

# 1. CONFIGURACIÓN
st.set_page_config(page_title="Geovisor de Cenizas Nivel Pro", layout="wide", page_icon="🌋")
st.title("🌋 Geovisor Integral de Cenizas Volcánicas")

# 2. CARGA DE DATOS Y BARRA LATERAL
st.sidebar.title("Panel de Control")
archivo_subido = st.sidebar.file_uploader("📂 Sube tu Base de Datos (Conteos)", type=["xlsx", "csv"])

if archivo_subido is not None:
    if archivo_subido.name.endswith('.csv'):
        df = pd.read_csv(archivo_subido)
    else:
        df = pd.read_excel(archivo_subido)
else:
    # DATOS DE PRUEBA (Ahora con conteos enteros)
    st.info("👆 Carga tu Excel. Mostrando datos de prueba.")
    datos_prueba = {
        'ID_Muestra': ['CAP-01', 'CAP-02', 'CAP-03'],
        'Vereda': ['Chapio', 'Quintana', 'Coconuco'],
        'Latitud': [2.443, 2.450, 2.341], 
        'Longitud': [-76.606, -76.610, -76.510],
        'Tamaño_Promedio_mm': [0.5, 0.8, 2.1],
        'LV1': [50, 20, 10],      # Lítico Gris
        'LVA1': [28, 15, 5],      # Lítico Alterado
        'Plagioclasa': [69, 40, 10],
        'FV1': [20, 50, 80],      # Vidrio
        'Cuarzo': [2, 5, 0],
        'URLs_Fotos': ['https://upload.wikimedia.org/wikipedia/commons/thumb/1/1a/Volcanic_ash.jpg/320px-Volcanic_ash.jpg', '', ''],
        'URL_Microscopio': ['', '', '']
    }
    df = pd.DataFrame(datos_prueba)

# --- PROCESAMIENTO MATEMÁTICO AUTOMÁTICO ---
# Definir qué columnas NO son minerales
cols_info = ['ID_Muestra', 'Vereda', 'Latitud', 'Longitud', 'Tamaño_Promedio_mm', 'URLs_Fotos', 'URL_Microscopio']

# Detectar automáticamente las columnas de conteo (todas las numéricas que no estén en cols_info)
cols_conteo = [col for col in df.columns if col not in cols_info and pd.api.types.is_numeric_dtype(df[col])]

# Calcular el total de granos por muestra
df['Total_Granos'] = df[cols_conteo].sum(axis=1)

# Calcular porcentajes dinámicamente para usar en gráficas
df_pct = df.copy()
for col in cols_conteo:
    # Evitar división por cero
    df_pct[col] = (df[col] / df['Total_Granos']).fillna(0) * 100

# 3. FILTROS EN BARRA LATERAL
st.sidebar.markdown("---")
st.sidebar.subheader("🔍 Filtros")
if 'Vereda' in df.columns:
    veredas_unicas = df['Vereda'].dropna().unique().tolist()
    veredas_seleccionadas = st.sidebar.multiselect("Filtrar por Vereda:", veredas_unicas, default=veredas_unicas)
else:
    veredas_seleccionadas = []

# Filtrar el DataFrame
if veredas_seleccionadas:
    df_filtrado = df[df['Vereda'].isin(veredas_seleccionadas)]
    df_pct_filtrado = df_pct[df_pct['Vereda'].isin(veredas_seleccionadas)]
else:
    df_filtrado = df
    df_pct_filtrado = df_pct

# 4. DASHBOARD
if df_filtrado.empty:
    st.warning("No hay datos para mostrar con los filtros actuales.")
else:
    # Métricas superiores
    c1, c2, c3 = st.columns(3)
    c1.metric("Muestras Visibles", len(df_filtrado))
    c2.metric("Total Granos Contados", int(df_filtrado['Total_Granos'].sum()))
    if 'Tamaño_Promedio_mm' in df_filtrado.columns:
        c3.metric("Tamaño Promedio", f"{df_filtrado['Tamaño_Promedio_mm'].mean():.2f} mm")
    st.markdown("---")

    tab1, tab2, tab3, tab4 = st.tabs(["🗺️ Mapa Interactivo", "📊 Composición de Muestra", "⚖️ Comparativa", "💾 Base de Datos"])

    # --- PESTAÑA 1: MAPA ---
    with tab1:
        centro_lat = df_filtrado['Latitud'].mean()
        centro_lon = df_filtrado['Longitud'].mean()
        m = folium.Map(location=[centro_lat, centro_lon], zoom_start=11, tiles='OpenStreetMap')
        marker_cluster = MarkerCluster().add_to(m)
        
        for idx, row in df_filtrado.iterrows():
            html_popup = f"""
            <div style='width:200px'>
            <b>ID: {row.get('ID_Muestra', 'N/A')}</b><br>
            <b>Vereda:</b> {row.get('Vereda', 'N/A')}<br>
            <b>Granos analizados:</b> {int(row['Total_Granos'])}<br>
            </div>
            """
            folium.Marker(
                location=[row['Latitud'], row['Longitud']],
                popup=folium.Popup(html_popup, max_width=300),
                tooltip=str(row.get('ID_Muestra', 'Muestra')),
                icon=folium.Icon(color="red", icon="info-sign")
            ).add_to(marker_cluster)
            
        st_folium(m, width="100%", height=500)

    # --- PESTAÑA 2: GRÁFICAS POR MUESTRA ---
    with tab2:
        st.subheader("Análisis Detallado por Muestra")
        muestra_sel = st.selectbox("Selecciona una muestra para ver su mineralogía:", df_filtrado['ID_Muestra'])
        
        # Obtener los porcentajes de la muestra seleccionada
        datos_muestra_pct = df_pct_filtrado[df_pct_filtrado['ID_Muestra'] == muestra_sel][cols_conteo].iloc[0]
        
        # Filtrar componentes que sean mayores a 0 para que la gráfica no se sature
        datos_grafica = datos_muestra_pct[datos_muestra_pct > 0].reset_index()
        datos_grafica.columns = ['Componente', 'Porcentaje']
        datos_grafica = datos_grafica.sort_values(by='Porcentaje', ascending=False)
        
        col_graf, col_foto = st.columns([2, 1])
        with col_graf:
            fig_pie = px.pie(
                datos_grafica, 
                names='Componente', 
                values='Porcentaje',
                hole=0.4,
                title=f"Composición Porcentual - {muestra_sel}"
            )
            fig_pie.update_traces(textposition='inside', textinfo='percent+label')
            st.plotly_chart(fig_pie, use_container_width=True)
            
        with col_foto:
            # Mostrar foto si existe
            datos_m_crudos = df_filtrado[df_filtrado['ID_Muestra'] == muestra_sel].iloc[0]
            if 'URLs_Fotos' in datos_m_crudos and pd.notna(datos_m_crudos['URLs_Fotos']):
                url = str(datos_m_crudos['URLs_Fotos']).split(',')[0].strip()
                if url:
                    st.image(url, caption="Foto Macroscópica", use_container_width=True)
            else:
                st.info("Sin foto macroscópica.")

    # --- PESTAÑA 3: DATOS CRUDOS ---
    with tab4 if 'tab4' in locals() else tab3:
        st.subheader("Base de Datos (Conteos Crudos)")
        st.dataframe(df_filtrado, use_container_width=True)
        # --- PESTAÑA 3: COMPARATIVA LADO A LADO ---
    with tab3:
        st.subheader("⚖️ Comparativa de Mineralogía entre dos Muestras")
        st.write("Selecciona dos muestras para contrastar su composición porcentual.")
        
        # Crear dos columnas idénticas
        comp_col1, comp_col2 = st.columns(2)
        
        with comp_col1:
            muestra_1 = st.selectbox("Primera Muestra:", df_filtrado['ID_Muestra'], key="comp1")
            datos_m1_pct = df_pct_filtrado[df_pct_filtrado['ID_Muestra'] == muestra_1][cols_conteo].iloc[0]
            datos_grafica_1 = datos_m1_pct[datos_m1_pct > 0].reset_index()
            datos_grafica_1.columns = ['Componente', 'Porcentaje']
            
            fig_pie_1 = px.pie(datos_grafica_1, names='Componente', values='Porcentaje', hole=0.4, title=f"Composición - {muestra_1}")
            fig_pie_1.update_traces(textposition='inside', textinfo='percent+label')
            st.plotly_chart(fig_pie_1, use_container_width=True)
            
        with comp_col2:
            # Seleccionamos la segunda muestra por defecto si hay más de una
            idx_default = 1 if len(df_filtrado) > 1 else 0
            muestra_2 = st.selectbox("Segunda Muestra:", df_filtrado['ID_Muestra'], index=idx_default, key="comp2")
            datos_m2_pct = df_pct_filtrado[df_pct_filtrado['ID_Muestra'] == muestra_2][cols_conteo].iloc[0]
            datos_grafica_2 = datos_m2_pct[datos_m2_pct > 0].reset_index()
            datos_grafica_2.columns = ['Componente', 'Porcentaje']
            
            fig_pie_2 = px.pie(datos_grafica_2, names='Componente', values='Porcentaje', hole=0.4, title=f"Composición - {muestra_2}")
            fig_pie_2.update_traces(textposition='inside', textinfo='percent+label')
            st.plotly_chart(fig_pie_2, use_container_width=True)

    # --- PESTAÑA 4: DATOS CRUDOS ---
    with tab4:
        st.subheader("Base de Datos (Conteos Crudos)")
        st.dataframe(df_filtrado, use_container_width=True)
