import logging
import os
import json
import urllib.parse
import re
from threading import Thread
from flask import Flask
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from groq import Groq
import google.generativeai as genai
from google.generativeai.types import HarmCategory, HarmBlockThreshold
import edge_tts

# ==========================================
# 🔐 CREDENCIALES (MODO SEGURO - NUBE)
# ==========================================
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# ==========================================
# ⚙️ CONFIGURACIÓN DE MOTORES
# ==========================================
MODELO_CHAT_GROQ = "llama-3.3-70b-versatile" 

# --- CORRECCIÓN: VOLVEMOS AL MODELO EXPERIMENTAL POTENTE ---
# Usamos el nombre técnico del Preview más avanzado disponible
MODELO_CODIGO_GEMINI = 'gemini-2.0-flash-exp' 

VOZ_ID = "es-CO-SalomeNeural" 
ARCHIVO_MEMORIA = "historial_chats.json"

# Inicializar clientes
try:
    groq_client = Groq(api_key=GROQ_API_KEY)
    genai.configure(api_key=GEMINI_API_KEY)
except Exception as e:
    print(f"⚠️ Advertencia de inicio: {e}")

# Configuración Gemini (Sin censura para código)
safety_settings = {
    HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_NONE,
    HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_NONE,
    HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_NONE,
    HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_NONE,
}

gemini_coder = genai.GenerativeModel(
    model_name=MODELO_CODIGO_GEMINI,
    safety_settings=safety_settings,
    system_instruction="Eres un experto Ingeniero de Software Senior. Tu tarea es generar código completo, funcional y limpio. No des explicaciones largas, ve al grano con el código."
)

# ==========================================
# 🌐 SERVIDOR FALSO (PARA RENDER)
# ==========================================
app_flask = Flask('')

@app_flask.route('/')
def home():
    return "<h1>KLMZ IA - Sistema Operativo (Experimental Mode)</h1>"

def run():
    port = int(os.environ.get("PORT", 8080))
    app_flask.run(host='0.0.0.0', port=port)

def keep_alive():
    t = Thread(target=run)
    t.start()

# ==========================================
# 🧠 MEMORIA
# ==========================================
historial_conversacion = {}

def cargar_memoria():
    global historial_conversacion
    if os.path.exists(ARCHIVO_MEMORIA):
        try:
            with open(ARCHIVO_MEMORIA, "r", encoding="utf-8") as f:
                historial_conversacion = json.load(f)
            print("🧠 Memoria cargada.")
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

# ==========================================
# 🔊 AUDIO
# ==========================================
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
# 🤖 LÓGICA DEL CEREBRO HÍBRIDO
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
        # 1. GROQ DECIDE QUÉ HACER
        mensajes_groq = [
            {
                "role": "system",
                "content": f"""
                Identidad: Eres KLMZ IA, asistente personal colombiana (paisa) de Fredy Granados.
                
                TUS REGLAS DE DECISIÓN (ROUTER):
                1. SI el usuario pide CÓDIGO, PROGRAMACIÓN, SCRIPTS, HTML, CSS:
                   Responde SOLO JSON: {{ "action": "generate_code", "prompt": "descripcion tecnica exacta" }}
                
                2. SI el usuario pide IMÁGENES:
                   Responde SOLO JSON: {{ "action": "generate_image", "prompt": "descripcion visual INGLES", "thought": "comentario coqueto" }}
                
                3. SI es charla normal:
                   Responde tú misma con tu personalidad paisa.
                   
                Usuario Actual: {nombre}. Si es Fredy (23/07/2000, El Salvador), trátalo como "Mi Arquitecto" o "Papito".
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
            temperature=0.7,
        )
        respuesta_groq = chat_completion.choices[0].message.content
        
        # 2. PROCESAR LA ORDEN
        match_json = re.search(r'\{.*\}', respuesta_groq, re.DOTALL)
        respuesta_final = respuesta_groq 
        
        if match_json:
            try:
                datos = json.loads(match_json.group(0))
                accion = datos.get("action")
                
                # --- CASO A: CÓDIGO (GEMINI PREVIEW / EXPERIMENTAL) ---
                if accion == "generate_code":
                    prompt_code = datos.get("prompt")
                    await update.message.reply_text("🔨 De una papito, pongo el modo Experimental a programar...")
                    await update.message.reply_chat_action("typing")
                    
                    try:
                        resp_gemini = gemini_coder.generate_content(prompt_code)
                        respuesta_final = resp_gemini.text
                    except Exception as e_gemini:
                        print(f"Error Gemini: {e_gemini}")
                        respuesta_final = f"Uy amor, Google me rebotó la conexión con el modelo experimental. Error: {e_gemini}"

                # --- CASO B: IMAGEN (FLUX) ---
                elif accion == "generate_image":
                    await update.message.reply_chat_action("upload_photo")
                    prompt_img = datos.get("prompt")
                    thought = datos.get("thought", "Aquí tienes.")
                    
                    encoded = urllib.parse.quote(prompt_img)
                    seed = update.message.message_id
                    url = f"https://image.pollinations.ai/prompt/{encoded}?model=flux&width=1024&height=1792&nologo=true&seed={seed}"
                    
                    await update.message.reply_photo(photo=url, caption=f"🎨 {thought}")
                    
                    memoria.append({"role": "user", "content": texto_usuario})
                    memoria.append({"role": "model", "content": f"[Imagen creada: {prompt_img}]"})
                    guardar_memoria()
                    
                    if es_audio: await enviar_audio(update, thought)
                    return

            except: pass

        # 3. ENVIAR RESPUESTA
        parse_mode = "Markdown" if "```" in respuesta_final else None
        
        if len(respuesta_final) > 4000:
            for x in range(0, len(respuesta_final), 4000):
                await update.message.reply_text(respuesta_final[x:x+4000], parse_mode=None)
        else:
            await update.message.reply_text(respuesta_final, parse_mode=parse_mode)
        
        if es_audio and "```" not in respuesta_final:
            clean_text = re.sub(r'[*_`#]', '', respuesta_final)
            await enviar_audio(update, clean_text)
            
        memoria.append({"role": "user", "content": texto_usuario})
        memoria.append({"role": "model", "content": respuesta_final})
        guardar_memoria()

    except Exception as e:
        print(f"Error General: {e}")
        await update.message.reply_text("Papito, error de conexión. Intente de nuevo.")

# ==========================================
# 🚀 INICIO
# ==========================================
if __name__ == "__main__":
    keep_alive()
    
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", lambda u,c: u.message.reply_text("¡Hola! Soy KLMZ IA. Arquitecto Fredy, estoy lista.")))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, procesar_mensaje))
    app.add_handler(MessageHandler(filters.VOICE, procesar_mensaje))
    
    print("✅ Bot KLMZ activo con Gemini Flash Preview.")
    app.run_polling()
