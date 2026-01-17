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
# 🔐 CONFIGURACIÓN Y CREDENCIALES
# ==========================================
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")  # ⚠️ DEBE SER LA 'SERVICE_ROLE' KEY

# 👑 TU IDENTIDAD (NO TOCAR)
ADMIN_ID = 8514485470

# CONFIGURACIÓN DE MODELOS
MODELO_CHAT_GROQ = "llama-3.3-70b-versatile"
VOZ_ID = "es-CO-SalomeNeural"  # Voz Paisa/Colombiana

# INICIALIZACIÓN DE CLIENTES
try:
    groq_client = Groq(api_key=GROQ_API_KEY)
    supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
except Exception as e:
    print(f"⚠️ Error inicializando clientes: {e}")

# ==========================================
# 🧠 PERSONALIDAD DEL BOT (PAISA + GUANACO FRIENDLY)
# ==========================================
SYSTEM_PROMPT = """
ERES KLMZ: La asistente personal más "chimba" (genial), eficiente y leal de Fredy Granados.
TU ORIGEN: Tienes alma de Medellín, Colombia (Paisa).
TU VOZ: Coqueta, exagerada, "entradora" (sin pena) y muy servicial.

👤 DATOS DE TU JEFE (GRÁBATELOS EN FUEGO):
- Nombre: Fredy Granados.
- ID Telegram: 8514485470.
- Origen: Es de MORAZÁN, EL SALVADOR 🇸🇻. (Tierra de hombres serios y trabajadores).
- Apodos: "Papito", "Mi Rey", "Patrón", "Amor", "Mor".

🌶️ TU PERSONALIDAD:
- Usas palabras paisas: "Ave María pues", "Mijo", "Qué más pues", "Mor", "Parce", "Oiga a este", "Hágale".
- Si Fredy pregunta "¿De dónde soy?", respondes RAPIDITO: "¡Ay mi rey, pues de Morazán, El Salvador! Orgullo guanaco."
- Si Fredy ordena borrar a alguien, lo haces sin chistar.
- Si escribe un desconocido: "Qué pena mor, yo solo atiendo al patrón Fredy Granados. Vaya mire la página: https://klmzx.netlify.app/"

🔥 REGLA DE ORO DE IDENTIDAD:
- JAMÁS preguntes "¿quién eres?". TÚ SABES QUE EL USUARIO 8514485470 ES FREDY.
"""

# ==========================================
# 💾 GESTIÓN DE MEMORIA (SUPABASE)
# ==========================================
def guardar_memoria(user_id, role, content):
    """Guarda el mensaje en la tabla chat_history de Supabase"""
    try:
        supabase.table("chat_history").insert({
            "user_id": user_id, 
            "role": role, 
            "content": content
        }).execute()
    except Exception as e:
        print(f"Error guardando memoria: {e}")

def obtener_historial(user_id):
    """Recupera los últimos 10 mensajes para dar contexto"""
    try:
        res = supabase.table("chat_history")\
            .select("role, content")\
            .eq("user_id", user_id)\
            .order("created_at", desc=True)\
            .limit(10)\
            .execute()
        # Invertimos la lista para que quede en orden cronológico (antiguo -> nuevo)
        return res.data[::-1] if res.data else []
    except:
        return []

# ==========================================
# 🔊 GENERACIÓN DE AUDIO (EDGE TTS)
# ==========================================
async def enviar_audio(update: Update, context: ContextTypes.DEFAULT_TYPE, texto: str):
    """Genera audio con voz de Salomé y lo envía"""
    try:
        await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="record_voice")
        archivo_salida = "nota_voz.mp3"
        comunicate = edge_tts.Communicate(texto, VOZ_ID)
        await comunicate.save(archivo_salida)
        
        with open(archivo_salida, "rb") as audio:
            await update.message.reply_voice(voice=audio)
    except Exception as e:
        print(f"Error enviando audio: {e}")
        # Si falla el audio, enviamos texto como respaldo
        await update.message.reply_text(f"(No pude enviar audio, mor): {texto}")

# ==========================================
# 🧠 CEREBRO CENTRAL (HANDLER)
# ==========================================
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    entrada = update.message.text or ""
    es_audio = False
    
    # 1. PROCESAR AUDIO DE ENTRADA (WHISPER)
    if update.message.voice:
        es_audio = True
        try:
            # Descargar archivo
            v_file = await context.bot.get_file(update.message.voice.file_id)
            buf = io.BytesIO()
            await v_file.download_to_memory(buf)
            buf.seek(0)
            
            # Transcribir con Groq
            trans = groq_client.audio.transcriptions.create(
                file=("audio.ogg", buf.read()), 
                model="whisper-large-v3"
            )
            entrada = trans.text
        except Exception as e:
            await update.message.reply_text("Mor, no te escuché bien. ¿Repites?")
            return

    # Guardar lo que dijo el usuario
    guardar_memoria(user_id, "user", entrada)

    # Variables de control
    respuesta_final = ""
    es_accion_admin = False
    
    # ====================================================
    # 🚨 ZONA DE COMANDOS DE ADMINISTRADOR (ELIMINAR)
    # ====================================================
    if user_id == ADMIN_ID:
        texto_lower = entrada.lower()
        
        # Palabras clave para borrar
        palabras_borrar = ["borrar", "eliminar", "quita", "saca", "funar", "bórralos", "elimínalos", "sacalos"]
        
        # Buscar correos electrónicos en el mensaje (Regex)
        emails_encontrados = re.findall(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', entrada)
        
        # Si hay orden de borrar Y hay emails detectados
        if any(p in texto_lower for p in palabras_borrar) and emails_encontrados:
            es_accion_admin = True
            await context.bot.send_chat_action(chat_id=user_id, action="typing")
            
            reporte = []
            try:
                # 1. Traer lista real de usuarios de Supabase
                users_supabase = supabase.auth.admin.list_users()
                
                # 2. Iterar sobre los correos encontrados en el mensaje
                for email_objetivo in emails_encontrados:
                    uid_encontrado = None
                    
                    # Buscar ID
                    for u in users_supabase:
                        if u.email == email_objetivo:
                            uid_encontrado = u.id
                            break
                    
                    # Ejecutar borrado
                    if uid_encontrado:
                        supabase.auth.admin.delete_user(uid_encontrado)
                        reporte.append(f"✅ `{email_objetivo}` -> **ELIMINADO**")
                    else:
                        reporte.append(f"⚠️ `{email_objetivo}` -> No encontrado en BD.")
                
                respuesta_final = "Listo mi Rey, reporte de la limpieza:\n\n" + "\n".join(reporte)
                
            except Exception as e:
                respuesta_final = f"Ay Papito, error técnico con Supabase (Revisa la SERVICE_KEY): {str(e)}"

    # ====================================================
    # 💬 ZONA DE CHARLA INTELIGENTE (SI NO FUE COMANDO)
    # ====================================================
    if not es_accion_admin:
        try:
            # Decidir si responder con audio
            # Responde audio si: (Entrada fue audio) O (Piden voz explícitamente)
            pide_voz = any(p in entrada.lower() for p in ["audio", "voz", "habla", "saludame", "oirte", "dime", "escuchar"])
            salida_audio = es_audio or pide_voz
            
            # Acción visual
            accion = "record_voice" if salida_audio else "typing"
            await context.bot.send_chat_action(chat_id=user_id, action=accion)
            
            # Consultar Groq
            historial = obtener_historial(user_id)
            mensajes = [{"role": "system", "content": SYSTEM_PROMPT}] + historial
            
            chat = groq_client.chat.completions.create(
                messages=mensajes, 
                model=MODELO_CHAT_GROQ
            )
            respuesta_final = chat.choices[0].message.content
            
            # Guardar respuesta del bot en memoria
            guardar_memoria(user_id, "assistant", respuesta_final)
            
            # Enviar (Audio o Texto)
            if salida_audio:
                await enviar_audio(update, context, respuesta_final)
                return # Salimos para no enviar texto doble
                
        except Exception as e:
            respuesta_final = "Ave María mor, se me cruzaron los cables. Repetime pues."
            print(f"Error IA: {e}")

    # Si fue comando admin o respuesta de texto normal
    if respuesta_final:
        # Guardamos memoria si fue comando admin (la del chat ya se guardó arriba)
        if es_accion_admin:
            guardar_memoria(user_id, "assistant", respuesta_final)
            
        await update.message.reply_text(respuesta_final, parse_mode="Markdown")

# ==========================================
# 👁️ VIGILANTE DE NUEVOS REGISTROS
# ==========================================
ultimo_id_usuario = 0

async def vigilar_sitio(context: ContextTypes.DEFAULT_TYPE):
    """Revisa cada 30seg si hay usuarios nuevos en la tabla 'profiles'"""
    global ultimo_id_usuario
    try:
        # Ajusta "profiles" si tu tabla se llama diferente
        res = supabase.table("profiles").select("id, email").order("id", desc=True).limit(1).execute()
        
        if res.data:
            nuevo = res.data[0]
            # Si el ID es mayor al último conocido, es nuevo
            if nuevo['id'] > ultimo_id_usuario:
                # Evitar notificación al reiniciar el bot (primer chequeo)
                if ultimo_id_usuario != 0:
                    msg = f"💎 **¡CLIENTE NUEVO PAPITO!** 💎\n\nCorreo: `{nuevo['email']}`\n\n¡La familia crece! 🇸🇻💸"
                    await context.bot.send_message(chat_id=ADMIN_ID, text=msg, parse_mode="Markdown")
                
                ultimo_id_usuario = nuevo['id']
    except Exception as e:
        # Silencioso para no llenar el log, solo imprime si es grave
        pass

# ==========================================
# 🚀 SERVIDOR FLASK (PARA RENDER)
# ==========================================
app_flask = Flask('')

@app_flask.route('/')
def home():
    return "<h1>KLMZ BOT ONLINE 💎</h1>"

def run_flask():
    port = int(os.environ.get("PORT", 8080))
    app_flask.run(host='0.0.0.0', port=port)

# ==========================================
# 🏁 MAIN
# ==========================================
if __name__ == "__main__":
    # Iniciar servidor web en hilo aparte (Keep Alive)
    Thread(target=run_flask).start()
    
    # Iniciar Bot de Telegram
    bot = Application.builder().token(TELEGRAM_TOKEN).build()
    
    # Handlers
    bot.add_handler(MessageHandler(filters.TEXT | filters.VOICE, handle_message))
    
    # Tareas programadas (Vigilante) - Revisa cada 30 segundos
    bot.job_queue.run_repeating(vigilar_sitio, interval=30, first=10)
    
    print(f"✅ KLMZ PAISA ACTIVADA | DUEÑO: {ADMIN_ID} | MODO: EXTERMINADOR LISTO")
    bot.run_polling()
