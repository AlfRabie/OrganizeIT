import os
import json
import gspread
from google import genai
from google.oauth2.service_account import Credentials
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    MessageHandler,
    CommandHandler,
    CallbackQueryHandler,
    filters,
    ContextTypes
)

# 1. Credenciales desde Variables de Entorno
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

# 2. Configurar Google Sheets
scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]

cred_info = None
if "GOOGLE_CREDENTIALS_JSON" in os.environ:
    cred_info = json.loads(os.environ["GOOGLE_CREDENTIALS_JSON"])
elif os.path.exists("credenciales.json"):
    creds = Credentials.from_service_account_file("credenciales.json", scopes=scopes)

if cred_info:
    creds = Credentials.from_service_account_info(cred_info, scopes=scopes)

client = gspread.authorize(creds)
sh = client.open("Dashboard Alfonso Jose")
sheet_actividades = sh.worksheet("Actividades")
sheet_etiquetas = sh.worksheet("Etiquetas")
sheet_horario = sh.worksheet("Horario")

# 3. Configurar Gemini Client
if not GEMINI_API_KEY:
    raise ValueError("Falta configurar la variable de entorno GEMINI_API_KEY")

client_ai = genai.Client(api_key=GEMINI_API_KEY)

def obtener_contexto_etiquetas():
    etiquetas = sheet_etiquetas.get_all_records()
    return [row.get('nombre') for row in etiquetas if row.get('nombre')]

def ejecutar_eliminar(accion_eliminar):
    hoja_nombre = str(accion_eliminar.get("hoja", "")).lower()
    criterio = str(accion_eliminar.get("criterio", "")).lower().strip()
    
    if not criterio:
        return "No se especificó qué eliminar."

    target_sheet = None
    if "horario" in hoja_nombre:
        target_sheet = sheet_horario
    elif "actividades" in hoja_nombre or "tarea" in hoja_nombre or "evento" in hoja_nombre:
        target_sheet = sheet_actividades
    elif "etiqueta" in hoja_nombre or "ramo" in hoja_nombre or "proyecto" in hoja_nombre:
        target_sheet = sheet_etiquetas

    if not target_sheet:
        return "No se reconoció la hoja a modificar."

    filas = target_sheet.get_all_records()
    eliminados = 0
    for idx in range(len(filas) - 1, -1, -1):
        row_str = " ".join([str(val).lower() for val in filas[idx].values()])
        if criterio in row_str:
            target_sheet.delete_rows(idx + 2)
            eliminados += 1

    if eliminados > 0:
        return f"Se eliminaron {eliminados} registro(s) coincidentes."
    return f"No se encontraron registros coincidentes con '{criterio}'."

def ejecutar_guardar(lista_datos):
    etiquetas_actuales = sheet_etiquetas.get_all_records()
    mapa_colores = {str(row.get('nombre', '')).strip().lower(): row.get('color') for row in etiquetas_actuales if row.get('nombre')}
    
    registros_actividades = sheet_actividades.get_all_records()
    nuevo_id_act = len(registros_actividades) + 1

    registros_horario = sheet_horario.get_all_records()
    nuevo_id_hor = len(registros_horario) + 1
    
    for datos in lista_datos:
        ramo = datos.get('ramo') or datos.get('titulo') or 'Personal'
        ramo_key = ramo.strip().lower()
        color_ia = datos.get('color', '#4A90E2')
        tipo_etiqueta = datos.get('categoria_etiqueta', 'ramo')
        
        if ramo_key not in mapa_colores:
            sheet_etiquetas.append_row([ramo, tipo_etiqueta, color_ia])
            mapa_colores[ramo_key] = color_ia
        else:
            color_ia = mapa_colores[ramo_key]

        tipo_item = datos.get('tipo', 'tarea')

        if tipo_item == 'horario':
            fila_horario = [
                str(nuevo_id_hor),
                datos.get('dia', ''),
                datos.get('hora_inicio', ''),
                datos.get('hora_termino', ''),
                ramo,
                datos.get('sala', ''),
                color_ia
            ]
            sheet_horario.append_row(fila_horario)
            nuevo_id_hor += 1
        else:
            fila_actividad = [
                str(nuevo_id_act),
                tipo_item,
                datos.get('titulo', ''),
                ramo,
                datos.get('fecha', ''),
                datos.get('hora') or '',
                datos.get('prioridad', 'media'),
                'pendiente',
                color_ia
            ]
            sheet_actividades.append_row(fila_actividad)
            nuevo_id_act += 1

# 4. Handlers de Telegram
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("¡Hola Alfonso José! ⚡ Bot activo con modo de confirmación previa.")

async def procesar_mensaje(update: Update, context: ContextTypes.DEFAULT_TYPE):
    mensaje_usuario = update.message.text
    mensaje_espera = await update.message.reply_text("⏳ Analizando solicitud...")
    
    try:
        etiquetas_existentes = obtener_contexto_etiquetas()
        
        instrucciones = f"""
Eres el asistente personal inteligente de Alfonso José.
LISTA DE RAMOS/PROYECTOS EXISTENTES:
{json.dumps(etiquetas_existentes, ensure_ascii=False)}

REGLAS DE ASOCIACIÓN:
1. Si el usuario menciona un ramo/proyecto existente de forma corta, usa el NOMBRE EXACTO de la lista.
2. Determina si los nuevos elementos son "ramo" o "proyecto".

FORMATOS JSON DE RESPUESTA:
- Si pide BORRAR / ELIMINAR / QUITAR:
{{
  "accion": "eliminar",
  "hoja": "horario" (o "actividades" o "etiquetas"),
  "criterio": "texto a eliminar"
}}

- Si pide AGREGAR / GUARDAR / CREAR:
[
  {{
    "accion": "agregar",
    "tipo": "horario" (o "evento" o "tarea"),
    "categoria_etiqueta": "ramo" (o "proyecto"),
    "titulo": "Nombre de la materia / actividad",
    "ramo": "Nombre exacto del ramo o proyecto",
    "dia": "Lunes" (solo para horario),
    "fecha": "YYYY-MM-DD" (solo para evento/tarea),
    "hora_inicio": "HH:MM",
    "hora_termino": "HH:MM",
    "hora": "HH:MM",
    "sala": "Nombre o número de sala",
    "prioridad": "alta", "media" o "baja",
    "color": "#HEX"
  }}
]
"""
        prompt = f"{instrucciones}\n\nMensaje:\n{mensaje_usuario}"
        respuesta = client_ai.models.generate_content(
            model='gemini-3.6-flash',
            contents=prompt,
        )
        
        texto_limpio = respuesta.text.replace('```json', '').replace('```', '').strip()
        parsed_data = json.loads(texto_limpio)
        
        # Guardar en memoria temporal del contexto de usuario
        context.user_data['pending_action'] = parsed_data
        
        # Construir mensaje de pre-visualización
        if isinstance(parsed_data, dict) and parsed_data.get("accion") == "eliminar":
            preview = f"🗑️ **¿Confirmas ELIMINAR este registro?**\n\n"
            preview += f"• **Pestaña:** {parsed_data.get('hoja')}\n"
            preview += f"• **Criterio:** {parsed_data.get('criterio')}"
        else:
            lista_datos = parsed_data if isinstance(parsed_data, list) else [parsed_data]
            preview = f"📝 **¿Confirmas GUARDAR lo siguiente?**\n\n"
            for item in lista_datos:
                tipo = item.get('tipo', 'tarea')
                ramo = item.get('ramo', 'Personal')
                cat = item.get('categoria_etiqueta', 'ramo').capitalize()
                titulo = item.get('titulo', '')
                preview += f"• **{tipo.upper()}**: {titulo} ({cat}: {ramo})\n"

        # Crear botones interactivos
        keyboard = [
            [
                InlineKeyboardButton("✅ Sí, aplicar", callback_data="confirmar_si"),
                InlineKeyboardButton("❌ Cancelar", callback_data="confirmar_no")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await mensaje_espera.edit_text(preview, parse_mode='Markdown', reply_markup=reply_markup)

    except Exception as e:
        await mensaje_espera.edit_text(f"❌ Error al analizar: {e}")

async def procesar_confirmacion(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "confirmar_no":
        context.user_data.pop('pending_action', None)
        await query.edit_message_text("❌ **Acción cancelada.** No se realizaron cambios en Google Sheets.")
        return

    pending_action = context.user_data.get('pending_action')
    if not pending_action:
        await query.edit_message_text("⚠️ No se encontró ninguna acción pendiente.")
        return

    try:
        # Caso 1: Eliminar
        if isinstance(pending_action, dict) and pending_action.get("accion") == "eliminar":
            res = ejecutar_eliminar(pending_action)
            await query.edit_message_text(f"✅ **¡Completado!** {res}")
        # Caso 2: Agregar
        else:
            lista_datos = pending_action if isinstance(pending_action, list) else [pending_action]
            ejecutar_guardar(lista_datos)
            await query.edit_message_text("✅ **¡Sincronizado con éxito en tu Google Sheet!**")

    except Exception as e:
        await query.edit_message_text(f"❌ Error al aplicar cambios: {e}")
    finally:
        context.user_data.pop('pending_action', None)

if __name__ == '__main__':
    print("Iniciando bot...")
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), procesar_mensaje))
    app.add_handler(CallbackQueryHandler(procesar_confirmacion))
    app.run_polling()