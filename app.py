import streamlit as st
import pandas as pd
import plotly.express as px

# 1. CONFIGURACIÓN
st.set_page_config(page_title="Geovisor de Cenizas", layout="wide")
st.title("🌋 Geovisor Interactivo de Cenizas")

# 2. BARRA LATERAL PARA CARGAR DATOS Y FILTRAR
st.sidebar.title("Herramientas")
archivo_subido = st.sidebar.file_uploader("1. Sube tu archivo Excel o CSV", type=["xlsx", "csv"])

# Lógica para cargar datos (los tuyos o los de prueba)
if archivo_subido is not None:
    if archivo_subido.name.endswith('.csv'):
        df = pd.read_csv(archivo_subido)
    else:
        df = pd.read_excel(archivo_subido)
else:
    st.info("👆 Carga tu archivo en la barra lateral izquierda para ver tus datos reales. Mientras tanto, explora con estos datos de ejemplo:")
    datos_prueba = {
        'ID_Muestra': ['CEN-01', 'CEN-02', 'CEN-03', 'CEN-04'],
        'Latitud': [2.443, 2.450, 2.435, 2.460], 
        'Longitud': [-76.606, -76.610, -76.590, -76.620],
        'Cuarzo_%': [40, 20, 50, 80],
        'Feldespato_%': [30, 50, 20, 10],
        'Vidrio_%': [30, 30, 30, 10],
        'URL_Foto': [
            'https://upload.wikimedia.org/wikipedia/commons/thumb/1/1a/Volcanic_ash.jpg/320px-Volcanic_ash.jpg',
            'https://upload.wikimedia.org/wikipedia/commons/thumb/1/1a/Volcanic_ash.jpg/320px-Volcanic_ash.jpg',
            'https://upload.wikimedia.org/wikipedia/commons/thumb/1/1a/Volcanic_ash.jpg/320px-Volcanic_ash.jpg',
            'https://upload.wikimedia.org/wikipedia/commons/thumb/1/1a/Volcanic_ash.jpg/320px-Volcanic_ash.jpg'
        ]
    }
    df = pd.DataFrame(datos_prueba)

# 3. FILTROS EN LA BARRA LATERAL
st.sidebar.markdown("---")
st.sidebar.subheader("2. Filtra tus datos")
min_cuarzo = st.sidebar.slider("Mínimo de Cuarzo (%):", min_value=0, max_value=100, value=0)

# Aplicar el filtro a los datos
df_filtrado = df[df['Cuarzo_%'] >= min_cuarzo]

# 4. DIBUJAR LA PANTALLA
if df_filtrado.empty:
    st.warning("No hay muestras que cumplan con este filtro. Intenta bajar el porcentaje.")
else:
    col1, col2 = st.columns([2, 1])

    with col1:
        st.subheader(f"Mapa de Recolección ({len(df_filtrado)} muestras)")
        # Ahora los puntos cambian de color según el cuarzo
        fig_map = px.scatter_mapbox(
            df_filtrado, lat="Latitud", lon="Longitud", 
            hover_name="ID_Muestra", 
            color="Cuarzo_%",
            color_continuous_scale="YlOrRd", # Colores de Amarillo a Rojo
            zoom=11, height=550
        )
        fig_map.update_layout(mapbox_style="open-street-map", margin={"r":0,"t":0,"l":0,"b":0})
        st.plotly_chart(fig_map, use_container_width=True)

    with col2:
        st.subheader("Análisis Individual")
        muestra_seleccionada = st.selectbox("Selecciona una muestra:", df_filtrado['ID_Muestra'])
        
        datos_muestra = df_filtrado[df_filtrado['ID_Muestra'] == muestra_seleccionada].iloc[0]
        
        # Gráfica de mineralogía (ahora estilo dona)
        minerales = ['Cuarzo_%', 'Feldespato_%', 'Vidrio_%']
        valores = [datos_muestra['Cuarzo_%'], datos_muestra['Feldespato_%'], datos_muestra['Vidrio_%']]
        
        fig_pie = px.pie(names=minerales, values=valores, hole=0.4)
        fig_pie.update_layout(margin=dict(t=0, b=0, l=0, r=0))
        st.plotly_chart(fig_pie, use_container_width=True)
        
        # Foto de la muestra
        st.image(datos_muestra['URL_Foto'], caption=f"Fotografía de {muestra_seleccionada}")
