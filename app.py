import os
import json
import pandas as pd
import streamlit as st
import gspread
from google.oauth2.service_account import Credentials

# Configuración de página
st.set_page_config(page_title="Dashboard Alfonso José", page_icon="🎓", layout="wide")

# 1. Conexión segura a Google Sheets
scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]

@st.cache_resource
def conectar_sheets():
    # Opción A: Intentar leer desde los Secrets de Streamlit Cloud
    if "GOOGLE_CREDENTIALS_JSON" in st.secrets:
        cred_data = st.secrets["GOOGLE_CREDENTIALS_JSON"]
        if isinstance(cred_data, str):
            cred_info = json.loads(cred_data)
        else:
            cred_info = dict(cred_data)
        creds = Credentials.from_service_account_info(cred_info, scopes=scopes)

    # Opción B: Intentar leer desde Variable de Entorno del sistema
    elif "GOOGLE_CREDENTIALS_JSON" in os.environ:
        cred_info = json.loads(os.environ["GOOGLE_CREDENTIALS_JSON"])
        creds = Credentials.from_service_account_info(cred_info, scopes=scopes)

    # Opción C: Respaldo Local (en tu Mac)
    elif os.path.exists("credenciales.json"):
        creds = Credentials.from_service_account_file("credenciales.json", scopes=scopes)

    else:
        st.error("❌ No se encontraron las credenciales de Google Sheets. Configura GOOGLE_CREDENTIALS_JSON en los Secrets de Streamlit.")
        st.stop()

    client = gspread.authorize(creds)
    return client.open("Dashboard Alfonso Jose")

# Conectar a la planilla
sh = conectar_sheets()
sheet_actividades = sh.worksheet("Actividades")
sheet_etiquetas = sh.worksheet("Etiquetas")
sheet_horario = sh.worksheet("Horario")

# 2. Cargar Datos
st.title("🎓 Dashboard Personal - Alfonso José")

df_actividades = pd.DataFrame(sheet_actividades.get_all_records())
df_etiquetas = pd.DataFrame(sheet_etiquetas.get_all_records())
df_horario = pd.DataFrame(sheet_horario.get_all_records())

# Métricas rápidas
col1, col2, col3 = st.columns(3)
with col1:
    st.metric("Total Actividades", len(df_actividades) if not df_actividades.empty else 0)
with col2:
    st.metric("Ramos / Proyectos", len(df_etiquetas) if not df_etiquetas.empty else 0)
with col3:
    st.metric("Clases en Horario", len(df_horario) if not df_horario.empty else 0)

st.divider()

# Sección de Actividades y Etiquetas
col_left, col_right = st.columns([2, 1])

with col_left:
    st.subheader("📌 Tareas y Eventos")
    if not df_actividades.empty:
        st.dataframe(df_actividades, use_container_width=True)
    else:
        st.info("No hay actividades registradas aún.")

with col_right:
    st.subheader("🏷️ Etiquetas y Colores")
    if not df_etiquetas.empty:
        st.dataframe(df_etiquetas, use_container_width=True)
    else:
        st.info("No hay etiquetas registradas.")

st.divider()

# Sección de Horario
st.subheader("📅 Horario de Clases")
if not df_horario.empty:
    st.dataframe(df_horario, use_container_width=True)
else:
    st.info("La pestaña de Horario está lista para recibir tus ramos.")