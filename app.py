import streamlit as st
import pandas as pd
import plotly.express as px
import folium
from folium.plugins import MarkerCluster, HeatMap
from streamlit_folium import st_folium
import re

# 1. CONFIGURACIÓN INSTITUCIONAL
st.set_page_config(page_title="AshViewer-CVLC", layout="wide")

# Forzar un estilo limpio usando CSS inyectado
st.markdown("""
    <style>
    .main {background-color: #FAFAFA;}
    h1, h2, h3 {color: #2C3E50;}
    </style>
    """, unsafe_allow_html=True)

st.title("AshViewer-CVLC | Plataforma de Análisis de Cenizas Volcánicas")

# 2. CARGA DE DATOS Y PANEL LATERAL
st.sidebar.title("Panel de Control")
archivo_subido = st.sidebar.file_uploader("Cargar Base de Datos (.xlsx / .csv)", type=["xlsx", "csv"])

if archivo_subido is not None:
    if archivo_subido.name.endswith('.csv'):
        df = pd.read_csv(archivo_subido)
    else:
        df = pd.read_excel(archivo_subido)
else:
    st.info("Carga tu base de datos para iniciar. Mostrando entorno de prueba.")
    datos_prueba = {
        'ID_Muestra': ['CAP-01', 'CAP-02', 'CAP-03'],
        'Vereda': ['Chapio', 'Quintana', 'Coconuco'],
        'Latitud': [2.443, 2.450, 2.341], 
        'Longitud': [-76.606, -76.610, -76.510],
        'Tamaño_Promedio_mm': [0.5, 0.8, 2.1],
        'Espesor_Deposito_mm': [10, 5, 2], # Nueva variable para el futuro mapa
        'Fecha_Recoleccion': ['2026-08-01', '2026-08-05', '2026-08-10'],
        'LV1': [50, 20, 10], 'LVA1': [28, 15, 5], 'Plagioclasa': [69, 40, 10],
        'FV1': [20, 50, 80], 'Cuarzo': [2, 5, 0],
        'URLs_Fotos': ['https://drive.google.com/uc?id=1cmIiAIVyRSGl5lmngEA24AY7bL6ZhxX3, https://drive.google.com/uc?id=1uvB0MrDh8n2buLHX-vB4nHe5h12FT86z', '', ''],
        'Enlace_Reporte': ['https://docs.google.com/', '', '']
    }
    df = pd.DataFrame(datos_prueba)

# --- PROCESAMIENTO ---
# Asegurar formato de fecha si existe
if 'Fecha_Recoleccion' in df.columns:
    df['Fecha_Recoleccion'] = pd.to_datetime(df['Fecha_Recoleccion'], errors='coerce')

cols_info = ['ID_Muestra', 'Vereda', 'Latitud', 'Longitud', 'Tamaño_Promedio_mm', 'Espesor_Deposito_mm', 'URLs_Fotos', 'URL_Microscopio', 'Fecha_Recoleccion', 'Enlace_Reporte']
cols_conteo = [col for col in df.columns if col not in cols_info and pd.api.types.is_numeric_dtype(df[col])]

df['Total_Granos'] = df[cols_conteo].sum(axis=1)
df_pct = df.copy()
for col in cols_conteo:
    df_pct[col] = (df[col] / df['Total_Granos']).fillna(0) * 100

# 3. FILTROS AVANZADOS
st.sidebar.markdown("---")
st.sidebar.subheader("Filtros Espaciales y Temporales")

# Filtro Vereda
if 'Vereda' in df.columns:
    veredas_unicas = df['Vereda'].dropna().unique().tolist()
    veredas_seleccionadas = st.sidebar.multiselect("Localidad / Vereda:", veredas_unicas, default=veredas_unicas)
else:
    veredas_seleccionadas = []

# Filtro Fecha
if 'Fecha_Recoleccion' in df.columns and not df['Fecha_Recoleccion'].isnull().all():
    min_date = df['Fecha_Recoleccion'].min().date()
    max_date = df['Fecha_Recoleccion'].max().date()
    fechas = st.sidebar.date_input("Rango de recolección:", [min_date, max_date], min_value=min_date, max_value=max_date)
    
    if len(fechas) == 2:
        mask_fecha = (df['Fecha_Recoleccion'].dt.date >= fechas[0]) & (df['Fecha_Recoleccion'].dt.date <= fechas[1])
    else:
        mask_fecha = pd.Series(True, index=df.index)
else:
    mask_fecha = pd.Series(True, index=df.index)

# Aplicar filtros
mask_vereda = df['Vereda'].isin(veredas_seleccionadas) if veredas_seleccionadas else pd.Series(True, index=df.index)
df_filtrado = df[mask_vereda & mask_fecha]
df_pct_filtrado = df_pct[mask_vereda & mask_fecha]

# Paleta de colores profesional
colores_profesionales = px.colors.qualitative.Pastel

# Función para limpiar links de Google Drive
# Función mejorada y a prueba de errores para links de Drive
def obtener_url_imagen(url_original):
    # Limpiamos espacios y caracteres invisibles que se cuelan del Excel
    url_limpia = str(url_original).strip()
    
    if "drive.google.com" in url_limpia:
        # Busca el ID de 33 caracteres de Google Drive sin importar cómo esté formateado el link
        match = re.search(r'[-\w]{25,}', url_limpia)
        if match:
            # Usamos el formato oficial de descarga directa de Google
            return f"https://drive.google.com/uc?export=view&id={match.group(0)}"
    return url_limpia

# 4. DASHBOARD PRINCIPAL
if df_filtrado.empty:
    st.warning("No se encontraron registros bajo los parámetros seleccionados.")
else:
    st.markdown("---")
    
    # 5 Pestañas institucionales
    tab_mapa, tab_comp, tab_analisis, tab_reportes, tab_datos = st.tabs([
        "Mapa de Distribución", "Análisis de Muestra", "Análisis Avanzado", "Verificación de Campo", "Base de Datos"
    ])

    # --- PESTAÑA 1: MAPAS ESPACIALES ---
    with tab_mapa:
        # Usamos columnas para poner botones o selectores encima del mapa
        st.subheader("Distribución Espacial de Muestras y Depósitos")
        
        # Un selector para que el usuario decida qué tipo de mapa quiere ver
        tipo_mapa = st.radio(
            "Seleccione la vista espacial:",
            ["📍 Puntos de Recolección (Muestras individuales)", "🔥 Mapa de Calor (Espesor del depósito)"],
            horizontal=True
        )
        
        st.markdown("---")
        
        centro_lat = df_filtrado['Latitud'].mean()
        centro_lon = df_filtrado['Longitud'].mean()
        m = folium.Map(location=[centro_lat, centro_lon], zoom_start=11, tiles='CartoDB positron')
        
        if "Puntos" in tipo_mapa:
            # Dibuja el mapa normal con los puntos
            marker_cluster = MarkerCluster().add_to(m)
            
            for idx, row in df_filtrado.iterrows():
                html_popup = f"""
                <div style='width:200px; font-family:sans-serif;'>
                <b>ID: {row.get('ID_Muestra', 'N/A')}</b><br>
                <b>Vereda:</b> {row.get('Vereda', 'N/A')}<br>
                <b>Fecha:</b> {row['Fecha_Recoleccion'].strftime('%Y-%m-%d') if 'Fecha_Recoleccion' in df_filtrado.columns and pd.notna(row.get('Fecha_Recoleccion')) else 'N/A'}<br>
                <b>Espesor:</b> {row.get('Espesor_Deposito_mm', 'N/A')} mm
                </div>
                """
                folium.Marker(
                    location=[row['Latitud'], row['Longitud']],
                    popup=folium.Popup(html_popup, max_width=300),
                    tooltip=str(row.get('ID_Muestra', 'Muestra')),
                    icon=folium.Icon(color="darkblue", icon="info-sign")
                ).add_to(marker_cluster)
                
        else:
            # Dibuja el Mapa de Calor (Heatmap)
            st.info("El mapa de calor muestra la concentración basada en la variable 'Espesor_Deposito_mm'. Zonas rojas indican mayor acumulación de ceniza.")
            
            if 'Espesor_Deposito_mm' in df_filtrado.columns:
                # Filtrar datos que sí tienen valores válidos de lat/lon y espesor
                heat_data = df_filtrado.dropna(subset=['Latitud', 'Longitud', 'Espesor_Deposito_mm'])
                
                # Crear la lista de datos que necesita folium: [Latitud, Longitud, Peso]
                # Multiplicamos el peso para que el mapa resalte visualmente los cambios
                heat_points = [[row['Latitud'], row['Longitud'], float(row['Espesor_Deposito_mm']) * 2] for index, row in heat_data.iterrows()]
                
                HeatMap(
                    heat_points, 
                    radius=25, # Qué tan grande es la mancha de calor
                    blur=15,   # Qué tan difuminados están los bordes
                    gradient={0.2: 'blue', 0.5: 'yellow', 1.0: 'red'} # Colores (Azul = poco, Rojo = mucho)
                ).add_to(m)
            else:
                st.warning("No se puede generar el mapa de calor porque falta la columna 'Espesor_Deposito_mm' en tu base de datos.")
                
        st_folium(m, width="100%", height=550)

    # --- PESTAÑA 2: COMPOSICIÓN (MÚLTIPLES FOTOS) ---
    with tab_comp:
        st.subheader("Caracterización Mineralógica Individual")
        muestra_sel = st.selectbox("Seleccione ID de Muestra:", df_filtrado['ID_Muestra'])
        
        datos_muestra_pct = df_pct_filtrado[df_pct_filtrado['ID_Muestra'] == muestra_sel][cols_conteo].iloc[0]
        datos_grafica = datos_muestra_pct[datos_muestra_pct > 0].reset_index()
        datos_grafica.columns = ['Componente', 'Porcentaje']
        
        col_graf, col_foto = st.columns([1, 1.2]) # Hacemos la columna de fotos un poco más ancha
        with col_graf:
            fig_pie = px.pie(
                datos_grafica, names='Componente', values='Porcentaje', hole=0.3,
                color_discrete_sequence=colores_profesionales
            )
            fig_pie.update_traces(textposition='inside', textinfo='percent+label')
            fig_pie.update_layout(margin=dict(t=20, b=20, l=20, r=20))
            st.plotly_chart(fig_pie, use_container_width=True)
            
         with col_foto:
            datos_m_crudos = df_filtrado[df_filtrado['ID_Muestra'] == muestra_sel].iloc[0]
            
            # --- GALERÍA CARRUSEL ---
            if 'URLs_Fotos' in datos_m_crudos and pd.notna(datos_m_crudos['URLs_Fotos']):
                urls_crudas = str(datos_m_crudos['URLs_Fotos']).split(',')
                urls_limpias = [u.strip() for u in urls_crudas if u.strip() and u.strip() != 'nan']
                
                if urls_limpias:
                    st.write("📷 **Registro Fotográfico de la Muestra:**")
                    
                    # Manejo de estado para recordar qué foto estamos viendo
                    clave_estado = f"foto_idx_{muestra_sel}"
                    if clave_estado not in st.session_state:
                        st.session_state[clave_estado] = 0
                        
                    # Controles del carrusel (Botones Anterior / Siguiente)
                    col_btn1, col_texto, col_btn2 = st.columns([1, 2, 1])
                    
                    with col_btn1:
                        if st.button("⬅️ Anterior", key=f"prev_{muestra_sel}"):
                            st.session_state[clave_estado] = (st.session_state[clave_estado] - 1) % len(urls_limpias)
                    
                    with col_texto:
                        st.markdown(f"<div style='text-align: center; margin-top: 8px;'>Foto {st.session_state[clave_estado] + 1} de {len(urls_limpias)}</div>", unsafe_allow_html=True)
                        
                    with col_btn2:
                        if st.button("Siguiente ➡️", key=f"next_{muestra_sel}"):
                            st.session_state[clave_estado] = (st.session_state[clave_estado] + 1) % len(urls_limpias)
                    
                    # Mostrar la foto actual seleccionada grande y hermosa
                    url_actual = urls_limpias[st.session_state[clave_estado]]
                    url_final = obtener_url_imagen(url_actual)
                    
                    st.image(url_final, use_container_width=True)
                    
                else:
                    st.info("No se encontraron enlaces válidos de fotografías.")
            else:
                st.info("Esta muestra no tiene registro fotográfico asociado en la base de datos.")

    # --- PESTAÑA 3: ANÁLISIS AVANZADO ---
    with tab_analisis:
        st.subheader("Comparativa de Distribución Mineralógica")
        comp_col1, comp_col2 = st.columns(2)
        
        with comp_col1:
            muestra_1 = st.selectbox("Muestra A:", df_filtrado['ID_Muestra'], key="comp1")
            datos_m1_pct = df_pct_filtrado[df_pct_filtrado['ID_Muestra'] == muestra_1][cols_conteo].iloc[0]
            datos_grafica_1 = datos_m1_pct[datos_m1_pct > 0].reset_index()
            datos_grafica_1.columns = ['Componente', 'Porcentaje']
            
        with comp_col2:
            idx_default = 1 if len(df_filtrado) > 1 else 0
            muestra_2 = st.selectbox("Muestra B:", df_filtrado['ID_Muestra'], index=idx_default, key="comp2")
            datos_m2_pct = df_pct_filtrado[df_pct_filtrado['ID_Muestra'] == muestra_2][cols_conteo].iloc[0]
            datos_grafica_2 = datos_m2_pct[datos_m2_pct > 0].reset_index()
            datos_grafica_2.columns = ['Componente', 'Porcentaje']

        datos_grafica_1['Muestra'] = muestra_1
        datos_grafica_2['Muestra'] = muestra_2
        df_comparativo = pd.concat([datos_grafica_1, datos_grafica_2])
        
        fig_barras = px.bar(
            df_comparativo, x="Muestra", y="Porcentaje", color="Componente", 
            text="Porcentaje", color_discrete_sequence=colores_profesionales
        )
        fig_barras.update_traces(texttemplate='%{text:.1f}%', textposition='inside')
        st.plotly_chart(fig_barras, use_container_width=True)

        st.markdown("---")
        
        st.subheader("Tendencia: Tamaño de Grano vs. Mineralogía")
        if 'Tamaño_Promedio_mm' in df_filtrado.columns:
            mineral_tendencia = st.selectbox("Seleccione componente a analizar:", cols_conteo)
            
            df_tendencia = df_filtrado[['ID_Muestra', 'Vereda', 'Tamaño_Promedio_mm']].copy()
            df_tendencia['Porcentaje'] = df_pct_filtrado[mineral_tendencia]
            
            fig_scatter = px.scatter(
                df_tendencia, x="Tamaño_Promedio_mm", y="Porcentaje", 
                color="Vereda", hover_name="ID_Muestra", size="Tamaño_Promedio_mm", 
                trendline="ols", color_discrete_sequence=colores_profesionales,
                labels={"Tamaño_Promedio_mm": "Tamaño de Grano (mm)", "Porcentaje": f"% de {mineral_tendencia}"}
            )
            st.plotly_chart(fig_scatter, use_container_width=True)
        else:
            st.warning("No se encontró la columna 'Tamaño_Promedio_mm' en la base de datos.")
    # --- PESTAÑA 4: REPORTES DE CAMPO ---
    with tab_reportes:
        st.subheader("Verificación Operativa")
        st.write("Consulte los reportes de campo asociados a las muestras consolidadas.")
        
        # Tabla simplificada para verificación
        if 'Enlace_Reporte' in df_filtrado.columns:
            df_reportes = df_filtrado[['ID_Muestra', 'Vereda', 'Fecha_Recoleccion', 'Enlace_Reporte']].copy()
            st.dataframe(
                df_reportes,
                column_config={
                    "Enlace_Reporte": st.column_config.LinkColumn("Documento de Campo")
                },
                hide_index=True,
                use_container_width=True
            )
        else:
            st.warning("Agregue la columna 'Enlace_Reporte' a su base de datos.")

    # --- PESTAÑA 5: BASE DE DATOS ---
    with tab_datos:
        st.subheader("Consolidado de Datos")
        st.dataframe(df_filtrado, use_container_width=True)
