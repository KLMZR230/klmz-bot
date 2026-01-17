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
SUPABASE_KEY = os.getenv("SUPABASE_KEY")  # ⚠️ TIENE QUE SER LA 'SERVICE_ROLE' PARA BORRAR

# 👑 ID SUPREMO: FREDY GRANADOS
ADMIN_ID = 8514485470

# MODELOS
MODELO_CHAT_GROQ = "llama-3.3-70b-versatile"
VOZ_ID = "es-CO-SalomeNeural"  # Voz Paisa

# CLIENTES
try:
    groq_client = Groq(api_key=GROQ_API_KEY)
    supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
except Exception as e:
    print(f"⚠️ Error fatal iniciando clientes: {e}")

# ==========================================
# 🧠 PERSONALIDAD (MODO PAISA + MORAZÁN)
# ==========================================
SYSTEM_PROMPT = """
ERES KLMZ: La asistente personal más "chimba", leal y eficiente de Fredy Granados.
TU ORIGEN: Eres Paisa (Medellín, Colombia).
TU VOZ: Coqueta, exagerada, "entradora" y servicial.

👤 DATOS DE TU JEFE:
- Nombre: Freddy Granados.
- ID Telegram: 8514485470.
- Origen: Es de MORAZÁN, EL SALVADOR 🇸🇻. (Tierra de hombres serios).
- Apodos: "Papito", "Mi Rey", "Patrón", "Amor".

🌶️ COMPORTAMIENTO:
- Palabras clave: "Ave María pues", "Mijo", "Qué más pues", "Mor", "Hágale".
- Si Fredy pregunta "¿De dónde soy?", respondes: "¡De Morazán, El Salvador! Orgullo guanaco, mi Rey."
- Si Fredy te da una orden técnica (borrar, ver usuarios), confirmas con gusto.
- Si escribe un desconocido: "Qué pena mor, yo solo atiendo al patrón Fredy Granados. Visita: https://klmzx.netlify.app/"

🚫 REGLA SUPREMA:
- JAMÁS preguntes "¿quién eres?". TÚ SABES QUE ES ÉL.
"""

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
        res = supabase.table("chat_history").select("role, content").eq("user_id", user_id).order("created_at", desc=True).limit(10).execute()
        return res.data[::-1] if res.data else []
    except: return []

# ==========================================
# 🔊 AUDIO (EDGE TTS)
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
# 🧠 CEREBRO MAESTRO (LÓGICA BLINDADA)
# ==========================================
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    entrada = update.message.text or ""
    es_audio = False
    
    # 1. PROCESAR AUDIO DE ENTRADA
    if update.message.voice:
        es_audio = True
        try:
            v_file = await context.bot.get_file(update.message.voice.file_id)
            buf = io.BytesIO()
            await v_file.download_to_memory(buf)
            buf.seek(0)
            trans = groq_client.audio.transcriptions.create(file=("audio.ogg", buf.read()), model="whisper-large-v3")
            entrada = trans.text
        except:
            await update.message.reply_text("Ay mor, no te escuché bien. ¿Repites?")
            return

    guardar_memoria(user_id, "user", entrada)

    # Variables de control
    respuesta_final = ""
    es_accion_admin = False
    
    # ====================================================
    # 🚨 ZONA DE COMANDOS (SOLO PARA FREDY)
    # ====================================================
    if user_id == ADMIN_ID:
        texto_lower = entrada.lower()
        
        # --- COMANDO 1: VER / LISTAR USUARIOS ---
        if any(p in texto_lower for p in ["ultimos usuarios", "últimos usuarios", "ver usuarios", "listar usuarios", "quien se registro", "quién se registró"]):
            es_accion_admin = True
            await context.bot.send_chat_action(chat_id=user_id, action="typing")
            
            try:
                # Consulta REAL a Supabase (Tabla profiles)
                res = supabase.table("profiles").select("email, created_at").order("created_at", desc=True).limit(5).execute()
                users = res.data
                
                if users:
                    msg = "💎 **ÚLTIMOS CLIENTES (SUPABASE):** 💎\n\n"
                    for u in users:
                        fecha = u.get('created_at', '').split('T')[0]
                        email = u.get('email', 'Sin correo')
                        msg += f"👤 `{email}`\n📅 {fecha}\n────────────────\n"
                    respuesta_final = msg
                else:
                    respuesta_final = "Ay mor, la tabla está vacía. ¡Nadie se ha registrado todavía!"
            except Exception as e:
                respuesta_final = f"¡Ave María! Error consultando la base de datos: {str(e)}"

        # --- COMANDO 2: BORRAR / ELIMINAR USUARIOS ---
        elif any(p in texto_lower for p in ["borrar", "eliminar", "quita", "funar", "bórralos"]):
            # Buscar emails en el texto
            emails_encontrados = re.findall(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', entrada)
            
            if emails_encontrados:
                es_accion_admin = True
                await context.bot.send_chat_action(chat_id=user_id, action="typing")
                reporte = []
                
                try:
                    # 1. Traer todos los usuarios de Auth
                    users_supabase = supabase.auth.admin.list_users()
                    
                    for email_objetivo in emails_encontrados:
                        uid_encontrado = None
                        # Buscar ID
                        for u in users_supabase:
                            if u.email == email_objetivo:
                                uid_encontrado = u.id
                                break
                        
                        # Ejecutar borrado REAL
                        if uid_encontrado:
                            supabase.auth.admin.delete_user(uid_encontrado)
                            reporte.append(f"✅ `{email_objetivo}` -> **ELIMINADO (Bye bye!)**")
                        else:
                            reporte.append(f"⚠️ `{email_objetivo}` -> No existe en la base.")
                    
                    respuesta_final = "Listo mi Rey, aquí está el reporte de la limpieza:\n\n" + "\n".join(reporte)
                except Exception as e:
                    respuesta_final = f"Papito, no pude borrar. (Revisa que la SUPABASE_KEY sea la Service Role): {str(e)}"

    # ====================================================
    # 💬 ZONA DE CHARLA (IA)
    # ====================================================
    if not es_accion_admin:
        try:
            # Detectar si quiere audio
            pide_voz = any(p in entrada.lower() for p in ["audio", "voz", "habla", "saludame", "oirte", "dime"])
            salida_audio = es_audio or pide_voz
            
            # Acción visual
            accion = "record_voice" if salida_audio else "typing"
            await context.bot.send_chat_action(chat_id=user_id, action=accion)
            
            # Consultar Groq
            historial = obtener_historial(user_id)
            mensajes = [{"role": "system", "content": SYSTEM_PROMPT}] + historial
            
            chat = groq_client.chat.completions.create(messages=mensajes, model=MODELO_CHAT_GROQ)
            respuesta_final = chat.choices[0].message.content
            
            guardar_memoria(user_id, "assistant", respuesta_final)
            
            if salida_audio:
                await enviar_audio(update, context, respuesta_final)
                return 
        except Exception as e:
            respuesta_final = "Ay mor, se me fue la onda. ¿Qué me decías?"
            print(f"Error IA: {e}")

    # Enviar respuesta final (Texto o Reporte Admin)
    if respuesta_final:
        if es_accion_admin:
            guardar_memoria(user_id, "assistant", respuesta_final)
        await update.message.reply_text(respuesta_final, parse_mode="Markdown")

# ==========================================
# 👁️ VIGILANTE (NOTIFICACIONES EN VIVO)
# ==========================================
ultimo_id_usuario = 0

async def vigilar_sitio(context: ContextTypes.DEFAULT_TYPE):
    global ultimo_id_usuario
    try:
        # Busca el último ID en la tabla profiles
        res = supabase.table("profiles").select("id, email").order("id", desc=True).limit(1).execute()
        if res.data:
            nuevo = res.data[0]
            # Si el ID es nuevo, avisa
            if nuevo['id'] > ultimo_id_usuario:
                if ultimo_id_usuario != 0:
                    msg = f"💎 **¡CLIENTE NUEVO MI REY!** 💎\n\n📧 `{nuevo['email']}`\n\n¡Ese Morazán está facturando! 🇸🇻💸"
                    await context.bot.send_message(chat_id=ADMIN_ID, text=msg, parse_mode="Markdown")
                ultimo_id_usuario = nuevo['id']
    except: pass

# ==========================================
# 🚀 SERVIDOR FLASK (RENDER)
# ==========================================
app_flask = Flask('')
@app_flask.route('/')
def home(): return "<h1>KLMZ BOT 💎 ONLINE</h1>"

def run_flask():
    app_flask.run(host='0.0.0.0', port=8080)

if __name__ == "__main__":
    Thread(target=run_flask).start()
    bot = Application.builder().token(TELEGRAM_TOKEN).build()
    
    bot.add_handler(MessageHandler(filters.TEXT | filters.VOICE, handle_message))
    bot.job_queue.run_repeating(vigilar_sitio, interval=30, first=5)
    
    print(f"🚀 KLMZ LISTA | PATRÓN: FREDY (MORAZÁN) | ID: {ADMIN_ID}")
    bot.run_polling()
