import os
import json
import gspread
from google import genai
from google.oauth2.service_account import Credentials
from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, CommandHandler, filters, ContextTypes

# 1. Credenciales desde Variables de Entorno
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

# 2. Configurar Google Sheets (Nube vs Local)
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

# 3. Configurar la IA de forma explícita
if not GEMINI_API_KEY:
    raise ValueError("Falta configurar la variable de entorno GEMINI_API_KEY")

client_ai = genai.Client(api_key=GEMINI_API_KEY)

def obtener_contexto_etiquetas():
    etiquetas = sheet_etiquetas.get_all_records()
    lista_existentes = [row.get('nombre') for row in etiquetas if row.get('nombre')]
    return lista_existentes

def eliminar_registros(accion_eliminar):
    # accion_eliminar: {"accion": "eliminar", "hoja": "horario" | "actividades" | "etiquetas", "criterio": "..."}
    hoja_nombre = accion_eliminar.get("hoja", "").lower()
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
    # Recorrer de abajo hacia arriba para mantener los índices de fila válidos
    for idx in range(len(filas) - 1, -1, -1):
        row_str = " ".join([str(val).lower() for val in filas[idx].values()])
        if criterio in row_str:
            target_sheet.delete_rows(idx + 2) # +2 por cabecera e índice 1-based
            eliminados += 1

    if eliminados > 0:
        return f"Se eliminaron {eliminados} registro(s) que coincidían con '{criterio}'."
    return f"No se encontraron registros coincidentes con '{criterio}'."

def gestionar_etiqueta_y_guardar(lista_datos):
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
        tipo_etiqueta = datos.get('categoria_etiqueta', 'ramo') # 'ramo' o 'proyecto'
        
        # Guardar / Verificar Etiqueta
        if ramo_key not in mapa_colores:
            sheet_etiquetas.append_row([ramo, tipo_etiqueta, color_ia])
            mapa_colores[ramo_key] = color_ia
        else:
            color_ia = mapa_colores[ramo_key]

        tipo_item = datos.get('tipo', 'tarea')

        # Si es un bloque de HORARIO semanal
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

        # Si es EVENTO o TAREA puntual
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

# 4. Lógica del Bot
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "¡Hola Alfonso José! 🎓 Bot activo y listo para sincronizar tus actividades y horario."
    )

async def procesar_mensaje(update: Update, context: ContextTypes.DEFAULT_TYPE):
    mensaje_usuario = update.message.text
    print(f"Recibido de Alfonso José: {mensaje_usuario}")
    
    mensaje_espera = await update.message.reply_text("⏳ Procesando solicitud...")
    
    try:
        etiquetas_existentes = obtener_contexto_etiquetas()
        
        instrucciones = f"""
Eres el asistente personal inteligente de Alfonso José. Tu trabajo es analizar mensajes y gestionar tareas, eventos, horario de clases o solicitudes de borrado.
Hoy es {datetime.now().strftime('%A %d de %B de %Y')}.

LISTA DE RAMOS/PROYECTOS YA EXISTENTES:
{json.dumps(etiquetas_existentes, ensure_ascii=False)}

REGLAS DE ASOCIACIÓN:
1. Si el usuario menciona un ramo o proyecto en formato corto o con variación (ej: "Visualización"), busca si coincide con la lista de EXISTENTES y usa el NOMBRE EXACTO de la lista.
2. Si es un nuevo elemento, determina si es "ramo" o "proyecto" en el campo "categoria_etiqueta".

DETECCIÓN DE ACCIÓN:
- Si el usuario pide BORRAR, ELIMINAR o QUITAR un ramo, tarea, clase o evento, responde con este formato JSON:
{{
  "accion": "eliminar",
  "hoja": "horario" (o "actividades" o "etiquetas"),
  "criterio": "nombre o texto a eliminar"
}}

- Si el usuario pide AGREGAR o REGISTRAR algo, responde con una LISTA de objetos JSON:
[
  {{
    "accion": "agregar",
    "tipo": "horario" (o "evento" o "tarea"),
    "categoria_etiqueta": "ramo" (o "proyecto"),
    "titulo": "Nombre de la materia / actividad",
    "ramo": "Nombre exacto del ramo o proyecto",
    "dia": "Lunes" (solo si es "horario"),
    "fecha": "YYYY-MM-DD" (solo si es "evento" o "tarea"),
    "hora_inicio": "HH:MM" (solo para "horario"),
    "hora_termino": "HH:MM" (solo para "horario"),
    "hora": "HH:MM" (para evento/tarea o null),
    "sala": "Nombre o número de sala",
    "prioridad": "alta", "media" o "baja",
    "color": "#HEX"
  }}
]

Responde ÚNICAMENTE con el JSON válido sin bloques markdown extra si es posible.
"""

        prompt = f"{instrucciones}\n\nMensaje:\n{mensaje_usuario}"
        respuesta = client_ai.models.generate_content(
            model='gemini-3.6-flash',
            contents=prompt,
        )
        
        texto_limpio = respuesta.text.replace('```json', '').replace('```', '').strip()
        data = json.loads(texto_limpio)
        
        # Caso 1: Eliminación
        if isinstance(data, dict) and data.get("accion") == "eliminar":
            resultado_txt = eliminar_registros(data)
            await mensaje_espera.edit_text(f"🗑️ {resultado_txt}")
            return

        # Caso 2: Agregar elementos
        lista_datos = data if isinstance(data, list) else [data]
        gestionar_etiqueta_y_guardar(lista_datos)
        
        resumen = "✅ **¡Sincronizado con éxito en tu Sheet!**\n\n"
        for item in lista_datos:
            tipo_item = item.get("tipo")
            cat_item = item.get("categoria_etiqueta", "ramo")
            if tipo_item == "horario":
                icono = "📅 Clase"
            elif tipo_item == "evento":
                icono = "📌 Evento"
            else:
                icono = "✅ Tarea"
            
            titulo_item = item.get('titulo', '')
            ramo_item = item.get('ramo', 'Personal')
            resumen += f"• {icono}: **{titulo_item}** ({cat_item.capitalize()}: {ramo_item})\n"
            
        await mensaje_espera.edit_text(resumen, parse_mode='Markdown')
        
    except Exception as e:
        await mensaje_espera.edit_text(f"❌ Error al procesar: {e}")

if __name__ == '__main__':
    print("Iniciando bot...")
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), procesar_mensaje))
    app.run_polling()