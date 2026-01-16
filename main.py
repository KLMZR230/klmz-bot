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
MODELO_CODIGO_GEMINI = 'gemini-2.0-flash-exp'
ADMIN_ID = None 

# Regex para detectar emails en el texto
EMAIL_REGEX = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'

# Inicializar clientes
try:
    groq_client = Groq(api_key=GROQ_API_KEY)
    genai.configure(api_key=GEMINI_API_KEY)
    supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
except Exception as e:
    print(f"⚠️ Error Clientes: {e}")

# ==========================================
# 🌐 SERVIDOR FLASK
# ==========================================
app_flask = Flask('')

@app_flask.route('/')
def home():
    return "<h1>KLMZ IA - Smart Admin 🧠</h1>"

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
# 🤖 CHAT INTELIGENTE (AQUÍ ESTÁ LA MAGIA)
# ==========================================
async def procesar_mensaje(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_txt = update.message.text
    if not user_txt: return
    
    user_id = update.effective_user.id
    
    # --- LÓGICA DE JEFE (Solo si eres Admin) ---
    if user_id == ADMIN_ID:
        # Buscamos si hay un email en el mensaje
        email_match = re.search(EMAIL_REGEX, user_txt)
        
        if email_match:
            email = email_match.group(0)
            txt_lower = user_txt.lower()
            
            # --- CASO 1: BORRAR ---
            if any(palabra in txt_lower for palabra in ["borrar", "eliminar", "quita", "borra", "mata"]):
                await update.message.reply_text(f"🗑️ Entendido. Buscando a `{email}` para borrarlo...", parse_mode="Markdown")
                try:
                    users = supabase.auth.admin.list_users()
                    uid = next((u.id for u in users if u.email == email), None)
                    
                    if uid:
                        supabase.auth.admin.delete_user(uid)
                        await update.message.reply_text(f"✅ Listo. El usuario `{email}` ha sido eliminado.", parse_mode="Markdown")
                    else:
                        await update.message.reply_text(f"❌ No encontré a nadie con el correo `{email}`.")
                except Exception as e:
                    await update.message.reply_text(f"❌ Error técnico borrando: {e}")
                return # IMPORTANTE: Detenemos aquí para que Groq no conteste

            # --- CASO 2: CREAR ---
            elif any(palabra in txt_lower for palabra in ["crear", "agrega", "nuevo", "registra", "mete"]):
                # Intentamos adivinar la contraseña (la palabra después del email)
                palabras = user_txt.split()
                try:
                    # Buscamos en qué posición está el email
                    idx = -1
                    for i, p in enumerate(palabras):
                        if email in p:
                            idx = i
                            break
                    
                    # Si hay una palabra después del email, esa es la clave
                    if idx != -1 and idx + 1 < len(palabras):
                        password = palabras[idx+1]
                        
                        user = supabase.auth.admin.create_user({
                            "email": email,
                            "password": password,
                            "email_confirm": True
                        })
                        await update.message.reply_text(f"✅ **Hecho.** Usuario creado:\n👤 `{email}`\n🔑 Clave: `{password}`", parse_mode="Markdown")
                    else:
                        await update.message.reply_text("⚠️ Entendí que quieres crear un usuario, pero me falta la contraseña.\nEscribe: `crear email contraseña`", parse_mode="Markdown")
                except Exception as e:
                    await update.message.reply_text(f"❌ Error al crear (¿Quizás ya existe?): {e}")
                return # Detenemos aquí

    # --- CHAT NORMAL (Groq) ---
    # Si no era una orden de admin, conversamos normal
    try:
        chat = groq_client.chat.completions.create(
            messages=[
                {"role": "system", "content": "Eres KLMZ IA, un asistente leal y eficiente. Respondes breve y directo."},
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
    await update.message.reply_text("🫡 **A sus órdenes, Jefe.**\n\nPuedes pedirme:\n- \"Borra a tal@gmail.com\"\n- \"Crea a nuevo@gmail.com 123456\"\n- O simplemente charlar.")

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
