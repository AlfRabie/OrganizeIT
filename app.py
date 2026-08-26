import os
import json
import io
import pandas as pd
import streamlit as st
import gspread
from datetime import datetime, date, timedelta, time
from google.oauth2.service_account import Credentials

# Configuración de página
st.set_page_config(page_title="Dashboard Personal - Alfonso José", page_icon="⚡", layout="wide")

# CSS personalizado optimizado para móvil y desktop
st.markdown("""
    <style>
    .block-container {
        padding-top: 1.5rem !important;
        padding-bottom: 2rem !important;
    }
    h1 {
        font-size: 1.8rem !important;
        margin-bottom: 0.5rem !important;
    }
    div[data-testid="stMetricValue"] {
        font-size: 1.3rem !important;
    }
    .custom-kpi-card {
        background-color: transparent;
        padding: 0;
        margin-top: 0;
    }
    .custom-kpi-label {
        font-size: 0.85rem;
        color: rgba(250, 250, 250, 0.6);
        margin-bottom: 0.3rem;
    }
    .custom-kpi-value {
        font-size: 1.05rem;
        font-weight: 600;
        line-height: 1.4;
    }
    .class-status-banner {
        padding: 12px 16px;
        border-radius: 10px;
        margin-bottom: 15px;
        display: flex;
        align-items: center;
        justify-content: space-between;
        font-size: 0.95rem;
    }
    </style>
""", unsafe_allow_html=True)

scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]

@st.cache_resource
def conectar_sheets():
    cred_info = None
    try:
        if "GOOGLE_CREDENTIALS_JSON" in st.secrets:
            cred_data = st.secrets["GOOGLE_CREDENTIALS_JSON"]
            cred_info = json.loads(cred_data) if isinstance(cred_data, str) else dict(cred_data)
    except Exception:
        pass

    if cred_info is None and "GOOGLE_CREDENTIALS_JSON" in os.environ:
        cred_info = json.loads(os.environ["GOOGLE_CREDENTIALS_JSON"])

    if cred_info:
        creds = Credentials.from_service_account_info(cred_info, scopes=scopes)
    elif os.path.exists("credenciales.json"):
        creds = Credentials.from_service_account_file("credenciales.json", scopes=scopes)
    else:
        st.error("❌ No se encontraron credenciales válidas.")
        st.stop()

    client = gspread.authorize(creds)
    return client.open("Dashboard Alfonso Jose")

# Conexión
sh = conectar_sheets()
sheet_actividades = sh.worksheet("Actividades")
sheet_horario = sh.worksheet("Horario")

# Cargar Datos
def cargar_datos():
    df_act = pd.DataFrame(sheet_actividades.get_all_records())
    df_hor = pd.DataFrame(sheet_horario.get_all_records())
    return df_act, df_hor

df_actividades, df_horario = cargar_datos()

# Generador de archivo .ics para Apple Calendar y Google Calendar
def generar_ics(df_act, df_hor):
    ics_lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//Dashboard Alfonso Jose//ES",
        "CALSCALE:GREGORIAN"
    ]
    
    # Exportar Actividades / Certámenes
    if not df_act.empty:
        for _, row in df_act.iterrows():
            fecha_str = str(row.get('fecha', '')).strip()
            if fecha_str:
                try:
                    f_dt = datetime.strptime(fecha_str, "%Y-%m-%d").date()
                    f_clean = f_dt.strftime("%Y%m%d")
                    titulo = str(row.get('titulo', 'Actividad')).replace("\n", " ")
                    ramo = str(row.get('ramo', 'General')).replace("\n", " ")
                    tipo = str(row.get('tipo', 'tarea')).upper()
                    
                    ics_lines.extend([
                        "BEGIN:VEVENT",
                        f"SUMMARY:[{ramo}] {titulo} ({tipo})",
                        f"DTSTART;VALUE=DATE:{f_clean}",
                        f"DTEND;VALUE=DATE:{f_clean}",
                        f"DESCRIPTION:Prioridad: {row.get('prioridad', 'media')}",
                        "STATUS:CONFIRMED",
                        "END:VEVENT"
                    ])
                except Exception:
                    pass

    ics_lines.append("END:VCALENDAR")
    return "\r\n".join(ics_lines)

# Header y Controles Superiores
col_title, col_cal, col_sync = st.columns([0.5, 0.3, 0.2])
with col_title:
    st.markdown("# ⚡ Dashboard Alfonso José")

with col_cal:
    ics_data = generar_ics(df_actividades, df_horario)
    st.download_button(
        label="📥 Exportar Calendario (.ics)",
        data=ics_data,
        file_name="calendario_alfonso_jose.ics",
        mime="text/calendar",
        use_container_width=True
    )

with col_sync:
    if st.button("🔄 Sincronizar", use_container_width=True):
        st.cache_resource.clear()
        st.rerun()

# Días en español y contexto temporal
dias_semana = {0: "Lunes", 1: "Martes", 2: "Miércoles", 3: "Jueves", 4: "Viernes", 5: "Sábado", 6: "Domingo"}
hoy_dt = datetime.now()
hoy_nombre = dias_semana[hoy_dt.weekday()]
hoy_fecha = hoy_dt.date()
hora_actual = hoy_dt.time()

# ----------------------------------------------------
# 1. INDICADOR DE CLASE ACTUAL / PRÓXIMA INMEDIATA
# ----------------------------------------------------
if not df_horario.empty and "dia" in df_horario.columns:
    df_hoy_clases = df_horario[df_horario["dia"].astype(str).str.capitalize() == hoy_nombre].copy()
    
    clase_en_curso = None
    proxima_clase = None
    minutos_para_proxima = 9999

    for _, c in df_hoy_clases.iterrows():
        try:
            h_ini = datetime.strptime(str(c["hora_inicio"]).strip(), "%H:%M").time()
            h_fin = datetime.strptime(str(c["hora_termino"]).strip(), "%H:%M").time()
            
            if h_ini <= hora_actual <= h_fin:
                clase_en_curso = c
                break
            elif h_ini > hora_actual:
                dt_ini = datetime.combine(hoy_fecha, h_ini)
                dt_now = datetime.combine(hoy_fecha, hora_actual)
                dif_min = int((dt_ini - dt_now).total_seconds() / 60)
                if dif_min < minutos_para_proxima:
                    minutos_para_proxima = dif_min
                    proxima_clase = c
        except Exception:
            continue

    if clase_en_curso is not None:
        color = clase_en_curso.get('color') or '#27AE60'
        sala = clase_en_curso.get('sala') or 'Sin sala'
        st.markdown(
            f"""
            <div class="class-status-banner" style="background-color: {color}; color: white;">
                <div>
                    <strong>🔴 EN CLASE AHORA:</strong> {clase_en_curso['ramo']} (📍 {sala})
                </div>
                <div>⏰ Termina a las {clase_en_curso['hora_termino']}</div>
            </div>
            """,
            unsafe_allow_html=True
        )
    elif proxima_clase is not None and minutos_para_proxima <= 180:
        color = proxima_clase.get('color') or '#2980B9'
        sala = proxima_clase.get('sala') or 'Sin sala'
        tiempo_txt = f"En {minutos_para_proxima} min" if minutos_para_proxima > 0 else "¡Comenzando ahora!"
        st.markdown(
            f"""
            <div class="class-status-banner" style="background-color: {color}; color: white;">
                <div>
                    <strong>⏳ PRÓXIMA CLASE:</strong> {proxima_clase['ramo']} (📍 {sala})
                </div>
                <div>⏰ {proxima_clase['hora_inicio']} ({tiempo_txt})</div>
            </div>
            """,
            unsafe_allow_html=True
        )

# Modo Enfoque Toggle
col_t1, col_t2 = st.columns([0.7, 0.3])
with col_t2:
    modo_enfoque = st.toggle("🎯 Modo Enfoque ('Solo Hoy')", value=False)

# ==========================================
# SECCIÓN 1: MÉTRICAS Y KPI
# ==========================================
col_kpi1, col_kpi2, col_kpi3 = st.columns(3)

# 1. Clases hoy
clases_hoy_count = 0
if not df_horario.empty and "dia" in df_horario.columns:
    clases_hoy_count = len(df_horario[df_horario["dia"].astype(str).str.capitalize() == hoy_nombre])

# 2. Pendientes y cálculo de progreso
pendientes_semana_count = 0
total_semana_count = 0
completadas_semana_count = 0
ratio_progreso = 0.0
proximo_certamen_html = "<span>Ninguno agendado</span>"

if not df_actividades.empty:
    df_actividades['fecha_dt'] = pd.to_datetime(df_actividades['fecha'], errors='coerce').dt.date
    
    inicio_semana = hoy_fecha - timedelta(days=hoy_dt.weekday())
    fin_semana = inicio_semana + timedelta(days=6)

    df_semana = df_actividades[
        (df_actividades['fecha_dt'] >= inicio_semana) & 
        (df_actividades['fecha_dt'] <= fin_semana)
    ]
    
    total_semana_count = len(df_semana)
    completadas_semana_count = len(df_semana[df_semana['estado'].astype(str).str.lower() == 'completado'])
    pendientes_semana_count = total_semana_count - completadas_semana_count
    
    if total_semana_count > 0:
        ratio_progreso = completadas_semana_count / total_semana_count

    df_pendientes = df_actividades[df_actividades['estado'].astype(str).str.lower() != 'completado']
    df_eventos = df_pendientes[
        (df_pendientes['tipo'].astype(str).str.lower() == 'evento') & 
        (df_pendientes['fecha_dt'] >= hoy_fecha)
    ].sort_values('fecha_dt')

    if not df_eventos.empty:
        filas_eventos = []
        for _, prox_evt in df_eventos.head(3).iterrows():
            dias_faltantes = (prox_evt['fecha_dt'] - hoy_fecha).days
            if dias_faltantes == 0:
                cuenta_regresiva = "¡HOY!"
            elif dias_faltantes == 1:
                cuenta_regresiva = "Mañana"
            else:
                cuenta_regresiva = f"En {dias_faltantes}d"
                
            ramo_nombre = str(prox_evt.get('ramo', 'General')).strip()
            color_ramo = str(prox_evt.get('color', '#4A90E2')).strip()
            if not color_ramo or color_ramo.lower() == 'nan':
                color_ramo = '#4A90E2'

            item_html = f"""
            <div style="margin-bottom: 5px;">
                <span>• {prox_evt['titulo']} ({cuenta_regresiva})</span> 
                <span style="color: {color_ramo}; font-weight: bold; background-color: rgba(255,255,255,0.08); padding: 1px 5px; border-radius: 4px; font-size: 0.85rem;">[{ramo_nombre}]</span>
            </div>
            """
            filas_eventos.append(item_html)
            
        proximo_certamen_html = "".join(filas_eventos)

with col_kpi1:
    st.metric("📅 Clases Hoy", f"{clases_hoy_count}")

with col_kpi2:
    st.metric("⏳ Pendientes Semana", f"{pendientes_semana_count}")

with col_kpi3:
    st.markdown(
        f"""
        <div class="custom-kpi-card">
            <div class="custom-kpi-label">🎯 Próximos Eventos / Certámenes</div>
            <div class="custom-kpi-value">{proximo_certamen_html}</div>
        </div>
        """,
        unsafe_allow_html=True
    )

# Barra de Progreso Semanal
st.write("")
if total_semana_count > 0:
    porcentaje_txt = int(ratio_progreso * 100)
    st.caption(f"📊 **Progreso semanal:** {completadas_semana_count} de {total_semana_count} actividades ({porcentaje_txt}%)")
    st.progress(ratio_progreso)
else:
    st.caption("📊 **Progreso semanal:** Sin actividades agendadas para esta semana.")

st.divider()

# ==========================================
# SECCIÓN 2: HORARIO DE CLASES
# ==========================================
st.subheader("📅 Horario de Clases")

if not modo_enfoque:
    ver_toda_semana = st.toggle("Ver toda la semana (Agenda 5 días)", value=False)
else:
    ver_toda_semana = False

if not df_horario.empty:
    if not ver_toda_semana:
        st.caption(f"Clases de hoy (**{hoy_nombre}**):")
        df_mostrar = df_horario[df_horario["dia"].astype(str).str.capitalize() == hoy_nombre].copy()
        if df_mostrar.empty:
            st.success("🎉 ¡No tienes clases programadas para hoy!")
        else:
            df_mostrar_mvil = df_mostrar[["hora_inicio", "hora_termino", "ramo", "sala"]].copy()
            df_mostrar_mvil.columns = ["Inicio", "Fin", "Ramo", "Sala"]
            
            st.dataframe(
                df_mostrar_mvil,
                use_container_width=True,
                hide_index=True
            )
    else:
        st.caption("Horario semanal agrupado por días:")
        cols_dias = st.columns(5)
        dias_lista = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes"]

        for idx, dia in enumerate(dias_lista):
            with cols_dias[idx]:
                st.markdown(f"### {dia}")
                df_dia = df_horario[df_horario["dia"].astype(str).str.capitalize() == dia]
                if df_dia.empty:
                    st.caption("*(Sin clases)*")
                else:
                    for _, row in df_dia.iterrows():
                        color_ramo = row.get('color') if row.get('color') else '#4A90E2'
                        sala_txt = row.get('sala') if row.get('sala') else 'Sin sala'
                        
                        st.markdown(
                            f"""
                            <div style="
                                background-color: {color_ramo};
                                color: white;
                                padding: 10px;
                                border-radius: 8px;
                                margin-bottom: 10px;
                                font-size: 0.9rem;
                            ">
                                <strong>{row['ramo']}</strong><br>
                                ⏰ {row['hora_inicio']} - {row['hora_termino']}<br>
                                📍 {sala_txt}
                            </div>
                            """,
                            unsafe_allow_html=True
                        )
else:
    st.info("No hay clases registradas en el horario.")

st.divider()

# ==========================================
# SECCIÓN 3: PENDIENTES & EVENTOS
# ==========================================
st.subheader("✅ Pendientes & Eventos")

if not df_actividades.empty:
    df_filtrado = df_actividades.copy()
    
    # 3. FILTROS RÁPIDOS DE URGENCIA
    if not modo_enfoque:
        col_f1, col_f2 = st.columns([0.55, 0.45])
        
        with col_f1:
            filtro_urgencia = st.segmented_control(
                "Filtro rápido:",
                options=["Todo", "🔴 Hoy/Mañana", "🟡 Esta Semana", "🔥 Prioridad Alta"],
                default="Todo"
            )
        with col_f2:
            ver_completadas = st.toggle("Ver historial completo", value=False)

        col_f3, _ = st.columns([0.5, 0.5])
        with col_f3:
            ramos_unicos = ["Todos"] + list(df_actividades["ramo"].dropna().unique())
            filtro_ramo = st.selectbox("Filtrar por Ramo/Proyecto:", ramos_unicos)

        # Aplicar filtro de ramo
        if filtro_ramo != "Todos":
            df_filtrado = df_filtrado[df_filtrado["ramo"] == filtro_ramo]

        # Aplicar filtros de urgencia
        if filtro_urgencia == "🔴 Hoy/Mañana":
            df_filtrado = df_filtrado[
                (df_filtrado['fecha_dt'] >= hoy_fecha) & 
                (df_filtrado['fecha_dt'] <= hoy_fecha + timedelta(days=1))
            ]
        elif filtro_urgencia == "🟡 Esta Semana":
            df_filtrado = df_filtrado[
                (df_filtrado['fecha_dt'] >= inicio_semana) & 
                (df_filtrado['fecha_dt'] <= fin_semana)
            ]
        elif filtro_urgencia == "🔥 Prioridad Alta":
            df_filtrado = df_filtrado[df_filtrado["prioridad"].astype(str).str.lower() == "alta"]

        if not ver_completadas:
            df_filtrado = df_filtrado[df_filtrado["estado"].astype(str).str.lower() != "completado"]

    else:
        # En modo enfoque: solo actividades de hoy no completadas
        st.info("🎯 **Modo Enfoque activo:** Mostrando únicamente los pendientes para hoy.")
        df_filtrado = df_filtrado[
            (df_filtrado['fecha_dt'] == hoy_fecha) & 
            (df_filtrado['estado'].astype(str).str.lower() != "completado")
        ]

    # Mapeo de Emojis de Prioridad
    mapa_prioridades = {"alta": "🔴", "media": "🟡", "baja": "🟢"}
    df_filtrado["prioridad_emoji"] = df_filtrado["prioridad"].astype(str).str.lower().map(mapa_prioridades).fillna("🟡")
    
    # Checkbox de estado completado
    df_filtrado["Completado"] = df_filtrado["estado"].astype(str).str.lower() == "completado"

    if df_filtrado.empty:
        st.success("🎉 ¡No hay pendientes con este filtro!")
    else:
        cols_mostrar = ["Completado", "titulo", "ramo", "fecha", "prioridad_emoji"]
        df_mostrar_todo = df_filtrado[cols_mostrar].copy()
        df_mostrar_todo.columns = ["✔", "Tarea", "Ramo", "Fecha", "Prio"]

        # Ordenar por fecha
        df_mostrar_todo = df_mostrar_todo.sort_values("Fecha")

        # Tabla editable para interactividad
        edited_df = st.data_editor(
            df_mostrar_todo,
            use_container_width=True,
            hide_index=True,
            disabled=["Tarea", "Ramo", "Fecha", "Prio"]
        )

        # Detectar cambios en checkboxes para guardar en Sheets
        for idx, row in edited_df.iterrows():
            if row["✔"] != df_filtrado.loc[idx, "Completado"]:
                nuevo_estado = "completado" if row["✔"] else "pendiente"
                id_fila = df_filtrado.loc[idx, "id"]
                
                cell = sheet_actividades.find(str(id_fila))
                if cell:
                    sheet_actividades.update_cell(cell.row, 8, nuevo_estado)
                    st.toast(f"Actualizado: {row['Tarea']} -> {nuevo_estado}")
                    st.cache_resource.clear()
                    st.rerun()
else:
    st.info("No tienes tareas ni eventos pendientes.")