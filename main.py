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

# Clientes
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
    return "<h1>KLMZ IA - Diagnóstico Activo 🚑</h1>"

def run():
    port = int(os.environ.get("PORT", 8080))
    app_flask.run(host='0.0.0.0', port=port)

def keep_alive():
    t = Thread(target=run)
    t.start()

# ==========================================
# 👁️ VIGILANCIA SUPABASE (Modo Debug)
# ==========================================
# Guardamos la fecha de arranque
ultimo_chequeo = datetime.utcnow().isoformat()

async def vigilar_usuarios(context: ContextTypes.DEFAULT_TYPE):
    global ultimo_chequeo
    if not ADMIN_ID: return

    try:
        # 1. Obtener usuarios (Intenta ordenar por fecha si es posible, o trae todos)
        response = supabase.auth.admin.list_users()
        users = response.users
        
        # 2. Filtrar nuevos
        nuevos = []
        
        # Convertimos ultimo_chequeo a string simple para comparar
        check_time = str(ultimo_chequeo)

        for user in users:
            # Truco: Convertimos todo a string para evitar errores de formato
            user_time = str(user.created_at)
            
            # Si el usuario se creó DESPUÉS de que prendimos el bot
            if user_time > check_time:
                nuevos.append(user.email)

        if nuevos:
            mensaje = "🚨 **¡NUEVO USUARIO DETECTADO!** 🚨\n\n"
            for email in nuevos:
                mensaje += f"👤 Email: `{email}`\n"
            
            # Actualizamos el reloj al AHORA
            ultimo_chequeo = datetime.utcnow().isoformat()
            
            await context.bot.send_message(chat_id=ADMIN_ID, text=mensaje, parse_mode="Markdown")

    except Exception as e:
        # Si falla, ¡AVISA AL CHAT PARA QUE SEPAMOS QUÉ ES!
        print(f"Error Loop: {e}")

# ==========================================
# 🧪 COMANDO DE PRUEBA (NUEVO)
# ==========================================
async def test_supabase(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando para ver qué carajos está pasando en la BD"""
    try:
        await update.message.reply_text("🕵️‍♂️ Revisando conexión a Supabase...")
        
        response = supabase.auth.admin.list_users()
        users = response.users
        total = len(users)
        
        if total > 0:
            ultimo_user = users[-1] # El último de la lista (o el primero dependiendo del orden)
            # A veces la lista viene desordenada, busquemos el más reciente manualmente
            users.sort(key=lambda x: x.created_at, reverse=True)
            mas_reciente = users[0]
            
            msg = (
                f"✅ **Conexión Exitosa**\n"
                f"👥 Total Usuarios: `{total}`\n"
                f"🆕 Más reciente: `{mas_reciente.email}`\n"
                f"📅 Creado: `{mas_reciente.created_at}`\n"
                f"⏱️ Mi reloj interno: `{ultimo_chequeo}`"
            )
        else:
            msg = "✅ Conexión Exitosa, pero **NO hay usuarios** (Lista vacía)."
            
        await update.message.reply_text(msg, parse_mode="Markdown")
        
    except Exception as e:
        await update.message.reply_text(f"❌ **ERROR FATAL:**\n`{str(e)}`", parse_mode="Markdown")

# ==========================================
# 🤖 CHAT BÁSICO
# ==========================================
async def procesar_mensaje(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Lógica simple para responder mientras probamos
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
    except Exception as e:
        await update.message.reply_text(f"Error Groq: {e}")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global ADMIN_ID
    ADMIN_ID = update.effective_user.id
    await update.message.reply_text("🤖 **Vigilante Reiniciado.**\nUsa `/test` para verificar Supabase.")

# ==========================================
# 🚀 ARRANQUE
# ==========================================
if __name__ == "__main__":
    keep_alive()
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("test", test_supabase)) # <--- COMANDO NUEVO
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, procesar_mensaje))
    
    # Vigilancia cada 30 seg
    app.job_queue.run_repeating(vigilar_usuarios, interval=30, first=10)
    
    print("✅ Bot Iniciado")
    app.run_polling()
