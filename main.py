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
VOZ_ID = "es-CO-SalomeNeural" 
ARCHIVO_MEMORIA = "historial_chats.json"
ADMIN_ID = None 

# Inicializar clientes
try:
    groq_client = Groq(api_key=GROQ_API_KEY)
    genai.configure(api_key=GEMINI_API_KEY)
    supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
except Exception as e:
    print(f"⚠️ Error Clientes: {e}")

# Gemini Coder
safety_settings = {
    HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_NONE,
    HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_NONE,
    HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_NONE,
    HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_NONE,
}
gemini_coder = genai.GenerativeModel(
    model_name=MODELO_CODIGO_GEMINI,
    safety_settings=safety_settings,
    system_instruction="Eres un experto Ingeniero de Software Senior."
)

# ==========================================
# 🌐 SERVIDOR FLASK
# ==========================================
app_flask = Flask('')

@app_flask.route('/')
def home():
    return "<h1>KLMZ IA - Vigilante Activo 👁️</h1>"

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
        # CORRECCIÓN: La respuesta YA ES la lista
        users = supabase.auth.admin.list_users()
        
        nuevos = []
        check_time = str(ultimo_chequeo)

        for user in users:
            # Convertimos a string para comparar fácil
            user_time = str(user.created_at)
            
            if user_time > check_time:
                nuevos.append(user.email)

        if nuevos:
            mensaje = "🚨 **¡NUEVO USUARIO DETECTADO!** 🚨\n\n"
            for email in nuevos:
                mensaje += f"👤 Email: `{email}`\n"
            
            # Actualizamos el reloj
            ultimo_chequeo = datetime.utcnow().isoformat()
            
            await context.bot.send_message(chat_id=ADMIN_ID, text=mensaje, parse_mode="Markdown")

    except Exception as e:
        print(f"Error Loop: {e}")

# ==========================================
# 🧪 COMANDO DE PRUEBA
# ==========================================
async def test_supabase(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        await update.message.reply_text("🕵️‍♂️ Revisando conexión...")
        
        # CORRECCIÓN AQUÍ TAMBIÉN
        users = supabase.auth.admin.list_users()
        total = len(users)
        
        if total > 0:
            # Ordenamos para ver el último
            users.sort(key=lambda x: str(x.created_at), reverse=True)
            mas_reciente = users[0]
            
            msg = (
                f"✅ **CONEXIÓN EXITOSA**\n"
                f"👥 Total Usuarios: `{total}`\n"
                f"🆕 Último registrado: `{mas_reciente.email}`\n"
                f"📅 Fecha: `{mas_reciente.created_at}`"
            )
        else:
            msg = "✅ Conexión OK, pero lista vacía."
            
        await update.message.reply_text(msg, parse_mode="Markdown")
        
    except Exception as e:
        await update.message.reply_text(f"❌ Error: `{str(e)}`", parse_mode="Markdown")

# ==========================================
# 🤖 CHAT
# ==========================================
async def procesar_mensaje(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_txt = update.message.text
    if not user_txt: return
    try:
        chat = groq_client.chat.completions.create(
            messages=[
                {"role": "system", "content": "Eres un asistente útil."},
                {"role": "user", "content": user_txt}
            ],
            model=MODELO_CHAT_GROQ
        )
        resp = chat.choices[0].message.content
        await update.message.reply_text(resp)
    except: await update.message.reply_text("Error procesando mensaje.")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global ADMIN_ID
    ADMIN_ID = update.effective_user.id
    await update.message.reply_text("🤖 **Vigilante Listo.**\nUsa `/test` para ver si veo tus usuarios.")

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
