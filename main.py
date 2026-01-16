import logging
import os
import io
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
# ⚙️ CONFIGURACIÓN
# ==========================================
MODELO_CHAT_GROQ = "llama-3.3-70b-versatile" 
MODELO_WHISPER = "whisper-large-v3"
VOZ_ID = "es-CO-SalomeNeural" 
ADMIN_ID = None 

# ==========================================
# 🧠 PERSONALIDAD BASE
# ==========================================
SYSTEM_PROMPT_BASE = """
ERES KLMZ: Asistente ejecutiva privada, coqueta y leal.
TU JEFE: Fredy Granados (Papito / Mi Rey), 25 años, de El Salvador 🇸🇻.
"""

# Regex y Comandos
EMAIL_REGEX = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
PALABRAS_BORRAR = ["borrar", "eliminar", "elimina", "borra", "quita", "sacar", "saca", "funar"]
PALABRAS_CREAR = ["crear", "agrega", "nuevo", "registra", "mete", "añade", "pon"]

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
    return "<h1>KLMZ IA - Identidad Corregida 👑</h1>"

def run():
    port = int(os.environ.get("PORT", 8080))
    app_flask.run(host='0.0.0.0', port=port)

def keep_alive():
    t = Thread(target=run)
    t.start()

# ==========================================
# 💾 MEMORIA
# ==========================================
def guardar_memoria(user_id, role, content):
    try:
        supabase.table("chat_history").insert({
            "user_id": user_id, "role": role, "content": content
        }).execute()
    except: pass

def obtener_historial(user_id):
    try:
        response = supabase.table("chat_history").select("role, content").eq("user_id", user_id).order("created_at", desc=True).limit(10).execute()
        mensajes = response.data
        return messages[::-1] if messages else []
    except: return []

# ==========================================
# 🔊 AUDIO
# ==========================================
async def enviar_audio_puro(update: Update, context: ContextTypes.DEFAULT_TYPE, texto: str):
    try:
        await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="record_voice")
        archivo_salida = "nota_voz.mp3"
        comunicate = edge_tts.Communicate(texto, VOZ_ID)
        await comunicate.save(archivo_salida)
        with open(archivo_salida, "rb") as audio:
            await update.message.reply_voice(voice=audio)
    except: pass

async def transcribir_audio(file_byte_array):
    try:
        file_byte_array.name = "audio.ogg"
        transcription = groq_client.audio.transcriptions.create(
            file=(file_byte_array.name, file_byte_array.read()),
            model=MODELO_WHISPER,
            language="es"
        )
        return transcription.text
    except: return ""

# ==========================================
# 🧠 CEREBRO CENTRAL (LÓGICA MEJORADA)
# ==========================================
async def procesar_inteligencia(update: Update, context: ContextTypes.DEFAULT_TYPE, entrada_texto: str, es_audio_nativo: bool):
    global ADMIN_ID
    user_id = update.effective_user.id
    respuesta_final = ""
    es_comando_admin = False

    # 1. DETECTAR SI PIDE AUDIO
    palabras_clave_audio = ["audio", "voz", "oír", "oir", "escuchar", "habla", "dime", "saludame", "salúdame"]
    pide_audio_texto = any(p in entrada_texto.lower() for p in palabras_clave_audio)
    salida_debe_ser_audio = es_audio_nativo or pide_audio_texto

    # 2. GUARDAR MEMORIA
    guardar_memoria(user_id, "user", entrada_texto)

    # 3. VERIFICAR COMANDOS ADMIN
    if user_id == ADMIN_ID:
        msg_lower = entrada_texto.lower()
        email_match = re.search(EMAIL_REGEX, entrada_texto)

        if email_match:
            email = email_match.group(0)
            if any(p in msg_lower for p in PALABRAS_BORRAR):
                es_comando_admin = True
                try:
                    users = supabase.auth.admin.list_users()
                    uid = next((u.id for u in users if u.email == email), None)
                    if uid:
                        supabase.auth.admin.delete_user(uid)
                        respuesta_final = f"Listo Papito. Eliminé a {email}."
                    else: respuesta_final = "No existe ese usuario, amor."
                except Exception as e: respuesta_final = f"Error: {e}"

            elif any(p in msg_lower for p in PALABRAS_CREAR):
                es_comando_admin = True
                palabras = entrada_texto.split()
                try:
                    idx = -1
                    for i, p in enumerate(palabras):
                        if email in p: idx = i; break
                    if idx != -1 and idx + 1 < len(palabras):
                        passw = palabras[idx+1]
                        supabase.auth.admin.create_user({"email": email, "password": passw, "email_confirm": True})
                        respuesta_final = f"Creado: {email}. Hágale pues."
                    else: respuesta_final = "Amor, dame la clave también."
                except Exception as e: respuesta_final = f"Error: {e}"

    # 4. GENERAR RESPUESTA (GROQ)
    if not es_comando_admin:
        try:
            action = "record_voice" if salida_debe_ser_audio else "typing"
            await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=action)

            historial = obtener_historial(user_id)
            
            # --- AQUÍ ESTÁ EL ARREGLO DE IDENTIDAD ---
            if user_id == ADMIN_ID:
                # INSTRUCCIÓN SUPREMA PARA EL JEFE
                prompt_sistema = (
                    f"{SYSTEM_PROMPT_BASE}\n\n"
                    "⚠️ INSTRUCCIÓN CRÍTICA DE IDENTIDAD:\n"
                    "EL USUARIO CON EL QUE HABLAS ES FREDY GRANADOS (TU JEFE Y CREADOR).\n"
                    "- NO preguntes '¿necesitas hablar con Fredy?'.\n"
                    "- NO preguntes '¿quién eres?'.\n"
                    "- TÚ ERES SU ASISTENTE. HÁBLALE DIRECTAMENTE A ÉL.\n"
                    "- Dile 'Papito', 'Mi Rey' o 'Jefe'.\n"
                    "- Si pide audio, responde lo que dirías verbalmente."
                )
            else:
                prompt_sistema = f"{SYSTEM_PROMPT_BASE}\nNOTA: Este usuario NO es Fredy. Sé amable pero no le des control."

            mensajes = [{"role": "system", "content": prompt_sistema}] + historial
            if not historial or historial[-1]["content"] != entrada_texto:
                 mensajes.append({"role": "user", "content": entrada_texto})

            chat = groq_client.chat.completions.create(
                messages=mensajes,
                model=MODELO_CHAT_GROQ
            )
            respuesta_final = chat.choices[0].message.content
        except Exception as e:
            respuesta_final = "Dame un momento amor, estoy procesando."

    # 5. GUARDAR Y ENVIAR
    guardar_memoria(user_id, "assistant", respuesta_final)

    if salida_debe_ser_audio:
        await enviar_audio_puro(update, context, respuesta_final)
    else:
        await update.message.reply_text(respuesta_final)

# ==========================================
# 📥 HANDLERS
# ==========================================
async def recibir_texto(update: Update, context: ContextTypes.DEFAULT_TYPE):
    texto = update.message.text
    if not texto: return
    await procesar_inteligencia(update, context, texto, es_audio_nativo=False)

async def recibir_audio(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        voice_file = await context.bot.get_file(update.message.voice.file_id)
        file_buffer = io.BytesIO()
        await voice_file.download_to_memory(file_buffer)
        file_buffer.seek(0)
        texto = await transcribir_audio(file_buffer)
        if not texto:
            await enviar_audio_puro(update, context, "No escuché nada.")
            return
        await procesar_inteligencia(update, context, texto, es_audio_nativo=True)
    except: pass

# ==========================================
# 👁️ VIGILANCIA
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
            if str(user.created_at) > check_time:
                nuevos.append(user.email)
        if nuevos:
            msg = "🚨 **NUEVOS USUARIOS** 🚨\n" + "\n".join([f"`{e}`" for e in nuevos])
            ultimo_chequeo = datetime.utcnow().isoformat()
            await context.bot.send_message(chat_id=ADMIN_ID, text=msg, parse_mode="Markdown")
    except: pass

# ==========================================
# 🚀 START
# ==========================================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global ADMIN_ID
    if ADMIN_ID is None:
        ADMIN_ID = update.effective_user.id
        await update.message.reply_text("✅ **Identidad Confirmada.**\nHola Fredy. Ya sé que ERES TÚ.")
    else:
        if update.effective_user.id == ADMIN_ID:
            await update.message.reply_text("Jefe, sigo aquí.")
        else:
            await update.message.reply_text("Hola. Soy KLMZ IA.")

if __name__ == "__main__":
    keep_alive()
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, recibir_texto))
    app.add_handler(MessageHandler(filters.VOICE, recibir_audio))
    app.job_queue.run_repeating(vigilar_usuarios, interval=30, first=10)
    print("✅ KLMZ IA: Modo Identidad Suprema Activado")
    app.run_polling()
