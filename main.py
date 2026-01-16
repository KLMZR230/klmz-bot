import logging
import os
import json
import urllib.parse
import re
import asyncio
from datetime import datetime, timedelta
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

# ID del Admin (Se guardará cuando des /start)
ADMIN_ID = None 

# Inicializar clientes
try:
    groq_client = Groq(api_key=GROQ_API_KEY)
    genai.configure(api_key=GEMINI_API_KEY)
    supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
except Exception as e:
    print(f"⚠️ Advertencia de inicio: {e}")

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
    system_instruction="Eres un experto Ingeniero de Software Senior. Genera código limpio y profesional."
)

# ==========================================
# 🌐 SERVIDOR FALSO
# ==========================================
app_flask = Flask('')

@app_flask.route('/')
def home():
    return "<h1>KLMZ IA - Vigilante de Supabase Activo 👁️</h1>"

def run():
    port = int(os.environ.get("PORT", 8080))
    app_flask.run(host='0.0.0.0', port=port)

def keep_alive():
    t = Thread(target=run)
    t.start()

# ==========================================
# 🧠 MEMORIA Y AUDIO
# ==========================================
historial_conversacion = {}

def cargar_memoria():
    global historial_conversacion
    if os.path.exists(ARCHIVO_MEMORIA):
        try:
            with open(ARCHIVO_MEMORIA, "r", encoding="utf-8") as f:
                historial_conversacion = json.load(f)
        except: historial_conversacion = {}

def guardar_memoria():
    try:
        with open(ARCHIVO_MEMORIA, "w", encoding="utf-8") as f:
            json.dump(historial_conversacion, f, ensure_ascii=False, indent=4)
    except: pass

cargar_memoria()

def obtener_historial(user_id):
    uid = str(user_id)
    if uid not in historial_conversacion: historial_conversacion[uid] = []
    return historial_conversacion[uid]

async def enviar_audio(update, texto):
    archivo = f"audio_{update.effective_user.id}.mp3"
    try:
        communicate = edge_tts.Communicate(texto, VOZ_ID, rate="+0%")
        await communicate.save(archivo)
        with open(archivo, 'rb') as audio:
            await update.message.reply_voice(voice=audio)
    except: pass
    finally:
        if os.path.exists(archivo): os.remove(archivo)

async def transcribir_con_groq(update, context):
    file_id = update.message.voice.file_id
    new_file = await context.bot.get_file(file_id)
    archivo = f"voice_{update.effective_user.id}.ogg"
    await new_file.download_to_drive(archivo)
    try:
        with open(archivo, "rb") as file:
            transcription = groq_client.audio.transcriptions.create(
                file=(archivo, file.read()), model="whisper-large-v3", language="es"
            )
        return transcription.text
    except: return None
    finally:
        if os.path.exists(archivo): os.remove(archivo)

# ==========================================
# 👁️ SISTEMA DE VIGILANCIA (SUPABASE)
# ==========================================
ultimo_chequeo = datetime.utcnow().isoformat()

async def vigilar_usuarios(context: ContextTypes.DEFAULT_TYPE):
    global ultimo_chequeo
    if not ADMIN_ID: return

    try:
        # Busca usuarios nuevos en la tabla de autenticación
        response = supabase.auth.admin.list_users() 
        users = response.users
        
        nuevos = []
        for user in users:
            # Compara si se creó después del último chequeo
            if user.created_at > ultimo_chequeo:
                nuevos.append(user.email)

        if nuevos:
            mensaje = "🚨 **¡NUEVO USUARIO DETECTADO!** 🚨\n\n"
            for email in nuevos:
                mensaje += f"👤 Email: `{email}`\n"
            mensaje += f"\n📅 Hora: {datetime.now().strftime('%H:%M')}"
            
            await context.bot.send_message(chat_id=ADMIN_ID, text=mensaje, parse_mode="Markdown")
            
            # Actualizamos la hora para no repetir la alerta
            ultimo_chequeo = datetime.utcnow().isoformat()

    except Exception as e:
        print(f"Error vigilando Supabase: {e}")

# ==========================================
# 🤖 LÓGICA PRINCIPAL (CHAT)
# ==========================================
async def procesar_mensaje(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    nombre = update.effective_user.first_name
    es_audio = False
    
    if update.message.voice:
        es_audio = True
        await update.message.reply_chat_action("record_voice")
        texto_usuario = await transcribir_con_groq(update, context)
        if not texto_usuario: return
    else:
        texto_usuario = update.message.text

    if not texto_usuario: return

    memoria = obtener_historial(user_id)
    await update.message.reply_chat_action("typing")

    try:
        mensajes_groq = [
            {
                "role": "system",
                "content": f"""
                ERES: KLMZ IA, asistente paisa inteligente.
                DUEÑO: Fredy Granados (HOMBRE, "Papito", "Mi Rey").
                
                CAPACIDADES:
                1. Super Inteligencia (Responde todo).
                2. Vigilante (Monitoreas Supabase en segundo plano).
                
                ROUTER:
                - SI PIDE CÓDIGO: {{ "action": "generate_code", "prompt": "..." }}
                - SI PIDE IMAGEN: {{ "action": "generate_image", "prompt": "..." }}
                - SI CHARLA: Responde normal, paisa y coherente.
                """
            }
        ]
        
        for m in memoria[-6:]: 
            role = "assistant" if m["role"] == "model" else "user"
            mensajes_groq.append({"role": role, "content": m["content"]})
            
        mensajes_groq.append({"role": "user", "content": texto_usuario})

        chat_completion = groq_client.chat.completions.create(
            messages=mensajes_groq,
            model=MODELO_CHAT_GROQ,
            temperature=0.5, 
        )
        respuesta_groq = chat_completion.choices[0].message.content
        
        match_json = re.search(r'\{.*\}', respuesta_groq, re.DOTALL)
        respuesta_final = respuesta_groq 
        
        if match_json:
            try:
                datos = json.loads(match_json.group(0))
                accion = datos.get("action")
                
                if accion == "generate_code":
                    prompt_code = datos.get("prompt")
                    await update.message.reply_text("🔨 De una papito, programando...")
                    try:
                        resp_gemini = gemini_coder.generate_content(prompt_code)
                        respuesta_final = resp_gemini.text
                    except Exception as e: respuesta_final = f"Error Gemini: {e}"

                elif accion == "generate_image":
                    prompt_img = datos.get("prompt")
                    encoded = urllib.parse.quote(prompt_img)
                    url = f"https://image.pollinations.ai/prompt/{encoded}?model=flux&width=1024&height=1792&nologo=true&seed={update.message.message_id}"
                    await update.message.reply_photo(photo=url)
                    memoria.append({"role": "user", "content": texto_usuario})
                    memoria.append({"role": "model", "content": f"[Imagen creada]"})
                    guardar_memoria()
                    return

            except: pass

        if len(respuesta_final) > 4000:
            for x in range(0, len(respuesta_final), 4000):
                await update.message.reply_text(respuesta_final[x:x+4000])
        else:
            await update.message.reply_text(respuesta_final)
            
        if es_audio:
            clean_text = re.sub(r'[*_`#]', '', respuesta_final)
            await enviar_audio(update, clean_text)
            
        memoria.append({"role": "user", "content": texto_usuario})
        memoria.append({"role": "model", "content": respuesta_final})
        guardar_memoria()

    except Exception as e:
        print(f"Error: {e}")
        await update.message.reply_text("Papito, error de sistema.")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global ADMIN_ID
    ADMIN_ID = update.effective_user.id
    await update.message.reply_text(f"¡Hola Papito! Soy KLMZ IA.\n👁️ **Sistema de Vigilancia Conectado a Supabase.**\nTe avisaré si alguien se registra.")

# ==========================================
# 🚀 ARRANQUE
# ==========================================
if __name__ == "__main__":
    keep_alive()
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, procesar_mensaje))
    app.add_handler(MessageHandler(filters.VOICE, procesar_mensaje))
    
    # Tarea de vigilancia cada 30 segundos
    app.job_queue.run_repeating(vigilar_usuarios, interval=30, first=10)
    
    print("✅ KLMZ IA: Vigilante Activo.")
    app.run_polling()
