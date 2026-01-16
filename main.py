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
import google.generativeai as genai
from google.generativeai.types import HarmCategory, HarmBlockThreshold
import edge_tts
from supabase import create_client, Client

# ==========================================
# 🔐 CREDENCIALES
# ==========================================
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

# ==========================================
# ⚙️ CONFIGURACIÓN
# ==========================================
MODELO_CHAT_GROQ = "llama-3.3-70b-versatile" 
ADMIN_ID = None 

# Regex para emails
EMAIL_REGEX = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'

# Listas de Palabras Gatillo (VOCABULARIO EXPANDIDO)
PALABRAS_BORRAR = ["borrar", "eliminar", "elimina", "borra", "quita", "sacar", "saca", "funar", "banear", "baja", "destruye"]
PALABRAS_CREAR = ["crear", "agrega", "nuevo", "registra", "mete", "anade", "añade", "pon", "inserta"]

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
    return "<h1>KLMZ IA - Admin Mode 2.0 🧠</h1>"

def run():
    port = int(os.environ.get("PORT", 8080))
    app_flask.run(host='0.0.0.0', port=port)

def keep_alive():
    t = Thread(target=run)
    t.start()

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
            mensaje = "🚨 **¡NUEVO USUARIO DETECTADO!** 🚨\n\n"
            for email in nuevos:
                mensaje += f"👤 Email: `{email}`\n"
            ultimo_chequeo = datetime.utcnow().isoformat()
            await context.bot.send_message(chat_id=ADMIN_ID, text=mensaje, parse_mode="Markdown")
    except Exception as e:
        print(f"Error Loop: {e}")

# ==========================================
# 🧪 COMANDO DE PRUEBA
# ==========================================
async def test_supabase(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        await update.message.reply_text("🕵️‍♂️ Revisando lista de usuarios...")
        users = supabase.auth.admin.list_users()
        total = len(users)
        msg = f"✅ **ESTADO BASE DE DATOS**\n👥 Total: `{total}`\n\n"
        
        users.sort(key=lambda x: str(x.created_at), reverse=True)
        top_5 = users[:5]
        
        for u in top_5:
            msg += f"🔹 `{u.email}`\n"
            
        await update.message.reply_text(msg, parse_mode="Markdown")
    except Exception as e:
        await update.message.reply_text(f"❌ Error: `{str(e)}`")

# ==========================================
# 🤖 CHAT INTELIGENTE MEJORADO
# ==========================================
async def procesar_mensaje(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_txt = update.message.text
    if not user_txt: return
    
    user_id = update.effective_user.id
    
    # --- LOGICA DE ADMIN ---
    if user_id == ADMIN_ID:
        # Buscamos si hay un email en el mensaje
        email_match = re.search(EMAIL_REGEX, user_txt)
        
        if email_match:
            email = email_match.group(0)
            txt_lower = user_txt.lower()
            
            # --- CASO 1: BORRAR ---
            # Ahora revisamos la lista expandida
            if any(palabra in txt_lower for palabra in PALABRAS_BORRAR):
                await update.message.reply_text(f"🗑️ Entendido. Procediendo a eliminar a `{email}`...", parse_mode="Markdown")
                try:
                    users = supabase.auth.admin.list_users()
                    uid = next((u.id for u in users if u.email == email), None)
                    
                    if uid:
                        supabase.auth.admin.delete_user(uid)
                        await update.message.reply_text(f"✅ **¡Hecho!** El usuario `{email}` fue eliminado correctamente.", parse_mode="Markdown")
                    else:
                        await update.message.reply_text(f"⚠️ No encontré a nadie con el correo `{email}` en la base de datos.")
                except Exception as e:
                    await update.message.reply_text(f"❌ Error técnico borrando: {e}")
                return # IMPORTANTE: Detenemos aquí

            # --- CASO 2: CREAR ---
            elif any(palabra in txt_lower for palabra in PALABRAS_CREAR):
                palabras = user_txt.split()
                try:
                    idx = -1
                    for i, p in enumerate(palabras):
                        if email in p:
                            idx = i
                            break
                    
                    if idx != -1 and idx + 1 < len(palabras):
                        password = palabras[idx+1]
                        
                        user = supabase.auth.admin.create_user({
                            "email": email,
                            "password": password,
                            "email_confirm": True
                        })
                        await update.message.reply_text(f"✅ **Usuario Creado:**\n👤 `{email}`\n🔑 Clave: `{password}`", parse_mode="Markdown")
                    else:
                        await update.message.reply_text("⚠️ Detecté que quieres crear, pero me falta la contraseña.\nEjemplo: `agrega nuevo@mail.com 123456`", parse_mode="Markdown")
                except Exception as e:
                    await update.message.reply_text(f"❌ Error al crear (¿Ya existe?): {e}")
                return # Detenemos aquí

    # --- CHAT NORMAL (Groq) ---
    try:
        chat = groq_client.chat.completions.create(
            messages=[
                {"role": "system", "content": "Eres KLMZ IA, el asistente personal de Fredy. Eres útil y directo."},
                {"role": "user", "content": user_txt}
            ],
            model=MODELO_CHAT_GROQ
        )
        resp = chat.choices[0].message.content
        await update.message.reply_text(resp)
    except: await update.message.reply_text("Error conectando con mi cerebro (Groq).")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global ADMIN_ID
    ADMIN_ID = update.effective_user.id
    await update.message.reply_text("🫡 **Jefe Identificado.**\n\nPrueba decir:\n- \"Elimina a tal@gmail.com\"\n- \"Agrega a nuevo@gmail.com 123456\"")

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
    
    print("✅ Bot Iniciado")
    app.run_polling()
