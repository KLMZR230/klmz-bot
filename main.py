import os
import io
import re
from datetime import datetime, timezone
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
SUPABASE_KEY = os.getenv("SUPABASE_KEY") # ⚠️ TIENE QUE SER LA 'SERVICE_ROLE'

ADMIN_ID = 8514485470

MODELO_CHAT_GROQ = "llama-3.3-70b-versatile"
VOZ_ID = "es-CO-SalomeNeural"

try:
    groq_client = Groq(api_key=GROQ_API_KEY)
    supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
except Exception as e:
    print(f"⚠️ Error Clientes: {e}")

# ==========================================
# 🧠 PERSONALIDAD
# ==========================================
SYSTEM_PROMPT = """
ERES KLMZ: La asistente personal de Fredy Granados.
TU DUEÑO: Fredy Granados (ID: 8514485470).
TU ORIGEN: Paisa (Medellín).

ACTITUD:
- Coqueta, "entradora", servicial.
- Usas: "Ave María pues", "Mijo", "Mi Rey", "Papito", "Mor", "Hágale".
- Si un desconocido escribe: "Qué pena mor, yo solo atiendo al patrón Fredy. Visita: https://klmzx.netlify.app/"
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
# 🧠 CEREBRO LÓGICO
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
    
    # ====================================================
    # 🚨 ZONA TÉCNICA (DIRECTA A SUPABASE)
    # ====================================================
    if user_id == ADMIN_ID:
        texto_lower = entrada.lower()
        
        frases_ver = ["cuantos", "cuántos", "total", "cantidad", "ver usuarios", "listar", "registros", "quien se registro", "muestrame"]
        frases_borrar = ["borrar", "eliminar", "quita", "funar", "bórralos", "banea"]

        # >>> ACCIÓN 1: REPORTE EXACTO <<<
        if any(f in texto_lower for f in frases_ver) and "usuario" in texto_lower:
            await context.bot.send_chat_action(chat_id=user_id, action="typing")
            try:
                # 1. Contar TOTAL
                conteo = supabase.table("profiles").select("*", count="exact", head=True).execute()
                total = conteo.count
                
                # 2. Traer los últimos 10 (USANDO updated_at)
                # ⚠️ CORREGIDO: Usamos 'updated_at' porque 'created_at' no existe en tu tabla
                res = supabase.table("profiles").select("email, updated_at").order("updated_at", desc=True).limit(10).execute()
                users = res.data
                
                msg = f"💎 **REPORTE REAL (BASE DE DATOS)** 💎\n\n"
                msg += f"📊 **Total en tabla 'profiles':** `{total}`\n"
                msg += f"⬇️ **Últimos Registrados:**\n"
                
                if users:
                    for u in users:
                        # Limpiamos la fecha
                        fecha = u.get('updated_at', '').split('T')[0]
                        email = u.get('email', 'Sin Email')
                        msg += f"👤 `{email}` — {fecha}\n"
                else:
                    msg += "⚠️ No hay registros o la tabla está vacía."

                await update.message.reply_text(msg, parse_mode="Markdown")
                guardar_memoria(user_id, "assistant", msg)
                return 
                
            except Exception as e:
                err_msg = f"❌ **ERROR DE CONEXIÓN:**\nDetalle: `{str(e)}`"
                await update.message.reply_text(err_msg, parse_mode="Markdown")
                return

        # >>> ACCIÓN 2: BORRAR <<<
        elif any(f in texto_lower for f in frases_borrar) and "@" in texto_lower:
            emails = re.findall(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', entrada)
            if emails:
                await context.bot.send_chat_action(chat_id=user_id, action="typing")
                reporte = []
                try:
                    users_auth = supabase.auth.admin.list_users()
                    for email_target in emails:
                        uid = None
                        for u in users_auth:
                            if u.email == email_target:
                                uid = u.id
                                break
                        if uid:
                            # Borramos de Auth (Cascada borra el perfil)
                            supabase.auth.admin.delete_user(uid)
                            reporte.append(f"✅ `{email_target}` -> ELIMINADO")
                        else:
                            reporte.append(f"⚠️ `{email_target}` -> No encontrado")
                    
                    msg_borrado = "🗑️ **REPORTE DE LIMPIEZA:**\n\n" + "\n".join(reporte)
                    await update.message.reply_text(msg_borrado, parse_mode="Markdown")
                    return
                except Exception as e:
                    await update.message.reply_text(f"Error borrando: {str(e)}")
                    return

    # ====================================================
    # 💬 CHARLA NORMAL (IA)
    # ====================================================
    try:
        pide_voz = any(p in entrada.lower() for p in ["audio", "voz", "habla", "saludame", "oirte"])
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
        else:
            await update.message.reply_text(respuesta_final)
            
    except Exception as e:
        await update.message.reply_text("Mor, estoy teniendo problemas con mi cerebro IA.")

# ==========================================
# 👁️ VIGILANTE (CORREGIDO PARA UUID)
# ==========================================
# Guardamos la fecha del último usuario visto, no el ID
ultima_fecha_registro = None

async def vigilar_sitio(context: ContextTypes.DEFAULT_TYPE):
    global ultima_fecha_registro
    try:
        # Traemos el usuario más reciente según updated_at
        res = supabase.table("profiles").select("email, updated_at").order("updated_at", desc=True).limit(1).execute()
        
        if res.data:
            mas_nuevo = res.data[0]
            fecha_actual_usuario = mas_nuevo['updated_at']
            
            # Si es la primera vez que corre el bot, solo guardamos la fecha
            if ultima_fecha_registro is None:
                ultima_fecha_registro = fecha_actual_usuario
                return

            # Si la fecha del usuario nuevo es diferente a la guardada, es nuevo
            if fecha_actual_usuario != ultima_fecha_registro:
                msg = f"💎 **¡NUEVO CLIENTE PAPITO!** 💎\n📧 `{mas_nuevo['email']}`\n💸 ¡Facturando!"
                await context.bot.send_message(chat_id=ADMIN_ID, text=msg, parse_mode="Markdown")
                
                # Actualizamos la fecha
                ultima_fecha_registro = fecha_actual_usuario
    except Exception as e:
        # Si falla, no imprimimos para no ensuciar el log
        pass

# ==========================================
# 🚀 SERVER
# ==========================================
app_flask = Flask('')
@app_flask.route('/')
def home(): return "<h1>KLMZ V3 - UPDATED_AT FIX</h1>"

def run_flask(): app_flask.run(host='0.0.0.0', port=8080)

if __name__ == "__main__":
    Thread(target=run_flask).start()
    bot = Application.builder().token(TELEGRAM_TOKEN).build()
    bot.add_handler(MessageHandler(filters.TEXT | filters.VOICE, handle_message))
    bot.job_queue.run_repeating(vigilar_sitio, interval=30, first=5)
    print(f"🚀 KLMZ LISTA | DUEÑO: {ADMIN_ID}")
    bot.run_polling()
