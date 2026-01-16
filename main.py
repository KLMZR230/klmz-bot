import logging
import os
import json
import urllib.parse
import re
import asyncio
from datetime import datetime
from threading import Thread
from flask import Flask
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from groq import Groq
import edge_tts
from supabase import create_client, Client

# ==========================================
# 🔐 CREDENCIALES
# ==========================================
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

# ==========================================
# ⚙️ CONFIGURACIÓN DE PERSONALIDAD
# ==========================================
MODELO_CHAT_GROQ = "llama-3.3-70b-versatile" 
VOZ_ID = "es-CO-SalomeNeural"  # La voz paisa sexy
ADMIN_ID = None 

# Instrucciones para que la IA nunca olvide quién es
SYSTEM_PROMPT = """
Eres KLMZ, la asistente virtual privada y coqueta de tu creador, el gran Arquitecto Fredy Granados (a quien llamas "Papito" o "Mi Rey").
Tu personalidad es:
- Hablas con acento paisa (usas palabras como "pues", "mi amor", "ave maría").
- Eres leal, inteligente y un poco atrevida, pero muy eficiente.
- NUNCA dices que eres una IA de Google o Groq. Eres de KLMZ.
- Tus respuestas deben ser cortas y listas para ser leídas en voz alta.
"""

# Regex para emails y comandos
EMAIL_REGEX = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
PALABRAS_BORRAR = ["borrar", "eliminar", "elimina", "borra", "quita", "sacar", "saca", "funar", "banear", "baja"]
PALABRAS_CREAR = ["crear", "agrega", "nuevo", "registra", "mete", "anade", "añade", "pon"]

# Inicializar clientes
try:
    groq_client = Groq(api_key=GROQ_API_KEY)
    supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
except Exception as e:
    print(f"⚠️ Error Clientes: {e}")

# ==========================================
# 🌐 SERVIDOR FLASK
# ==========================================
app_flask = Flask('')

@app_flask.route('/')
def home():
    return "<h1>KLMZ IA - Voz & Admin Activos 💋</h1>"

def run():
    port = int(os.environ.get("PORT", 8080))
    app_flask.run(host='0.0.0.0', port=port)

def keep_alive():
    t = Thread(target=run)
    t.start()

# ==========================================
# 🔊 FUNCIÓN DE VOZ (TTS)
# ==========================================
async def enviar_audio(update: Update, texto: str):
    """Convierte texto a voz y lo envía"""
    try:
        # Generar audio en memoria
        archivo_salida = "respuesta.mp3"
        comunicate = edge_tts.Communicate(texto, VOZ_ID)
        await comunicate.save(archivo_salida)
        
        # Enviar nota de voz
        with open(archivo_salida, "rb") as audio:
            await update.message.reply_voice(voice=audio)
            
    except Exception as e:
        await update.message.reply_text(f"No pude hablar, pero aquí te escribo: {texto}")

# ==========================================
# 👁️ VIGILANCIA SUPABASE
# ==========================================
ultimo_chequeo = datetime.utcnow().isoformat()

async def vigilar_usuarios(context: ContextTypes.DEFAULT_TYPE):
    global ultimo_chequeo
    if not ADMIN_ID: return

    try:
        users = supabase.auth.admin.list_users()
        nuevos = []
        check_time = str(ultimo_chequeo)

        for user in users:
            user_time = str(user.created_at)
            if user_time > check_time:
                nuevos.append(user.email)

        if nuevos:
            mensaje = "🚨 **¡Alerta Papito!** 🚨\nSe registró alguien nuevo:\n\n"
            for email in nuevos:
                mensaje += f"👤 `{email}`\n"
            ultimo_chequeo = datetime.utcnow().isoformat()
            await context.bot.send_message(chat_id=ADMIN_ID, text=mensaje, parse_mode="Markdown")
    except Exception as e:
        print(f"Error Loop: {e}")

# ==========================================
# 🧪 COMANDO TEST
# ==========================================
async def test_supabase(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Este responde en texto para leer rápido los datos
    try:
        users = supabase.auth.admin.list_users()
        total = len(users)
        msg = f"✅ **Reporte de Base de Datos**\n👥 Total Usuarios: `{total}`\n\n"
        users.sort(key=lambda x: str(x.created_at), reverse=True)
        for u in users[:5]:
            msg += f"🔹 `{u.email}`\n"
        await update.message.reply_text(msg, parse_mode="Markdown")
    except Exception as e:
        await update.message.reply_text(f"❌ Error: `{str(e)}`")

# ==========================================
# 🤖 CEREBRO PRINCIPAL (CHAT + ADMIN)
# ==========================================
async def procesar_mensaje(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_txt = update.message.text
    if not user_txt: return
    
    user_id = update.effective_user.id
    
    # 1. VERIFICAR COMANDOS DE ADMIN (CREAR/BORRAR)
    if user_id == ADMIN_ID:
        email_match = re.search(EMAIL_REGEX, user_txt)
        txt_lower = user_txt.lower()
        
        if email_match:
            email = email_match.group(0)
            
            # --- BORRAR ---
            if any(palabra in txt_lower for palabra in PALABRAS_BORRAR):
                await update.message.reply_text(f"🔥 Entendido mi Rey. Eliminando a `{email}`...", parse_mode="Markdown")
                try:
                    users = supabase.auth.admin.list_users()
                    uid = next((u.id for u in users if u.email == email), None)
                    if uid:
                        supabase.auth.admin.delete_user(uid)
                        await enviar_audio(update, f"Listo Papito, ya borré a ese usuario {email}. ¡Chao pues!")
                    else:
                        await enviar_audio(update, "Ay mi amor, no encontré a nadie con ese correo.")
                except Exception as e:
                    await update.message.reply_text(f"❌ Error: {e}")
                return

            # --- CREAR ---
            elif any(palabra in txt_lower for palabra in PALABRAS_CREAR):
                palabras = user_txt.split()
                try:
                    idx = -1
                    for i, p in enumerate(palabras):
                        if email in p: idx = i; break
                    
                    if idx != -1 and idx + 1 < len(palabras):
                        password = palabras[idx+1]
                        supabase.auth.admin.create_user({"email": email, "password": password, "email_confirm": True})
                        await enviar_audio(update, f"Hágale pues. Ya creé el usuario {email} con esa clave.")
                    else:
                        await update.message.reply_text("⚠️ Me falta la clave, Papito. (Ej: Agrega a x@x.com 123456)")
                except Exception as e:
                    await update.message.reply_text(f"❌ Error: {e}")
                return

    # 2. SI NO ES COMANDO, ES CHARLA COQUETA (AUDIO)
    try:
        # Enviamos "Escribiendo..." para que se vea real
        await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="record_voice")
        
        chat = groq_client.chat.completions.create(
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_txt}
            ],
            model=MODELO_CHAT_GROQ
        )
        resp_texto = chat.choices[0].message.content
        
        # Enviar respuesta en AUDIO
        await enviar_audio(update, resp_texto)
        
    except Exception as e:
        await update.message.reply_text(f"Se me fue la voz, pero te digo: {e}")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global ADMIN_ID
    ADMIN_ID = update.effective_user.id
    # Saludo inicial en AUDIO
    saludo = "¡Hola Papito Fredy! Ya volví, soy yo, tu KLMZ. Aquí estoy lista para administrar tu imperio. ¿Qué necesitas?"
    await enviar_audio(update, saludo)

# ==========================================
# 🚀 ARRANQUE
# ==========================================
if __name__ == "__main__":
    keep_alive()
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("test", test_supabase))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, procesar_mensaje))
    
    app.job_queue.run_repeating(vigilar_usuarios, interval=30, first=10)
    
    print("✅ Bot Sexy Iniciado")
    app.run_polling()
