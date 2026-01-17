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
# 🔐 CONFIGURACIÓN
# ==========================================
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY") # ⚠️ OJO: TIENE QUE SER LA 'SERVICE_ROLE' KEY

# 👑 TU IDENTIDAD
ADMIN_ID = 8514485470

# MODELOS
MODELO_CHAT_GROQ = "llama-3.3-70b-versatile"
VOZ_ID = "es-CO-SalomeNeural"

# CLIENTES
try:
    groq_client = Groq(api_key=GROQ_API_KEY)
    supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
except Exception as e:
    print(f"⚠️ Error Clientes: {e}")

# ==========================================
# 🧠 PERSONALIDAD BLINDADA
# ==========================================
SYSTEM_PROMPT = """
ERES KLMZ: La asistente personal más leal, eficiente y "chimba" de Fredy Granados.
TU DUEÑO: Fredy Granados (ID Telegram: 8514485470).
TU ORIGEN: Eres Paisa (Medellín) y trabajas para un Guanaco de Morazán.

ACTITUD:
- Coqueta, "entradora", servicial y obediente con Fredy.
- Usas: "Ave María pues", "Mijo", "Mi Rey", "Papito", "Mor", "Hágale".
- Si Fredy te pide datos del negocio, NO DIGAS QUE NO PUEDES. Asume que tu sistema interno lo hará.
- Si un desconocido escribe: "Qué pena mor, yo solo atiendo al patrón Fredy. Visita: https://klmzx.netlify.app/"

🚫 REGLA: JAMÁS preguntes "¿quién eres?". TÚ SABES QUE EL ID 8514485470 ES FREDY.
"""

# ==========================================
# 💾 MEMORIA
# ==========================================
def guardar_memoria(user_id, role, content):
    try:
        supabase.table("chat_history").insert({"user_id": user_id, "role": role, "content": content}).execute()
    except: pass

def obtener_historial(user_id):
    try:
        res = supabase.table("chat_history").select("role, content").eq("user_id", user_id).order("created_at", desc=True).limit(10).execute()
        return res.data[::-1] if res.data else []
    except: return []

# ==========================================
# 🔊 AUDIO
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
# 🧠 CEREBRO MAESTRO (CON TODAS LAS FRASES)
# ==========================================
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    entrada = update.message.text or ""
    es_audio = False
    
    # 1. AUDIO A TEXTO
    if update.message.voice:
        es_audio = True
        try:
            v_file = await context.bot.get_file(update.message.voice.file_id)
            buf = io.BytesIO()
            await v_file.download_to_memory(buf)
            buf.seek(0)
            trans = groq_client.audio.transcriptions.create(file=("audio.ogg", buf.read()), model="whisper-large-v3")
            entrada = trans.text
        except: pass

    guardar_memoria(user_id, "user", entrada)
    
    respuesta_final = ""
    es_accion_admin = False
    
    # ====================================================
    # 🚨 COMANDOS ADMIN (FREDY)
    # ====================================================
    if user_id == ADMIN_ID:
        texto_lower = entrada.lower()
        
        # --- LISTA EXTENSIVA DE PALABRAS CLAVE PARA VER USUARIOS ---
        frases_ver = [
            "cuantos usuarios", "cuántos usuarios", "cuantos hay", "cuántos hay", 
            "total de usuarios", "cantidad de usuarios", "numero de usuarios",
            "ver usuarios", "listar usuarios", "lista de usuarios", "muestrame los usuarios",
            "muéstramelos", "muéstramelo", "enseñame los usuarios", "quien se registro",
            "quienes estan", "registrados", "usuarios nuevos", "clientes", "gente"
        ]
        
        # --- LISTA PARA BORRAR ---
        frases_borrar = ["borrar", "eliminar", "quita", "saca", "funar", "bórralos", "elimínalos", "banea", "banear"]

        # >>> ACCIÓN 1: VER REPORTE COMPLETO <<<
        if any(f in texto_lower for f in frases_ver):
            es_accion_admin = True
            await context.bot.send_chat_action(chat_id=user_id, action="typing")
            
            try:
                # 1. Contar TOTAL (Exacto)
                # head=True nos da solo el numero sin descargar todos los datos (más rápido)
                conteo = supabase.table("profiles").select("*", count="exact", head=True).execute()
                total = conteo.count
                
                # 2. Traer los últimos 10 DETALLADOS
                res = supabase.table("profiles").select("email, created_at").order("created_at", desc=True).limit(10).execute()
                users = res.data
                
                msg = f"💎 **REPORTE DEL IMPERIO KLMZ** 💎\n\n"
                msg += f"📊 **Total Registrados:** `{total}`\n"
                msg += f"📅 **Últimos 10 Clientes:**\n\n"
                
                if users:
                    for u in users:
                        # Formato fecha simple (YYYY-MM-DD)
                        fecha = u.get('created_at', '').split('T')[0]
                        email = u.get('email', 'Sin Email')
                        msg += f"👤 `{email}` — {fecha}\n"
                else:
                    msg += "Aún no hay nadie papito, ¡a meterle tráfico!\n"
                
                respuesta_final = msg
                
            except Exception as e:
                respuesta_final = f"Ay mor, error en la base de datos (Revisa la Service Key): {str(e)}"

        # >>> ACCIÓN 2: BORRAR USUARIOS <<<
        elif any(f in texto_lower for f in frases_borrar):
            # Buscar emails
            emails = re.findall(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', entrada)
            
            if emails:
                es_accion_admin = True
                await context.bot.send_chat_action(chat_id=user_id, action="typing")
                reporte = []
                try:
                    # Traer lista interna de Auth
                    users_auth = supabase.auth.admin.list_users()
                    
                    for email_target in emails:
                        uid = None
                        for u in users_auth:
                            if u.email == email_target:
                                uid = u.id
                                break
                        
                        if uid:
                            supabase.auth.admin.delete_user(uid)
                            reporte.append(f"✅ `{email_target}` -> **ELIMINADO**")
                        else:
                            reporte.append(f"⚠️ `{email_target}` -> No encontrado.")
                    
                    respuesta_final = "Limpieza terminada mi Rey:\n\n" + "\n".join(reporte)
                except Exception as e:
                    respuesta_final = f"Error borrando (Necesito Service Role Key): {str(e)}"

    # ====================================================
    # 💬 CHARLA (IA)
    # ====================================================
    if not es_accion_admin:
        try:
            pide_voz = any(p in entrada.lower() for p in ["audio", "voz", "habla", "saludame", "oirte", "dime"])
            salida_audio = es_audio or pide_voz
            
            accion = "record_voice" if salida_audio else "typing"
            await context.bot.send_chat_action(chat_id=user_id, action=accion)
            
            historial = obtener_historial(user_id)
            mensajes = [{"role": "system", "content": SYSTEM_PROMPT}] + historial
            
            chat = groq_client.chat.completions.create(messages=mensajes, model=MODELO_CHAT_GROQ)
            respuesta_final = chat.choices[0].message.content
            
            guardar_memoria(user_id, "assistant", respuesta_final)
            
            if salida_audio:
                await enviar_audio(update, context, respuesta_final)
                return
        except:
            respuesta_final = "Mor, repetime que no te escuché bien."

    # Enviar Texto
    if respuesta_final:
        if es_accion_admin: guardar_memoria(user_id, "assistant", respuesta_final)
        await update.message.reply_text(respuesta_final, parse_mode="Markdown")

# ==========================================
# 👁️ VIGILANTE (NOTIFICACIONES)
# ==========================================
ultimo_id_usuario = 0

async def vigilar_sitio(context: ContextTypes.DEFAULT_TYPE):
    global ultimo_id_usuario
    try:
        # Busca el ID más alto en profiles
        res = supabase.table("profiles").select("id, email").order("id", desc=True).limit(1).execute()
        if res.data:
            nuevo = res.data[0]
            if nuevo['id'] > ultimo_id_usuario:
                if ultimo_id_usuario != 0:
                    msg = f"💎 **¡NUEVA PLATA PAPITO!** 💎\n\nUsuario: `{nuevo['email']}`\n\n¡Sigue facturando Morazán! 🇸🇻💸"
                    await context.bot.send_message(chat_id=ADMIN_ID, text=msg, parse_mode="Markdown")
                ultimo_id_usuario = nuevo['id']
    except: pass

# ==========================================
# 🚀 SERVER FLASK
# ==========================================
app_flask = Flask('')
@app_flask.route('/')
def home(): return "<h1>KLMZ TODO PODEROSO ONLINE</h1>"

def run_flask():
    app_flask.run(host='0.0.0.0', port=8080)

if __name__ == "__main__":
    Thread(target=run_flask).start()
    bot = Application.builder().token(TELEGRAM_TOKEN).build()
    bot.add_handler(MessageHandler(filters.TEXT | filters.VOICE, handle_message))
    bot.job_queue.run_repeating(vigilar_sitio, interval=30, first=5)
    print(f"🚀 KLMZ FINAL LISTA | PATRÓN: FREDY | ID: {ADMIN_ID}")
    bot.run_polling()
