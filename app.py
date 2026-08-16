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
st.sidebar.image("https://cdn-icons-png.flaticon.com/512/2909/2909592.png", width=100) # Logo de ejemplo
st.sidebar.title("Panel de Control")
archivo_subido = st.sidebar.file_uploader("📂 Sube tu Base de Datos (Excel/CSV)", type=["xlsx", "csv"])

if archivo_subido is not None:
    if archivo_subido.name.endswith('.csv'):
        df = pd.read_csv(archivo_subido)
    else:
        df = pd.read_excel(archivo_subido)
else:
    # DATOS DE PRUEBA AVANZADOS
    st.info("👆 Carga tu Excel. Mostrando datos de prueba de la región del Puracé/Popayán.")
    datos_prueba = {
        'ID_Muestra': ['CEN-01', 'CEN-02', 'CEN-03', 'CEN-04', 'CEN-05'],
        'Vereda': ['Quintana', 'Poblazón', 'Quintana', 'Coconuco', 'Paletará'],
        'Latitud': [2.443, 2.450, 2.435, 2.341, 2.152], 
        'Longitud': [-76.606, -76.610, -76.590, -76.510, -76.621],
        'Tamaño_Promedio_mm': [0.5, 0.8, 0.4, 2.1, 3.5], # Tamaños para tendencias
        'Cuarzo_%': [40, 20, 50, 15, 10],
        'Feldespato_%': [30, 50, 20, 25, 10],
        'Vidrio_%': [20, 20, 20, 50, 70],
        'Plagioclasa_%': [10, 10, 10, 10, 10], # Nuevo mineral
        'URLs_Fotos': [
            'https://upload.wikimedia.org/wikipedia/commons/thumb/1/1a/Volcanic_ash.jpg/320px-Volcanic_ash.jpg',
            'https://upload.wikimedia.org/wikipedia/commons/thumb/1/1a/Volcanic_ash.jpg/320px-Volcanic_ash.jpg',
            'https://upload.wikimedia.org/wikipedia/commons/thumb/1/1a/Volcanic_ash.jpg/320px-Volcanic_ash.jpg',
            'https://upload.wikimedia.org/wikipedia/commons/thumb/1/1a/Volcanic_ash.jpg/320px-Volcanic_ash.jpg',
            'https://upload.wikimedia.org/wikipedia/commons/thumb/1/1a/Volcanic_ash.jpg/320px-Volcanic_ash.jpg'
        ],
        'URL_Microscopio': [
            'https://upload.wikimedia.org/wikipedia/commons/thumb/7/70/Volcanic_sand_from_the_black_sand_beach_of_Punalu%CA%BBu.jpg/800px-Volcanic_sand_from_the_black_sand_beach_of_Punalu%CA%BBu.jpg',
            'https://upload.wikimedia.org/wikipedia/commons/thumb/7/70/Volcanic_sand_from_the_black_sand_beach_of_Punalu%CA%BBu.jpg/800px-Volcanic_sand_from_the_black_sand_beach_of_Punalu%CA%BBu.jpg',
            'https://upload.wikimedia.org/wikipedia/commons/thumb/7/70/Volcanic_sand_from_the_black_sand_beach_of_Punalu%CA%BBu.jpg/800px-Volcanic_sand_from_the_black_sand_beach_of_Punalu%CA%BBu.jpg',
            'https://upload.wikimedia.org/wikipedia/commons/thumb/7/70/Volcanic_sand_from_the_black_sand_beach_of_Punalu%CA%BBu.jpg/800px-Volcanic_sand_from_the_black_sand_beach_of_Punalu%CA%BBu.jpg',
            'https://upload.wikimedia.org/wikipedia/commons/thumb/7/70/Volcanic_sand_from_the_black_sand_beach_of_Punalu%CA%BBu.jpg/800px-Volcanic_sand_from_the_black_sand_beach_of_Punalu%CA%BBu.jpg'
        ]
    }
    df = pd.DataFrame(datos_prueba)

# 3. FILTROS AVANZADOS
st.sidebar.markdown("---")
st.sidebar.subheader("🔍 Filtros de Búsqueda")

# Filtro por Vereda
veredas_unicas = df['Vereda'].unique().tolist()
veredas_seleccionadas = st.sidebar.multiselect("Filtrar por Vereda:", veredas_unicas, default=veredas_unicas)

min_cuarzo = st.sidebar.slider("Mínimo de Cuarzo (%):", 0, 100, 0)
min_tamano = st.sidebar.slider("Tamaño mínimo (mm):", float(df['Tamaño_Promedio_mm'].min()), float(df['Tamaño_Promedio_mm'].max()), float(df['Tamaño_Promedio_mm'].min()))

# Aplicar filtros
df_filtrado = df[
    (df['Cuarzo_%'] >= min_cuarzo) & 
    (df['Tamaño_Promedio_mm'] >= min_tamano) &
    (df['Vereda'].isin(veredas_seleccionadas))
]

# 4. DASHBOARD (PESTAÑAS)
if df_filtrado.empty:
    st.warning("No hay muestras con estos filtros.")
else:
    # Métricas rápidas arriba
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Muestras Visibles", len(df_filtrado))
    c2.metric("Tamaño Promedio", f"{df_filtrado['Tamaño_Promedio_mm'].mean():.2f} mm")
    c3.metric("Vidrio Promedio", f"{df_filtrado['Vidrio_%'].mean():.1f}%")
    c4.metric("Cuarzo Promedio", f"{df_filtrado['Cuarzo_%'].mean():.1f}%")
    st.markdown("---")

    # Crear pestañas de navegación
    tab1, tab2, tab3, tab4 = st.tabs(["🗺️ Mapa Interactivo", "📊 Composición y Tendencias", "🔬 Visor AmScope (Microscopio)", "💾 Datos"])

    # --- PESTAÑA 1: MAPA ---
    with tab1:
        col_mapa, col_info = st.columns([2, 1])
        with col_mapa:
            centro_lat = df_filtrado['Latitud'].mean()
            centro_lon = df_filtrado['Longitud'].mean()
            m = folium.Map(location=[centro_lat, centro_lon], zoom_start=10, tiles='OpenStreetMap')
            
            # TODO: Aquí cargaremos el archivo GeoJSON de Veredas cuando lo consigas
            
            marker_cluster = MarkerCluster().add_to(m)
            
            for idx, row in df_filtrado.iterrows():
                html_popup = f"""
                <div style='width:200px'>
                <b>{row['ID_Muestra']}</b><br>
                <b>Vereda:</b> {row['Vereda']}<br>
                <b>Tamaño:</b> {row['Tamaño_Promedio_mm']} mm<br>
                </div>
                """
                folium.Marker(
                    location=[row['Latitud'], row['Longitud']],
                    popup=folium.Popup(html_popup, max_width=300),
                    tooltip=row['ID_Muestra'],
                    icon=folium.Icon(color="red", icon="info-sign")
                ).add_to(marker_cluster)
                
            st_folium(m, width="100%", height=500)

        with col_info:
            st.info("💡 **Tip:** Haz clic en los grupos numéricos para acercarte a las muestras.")
            muestra_sel = st.selectbox("Ver fotos de campo de:", df_filtrado['ID_Muestra'])
            datos_m = df_filtrado[df_filtrado['ID_Muestra'] == muestra_sel].iloc[0]
            urls = str(datos_m['URLs_Fotos']).split(',')
            for url in urls:
                if url.strip():
                    st.image(url.strip(), use_container_width=True)

    # --- PESTAÑA 2: COMPOSICIÓN Y TENDENCIAS ---
    with tab2:
        col_graf1, col_graf2 = st.columns(2)
        
        with col_graf1:
            st.subheader("Composición Promedio de la Zona")
            minerales = ['Cuarzo_%', 'Feldespato_%', 'Vidrio_%', 'Plagioclasa_%']
            promedios = [df_filtrado[min].mean() for min in minerales]
            fig_pie = px.pie(names=minerales, values=promedios, hole=0.3, color_discrete_sequence=px.colors.qualitative.Pastel)
            st.plotly_chart(fig_pie, use_container_width=True)
            
        with col_graf2:
            st.subheader("📈 Tendencia: Tamaño vs Contenido de Vidrio")
            # Gráfico de dispersión para ver correlaciones
            fig_scatter = px.scatter(
                df_filtrado, x="Tamaño_Promedio_mm", y="Vidrio_%", 
                color="Vereda", hover_name="ID_Muestra",
                size="Tamaño_Promedio_mm", # Los puntos más grandes = muestras más grandes
                trendline="ols" # Línea de tendencia
            )
            st.plotly_chart(fig_scatter, use_container_width=True)

    # --- PESTAÑA 3: VISOR AMSCOPE ---
    with tab3:
        st.subheader("🔬 Análisis Microscópico Avanzado")
        st.write("Selecciona una muestra para visualizar la captura del microscopio AmScope. Recomendamos imágenes con barra de escala incluida.")
        
        muestra_micro = st.selectbox("Seleccionar muestra para microscopía:", df_filtrado['ID_Muestra'], key="micro_sel")
        datos_micro = df_filtrado[df_filtrado['ID_Muestra'] == muestra_micro].iloc[0]
        
        # Mostrar la imagen del microscopio en tamaño muy grande
        url_micro = str(datos_micro.get('URL_Microscopio', ''))
        if url_micro.strip() and url_micro != 'nan':
            # use_container_width permite que la imagen sea responsiva y grande
            st.image(url_micro.strip(), caption=f"Microfotografía AmScope - Muestra {muestra_micro}", use_container_width=True)
        else:
            st.warning("No hay foto de microscopio disponible para esta muestra.")

    # --- PESTAÑA 4: DATOS CRUDOS ---
    with tab4:
        st.subheader("Tabla de Datos Filtrados")
        st.dataframe(df_filtrado, use_container_width=True)
