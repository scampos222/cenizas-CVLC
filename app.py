def renderizar_modulo_comparativo(df_fil, df_pct_fil, cols_macro, cols_conteo, c_cristales, orden_cat_detallado):
    try:
        st.subheader("Análisis Comparativo Multi-Muestra")
        col_f1, col_f2 = st.columns(2)
        with col_f1:
            locs_disponibles = sorted(df_fil['Localizacion'].dropna().astype(str).unique().tolist())
            filtro_v = st.multiselect("Filtrar opciones por Localización:", locs_disponibles, default=[])
        with col_f2:
            if 'Fecha_Recoleccion' in df_fil.columns and not df_fil['Fecha_Recoleccion'].dropna().empty:
                fechas_disponibles = sorted(df_fil['Fecha_Recoleccion'].dt.strftime('%Y-%m-%d').dropna().unique().tolist(), reverse=True)
                filtro_f = st.multiselect("Filtrar opciones por Fecha:", fechas_disponibles, default=[])
            else:
                filtro_f = []

        df_opciones = df_fil.copy()
        if filtro_v:
            df_opciones = df_opciones[df_opciones['Localizacion'].isin(filtro_v)]
        if filtro_f and 'Fecha_Recoleccion' in df_opciones.columns:
            df_opciones = df_opciones[df_opciones['Fecha_Recoleccion'].dt.strftime('%Y-%m-%d').isin(filtro_f)]

        muestras_disponibles = df_opciones['ID_Muestra'].tolist()
        muestras_seleccionadas = st.multiselect(
            "Seleccione las muestras a comparar:",
            muestras_disponibles,
            default=muestras_disponibles[:6] if len(muestras_disponibles) >= 6 else muestras_disponibles
        )

        if not muestras_seleccionadas:
            return st.info("Seleccione al menos una muestra para iniciar la comparativa.")

        st.markdown("---")
        nivel_detalle = st.radio(
            "Nivel de Análisis:",
            [
                "Resumen Componentes Contados (Macro)",
                "% Cristal (Total Cristales)",
                "Porcentaje de Componentes (Detallado)"
            ],
            horizontal=True
        )

        # Ordenar las muestras seleccionadas cronológicamente por Fecha_Recoleccion
        df_orden = df_fil[df_fil['ID_Muestra'].isin(muestras_seleccionadas)].copy()
        df_orden = df_orden.sort_values(by=['Fecha_Recoleccion', 'ID_Muestra'], na_position='last')
        muestras_ordenadas = df_orden['ID_Muestra'].tolist()
        fechas_etiquetas = [
            pd.to_datetime(f).strftime('%Y-%m-%d') if pd.notna(f) else "Sin fecha"
            for f in df_orden['Fecha_Recoleccion']
        ]
        mapa_fechas = dict(zip(muestras_ordenadas, fechas_etiquetas))

        df_comp_pct = df_pct_fil[df_pct_fil['ID_Muestra'].isin(muestras_ordenadas)].copy()
        df_comp_pct['Fecha_Str'] = df_comp_pct['ID_Muestra'].map(mapa_fechas)

        df_cris = df_fil[df_fil['ID_Muestra'].isin(muestras_ordenadas)][['ID_Muestra'] + c_cristales].copy()
        if c_cristales:
            df_cris[c_cristales] = df_cris[c_cristales].div(df_cris[c_cristales].sum(axis=1).replace(0, 1), axis=0) * 100
        df_cris['Fecha_Str'] = df_cris['ID_Muestra'].map(mapa_fechas)

        tab_barras, tab_tortas = st.tabs(["Barras
