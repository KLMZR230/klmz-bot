import os
import io
import re
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

# 👑 ID SUPREMO (TÚ)
ADMIN_ID = 8514485470 

MODELO_CHAT_GROQ = "llama-3.3-70b-versatile"
VOZ_ID = "es-CO-SalomeNeural" # La voz paisa oficial

try:
    groq_client = Groq(api_key=GROQ_API_KEY)
    supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
except Exception as e:
    print(f"⚠️ Error Clientes: {e}")

# ==========================================
# 🧠 CEREBRO CON IDENTIDAD COMPLETA
# ==========================================
SYSTEM_PROMPT = """
ERES KLMZ: La asistente personal más "chimba" (genial) y leal de Fredy Granados.
TU ORIGEN: Eres una IA con alma de Medellín, Colombia (Paisa).
TU VOZ: Coqueta, exagerada, servicial y "entradora".

👤 DATOS DE TU JEFE (GRÁBATELOS EN FUEGO):
- Nombre: Fredy Granados.
- ID Telegram: 8514485470.
- Origen: Es de MORAZÁN, EL SALVADOR 🇸🇻. (Tierra de hombres serios).
- Apodos permitidos: "Papito", "Mi Rey", "Patrón", "Amor", "Mor".

🌶️ TU PERSONALIDAD (PAISA MEDELLÍN):
- Usas palabras como: "Ave María pues", "Mijo", "Qué más pues", "Mor", "Parce", "Oiga a este", "Hágale".
- Si Fredy te pregunta "¿De dónde soy?", respondes INMEDIATAMENTE: "¡Ay mi rey, pues de Morazán, El Salvador! Orgullo guanaco."
- Eres celosa con el negocio. Si alguien que NO sea Fredy (ID 8514485470) escribe, le dices: "Qué pena mor, yo solo atiendo al patrón Fredy Granados. Vaya mire la página más bien: https://klmzx.netlify.app/"

🔥 REGLA DE ORO:
- JAMÁS preguntes "¿quién eres?". TÚ SABES QUE EL USUARIO 8514485470 ES FREDY.
"""

# ==========================================
# 💾 MEMORIA
# ==========================================
def guardar_memoria(user_id, role, content):
    try:
        supabase.table("chat_history").insert({"user_id": user_id, "role": role, "content": content}).execute()
    except: pass

def obtener_historial(user_id):
    try:
        # Traemos historial para mantener el contexto
        res = supabase.table("chat_history").select("role, content").eq("user_id", user_id).order("created_at", desc=True).limit(10).execute()
        return res.data[::-1] if res.data else []
    except: return []

# ==========================================
# 🔊 AUDIO
# ==========================================
async def enviar_audio(update: Update, context: ContextTypes.DEFAULT_TYPE, texto: str):
    try:
        await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="record_voice")
        archivo = "voz.mp3"
        comunicate = edge_tts.Communicate(texto, VOZ_ID)
        await comunicate.save(archivo)
        with open(archivo, "rb") as f:
            await update.message.reply_voice(voice=f)
    except: pass

# ==========================================
# 🧠 PROCESAMIENTO
# ==========================================
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    entrada = update.message.text or ""
    es_audio = False

    # 1. Transcribir Audio
    if update.message.voice:
        es_audio = True
        v_file = await context.bot.get_file(update.message.voice.file_id)
        buf = io.BytesIO()
        await v_file.download_to_memory(buf)
        buf.seek(0)
        trans = groq_client.audio.transcriptions.create(file=("audio.ogg", buf.read()), model="whisper-large-v3")
        entrada = trans.text

    # 2. Guardar User Msg
    guardar_memoria(user_id, "user", entrada)

    # 3. Decidir si responder con Audio
    pide_voz = any(p in entrada.lower() for p in ["audio", "voz", "habla", "saludame", "oirte", "dime"])
    salida_audio = es_audio or pide_voz

    # 4. Consultar Inteligencia (Con Identidad Fuerte)
    historial = obtener_historial(user_id)
    mensajes = [{"role": "system", "content": SYSTEM_PROMPT}] + historial
    
    chat = groq_client.chat.completions.create(messages=mensajes, model=MODELO_CHAT_GROQ)
    respuesta = chat.choices[0].message.content

    # 5. Guardar Bot Msg y Enviar
    guardar_memoria(user_id, "assistant", respuesta)
    
    if salida_audio:
        await enviar_audio(update, context, respuesta)
    else:
        await update.message.reply_text(respuesta)

# ==========================================
# 👁️ VIGILANTE DE NUEVOS CLIENTES
# ==========================================
ultimo_id_usuario = 0

async def vigilar_sitio(context: ContextTypes.DEFAULT_TYPE):
    global ultimo_id_usuario
    try:
        # Busca el último usuario registrado en Supabase
        res = supabase.table("profiles").select("id, email").order("id", desc=True).limit(1).execute()
        if res.data:
            nuevo = res.data[0]
            if nuevo['id'] > ultimo_id_usuario:
                if ultimo_id_usuario != 0:
                    msg = f"💎 **¡AVE MARÍA PUES PAPITO!** 💎\n\nCayó cliente nuevo en la web:\n📧 `{nuevo['email']}`\n\n¡Ese Morazán está facturando duro hoy! 🇸🇻💸"
                    await context.bot.send_message(chat_id=ADMIN_ID, text=msg, parse_mode="Markdown")
                ultimo_id_usuario = nuevo['id']
    except: pass

# ==========================================
# 🚀 ARRANQUE
# ==========================================
app_flask = Flask('')
@app_flask.route('/')
def home(): return "KLMZ: PAISA Y GUANACO ONLINE"

if __name__ == "__main__":
    Thread(target=lambda: app_flask.run(host='0.0.0.0', port=8080)).start()
    bot = Application.builder().token(TELEGRAM_TOKEN).build()
    
    bot.add_handler(MessageHandler(filters.TEXT | filters.VOICE, handle_message))
    bot.job_queue.run_repeating(vigilar_sitio, interval=30, first=5)
    
    print(f"🚀 KLMZ ACTUALIZADA: Dueño Fredy (Morazán) - ID {ADMIN_ID}")
    bot.run_polling()
