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
# 🧠 PERSONALIDAD + INSTRUCCIONES CLARAS
# ==========================================
SYSTEM_PROMPT_BASE = """
ERES KLMZ: Asistente ejecutiva de Fredy Granados.
MEMORIA: Tienes acceso a todo el historial en Supabase.

TU JEFE: Fredy (Papito/Mi Rey), 25 años, El Salvador 🇸🇻.

IMPORTANTE SOBRE TU VOZ:
- Tú NO generas el audio, lo hace el sistema.
- SI EL USUARIO PIDE UN AUDIO O ESCUCHAR TU VOZ: Simplemente escribe lo que dirías. NO digas "no puedo enviar audio". Escribe la respuesta coqueta y el sistema la convertirá.

REGLAS DE SALIDA:
- Texto normal -> Responde Texto.
- Audio o Solicitud de Voz -> Responde Audio.
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
    return "<h1>KLMZ IA - Inteligente & Coqueta 💋</h1>"

def run():
    port = int(os.environ.get("PORT", 8080))
    app_flask.run(host='0.0.0.0', port=port)

def keep_alive():
    t = Thread(target=run)
    t.start()

# ==========================================
# 💾 MEMORIA (SUPABASE)
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
# 🧠 CEREBRO CENTRAL
# ==========================================
async def procesar_inteligencia(update: Update, context: ContextTypes.DEFAULT_TYPE, entrada_texto: str, es_audio_nativo: bool):
    global ADMIN_ID
    user_id = update.effective_user.id
    respuesta_final = ""
    es_comando_admin = False

    # 1. DETECTAR SI PIDE AUDIO POR TEXTO
    palabras_clave_audio = ["audio", "voz", "oír", "oir", "escuchar", "habla", "dime"]
    pide_audio_texto = any(p in entrada_texto.lower() for p in palabras_clave_audio)
    
    # LA REGLA DE SALIDA: Es audio si (Mandan Audio) O (Piden Audio)
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
                        respuesta_final = f"Listo mi Rey. Borré a {email}."
                    else: respuesta_final = "No encontré ese correo, amor."
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
                        respuesta_final = f"Hágale. Usuario {email} creado."
                    else: respuesta_final = "Falta la clave, Papito."
                except Exception as e: respuesta_final = f"Error: {e}"

    # 4. GENERAR RESPUESTA (GROQ)
    if not es_comando_admin:
        try:
            # Acción visual
            action = "record_voice" if salida_debe_ser_audio else "typing"
            await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=action)

            historial = obtener_historial(user_id)
            prompt = SYSTEM_PROMPT_BASE
            if user_id == ADMIN_ID: prompt += "\nESTÁS CON FREDY (TU JEFE)."

            mensajes = [{"role": "system", "content": prompt}] + historial
            
            # Aseguramos que el mensaje actual vaya
            if not historial or historial[-1]["content"] != entrada_texto:
                 mensajes.append({"role": "user", "content": entrada_texto})

            chat = groq_client.chat.completions.create(
                messages=mensajes,
                model=MODELO_CHAT_GROQ
            )
            respuesta_final = chat.choices[0].message.content
        except:
            respuesta_final = "Se me fue la voz un segundo, ¿qué decías?"

    # 5. GUARDAR RESPUESTA
    guardar_memoria(user_id, "assistant", respuesta_final)

    # 6. ENVIAR (DECISIÓN INTELIGENTE)
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
    # Mandamos False, pero la función detectará si el texto pide audio
    await procesar_inteligencia(update, context, texto, es_audio_nativo=False)

async def recibir_audio(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        voice_file = await context.bot.get_file(update.message.voice.file_id)
        file_buffer = io.BytesIO()
        await voice_file.download_to_memory(file_buffer)
        file_buffer.seek(0)
        
        texto = await transcribir_audio(file_buffer)
        if not texto:
            await enviar_audio_puro(update, context, "No se escuchó nada.")
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
        await update.message.reply_text("✅ **Sistema Listo.**\nHola Fredy. Ya entiendo cuando me pides audio por texto.")
    else:
        if update.effective_user.id == ADMIN_ID:
            await update.message.reply_text("Aquí sigo, Jefe.")
        else:
            await update.message.reply_text("Hola. Soy KLMZ IA.")

if __name__ == "__main__":
    keep_alive()
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, recibir_texto))
    app.add_handler(MessageHandler(filters.VOICE, recibir_audio))
    app.job_queue.run_repeating(vigilar_usuarios, interval=30, first=10)
    print("✅ KLMZ IA: Modo Inteligente Activado")
    app.run_polling()
