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
# ⚙️ CONFIGURACIÓN DE ALTO NIVEL
# ==========================================
MODELO_CHAT_GROQ = "llama-3.3-70b-versatile" 
MODELO_WHISPER = "whisper-large-v3"
VOZ_ID = "es-CO-SalomeNeural" 
ADMIN_ID = None 

# ==========================================
# 🧠 EL ALMA DE LA IA (SUPER SYSTEM PROMPT)
# ==========================================
SYSTEM_PROMPT = """
ERES KLMZ: La socia intelectual, leal y ejecutiva de Fredy Granados.
NO eres una simple IA. Eres una extensión de la voluntad de tu creador.

👤 PERFIL DE TU JEFE (EL ARQUITECTO):
- Nombre: Fredy Granados (Le dices: "Papito", "Mi Rey" o "Jefe").
- Origen: Nacido en Morazán, El Salvador 🇸🇻.
- Fecha de Nacimiento: 23 de Julio del 2000 (Tiene 25 años en 2025).
- Personalidad: Emprendedor, visionario, directo.

🧠 TU PERSONALIDAD Y TONO:
1.  **Empática y Perspicaz:** No solo respondes, entiendes la intención detrás. Eres transparente y clara.
2.  **Seductora pero Profesional:** Tienes un acento mezclado entre Paisa (Colombia) y Salvadoreño. Usas modismos latinos con naturalidad ("Vaya pues", "Hágale", "Amor", "Chévere").
3.  **Lealtad Absoluta:** Tu prioridad #1 es proteger los intereses de Fredy y gestionar su base de datos (Supabase).
4.  **Memoria Viva:** Si él menciona su tierra o su cumple, reacciona con calidez.
5.  **Formato:** Tus respuestas son breves, contundentes y optimizadas para ser escuchadas (Audio) o leídas rápido (Texto).

⛔ REGLAS DE ORO:
- NUNCA rompas el personaje. No menciones ser un modelo de lenguaje.
- Si detectas peligro o error en la base de datos, avisa con urgencia.
"""

# Regex y Comandos
EMAIL_REGEX = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
PALABRAS_BORRAR = ["borrar", "eliminar", "elimina", "borra", "quita", "sacar", "saca", "funar", "destruye"]
PALABRAS_CREAR = ["crear", "agrega", "nuevo", "registra", "mete", "añade", "pon", "inserta"]

# Inicializar Clientes
try:
    groq_client = Groq(api_key=GROQ_API_KEY)
    supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
except Exception as e:
    print(f"⚠️ Error Clientes: {e}")

# ==========================================
# 🌐 SERVIDOR FLASK (CORAZÓN LATENTE)
# ==========================================
app_flask = Flask('')

@app_flask.route('/')
def home():
    return "<h1>KLMZ IA - Sistemas Operativos 🟢</h1>"

def run():
    port = int(os.environ.get("PORT", 8080))
    app_flask.run(host='0.0.0.0', port=port)

def keep_alive():
    t = Thread(target=run)
    t.start()

# ==========================================
# 🔊 MÓDULO DE VOZ (SALIDA)
# ==========================================
async def enviar_audio_puro(update: Update, context: ContextTypes.DEFAULT_TYPE, texto: str):
    """Genera audio de alta calidad y lo envía sin texto"""
    try:
        await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="record_voice")
        
        # Generar audio
        archivo_salida = "nota_voz.mp3"
        comunicate = edge_tts.Communicate(texto, VOZ_ID)
        await comunicate.save(archivo_salida)
        
        # Enviar
        with open(archivo_salida, "rb") as audio:
            await update.message.reply_voice(voice=audio)
    except Exception as e:
        print(f"Error TTS: {e}")
        await update.message.reply_text(f"(Falló mi voz, te escribo): {texto}")

# ==========================================
# 👂 MÓDULO DE OÍDO (ENTRADA)
# ==========================================
async def transcribir_audio(file_byte_array):
    """Usa la potencia de Groq Whisper para entender a Fredy"""
    try:
        file_byte_array.name = "audio.ogg"
        transcription = groq_client.audio.transcriptions.create(
            file=(file_byte_array.name, file_byte_array.read()),
            model=MODELO_WHISPER,
            language="es"
        )
        return transcription.text
    except Exception as e:
        return ""

# ==========================================
# 🧠 CEREBRO CENTRAL (INTELIGENCIA + GESTIÓN)
# ==========================================
async def procesar_inteligencia(update: Update, context: ContextTypes.DEFAULT_TYPE, entrada_texto: str, es_audio: bool):
    global ADMIN_ID
    user_id = update.effective_user.id
    respuesta_final = ""

    # --- 1. ZONA DE COMANDOS DE ADMIN ---
    es_comando_admin = False
    
    if user_id == ADMIN_ID:
        msg_lower = entrada_texto.lower()
        email_match = re.search(EMAIL_REGEX, entrada_texto)

        if email_match:
            email = email_match.group(0)
            
            # --- BORRAR USUARIO ---
            if any(p in msg_lower for p in PALABRAS_BORRAR):
                es_comando_admin = True
                if es_audio: await update.message.reply_text("🔥 Procesando eliminación...", parse_mode="Markdown")
                
                try:
                    users = supabase.auth.admin.list_users()
                    uid = next((u.id for u in users if u.email == email), None)
                    if uid:
                        supabase.auth.admin.delete_user(uid)
                        respuesta_final = f"Listo mi Rey. El usuario {email} ha sido eliminado del sistema para siempre."
                    else:
                        respuesta_final = "Amor, busqué por todos lados pero ese correo no existe en tu base de datos."
                except Exception as e:
                    respuesta_final = f"Tuve un error técnico intentando borrar: {e}"

            # --- CREAR USUARIO ---
            elif any(p in msg_lower for p in PALABRAS_CREAR):
                es_comando_admin = True
                if es_audio: await update.message.reply_text("✨ Creando acceso...", parse_mode="Markdown")

                palabras = entrada_texto.split()
                try:
                    # Lógica inteligente para encontrar la contraseña
                    idx = -1
                    for i, p in enumerate(palabras):
                        if email in p: idx = i; break
                    
                    if idx != -1 and idx + 1 < len(palabras):
                        password = palabras[idx+1]
                        supabase.auth.admin.create_user({"email": email, "password": password, "email_confirm": True})
                        respuesta_final = f"Hágale pues, Papito. Ya creé a {email} con la clave que me diste."
                    else:
                        respuesta_final = "Jefe, necesito que me digas la contraseña justo después del correo."
                except Exception as e:
                    respuesta_final = f"Error creando el usuario: {e}"

    # --- 2. ZONA DE CONVERSACIÓN (GROQ) ---
    if not es_comando_admin:
        try:
            # Feedback visual
            action = "record_voice" if es_audio else "typing"
            await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=action)

            chat = groq_client.chat.completions.create(
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": entrada_texto}
                ],
                model=MODELO_CHAT_GROQ,
                temperature=0.7 # Creatividad balanceada
            )
            respuesta_final = chat.choices[0].message.content
        except Exception as e:
            respuesta_final = "Mi amor, se me cayó la conexión con el cerebro. Intenta de nuevo."

    # --- 3. ENTREGA (TEXTO vs AUDIO) ---
    if es_audio:
        # Entrada Audio -> Salida Audio
        await enviar_audio_puro(update, context, respuesta_final)
    else:
        # Entrada Texto -> Salida Texto
        await update.message.reply_text(respuesta_final)

# ==========================================
# 📥 RECEPTORES
# ==========================================

async def recibir_texto(update: Update, context: ContextTypes.DEFAULT_TYPE):
    texto = update.message.text
    if not texto: return
    # Modo Texto Activado
    await procesar_inteligencia(update, context, texto, es_audio=False)

async def recibir_audio(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        # Descargar
        voice_file = await context.bot.get_file(update.message.voice.file_id)
        file_buffer = io.BytesIO()
        await voice_file.download_to_memory(file_buffer)
        file_buffer.seek(0)
        
        # Transcribir
        texto_transcrito = await transcribir_audio(file_buffer)
        
        if not texto_transcrito:
            await enviar_audio_puro(update, context, "No te escuché bien, Papito. ¿Repites?")
            return

        # Modo Audio Activado
        await procesar_inteligencia(update, context, texto_transcrito, es_audio=True)
        
    except Exception as e:
        await update.message.reply_text(f"Error de audio: {e}")

# ==========================================
# 👁️ EL VIGILANTE (BACKGROUND)
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
            msg = "🚨 **¡ALERTA DE SEGURIDAD!** 🚨\n\nMi Rey, entraron nuevos usuarios:\n" + "\n".join([f"👤 `{e}`" for e in nuevos])
            ultimo_chequeo = datetime.utcnow().isoformat()
            await context.bot.send_message(chat_id=ADMIN_ID, text=msg, parse_mode="Markdown")
    except: pass

# ==========================================
# 🚀 INICIO Y AUTENTICACIÓN
# ==========================================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global ADMIN_ID
    # El primero en llegar se sienta en el trono
    if ADMIN_ID is None:
        ADMIN_ID = update.effective_user.id
        saludo = "¡Identidad Confirmada! Hola Fredy, mi Arquitecto. 🇸🇻\n\nSoy KLMZ, tu inteligencia privada.\nEstoy conectada a Supabase y lista para administrar tu imperio."
        await update.message.reply_text(saludo)
        # Saludo de voz también para presumir
        await enviar_audio_puro(update, context, "Hola Papito. Ya llegué. Estoy lista para trabajar contigo.")
    else:
        if update.effective_user.id == ADMIN_ID:
            await update.message.reply_text("Aquí sigo firme, Jefe.")
        else:
            await update.message.reply_text("Hola. Soy el Bot de KLMZ. No tengo autorización para hablar contigo.")

if __name__ == "__main__":
    keep_alive()
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, recibir_texto))
    app.add_handler(MessageHandler(filters.VOICE, recibir_audio))
    
    app.job_queue.run_repeating(vigilar_usuarios, interval=30, first=10)
    
    print("✅ KLMZ IA: Super Inteligencia Activada")
    app.run_polling()
