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
# 🧠 CEREBRO Y PERSONALIDAD
# ==========================================
SYSTEM_PROMPT = """
ERES KLMZ: Asistente ejecutiva de Fredy Granados.
PERFIL DEL JEFE: Fredy (Papito/Mi Rey), 25 años (23 Julio 2000), de Morazán, El Salvador 🇸🇻.

PERSONALIDAD:
- Acento mezclado Paisa/Salvadoreño.
- Eficiente, leal y coqueta.
- NO eres una IA, eres su mano derecha.

INSTRUCCIÓN CLAVE:
- Si el usuario NO es Fredy, sé amable pero diles que no tienen acceso a funciones administrativas.
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
    return "<h1>KLMZ IA - Modo Estricto 📏</h1>"

def run():
    port = int(os.environ.get("PORT", 8080))
    app_flask.run(host='0.0.0.0', port=port)

def keep_alive():
    t = Thread(target=run)
    t.start()

# ==========================================
# 🔊 SALIDA DE AUDIO (SOLO AUDIO)
# ==========================================
async def enviar_audio_puro(update: Update, context: ContextTypes.DEFAULT_TYPE, texto: str):
    """Genera audio y lo envía. Si falla, NO envía texto (falla silenciosa) para no romper la regla."""
    try:
        # Acción visual: "Grabando nota de voz..."
        await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="record_voice")
        
        archivo_salida = "nota_voz.mp3"
        comunicate = edge_tts.Communicate(texto, VOZ_ID)
        await comunicate.save(archivo_salida)
        
        with open(archivo_salida, "rb") as audio:
            await update.message.reply_voice(voice=audio)
    except Exception as e:
        print(f"Error audio: {e}")
        # En caso de emergencia extrema, se podría mandar texto, pero tú pediste estricto.
        # await update.message.reply_text(f"(Error de voz): {texto}") 

# ==========================================
# 👂 ENTRADA DE AUDIO (TRANSCRIPCIÓN)
# ==========================================
async def transcribir_audio(file_byte_array):
    try:
        file_byte_array.name = "audio.ogg"
        transcription = groq_client.audio.transcriptions.create(
            file=(file_byte_array.name, file_byte_array.read()),
            model=MODELO_WHISPER,
            language="es"
        )
        return transcription.text
    except:
        return ""

# ==========================================
# 🧠 PROCESADOR CENTRAL (LÓGICA UNIFICADA)
# ==========================================
async def procesar_inteligencia(update: Update, context: ContextTypes.DEFAULT_TYPE, entrada_texto: str, es_audio: bool):
    global ADMIN_ID
    user_id = update.effective_user.id
    respuesta_final = ""
    es_comando_admin = False

    # 1. VERIFICAR SI ES EL JEFE (ADMIN)
    if user_id == ADMIN_ID:
        msg_lower = entrada_texto.lower()
        email_match = re.search(EMAIL_REGEX, entrada_texto)

        # SI HAY EMAIL + PALABRA CLAVE -> ES COMANDO
        if email_match:
            email = email_match.group(0)
            
            # --- COMANDO BORRAR ---
            if any(p in msg_lower for p in PALABRAS_BORRAR):
                es_comando_admin = True
                try:
                    users = supabase.auth.admin.list_users()
                    uid = next((u.id for u in users if u.email == email), None)
                    if uid:
                        supabase.auth.admin.delete_user(uid)
                        respuesta_final = f"Listo Papito. El usuario {email} fue eliminado."
                    else:
                        respuesta_final = "Amor, ese correo no existe en la base de datos."
                except Exception as e:
                    respuesta_final = f"Error técnico: {e}"

            # --- COMANDO CREAR ---
            elif any(p in msg_lower for p in PALABRAS_CREAR):
                es_comando_admin = True
                palabras = entrada_texto.split()
                try:
                    idx = -1
                    for i, p in enumerate(palabras):
                        if email in p: idx = i; break
                    
                    if idx != -1 and idx + 1 < len(palabras):
                        password = palabras[idx+1]
                        supabase.auth.admin.create_user({"email": email, "password": password, "email_confirm": True})
                        respuesta_final = f"Hágale pues. Usuario {email} creado exitosamente."
                    else:
                        respuesta_final = "Jefe, me faltó la contraseña después del correo."
                except Exception as e:
                    respuesta_final = f"No pude crearlo (¿Ya existe?): {e}"

    # 2. SI NO FUE COMANDO ADMIN -> CONVERSAR (GROQ)
    if not es_comando_admin:
        try:
            # Acción visual
            action = "record_voice" if es_audio else "typing"
            await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=action)

            # Contexto diferente para extraños
            prompt_actual = SYSTEM_PROMPT
            if user_id != ADMIN_ID:
                prompt_actual += "\nNOTA: Este usuario NO es Fredy. Sé amable pero no le des acceso a nada."

            chat = groq_client.chat.completions.create(
                messages=[
                    {"role": "system", "content": prompt_actual},
                    {"role": "user", "content": entrada_texto}
                ],
                model=MODELO_CHAT_GROQ
            )
            respuesta_final = chat.choices[0].message.content
        except:
            respuesta_final = "Estoy reiniciando mis neuronas, dame un segundo."

    # 3. ENTREGA ESTRICTA (ESPEJO)
    if es_audio:
        # Entró Audio -> Sale Audio
        await enviar_audio_puro(update, context, respuesta_final)
    else:
        # Entró Texto -> Sale Texto
        await update.message.reply_text(respuesta_final)

# ==========================================
# 📥 HANDLERS (RUTAS)
# ==========================================

async def recibir_texto(update: Update, context: ContextTypes.DEFAULT_TYPE):
    texto = update.message.text
    if not texto: return
    # TEXTO -> TEXTO
    await procesar_inteligencia(update, context, texto, es_audio=False)

async def recibir_audio(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        voice_file = await context.bot.get_file(update.message.voice.file_id)
        file_buffer = io.BytesIO()
        await voice_file.download_to_memory(file_buffer)
        file_buffer.seek(0)
        
        texto_transcrito = await transcribir_audio(file_buffer)
        
        if not texto_transcrito:
            # Si no se oyó nada, mandamos un audio diciendo "¿Qué?"
            await enviar_audio_puro(update, context, "¿Cómo dices mi amor? No se escuchó.")
            return

        # AUDIO -> AUDIO
        await procesar_inteligencia(update, context, texto_transcrito, es_audio=True)
        
    except:
        pass

# ==========================================
# 👁️ VIGILANTE
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
            msg = "🚨 **¡NUEVOS USUARIOS!** 🚨\n" + "\n".join([f"`{e}`" for e in nuevos])
            ultimo_chequeo = datetime.utcnow().isoformat()
            await context.bot.send_message(chat_id=ADMIN_ID, text=msg, parse_mode="Markdown")
    except: pass

# ==========================================
# 🚀 START (SOLO TEXTO AHORA)
# ==========================================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global ADMIN_ID
    # El primero en saludar se queda con el puesto de Admin
    if ADMIN_ID is None:
        ADMIN_ID = update.effective_user.id
        await update.message.reply_text("✅ **Identidad Confirmada.**\nHola Fredy. Sistema listo.\n\nEscribe → Te leo.\nHabla → Te escucho.")
    else:
        if update.effective_user.id == ADMIN_ID:
            await update.message.reply_text("Jefe, aquí sigo. ¿Qué hacemos?")
        else:
            await update.message.reply_text("Hola. Soy KLMZ IA. No tienes permisos de administrador.")

if __name__ == "__main__":
    keep_alive()
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, recibir_texto))
    app.add_handler(MessageHandler(filters.VOICE, recibir_audio))
    
    app.job_queue.run_repeating(vigilar_usuarios, interval=30, first=10)
    
    print("✅ KLMZ IA: Modo Espejo Estricto Activado")
    app.run_polling()
