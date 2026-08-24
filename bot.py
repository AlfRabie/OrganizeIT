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

# 3. Configurar la IA
client_ai = genai.Client(api_key=GEMINI_API_KEY)

instrucciones = """
Eres el asistente personal inteligente de Alfonso José. Tu trabajo es analizar mensajes y extraer 
información de tareas, eventos o bloques de horario de clases para su dashboard personal. 
Hoy es Lunes 24 de Agosto de 2026. Calcula las fechas exactas en base a hoy.

CLASIFICACIÓN DE TIPO:
- Si el mensaje describe clases semanales o el horario completo de asignaturas/ramos, usa el tipo "horario".
- Si es una prueba, certamen, reunión o fecha importante puntual, usa "evento".
- Si es una tarea, entregable o pendiente, usa "tarea".

REGLA PARA CERTÁMENES/PRUEBAS:
Si menciona un evento de alta importancia como "certamen" o "examen", genera DOS elementos:
1. El evento principal del certamen.
2. Una tarea en el To-Do List para "Estudiar para [Nombre]" unos días antes.

COLORES (#HEX):
Asigna un color armónico por ramo (ej: Azul #4A90E2, Morado #BD10E0, Verde #7ED321, Naranja #F5A623, Turquesa #50E3C2, Coral #FF5A5F).

Responde ÚNICAMENTE con un JSON válido (Lista de objetos):
[
  {
    "tipo": "horario" (o "evento" o "tarea"),
    "titulo": "Nombre de la materia / actividad",
    "ramo": "Nombre del ramo o proyecto",
    "dia": "Lunes" (solo si es tipo "horario"),
    "fecha": "YYYY-MM-DD" (solo si es "evento" o "tarea"),
    "hora_inicio": "HH:MM" (solo si es "horario"),
    "hora_fin": "HH:MM" (solo si es "horario"),
    "hora": "HH:MM" (para evento/tarea o null),
    "prioridad": "alta", "media" o "baja",
    "color": "#HEX"
  }
]
"""

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
        
        # Guardar / Verificar Etiqueta
        if ramo_key not in mapa_colores:
            tipo_etiqueta = "proyecto" if "proyecto" in ramo.lower() or color_ia == "#FF5A5F" else "ramo"
            sheet_etiquetas.append_row([ramo, tipo_etiqueta, color_ia])
            mapa_colores[ramo_key] = color_ia
        else:
            color_ia = mapa_colores[ramo_key]

        tipo_item = datos.get('tipo', 'tarea')

        # Si es un bloque de HORARIO semanal
        if tipo_item == 'horario':
            fila_horario = [
                str(nuevo_id_hor),
                datos.get('ramo') or datos.get('titulo', ''),
                datos.get('dia', ''),
                datos.get('hora_inicio', ''),
                datos.get('hora_fin', ''),
                datos.get('sala', '') or '',
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
    
    mensaje_espera = await update.message.reply_text("⏳ Procesando y clasificando información...")
    
    try:
        prompt = f"{instrucciones}\n\nMensaje:\n{mensaje_usuario}"
        respuesta = client_ai.models.generate_content(
            model='gemini-3.6-flash',
            contents=prompt,
        )
        
        texto_limpio = respuesta.text.replace('```json', '').replace('```', '').strip()
        lista_datos = json.loads(texto_limpio)
        
        gestionar_etiqueta_y_guardar(lista_datos)
        
        resumen = "✅ **¡Sincronizado con éxito en tu Sheet!**\n\n"
        for item in lista_datos:
            tipo_item = item.get("tipo")
            if tipo_item == "horario":
                icono = "📅 Clase de Horario"
            elif tipo_item == "evento":
                icono = "📌 Evento Puntual"
            else:
                icono = "✅ Tarea"
            
            titulo_item = item.get('titulo', '')
            ramo_item = item.get('ramo', 'Personal')
            resumen += f"• {icono}: **{titulo_item}** ({ramo_item})\n"
            
        await mensaje_espera.edit_text(resumen, parse_mode='Markdown')
        
    except Exception as e:
        await mensaje_espera.edit_text(f"❌ Error al procesar: {e}")

if __name__ == '__main__':
    print("Iniciando bot...")
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), procesar_mensaje))
    app.run_polling()