import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime

# 1. Configuración de la página
st.set_page_config(page_title="Dashboard de Alfonso José", page_icon="🎓", layout="wide")

st.title("🎓 Dashboard Cloud — Alfonso José")
st.markdown("---")

# Conexión a Google Sheets con google-auth
@st.cache_resource
def conectar_gsheets():
    scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    creds = Credentials.from_service_account_file("credenciales.json", scopes=scopes)
    client = gspread.authorize(creds)
    sheet = client.open("Dashboard Alfonso Jose").sheet1
    return sheet

sheet = conectar_gsheets()

def cargar_actividades():
    data = sheet.get_all_records()
    if not data:
        return pd.DataFrame(columns=['id', 'tipo', 'titulo', 'ramo', 'fecha', 'hora', 'prioridad', 'estado', 'color'])
    return pd.DataFrame(data)

def cambiar_estado_tarea(id_tarea, estado_actual):
    nuevo_estado = "completada" if estado_actual == "pendiente" else "pendiente"
    cell = sheet.find(str(id_tarea))
    if cell:
        # La columna 'estado' es la H (columna 8)
        sheet.update_cell(cell.row, 8, nuevo_estado)

df_actividades = cargar_actividades()

# --- VISTA PRINCIPAL ---
col_izq, col_der = st.columns(2)

with col_izq:
    st.header("📅 Próximos Eventos & Certámenes")
    if df_actividades.empty:
        st.write("No hay eventos en la nube.")
    else:
        eventos = df_actividades[(df_actividades['tipo'] == 'evento') & (df_actividades['estado'] == 'pendiente')]
        if eventos.empty:
            st.write("No hay eventos pendientes.")
        else:
            for _, row in eventos.iterrows():
                hora_txt = f"a las {row['hora']}" if row['hora'] else "Todo el día"
                ramo = row['ramo'] if row['ramo'] else "Personal"
                color = row['color'] if row['color'] else "#4A90E2"
                
                st.markdown(f"""
                <div style="border-left: 5px solid {color}; padding-left: 10px; margin-bottom: 10px;">
                    <b>{row['titulo']}</b><br>
                    🗓️ {row['fecha']} | {hora_txt}<br>
                    <span style="background-color: {color}; color: white; padding: 2px 6px; border-radius: 4px; font-size: 0.8em;">{ramo}</span>
                </div>
                """, unsafe_allow_html=True)
                st.divider()

with col_der:
    st.header("✅ To-Do List & Tareas")
    if df_actividades.empty:
        st.write("¡Todo al día! 🎉")
    else:
        tareas = df_actividades[df_actividades['tipo'] == 'tarea']
        if tareas.empty:
            st.write("No hay tareas registradas.")
        else:
            for _, row in tareas.iterrows():
                completada = True if str(row['estado']).strip().lower() == 'completada' else False
                ramo = row['ramo'] if row['ramo'] else "Personal"
                
                marcado = st.checkbox(
                    f"**{row['titulo']}** [{ramo}] — Vence: {row['fecha']}",
                    value=completada,
                    key=f"tarea_{row['id']}"
                )
                if marcado != completada:
                    cambiar_estado_tarea(row['id'], row['estado'])
                    st.rerun()