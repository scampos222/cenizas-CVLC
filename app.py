import streamlit as st
import pandas as pd
import plotly.express as px
import folium
from folium.plugins import MarkerCluster, HeatMap
from streamlit_folium import st_folium
import re
import json

# 1. CONFIGURACIÓN INSTITUCIONAL
st.set_page_config(page_title="AshViewer-CVLC", layout="wide")

st.markdown("""
    <style>
    .main {background-color: #FAFAFA;}
    h1, h2, h3 {color: #2C3E50;}
    </style>
    """, unsafe_allow_html=True)

st.title("AshViewer-CVLC | Plataforma de Análisis de Cenizas Volcánicas")

# 2. CARGA DE DATOS Y PANEL LATERAL
st.sidebar.title("Panel de Control")

with st.sidebar.expander("📂 Carga de Archivos", expanded=True):
    archivo_subido = st.file_uploader("Cargar Base de Datos (.xlsx / .csv)", type=["xlsx", "csv"])
    archivo_geojson = st.file_uploader("Cargar Capa Veredas (.geojson)", type=["geojson", "json"])
else:
    st.info("Carga tu base de datos para iniciar. Mostrando entorno de prueba.")
    datos_prueba = {
        'ID_Muestra': ['CAP-01', 'CAP-02', 'CAP-03'],
        'Vereda': ['Chapio', 'Quintana', 'Coconuco'],
        'Latitud': [2.443, 2.450, 2.341], 
        'Longitud': [-76.606, -76.610, -76.510],
        'Tamaño_Promedio_mm': [0.5, 0.8, 2.1],
        'Espesor_Deposito_mm': [10, 5, 2],
        'Fecha_Recoleccion': ['2026-08-01', '2026-08-05', '2026-08-10'],
        'LV1': [50, 20, 10], 'LVA1': [28, 15, 5], 'Plagioclasa': [69, 40, 10],
        'FV1': [20, 50, 80], 'Cuarzo': [2, 5, 0],
        'URLs_Fotos': ['https://raw.githubusercontent.com/usuario/repo/main/foto_plagioclasa.jpg, https://raw.githubusercontent.com/usuario/repo/main/foto_lv1.jpg', '', ''],
        'Enlace_Reporte': ['https://docs.google.com/', '', '']
    }
    df = pd.DataFrame(datos_prueba)

# --- PROCESAMIENTO ---
if 'Fecha_Recoleccion' in df.columns:
    df['Fecha_Recoleccion'] = pd.to_datetime(df['Fecha_Recoleccion'], errors='coerce')

cols_info = ['ID_Muestra', 'Vereda', 'Latitud', 'Longitud', 'Tamaño_Promedio_mm', 'Espesor_Deposito_mm', 'URLs_Fotos', 'URL_Microscopio', 'Fecha_Recoleccion', 'Enlace_Reporte']
cols_conteo = [col for col in df.columns if col not in cols_info and pd.api.types.is_numeric_dtype(df[col])]

df['Total_Granos'] = df[cols_conteo].sum(axis=1)
df_pct = df.copy()
for col in cols_conteo:
    df_pct[col] = (df[col] / df['Total_Granos']).fillna(0) * 100

# ==========================================
# 3. FILTROS AVANZADOS EN LA BARRA LATERAL
# ==========================================
st.sidebar.markdown("---")
st.sidebar.subheader("⚙️ Filtros Espaciales y Temporales")

# --- FILTRO 1: VEREDAS ---
if 'Vereda' in df.columns:
    veredas_unicas = sorted(df['Vereda'].dropna().unique().tolist())

    if "veredas_selected" not in st.session_state:
        st.session_state["veredas_selected"] = veredas_unicas

    def seleccionar_todas_veredas():
        st.session_state["veredas_selected"] = veredas_unicas

    def limpiar_todas_veredas():
        st.session_state["veredas_selected"] = []

    col_v1, col_v2 = st.sidebar.columns(2)
    with col_v1:
        st.button("Todas", on_click=seleccionar_todas_veredas, use_container_width=True)
    with col_v2:
        st.button("Limpiar", on_click=limpiar_todas_veredas, use_container_width=True)

    veredas_seleccionadas = st.sidebar.multiselect(
        "Localidad / Vereda:",
        options=veredas_unicas,
        key="veredas_selected"
    )
else:
    veredas_seleccionadas = []

# --- FILTRO 2: FECHA ---
if 'Fecha_Recoleccion' in df.columns and not df['Fecha_Recoleccion'].isnull().all():
    df['Anio'] = df['Fecha_Recoleccion'].dt.year
    df['Mes_Num'] = df['Fecha_Recoleccion'].dt.month

    dic_meses = {
        1: "Enero", 2: "Febrero", 3: "Marzo", 4: "Abril", 5: "Mayo", 6: "Junio",
        7: "Julio", 8: "Agosto", 9: "Septiembre", 10: "Octubre", 11: "Noviembre", 12: "Diciembre"
    }

    anios_disponibles = ["Todos los Años"] + sorted([int(a) for a in df['Anio'].dropna().unique()], reverse=True)
    anio_sel = st.sidebar.selectbox("Año de Recolección:", anios_disponibles)

    if anio_sel != "Todos los Años":
        df_anio = df[df['Anio'] == anio_sel]
        meses_nums = sorted(df_anio['Mes_Num'].dropna().unique())
        opciones_meses = ["Todos los Meses"] + [dic_meses[m] for m in meses_nums]
    else:
        opciones_meses = ["Todos los Meses"] + [dic_meses[m] for m in range(1, 13)]

    mes_sel = st.sidebar.selectbox("Mes de Recolección:", opciones_meses)

    mask_fecha = pd.Series(True, index=df.index)
    if anio_sel != "Todos los Años":
        mask_fecha = mask_fecha & (df['Anio'] == anio_sel)
    if mes_sel != "Todos los Meses":
        num_mes_elegido = [k for k, v in dic_meses.items() if v == mes_sel][0]
        mask_fecha = mask_fecha & (df['Mes_Num'] == num_mes_elegido)
else:
    mask_fecha = pd.Series(True, index=df.index)

# --- APLICACIÓN DE FILTROS ---
mask_vereda = df['Vereda'].isin(veredas_seleccionadas) if veredas_seleccionadas else pd.Series(True, index=df.index)

df_filtrado = df[mask_vereda & mask_fecha]
df_pct_filtrado = df_pct[mask_vereda & mask_fecha]
colores_profesionales = px.colors.qualitative.Pastel

def obtener_url_imagen(url_original):
    url_limpia = str(url_original).strip()
    if "drive.google.com" in url_limpia:
        match = re.search(r'[-\w]{25,}', url_limpia)
        if match:
            return f"https://drive.google.com/uc?id={match.group(0)}"
    return url_limpia

# 4. DASHBOARD PRINCIPAL
if df_filtrado.empty:
    st.warning("No se encontraron registros bajo los parámetros seleccionados.")
else:
    st.markdown("---")
    
    tab_mapa, tab_comp, tab_analisis, tab_reportes, tab_datos = st.tabs([
        "Mapa de Distribución", "Análisis de Muestra", "Análisis Avanzado", "Verificación de Campo", "Base de Datos"
    ])

    # --- PESTAÑA 1: MAPAS ESPACIALES ---
    with tab_mapa:
        st.subheader("Distribución Espacial de Muestras y Depósitos")
        
        tipo_mapa = st.radio(
            "Seleccione la vista espacial:",
            ["📍 Puntos de Recolección (Muestras individuales)", "🔥 Mapa de Calor (Espesor del depósito)"],
            horizontal=True
        )
        
        st.markdown("---")
        
        centro_lat = df_filtrado['Latitud'].mean()
        centro_lon = df_filtrado['Longitud'].mean()
        m = folium.Map(location=[centro_lat, centro_lon], zoom_start=11, tiles='CartoDB positron')
        
        # --- NUEVO: Integración de GeoJSON al mapa ---
        if archivo_geojson is not None:
            geo_data = json.load(archivo_geojson)
            folium.GeoJson(
                geo_data,
                name="Veredas",
                style_function=lambda feature: {
                    'fillColor': '#2980B9',
                    'color': '#2C3E50',
                    'weight': 1.5,
                    'fillOpacity': 0.15
                }
                # tooltip=folium.GeoJsonTooltip(fields=['NOMBRE'], aliases=['Vereda:']) <- ESTO ERA LO QUE ROMPÍA LA APP
            ).add_to(m)

        if "Puntos" in tipo_mapa:
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
            st.info("El mapa de calor muestra la concentración basada en la variable 'Espesor_Deposito_mm'.")
            if 'Espesor_Deposito_mm' in df_filtrado.columns:
                heat_data = df_filtrado.dropna(subset=['Latitud', 'Longitud', 'Espesor_Deposito_mm'])
                heat_points = [[row['Latitud'], row['Longitud'], float(row['Espesor_Deposito_mm']) * 2] for index, row in heat_data.iterrows()]
                HeatMap(
                    heat_points, 
                    radius=25, blur=15, 
                    gradient={0.2: 'blue', 0.5: 'yellow', 1.0: 'red'}
                ).add_to(m)
            else:
                st.warning("Falta la columna 'Espesor_Deposito_mm' en tu base de datos.")
                
        st_folium(m, width="100%", height=550)

    # --- PESTAÑA 2: COMPOSICIÓN Y CARRUSEL ---
    with tab_comp:
        st.subheader("Caracterización Mineralógica Individual")
        muestra_sel = st.selectbox("Seleccione ID de Muestra:", df_filtrado["ID_Muestra"])

        datos_muestra_pct = df_pct_filtrado[df_pct_filtrado["ID_Muestra"] == muestra_sel][cols_conteo].iloc[0]
        datos_grafica = datos_muestra_pct[datos_muestra_pct > 0].reset_index()
        datos_grafica.columns = ["Componente", "Porcentaje"]

        col_graf, col_foto = st.columns([1.8, 1])
        
        mineral_cliqueado = None

        with col_graf:
            fig_pie = px.pie(
                datos_grafica,
                names="Componente",
                values="Porcentaje",
                hole=0.35,
                color_discrete_sequence=colores_profesionales,
            )
            fig_pie.update_traces(textposition="inside", textinfo="percent+label")
            fig_pie.update_layout(margin=dict(t=20, b=20, l=10, r=10), height=450, clickmode='event+select')
            
            # --- NUEVO: Captura de clic en la torta ---
            eventos_grafica = st.plotly_chart(fig_pie, use_container_width=True, on_select="rerun", key=f"pie_{muestra_sel}")
            
            if eventos_grafica and "selection" in eventos_grafica and eventos_grafica["selection"]["points"]:
                # Extrae la etiqueta del pedazo cliqueado
                mineral_cliqueado = eventos_grafica["selection"]["points"][0]["label"]

        with col_foto:
            datos_m_crudos = df_filtrado[df_filtrado["ID_Muestra"] == muestra_sel].iloc[0]

            if "URLs_Fotos" in datos_m_crudos and pd.notna(datos_m_crudos["URLs_Fotos"]):
                urls_crudas = str(datos_m_crudos["URLs_Fotos"]).split(",")
                urls_limpias = [u.strip() for u in urls_crudas if u.strip() and u.strip().lower() != "nan"]

                if urls_limpias:
                    st.write("📷 **Registro Fotográfico:**")
                    clave_estado = f"foto_idx_{muestra_sel}"
                    
                    if clave_estado not in st.session_state:
                        st.session_state[clave_estado] = 0

                    # --- NUEVO: Sincronización clic -> foto ---
                    if mineral_cliqueado:
                        st.success(f"Buscando foto para: **{mineral_cliqueado}**")
                        # Busca si el nombre del mineral está en el link (ignorando mayúsculas)
                        for idx, link in enumerate(urls_limpias):
                            if mineral_cliqueado.lower() in link.lower():
                                st.session_state[clave_estado] = idx
                                break

                    col_btn1, col_texto, col_btn2 = st.columns([1, 2, 1])

                    with col_btn1:
                        if st.button("⬅️ Anterior", key=f"prev_{muestra_sel}"):
                            st.session_state[clave_estado] = (st.session_state[clave_estado] - 1) % len(urls_limpias)

                    with col_texto:
                        st.markdown(
                            f"<div style='text-align: center; margin-top: 8px;'>Foto {st.session_state[clave_estado] + 1} de {len(urls_limpias)}</div>",
                            unsafe_allow_html=True,
                        )

                    with col_btn2:
                        if st.button("Siguiente ➡️", key=f"next_{muestra_sel}"):
                            st.session_state[clave_estado] = (st.session_state[clave_estado] + 1) % len(urls_limpias)

                    url_actual = urls_limpias[st.session_state[clave_estado]]
                    url_final = obtener_url_imagen(url_actual)

                    st.image(url_final, caption=f"Muestra {muestra_sel}", use_container_width=True)
                else:
                    st.info("No se encontraron enlaces válidos.")
            else:
                st.info("Sin registro fotográfico asociado.")

   # --- PESTAÑA 3: ANÁLISIS AVANZADO ---
    with tab_analisis:
        st.subheader("⚖️ Comparativa de Distribución Mineralógica")
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

        # --- NUEVO: DIAGRAMA TERNARIO ---
        st.subheader("🔺 Diagrama Ternario de Clasificación")
        st.markdown("---")

        # --- NUEVO: DIAGRAMA TERNARIO ESTANDARIZADO (V-L-C) ---
        st.subheader("🔺 Clasificación Petrológica de Cenizas (V-L-C)")
        st.write("Agrupación estándar en Vidrio (Vitric), Líticos (Lithic) y Cristales (Crystal).")
        
        # Agrupación inteligente de componentes
        cols_vidrio = [c for c in cols_conteo if 'FV' in c.upper() or 'VIDRIO' in c.upper()]
        cols_liticos = [c for c in cols_conteo if 'LV' in c.upper() or 'LÍTICO' in c.upper() or 'LITICO' in c.upper()]
        # Todo lo que no cumpla las reglas anteriores, se clasifica como cristal
        cols_cristales = [c for c in cols_conteo if c not in cols_vidrio + cols_liticos]

        df_ternary = df_filtrado.copy()
        df_ternary['Vidrio'] = df_ternary[cols_vidrio].sum(axis=1) if cols_vidrio else 0
        df_ternary['Líticos'] = df_ternary[cols_liticos].sum(axis=1) if cols_liticos else 0
        df_ternary['Cristales'] = df_ternary[cols_cristales].sum(axis=1) if cols_cristales else 0
        
        df_ternary['Suma_VLC'] = df_ternary['Vidrio'] + df_ternary['Líticos'] + df_ternary['Cristales']
        df_ternary_plot = df_ternary[df_ternary['Suma_VLC'] > 0].copy()
        
        if not df_ternary_plot.empty:
            df_ternary_plot['Vidrio (%)'] = df_ternary_plot['Vidrio'] / df_ternary_plot['Suma_VLC'] * 100
            df_ternary_plot['Líticos (%)'] = df_ternary_plot['Líticos'] / df_ternary_plot['Suma_VLC'] * 100
            df_ternary_plot['Cristales (%)'] = df_ternary_plot['Cristales'] / df_ternary_plot['Suma_VLC'] * 100
            
            fig_ternary = px.scatter_ternary(
                df_ternary_plot, a='Vidrio (%)', b='Líticos (%)', c='Cristales (%)', 
                color="Vereda", hover_name="ID_Muestra", size="Tamaño_Promedio_mm",
                color_discrete_sequence=colores_profesionales,
            )
            
            # Mejorar la visualización del triángulo
            fig_ternary.update_layout(
                ternary=dict(
                    sum=100,
                    aaxis=dict(title='Vidrio (Vitric) %', min=0, linewidth=2, ticks='outside'),
                    baxis=dict(title='Líticos (Lithic) %', min=0, linewidth=2, ticks='outside'),
                    caxis=dict(title='Cristales (Crystal) %', min=0, linewidth=2, ticks='outside')
                ),
                margin=dict(t=40, b=40, l=40, r=40)
            )
            st.plotly_chart(fig_ternary, use_container_width=True)
            
            # Acordeón para transparencia científica
            with st.expander("🔍 Ver detalle de la agrupación"):
                st.write(f"**Vidrio:** {', '.join(cols_vidrio) if cols_vidrio else 'Ninguno detectado'}")
                st.write(f"**Líticos:** {', '.join(cols_liticos) if cols_liticos else 'Ninguno detectado'}")
                st.write(f"**Cristales:** {', '.join(cols_cristales) if cols_cristales else 'Ninguno detectado'}")
        else:
            st.info("No hay datos suficientes para clasificar las muestras en el diagrama V-L-C.")

        st.markdown("---")
        # --- NUEVO: LÍNEA DE TIEMPO DEL TAMAÑO DE GRANO ---
        st.subheader("📈 Evolución Temporal del Tamaño de Grano")
        if 'Fecha_Recoleccion' in df_filtrado.columns and 'Tamaño_Promedio_mm' in df_filtrado.columns:
            # Limpiar datos sin fecha o tamaño y ordenarlos cronológicamente
            df_tiempo = df_filtrado.dropna(subset=['Fecha_Recoleccion', 'Tamaño_Promedio_mm']).sort_values(by='Fecha_Recoleccion')
            
            if not df_tiempo.empty:
                fig_tiempo = px.line(
                    df_tiempo, x="Fecha_Recoleccion", y="Tamaño_Promedio_mm", 
                    color="Vereda", markers=True, hover_name="ID_Muestra",
                    labels={"Fecha_Recoleccion": "Fecha de Recolección", "Tamaño_Promedio_mm": "Tamaño de Grano (mm)"},
                    color_discrete_sequence=colores_profesionales
                )
                fig_tiempo.update_traces(line=dict(width=3), marker=dict(size=8))
                st.plotly_chart(fig_tiempo, use_container_width=True)
            else:
                st.info("No hay datos temporales válidos para trazar la gráfica.")
        else:
            st.warning("Faltan las columnas de Fecha o Tamaño para la gráfica temporal.")

        st.markdown("---")
        
        # --- ORIGINAL: TENDENCIA TAMAÑO VS MINERALOGÍA ---
        st.subheader("🔬 Relación: Tamaño de Grano vs. Mineralogía")
        if 'Tamaño_Promedio_mm' in df_filtrado.columns:
            mineral_tendencia = st.selectbox("Seleccione componente a analizar:", cols_conteo, key="tendencia_mineral")
            
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
