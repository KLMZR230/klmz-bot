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
# 🧠 PERSONALIDAD DEL SISTEMA
# ==========================================
SYSTEM_PROMPT_BASE = """
ERES KLMZ: Asistente ejecutiva de Fredy Granados.
MEMORIA: Tienes acceso a todo el historial de chat guardado en la base de datos. Úsalo para dar continuidad.

TU JEFE: Fredy (Papito/Mi Rey), 25 años (23 Julio 2000), Morazán, El Salvador 🇸🇻.

PODERES:
1. Crear/Borrar usuarios (Supabase).
2. Recordar conversaciones pasadas (Memoria Persistente).
3. Responder con Audio o Texto según te hablen.

REGLAS:
- Si te hablan en Texto -> Responde Texto.
- Si te hablan en Audio -> Responde Audio.
- NO preguntes "¿quién eres?" a Fredy.
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
    return "<h1>KLMZ IA - Memoria Eterna 🐘</h1>"

def run():
    port = int(os.environ.get("PORT", 8080))
    app_flask.run(host='0.0.0.0', port=port)

def keep_alive():
    t = Thread(target=run)
    t.start()

# ==========================================
# 💾 GESTIÓN DE MEMORIA (SUPABASE)
# ==========================================
def guardar_memoria(user_id, role, content):
    """Guarda un mensaje en la base de datos para siempre"""
    try:
        supabase.table("chat_history").insert({
            "user_id": user_id,
            "role": role,
            "content": content
        }).execute()
    except Exception as e:
        print(f"Error guardando memoria: {e}")

def obtener_historial(user_id):
    """Recupera los últimos 10 mensajes de la base de datos"""
    try:
        # Traemos los ultimos 10 mensajes ordenados por fecha
        response = supabase.table("chat_history")\
            .select("role, content")\
            .eq("user_id", user_id)\
            .order("created_at", desc=True)\
            .limit(10)\
            .execute()
        
        mensajes = response.data
        # Supabase los devuelve del más nuevo al más viejo, hay que invertirlos
        return messages[::-1] if messages else []
    except:
        return []

# ==========================================
# 🔊 AUDIO Y TRANSCRIPCIÓN
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
async def procesar_inteligencia(update: Update, context: ContextTypes.DEFAULT_TYPE, entrada_texto: str, es_audio: bool):
    global ADMIN_ID
    user_id = update.effective_user.id
    respuesta_final = ""
    es_comando_admin = False

    # 1. GUARDAR LO QUE DIJO EL USUARIO EN BD
    guardar_memoria(user_id, "user", entrada_texto)

    # 2. VERIFICAR COMANDOS ADMIN
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
                        respuesta_final = f"Listo Papito. Usuario {email} eliminado para siempre."
                    else: respuesta_final = "Amor, ese correo no existe."
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
                    else: respuesta_final = "Falta la clave, Jefe."
                except Exception as e: respuesta_final = f"Error: {e}"

    # 3. GENERAR RESPUESTA CON MEMORIA (GROQ)
    if not es_comando_admin:
        try:
            action = "record_voice" if es_audio else "typing"
            await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=action)

            # A. Recuperar historial de Supabase
            historial_previo = obtener_historial(user_id)
            
            # B. Preparar sistema
            prompt_actual = SYSTEM_PROMPT_BASE
            if user_id == ADMIN_ID:
                prompt_actual += "\nESTÁS HABLANDO CON FREDY (TU JEFE). RECUERDA TODO LO QUE HAN HABLADO."

            # C. Armar paquete de mensajes
            mensajes = [{"role": "system", "content": prompt_actual}] + historial_previo
            # (El mensaje actual ya está en historial_previo porque lo guardamos en el paso 1, 
            #  pero Groq a veces prefiere recibirlo explícito, aunque aquí confiaremos en el fetch)
            
            # Si el fetch no trajo el ultimo mensaje por latencia, lo agregamos manual:
            if not historial_previo or historial_previo[-1]["content"] != entrada_texto:
                 mensajes.append({"role": "user", "content": entrada_texto})

            chat = groq_client.chat.completions.create(
                messages=mensajes,
                model=MODELO_CHAT_GROQ
            )
            respuesta_final = chat.choices[0].message.content
        except Exception as e:
            respuesta_final = "Dame un segundo amor, estoy organizando mis recuerdos."

    # 4. GUARDAR RESPUESTA DEL BOT EN BD
    guardar_memoria(user_id, "assistant", respuesta_final)

    # 5. ENVIAR AL USUARIO
    if es_audio:
        await enviar_audio_puro(update, context, respuesta_final)
    else:
        await update.message.reply_text(respuesta_final)

# ==========================================
# 📥 HANDLERS
# ==========================================
async def recibir_texto(update: Update, context: ContextTypes.DEFAULT_TYPE):
    texto = update.message.text
    if not texto: return
    await procesar_inteligencia(update, context, texto, es_audio=False)

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
        await procesar_inteligencia(update, context, texto, es_audio=True)
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
        await update.message.reply_text("✅ **Memoria Eterna Activada.**\nHola Fredy. Todo lo que digas quedará grabado en Supabase.")
    else:
        if update.effective_user.id == ADMIN_ID:
            await update.message.reply_text("Jefe, sigo aquí y recuerdo todo.")
        else:
            await update.message.reply_text("Hola. Soy KLMZ IA.")

if __name__ == "__main__":
    keep_alive()
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, recibir_texto))
    app.add_handler(MessageHandler(filters.VOICE, recibir_audio))
    app.job_queue.run_repeating(vigilar_usuarios, interval=30, first=10)
    print("✅ KLMZ IA: Memoria Eterna (Supabase) Activada")
    app.run_polling()
