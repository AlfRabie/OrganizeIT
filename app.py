import os
import json
import pandas as pd
import streamlit as st
import gspread
from datetime import datetime, date
from google.oauth2.service_account import Credentials

# Configuración de página
st.set_page_config(page_title="Dashboard Personal - Alfonso José", page_icon="⚡", layout="wide")

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

# Header y Botón de Recarga
col_title, col_sync = st.columns([0.8, 0.2])
with col_title:
    st.title("⚡ Dashboard Personal - Alfonso José")
with col_sync:
    st.write("")
    if st.button("🔄 Sincronizar datos", use_container_width=True):
        st.cache_resource.clear()
        st.rerun()

# Días en español
dias_semana = {0: "Lunes", 1: "Martes", 2: "Miércoles", 3: "Jueves", 4: "Viernes", 5: "Sábado", 6: "Domingo"}
hoy_dt = datetime.now()
hoy_nombre = dias_semana[hoy_dt.weekday()]
hoy_fecha = hoy_dt.date()

# ==========================================
# SECCIÓN 1: MÉTRICAS Y KPI
# ==========================================
col_kpi1, col_kpi2, col_kpi3 = st.columns(3)

# 1. Clases hoy
clases_hoy_count = 0
if not df_horario.empty and "dia" in df_horario.columns:
    clases_hoy_count = len(df_horario[df_horario["dia"].astype(str).str.capitalize() == hoy_nombre])

# 2. Pendientes esta semana
pendientes_semana_count = 0
proximo_certamen_str = "Ninguno agendado"

if not df_actividades.empty:
    df_actividades['fecha_dt'] = pd.to_datetime(df_actividades['fecha'], errors='coerce').dt.date
    df_pendientes = df_actividades[df_actividades['estado'].astype(str).str.lower() != 'completado']
    
    # Pendientes próximos 7 días
    pendientes_semana = df_pendientes[
        (df_pendientes['fecha_dt'] >= hoy_fecha) & 
        (df_pendientes['fecha_dt'] <= hoy_fecha + pd.Timedelta(days=7))
    ]
    pendientes_semana_count = len(pendientes_semana)

    # Próximo certamen / evento
    df_eventos = df_pendientes[
        (df_pendientes['tipo'].astype(str).str.lower() == 'evento') & 
        (df_pendientes['fecha_dt'] >= hoy_fecha)
    ].sort_values('fecha_dt')

    if not df_eventos.empty:
        prox_evt = df_eventos.iloc[0]
        dias_faltantes = (prox_evt['fecha_dt'] - hoy_fecha).days
        if dias_faltantes == 0:
            cuenta_regresiva = "¡HOY!"
        elif dias_faltantes == 1:
            cuenta_regresiva = "Mañana"
        else:
            cuenta_regresiva = f"En {dias_faltantes} días"
        proximo_certamen_str = f"{prox_evt['titulo']} ({cuenta_regresiva})"

with col_kpi1:
    st.metric("📅 Clases de Hoy", f"{clases_hoy_count} asignaturas")

with col_kpi2:
    st.metric("⏳ Pendientes esta Semana", f"{pendientes_semana_count} entregas")

with col_kpi3:
    st.metric("🎯 Próximo Certamen / Evento", proximo_certamen_str)

st.divider()

# ==========================================
# SECCIÓN 2: HORARIO DE CLASES
# ==========================================
st.subheader("📅 Horario de Clases")

ver_toda_semana = st.toggle("Ver toda la semana (Agenda en 5 columnas)", value=False)

if not df_horario.empty:
    if not ver_toda_semana:
        st.caption(f"Mostrando clases de hoy (**{hoy_nombre}**):")
        df_mostrar = df_horario[df_horario["dia"].astype(str).str.capitalize() == hoy_nombre]
        if df_mostrar.empty:
            st.success("🎉 ¡No tienes clases programadas para hoy!")
        else:
            st.dataframe(
                df_mostrar[["hora_inicio", "hora_termino", "ramo", "sala"]],
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
                        st.info(f"**{row['ramo']}**\n\n⏰ {row['hora_inicio']} - {row['hora_termino']}\n\n📍 {row.get('sala', 'Sin sala')}")
else:
    st.info("No hay clases registradas en el horario.")

st.divider()

# ==========================================
# SECCIÓN 3: PENDIENTES & EVENTOS
# ==========================================
st.subheader("✅ Pendientes & Eventos")

if not df_actividades.empty:
    # Filtros
    col_f1, col_f2 = st.columns([0.5, 0.5])
    
    ramos_unicos = ["Todos"] + list(df_actividades["ramo"].dropna().unique())
    with col_f1:
        filtro_ramo = st.selectbox("Filtrar por Ramo o Proyecto:", ramos_unicos)
    
    with col_f2:
        ver_completadas = st.toggle("Ver historial completo (incluyendo completadas)", value=False)

    # Filtrado
    df_filtrado = df_actividades.copy()
    
    if filtro_ramo != "Todos":
        df_filtrado = df_filtrado[df_filtrado["ramo"] == filtro_ramo]

    if not ver_completadas:
        df_filtrado = df_filtrado[df_filtrado["estado"].astype(str).str.lower() != "completado"]

    # Mapeo de Emojis de Prioridad
    mapa_prioridades = {"alta": "🔴 Alta", "media": "🟡 Media", "baja": "🟢 Baja"}
    df_filtrado["prioridad_emoji"] = df_filtrado["prioridad"].astype(str).str.lower().map(mapa_prioridades).fillna("🟡 Media")
    
    # Checkbox de estado completado
    df_filtrado["Completado"] = df_filtrado["estado"].astype(str).str.lower() == "completado"

    # Seleccionar columnas a mostrar
    cols_mostrar = ["Completado", "titulo", "ramo", "fecha", "prioridad_emoji"]
    df_mostrar_todo = df_filtrado[cols_mostrar].copy()
    df_mostrar_todo.columns = ["Completado", "Tarea / Evento", "Ramo o Proyecto", "Fecha", "Prioridad"]

    # Ordenar por fecha
    df_mostrar_todo = df_mostrar_todo.sort_values("Fecha")

    # Tabla editable para interactividad
    edited_df = st.data_editor(
        df_mostrar_todo,
        use_container_width=True,
        hide_index=True,
        disabled=["Tarea / Evento", "Ramo o Proyecto", "Fecha", "Prioridad"]
    )

    # Detectar cambios en checkboxes para guardar en Sheets
    for idx, row in edited_df.iterrows():
        if row["Completado"] != df_filtrado.loc[idx, "Completado"]:
            nuevo_estado = "completado" if row["Completado"] else "pendiente"
            id_fila = df_filtrado.loc[idx, "id"]
            
            # Buscar fila en gspread y actualizar
            cell = sheet_actividades.find(str(id_fila))
            if cell:
                # La columna 'estado' es la 8va (H)
                sheet_actividades.update_cell(cell.row, 8, nuevo_estado)
                st.toast(f"Actualizado: {row['Tarea / Evento']} -> {nuevo_estado}")
                st.cache_resource.clear()
                st.rerun()

else:
    st.info("No tienes tareas ni eventos pendientes.")