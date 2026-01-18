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
# 🔐 CREDENCIALES
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
ERES KLMZ: Asistente personal de Fredy Granados.
TU DUEÑO: Fredy Granados (ID: 8514485470).
ACTITUD: Paisa, eficiente, leal.
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
# 🧠 CEREBRO JERÁRQUICO (NO FALLA)
# ==========================================
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    entrada = update.message.text or ""
    es_audio = False
    
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
    # 🚨 ZONA DE COMANDOS (LÓGICA BLINDADA)
    # ====================================================
    if user_id == ADMIN_ID:
        texto_lower = entrada.lower()
        
        # 1. LISTAS DE GATILLO
        k_crear = ["agrega", "agregar", "crear", "crea", "nuevo", "registra", "devuelve", "restaura", "recupera"]
        k_borrar = ["borrar", "eliminar", "quita", "funar", "bórralos", "elimina", "borra", "saca", "este", "ese", "tambien", "otro"]
        k_ver = ["usuario", "usuarios", "clientes", "registrados", "bd", "revisa", "cuantos", "total", "ver", "listar"]
        
        # 2. BANDERAS DE INTENCIÓN (BOOLEANOS)
        intencion_crear = any(k in texto_lower for k in k_crear)
        intencion_borrar = any(k in texto_lower for k in k_borrar)
        intencion_ver = any(k in texto_lower for k in k_ver)
        
        tiene_arroba = "@" in texto_lower

        # >>> JERARQUÍA 1: CREAR (GANA SIEMPRE) <<<
        if intencion_crear and tiene_arroba:
            await context.bot.send_chat_action(chat_id=user_id, action="typing")
            
            emails = re.findall(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', entrada)
            # Regex corregido para aceptar "contrasña" (typo)
            pass_match = re.search(r'(?:contraseña|contrasña|clave|pass)[:\s]+(\S+)', entrada, re.IGNORECASE)
            password_final = pass_match.group(1) if pass_match else "klmz123456"
            
            if emails:
                target = emails[0]
                try:
                    nuevo_user = supabase.auth.admin.create_user({
                        "email": target,
                        "password": password_final,
                        "email_confirm": True
                    })
                    msg = f"✅ **¡RESUCITADO CON ÉXITO!**\n\n👤 `{target}`\n🔑 `{password_final}`\n\n¡Bienvenido de vuelta, Admin! 💎"
                    await update.message.reply_text(msg, parse_mode="Markdown")
                    return
                except Exception as e:
                    await update.message.reply_text(f"⚠️ Error creando: {str(e)}")
                    return

        # >>> JERARQUÍA 2: BORRAR (SOLO SI NO ES CREAR) <<<
        elif intencion_borrar and tiene_arroba:
            # BLOQUEO DE SEGURIDAD: Si dice "agrega", aborta el borrado.
            if not intencion_crear:
                emails = re.findall(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', entrada)
                if emails:
                    await context.bot.send_chat_action(chat_id=user_id, action="typing")
                    reporte = []
                    try:
                        users_auth = supabase.auth.admin.list_users()
                        for target in emails:
                            uid = None
                            for u in users_auth:
                                if u.email == target:
                                    uid = u.id
                                    break
                            if uid:
                                supabase.auth.admin.delete_user(uid)
                                reporte.append(f"✅ `{target}` -> **ELIMINADO** 💀")
                            else:
                                reporte.append(f"⚠️ `{target}` -> No encontrado.")
                        
                        await update.message.reply_text("🗑️ **LIMPIEZA:**\n" + "\n".join(reporte), parse_mode="Markdown")
                        return
                    except Exception as e:
                        await update.message.reply_text(f"Error borrando: {str(e)}")
                        return

        # >>> JERARQUÍA 3: REPORTES <<<
        elif intencion_ver: 
            await context.bot.send_chat_action(chat_id=user_id, action="typing")
            try:
                conteo = supabase.table("profiles").select("*", count="exact", head=True).execute()
                res = supabase.table("profiles").select("email, updated_at").order("updated_at", desc=True).limit(10).execute()
                
                msg = f"💎 **DATOS REALES:** 💎\n📊 Total: `{conteo.count}`\n"
                if res.data:
                    for u in res.data:
                        f = u.get('updated_at', 'S/F').split('T')[0]
                        e = u.get('email', 'Anónimo')
                        msg += f"👤 `{e}` ({f})\n"
                else: msg += "⚠️ Vacío."
                
                await update.message.reply_text(msg, parse_mode="Markdown")
                return 
            except Exception as e:
                await update.message.reply_text(f"❌ Error: {str(e)}")
                return

    # ====================================================
    # 💬 CHARLA IA
    # ====================================================
    try:
        pide_voz = any(p in entrada.lower() for p in ["audio", "voz", "habla", "saludame"])
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
            
    except:
        await update.message.reply_text("Mor, estoy reiniciando neuronas...")

# ==========================================
# 👁️ VIGILANTE
# ==========================================
ultima_fecha_registro = None

async def vigilar_sitio(context: ContextTypes.DEFAULT_TYPE):
    global ultima_fecha_registro
    try:
        res = supabase.table("profiles").select("email, updated_at").order("updated_at", desc=True).limit(1).execute()
        if res.data:
            mas_nuevo = res.data[0]
            fecha_actual = mas_nuevo['updated_at']
            if ultima_fecha_registro is None:
                ultima_fecha_registro = fecha_actual
                return
            if fecha_actual != ultima_fecha_registro:
                email = mas_nuevo.get('email', 'Anónimo')
                msg = f"💎 **¡NUEVO CLIENTE!** 💎\n📧 `{email}`"
                await context.bot.send_message(chat_id=ADMIN_ID, text=msg, parse_mode="Markdown")
                ultima_fecha_registro = fecha_actual
    except: pass

# ==========================================
# 🚀 SERVER
# ==========================================
app_flask = Flask('')
@app_flask.route('/')
def home(): return "<h1>KLMZ FINAL V6 💎</h1>"

def run_flask(): app_flask.run(host='0.0.0.0', port=8080)

if __name__ == "__main__":
    Thread(target=run_flask).start()
    bot = Application.builder().token(TELEGRAM_TOKEN).build()
    bot.add_handler(MessageHandler(filters.TEXT | filters.VOICE, handle_message))
    bot.job_queue.run_repeating(vigilar_sitio, interval=30, first=5)
    print(f"🚀 KLMZ FINAL | DUEÑO: {ADMIN_ID}")
    bot.run_polling()
