import streamlit as st
import pandas as pd
import plotly.express as px

# 1. CONFIGURACIÓN DE LA PÁGINA
st.set_page_config(page_title="Geovisor de Cenizas", layout="wide")
st.title("🌋 Geovisor de Muestras de Ceniza")

# 2. DATOS DE PRUEBA (Luego los cambiaremos por tu Excel)
datos_prueba = {
    'ID_Muestra': ['CEN-01', 'CEN-02', 'CEN-03'],
    'Latitud': [2.443, 2.450, 2.435], 
    'Longitud': [-76.606, -76.610, -76.590],
    'Cuarzo_%': [40, 20, 50],
    'Feldespato_%': [30, 50, 20],
    'Vidrio_%': [30, 30, 30],
    'URL_Foto': [
        'https://upload.wikimedia.org/wikipedia/commons/thumb/1/1a/Volcanic_ash.jpg/320px-Volcanic_ash.jpg',
        'https://upload.wikimedia.org/wikipedia/commons/thumb/1/1a/Volcanic_ash.jpg/320px-Volcanic_ash.jpg',
        'https://upload.wikimedia.org/wikipedia/commons/thumb/1/1a/Volcanic_ash.jpg/320px-Volcanic_ash.jpg'
    ]
}
df = pd.DataFrame(datos_prueba)

# 3. DISEÑO DE LA PANTALLA (2 Columnas)
col1, col2 = st.columns([2, 1]) # La columna 1 es más ancha para el mapa

with col1:
    st.subheader("Mapa de Recolección")
    # Crear el mapa con los puntos
    fig_map = px.scatter_mapbox(
        df, lat="Latitud", lon="Longitud", 
        hover_name="ID_Muestra", 
        zoom=12, height=500
    )
    # Usar un estilo de mapa gratuito
    fig_map.update_layout(mapbox_style="open-street-map", margin={"r":0,"t":0,"l":0,"b":0})
    st.plotly_chart(fig_map, use_container_width=True)

with col2:
    st.subheader("Detalles de la Muestra")
    # Selector de muestra
    muestra_seleccionada = st.selectbox("Elige una muestra para analizar:", df['ID_Muestra'])
    
    # Filtrar los datos solo para la muestra elegida
    datos_muestra = df[df['ID_Muestra'] == muestra_seleccionada].iloc[0]
    
    # Preparar datos para la gráfica de pastel
    minerales = ['Cuarzo_%', 'Feldespato_%', 'Vidrio_%']
    valores = [datos_muestra['Cuarzo_%'], datos_muestra['Feldespato_%'], datos_muestra['Vidrio_%']]
    
    # Crear gráfica de pastel
    fig_pie = px.pie(names=minerales, values=valores, title=f"Mineralogía - {muestra_seleccionada}")
    st.plotly_chart(fig_pie, use_container_width=True)
    
    # Mostrar la foto
    st.image(datos_muestra['URL_Foto'], caption=f"Foto de {muestra_seleccionada}")
