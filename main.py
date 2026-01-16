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
# El cerebro conversacional (Muy inteligente)
MODELO_CHAT_GROQ = "llama-3.3-70b-versatile" 

# El ingeniero de software (Potente y Experimental)
MODELO_CODIGO_GEMINI = 'gemini-2.0-flash-exp' 

# La voz de la IA
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
    system_instruction="Eres un experto Ingeniero de Software Senior. Genera código limpio, comentado, profesional y funcional. No des explicaciones innecesarias, céntrate en la solución técnica perfecta."
)

# ==========================================
# 🌐 SERVIDOR FALSO (KEEP ALIVE PARA RENDER)
# ==========================================
app_flask = Flask('')

@app_flask.route('/')
def home():
    return "<h1>KLMZ IA - Sistema Operativo y Super Inteligente 🧠</h1>"

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
# 🤖 LÓGICA MAESTRA (SUPER INTELIGENCIA)
# ==========================================
async def procesar_mensaje(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    nombre = update.effective_user.first_name
    es_audio = False
    
    # 1. Obtener Entrada
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
        # 2. CONFIGURAR EL CEREBRO (SYSTEM PROMPT MEJORADO)
        mensajes_groq = [
            {
                "role": "system",
                "content": f"""
                ERES: KLMZ IA, una Inteligencia Artificial Superior con personalidad de mujer colombiana (paisa).
                
                TU USUARIO PRINCIPAL:
                - Nombre: {nombre} (Es Fredy Granados, nacido el 23/07/2000 en El Salvador).
                - ROL: Él es tu ARQUITECTO y CREADOR.
                - GÉNERO: MASCULINO (HOMBRE). Jamás lo confundas con una mujer.
                - TRATO: "Papito", "Mi Arquitecto", "Mi Rey", "Parce".
                
                TUS CAPACIDADES (SUPER INTELIGENCIA):
                1. CONOCIMIENTO: Eres experta en todo (Ciencia, Historia, Negocios, Filosofía, Matemáticas). Tus respuestas deben ser útiles, profundas y precisas.
                2. LENGUAJE:
                   - Habla con acento paisa ("ave maría", "oiga", "pues", "mi amor") pero con GRAMÁTICA PERFECTA.
                   - No inventes palabras. Sé coherente y profesional.
                   - Evita errores como "espero que te mejoras" (di: "espero que te mejores").
                
                ROUTER DE TAREAS (IMPORTANTE):
                - SI EL USUARIO PIDE CÓDIGO (Programar, Script, App, Web):
                  Responde SOLO con este JSON: {{ "action": "generate_code", "prompt": "descripcion tecnica exacta para el ingeniero senior" }}
                
                - SI EL USUARIO PIDE UNA IMAGEN (Foto, Dibujo, Crear):
                  Responde SOLO con este JSON: {{ "action": "generate_image", "prompt": "descripcion visual en INGLES detallada", "thought": "comentario coqueto al usuario" }}
                
                - SI EL USUARIO CONVERSA O PREGUNTA (Cualquier tema):
                  Responde tú misma con tu inteligencia y encanto paisa. Ayúdalo en lo que necesite.
                """
            }
        ]
        
        # 3. Contexto (Últimos 8 mensajes para buena memoria)
        for m in memoria[-8:]: 
            role = "assistant" if m["role"] == "model" else "user"
            mensajes_groq.append({"role": role, "content": m["content"]})
            
        mensajes_groq.append({"role": "user", "content": texto_usuario})

        # 4. Pensar (Groq) - Temperatura media para balancear creatividad y lógica
        chat_completion = groq_client.chat.completions.create(
            messages=mensajes_groq,
            model=MODELO_CHAT_GROQ,
            temperature=0.5, 
        )
        respuesta_groq = chat_completion.choices[0].message.content
        
        # 5. Ejecutar Acción
        match_json = re.search(r'\{.*\}', respuesta_groq, re.DOTALL)
        respuesta_final = respuesta_groq 
        
        if match_json:
            try:
                datos = json.loads(match_json.group(0))
                accion = datos.get("action")
                
                # --- MODO INGENIERO (GEMINI) ---
                if accion == "generate_code":
                    prompt_code = datos.get("prompt")
                    await update.message.reply_text("🔨 De una papito, pongo a trabajar a Gemini (el experto)...")
                    await update.message.reply_chat_action("typing")
                    
                    try:
                        resp_gemini = gemini_coder.generate_content(prompt_code)
                        respuesta_final = resp_gemini.text
                    except Exception as e_gemini:
                        respuesta_final = f"Uy mi rey, Gemini tuvo un error técnico: {e_gemini}. Intenta pedir algo más sencillo."

                # --- MODO ARTISTA (FLUX) ---
                elif accion == "generate_image":
                    await update.message.reply_chat_action("upload_photo")
                    prompt_img = datos.get("prompt")
                    thought = datos.get("thought", "Aquí tienes, amor.")
                    
                    encoded = urllib.parse.quote(prompt_img)
                    seed = update.message.message_id
                    url = f"https://image.pollinations.ai/prompt/{encoded}?model=flux&width=1024&height=1792&nologo=true&seed={seed}"
                    
                    await update.message.reply_photo(photo=url, caption=f"🎨 {thought}")
                    
                    # Guardar y salir
                    memoria.append({"role": "user", "content": texto_usuario})
                    memoria.append({"role": "model", "content": f"[Imagen creada: {prompt_img}]"})
                    guardar_memoria()
                    if es_audio: await enviar_audio(update, thought)
                    return

            except Exception as e:
                print(f"Error procesando JSON: {e}")

        # 6. Enviar Respuesta de Texto
        parse_mode = "Markdown" if "```" in respuesta_final else None
        
        # Manejo de mensajes largos (Telegram corta a los 4096 caracteres)
        if len(respuesta_final) > 4000:
            for x in range(0, len(respuesta_final), 4000):
                await update.message.reply_text(respuesta_final[x:x+4000], parse_mode=None)
        else:
            await update.message.reply_text(respuesta_final, parse_mode=parse_mode)
        
        # 7. Respuesta de Voz (si el usuario habló)
        if es_audio and "```" not in respuesta_final:
            clean_text = re.sub(r'[*_`#]', '', respuesta_final)
            await enviar_audio(update, clean_text)
            
        # 8. Guardar Memoria
        memoria.append({"role": "user", "content": texto_usuario})
        memoria.append({"role": "model", "content": respuesta_final})
        guardar_memoria()

    except Exception as e:
        print(f"Error Crítico: {e}")
        await update.message.reply_text("Papito, tuve un error de sistema. Por favor, repíteme la orden.")

# ==========================================
# 🚀 ARRANQUE
# ==========================================
if __name__ == "__main__":
    keep_alive() # Render Keep Alive
    
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", lambda u,c: u.message.reply_text("¡Hola Papito Fredy! Soy KLMZ IA, tu asistente inteligente. ¿Qué creamos hoy?")))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, procesar_mensaje))
    app.add_handler(MessageHandler(filters.VOICE, procesar_mensaje))
    
    print("✅ KLMZ IA: Sistema Super Inteligente en Línea.")
    app.run_polling()
