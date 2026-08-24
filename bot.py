import json
import gspread
from google import genai
from google.oauth2.service_account import Credentials
from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, CommandHandler, filters, ContextTypes

# 1. Credenciales
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

# 2. Configurar Google Sheets con las 3 pestañas
scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
creds = Credentials.from_service_account_file("credenciales.json", scopes=scopes)
client = gspread.authorize(creds)

sh = client.open("Dashboard Alfonso Jose")
sheet_actividades = sh.worksheet("Actividades")
sheet_etiquetas = sh.worksheet("Etiquetas")
sheet_horario = sh.worksheet("Horario")

# 3. Configurar la IA
client_ai = genai.Client(api_key=GEMINI_API_KEY)

instrucciones = """
Eres el asistente personal inteligente de Alfonso José. Tu trabajo es analizar mensajes y extraer 
información de tareas, eventos o clases para su dashboard personal. 
Hoy es Lunes 24 de Agosto de 2026. Calcula las fechas exactas en base a hoy.
IMPORTANTE: Si Alfonso José menciona un evento de alta importancia como un "certamen", "examen" o "prueba", 
debes generar DOS elementos: 
1. El evento principal del certamen.
2. Una tarea en el To-Do List para "Estudiar para el certamen [Nombre]" unos días antes.

Además, debes asignar un color en formato hexadecimal (#HEX) representativo para cada actividad:
- Si es un ramo oficial, asigna un color armónico (ej: Azul #4A90E2, Morado #BD10E0, Verde #7ED321, Naranja #F5A623, Turquesa #50E3C2).
- Si es un proyecto personal o emprendimiento, asigna un color destacado (ej: Rojo coral #FF5A5F).
- Si es algo personal general, usa un gris (#9B9B9B).

Siempre debes responder ÚNICAMENTE con un objeto JSON válido que sea una LISTA de objetos, sin texto adicional.

Estructura obligatoria (Formato JSON Array):
[
  {
    "tipo": "evento" (o "tarea" o "nota"),
    "titulo": "Título descriptivo",
    "ramo": "Nombre del ramo o proyecto o null",
    "fecha": "YYYY-MM-DD",
    "hora": "HH:MM o null",
    "prioridad": "alta", "media" o "baja",
    "color": "#HEX"
  }
]
"""

def gestionar_etiqueta_y_guardar(lista_datos):
    # 1. Obtener etiquetas existentes en la pestaña 'Etiquetas'
    etiquetas_actuales = sheet_etiquetas.get_all_records()
    mapa_colores = {str(row.get('nombre', '')).strip().lower(): row.get('color') for row in etiquetas_actuales if row.get('nombre')}
    
    registros_actividades = sheet_actividades.get_all_records()
    nuevo_id = len(registros_actividades) + 1
    
    for datos in lista_datos:
        ramo = datos.get('ramo') or 'Personal'
        ramo_key = ramo.strip().lower()
        color_ia = datos.get('color', '#4A90E2')
        
        # Si el ramo/proyecto no está en la pestaña Etiquetas, lo agregamos automáticamente
        if ramo_key not in mapa_colores:
            tipo_etiqueta = "proyecto" if "proyecto" in ramo.lower() or color_ia == "#FF5A5F" else "ramo"
            sheet_etiquetas.append_row([ramo, tipo_etiqueta, color_ia])
            mapa_colores[ramo_key] = color_ia
        else:
            # Si ya existe, usamos el color oficial registrado en la pestaña Etiquetas
            color_ia = mapa_colores[ramo_key]

        # 2. Guardamos la actividad en la pestaña principal 'Actividades'
        fila = [
            str(nuevo_id),
            datos.get('tipo', 'tarea'),
            datos.get('titulo', ''),
            ramo,
            datos.get('fecha', ''),
            datos.get('hora') or '',
            datos.get('prioridad', 'media'),
            'pendiente',
            color_ia
        ]
        sheet_actividades.append_row(fila)
        nuevo_id += 1

# 4. Comandos y Lógica del Bot
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "¡Hola Alfonso José! 🎓 Bot sincronizado correctamente con tus 3 pestañas en la nube (Actividades, Etiquetas y Horario)."
    )

async def procesar_mensaje(update: Update, context: ContextTypes.DEFAULT_TYPE):
    mensaje_usuario = update.message.text
    print(f"Recibido de Alfonso José: {mensaje_usuario}")
    
    mensaje_espera = await update.message.reply_text("⏳ Procesando y sincronizando con Google Sheets...")
    
    try:
        prompt = f"{instrucciones}\n\nMensaje:\n{mensaje_usuario}"
        respuesta = client_ai.models.generate_content(
            model='gemini-3.6-flash',
            contents=prompt,
        )
        
        texto_limpio = respuesta.text.replace('```json', '').replace('```', '').strip()
        lista_datos = json.loads(texto_limpio)
        
        gestionar_etiqueta_y_guardar(lista_datos)
        
        resumen = "✅ **¡Registrado y vinculado con éxito en la nube!**\n\n"
        for item in lista_datos:
            tipo_icono = "📅 Evento" if item.get("tipo") == "evento" else "✅ Tarea"
            titulo_item = item.get('titulo', '')
            ramo_item = item.get('ramo', 'Personal')
            resumen += f"• {tipo_icono}: **{titulo_item}** ({ramo_item})\n"
            
        await mensaje_espera.edit_text(resumen, parse_mode='Markdown')
        
    except Exception as e:
        await mensaje_espera.edit_text(f"❌ Error al procesar: {e}")

if __name__ == '__main__':
    print("Iniciando bot inteligente con soporte de 3 pestañas... Presiona Ctrl+C para detener.")
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), procesar_mensaje))
    app.run_polling()