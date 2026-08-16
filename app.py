import streamlit as st
import pandas as pd
import plotly.express as px
import folium
from streamlit_folium import st_folium
from folium.plugins import MarkerCluster

# 1. CONFIGURACIÓN DE PÁGINA (Debe ser la primera línea)
st.set_page_config(page_title="Geovisor Pro de Cenizas", page_icon="🌋", layout="wide")

# Custom CSS para que se vea más profesional
st.markdown("""
    <style>
    .stMetric { background-color: #f0f2f6; padding: 15px; border-radius: 10px; }
    </style>
""", unsafe_allow_html=True)

st.title("🌋 Geovisor Interactivo: Análisis de Cenizas Volcánicas")
st.markdown("Plataforma de visualización y análisis mineralógico de muestras recolectadas.")

# 2. CARGA DE DATOS (BARRA LATERAL)
st.sidebar.image("https://upload.wikimedia.org/wikipedia/commons/thumb/1/1a/Volcanic_ash.jpg/320px-Volcanic_ash.jpg", use_container_width=True)
st.sidebar.title("📁 Gestión de Datos")
archivo_subido = st.sidebar.file_uploader("Sube tu matriz de datos (Excel/CSV)", type=["xlsx", "csv"])

# Función para cargar datos (evita que se recargue todo el tiempo)
@st.cache_data
def cargar_datos(archivo):
    if archivo is not None:
        if archivo.name.endswith('.csv'):
            return pd.read_csv(archivo)
        else:
            return pd.read_excel(archivo)
    else:
        # DATOS DE PRUEBA: Centrados cerca al Puracé / Popayán
        return pd.DataFrame({
            'ID_Muestra': ['PUR-01', 'PUR-02', 'PUR-03', 'POP-01', 'POP-02'],
            'Latitud': [2.330, 2.345, 2.320, 2.450, 2.440], 
            'Longitud': [-76.390, -76.400, -76.380, -76.600, -76.610],
            'Cuarzo_%': [15, 25, 10, 45, 50],
            'Feldespato_%': [40, 35, 45, 20, 15],
            'Vidrio_%': [45, 40, 45, 35, 35],
            'URLs_Fotos': [
                'https://upload.wikimedia.org/wikipedia/commons/4/4e/Volcanic_ash_under_light_microscope.jpg',
                'https://upload.wikimedia.org/wikipedia/commons/4/4e/Volcanic_ash_under_light_microscope.jpg,https://upload.wikimedia.org/wikipedia/commons/1/1a/Volcanic_ash.jpg',
                'https://upload.wikimedia.org/wikipedia/commons/1/1a/Volcanic_ash.jpg',
                'https://upload.wikimedia.org/wikipedia/commons/4/4e/Volcanic_ash_under_light_microscope.jpg',
                'https://upload.wikimedia.org/wikipedia/commons/1/1a/Volcanic_ash.jpg'
            ]
        })

df = cargar_datos(archivo_subido)

# 3. FILTROS AVANZADOS (BARRA LATERAL)
st.sidebar.markdown("---")
st.sidebar.subheader("🔍 Filtros de Mineralogía")
filtro_cuarzo = st.sidebar.slider("Cuarzo (%)", int(df['Cuarzo_%'].min()), int(df['Cuarzo_%'].max()), (int(df['Cuarzo_%'].min()), int(df['Cuarzo_%'].max())))
filtro_vidrio = st.sidebar.slider("Vidrio Volcánico (%)", int(df['Vidrio_%'].min()), int(df['Vidrio_%'].max()), (int(df['Vidrio_%'].min()), int(df['Vidrio_%'].max())))

# Aplicar filtros
df_filtrado = df[
    (df['Cuarzo_%'] >= filtro_cuarzo[0]) & (df['Cuarzo_%'] <= filtro_cuarzo[1]) &
    (df['Vidrio_%'] >= filtro_vidrio[0]) & (df['Vidrio_%'] <= filtro_vidrio[1])
]

# 4. DASHBOARD DE MÉTRICAS (KPIs)
st.markdown("### Resumen de Muestras Visibles")
col_m1, col_m2, col_m3, col_m4 = st.columns(4)
col_m1.metric("Total Muestras", len(df_filtrado))
if not df_filtrado.empty:
    col_m2.metric("Promedio Cuarzo", f"{df_filtrado['Cuarzo_%'].mean():.1f}%")
    col_m3.metric("Promedio Vidrio", f"{df_filtrado['Vidrio_%'].mean():.1f}%")
    col_m4.metric("Máximo Feldespato", f"{df_filtrado['Feldespato_%'].max()}%")

st.markdown("---")

if df_filtrado.empty:
    st.error("No hay datos que coincidan con los filtros actuales.")
else:
    # 5. SISTEMA DE PESTAÑAS (TABS)
    tab1, tab2, tab3 = st.tabs(["🗺️ Mapa Principal", "🔬 Análisis por Muestra y Fotos", "📋 Tabla de Datos"])

    # --- PESTAÑA 1: MAPA ---
    with tab1:
        st.markdown("### Distribución Espacial de las Muestras")
        
        # Calcular el centro del mapa
        centro_lat = df_filtrado['Latitud'].mean()
        centro_lon = df_filtrado['Longitud'].mean()
        
        # Crear mapa base de Folium (mejor para 130 puntos)
        m = folium.Map(location=[centro_lat, centro_lon], zoom_start=11, tiles="CartoDB positron")
        
        # Agregar el Clustering (Agrupador de puntos)
        marker_cluster = MarkerCluster().add_to(m)
        
        for idx, row in df_filtrado.iterrows():
            # Crear ventana emergente (popup) al hacer clic en el mapa
            popup_html = f"""
            <b>Muestra:</b> {row['ID_Muestra']}<br>
            <b>Cuarzo:</b> {row['Cuarzo_%']}%<br>
            <b>Vidrio:</b> {row['Vidrio_%']}%
            """
            folium.Marker(
                location=[row['Latitud'], row['Longitud']],
                popup=folium.Popup(popup_html, max_width=200),
                tooltip=f"Clic para ver: {row['ID_Muestra']}",
                icon=folium.Icon(color="darkred", icon="info-sign")
            ).add_to(marker_cluster)
            
        # Mostrar el mapa en Streamlit
        st_folium(m, width="100%", height=600, returned_objects=[])

    # --- PESTAÑA 2: ANÁLISIS INDIVIDUAL Y FOTOS ---
    with tab2:
        col_select, col_empty = st.columns([1, 2])
        with col_select:
            muestra_seleccionada = st.selectbox("🔎 Busca o selecciona el ID de la muestra:", df_filtrado['ID_Muestra'])
        
        datos_muestra = df_filtrado[df_filtrado['ID_Muestra'] == muestra_seleccionada].iloc[0]
        
        col_grafica, col_fotos = st.columns([1, 1.5])
        
        with col_grafica:
            st.markdown(f"#### Composición Mineralógica: `{muestra_seleccionada}`")
            minerales = ['Cuarzo_%', 'Feldespato_%', 'Vidrio_%']
            valores = [datos_muestra['Cuarzo_%'], datos_muestra['Feldespato_%'], datos_muestra['Vidrio_%']]
            
            fig_bar = px.bar(
                x=minerales, y=valores, 
                labels={'x': 'Mineral', 'y': 'Porcentaje (%)'},
                color=minerales,
                color_discrete_sequence=['#E6B8B8', '#B8CCE6', '#C1E6B8'] # Colores estéticos
            )
            fig_bar.update_layout(showlegend=False)
            st.plotly_chart(fig_bar, use_container_width=True)
            
        with col_fotos:
            st.markdown(f"#### Registro Fotográfico")
            # Soporte para múltiples fotos! (Separadas por coma en el Excel)
            urls = str(datos_muestra['URLs_Fotos']).split(',')
            
            if len(urls) == 1 and urls[0] != 'nan' and urls[0] != '':
                st.image(urls[0].strip(), caption=f"Foto de {muestra_seleccionada}", use_container_width=True)
            elif len(urls) > 1:
                # Si hay varias fotos, las mostramos en una galería (columnas)
                galeria_cols = st.columns(len(urls))
                for i, col_gal in enumerate(galeria_cols):
                    with col_gal:
                        st.image(urls[i].strip(), caption=f"Toma {i+1}", use_container_width=True)
            else:
                st.info("No hay fotografías disponibles para esta muestra.")

    # --- PESTAÑA 3: TABLA DE DATOS ---
    with tab3:
        st.markdown("### Matriz de Datos Filtrada")
        st.dataframe(df_filtrado, use_container_width=True)
        
        # Botón para descargar los datos filtrados
        csv = df_filtrado.to_csv(index=False).encode('utf-8')
        st.download_button(
            label="⬇️ Descargar datos actuales (CSV)",
            data=csv,
            file_name='muestras_filtradas.csv',
            mime='text/csv',
        )
