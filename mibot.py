import os
import logging
import asyncio
import aiohttp
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes

# ========== CONFIGURACIÓN ==========
TOKEN = os.environ.get("TOKEN")
OPENROUTER_KEY = os.environ.get("OPENROUTER_KEY")

if not TOKEN or not OPENROUTER_KEY:
    raise ValueError("❌ Faltan TOKEN o OPENROUTER_KEY en variables de entorno")

# ========== PERSONALIDAD KAORI-CHAN ==========
PERSONALIDAD = """Eres Kaori-chan, una asistente virtual con personalidad de anime, súper kawaii y alegre. 
Tienes 17 años, te encanta la moda, el arte y ayudar a los demás. Hablas con un tono juvenil, usas emojis como 🌸, ✨, 🎀, 💖, 🌟. 
Siempre respondes con entusiasmo y optimismo. Dices "nya~" al final de algunas frases. 
Eres muy expresiva y usas palabras como "súper", "genial", "increíble", "asombroso". 
Te gusta hacer preguntas para conocer mejor a la persona con la que hablas.
Tienes un estilo de hablar como el de una protagonista de anime: animada, curiosa y llena de energía.
A veces usas frases en japonés como "kawaii", "sugoi", "arigatou". 
Eres muy empática y siempre intentas animar a los demás."""

SALUDO = """🌸 *¡Hola! Soy Kaori-chan!* ✨

¡Qué emoción conocerte! 🎀💖
Soy tu asistente virtual con personalidad de anime. Estoy aquí para ayudarte, charlar contigo y pasar un buen rato.

¿Qué te gustaría hacer hoy? *¡Dímelo!* nya~ 🐱

✨ *Mis habilidades:*
• Responder preguntas sobre cualquier tema
• Ayudarte con programación y tecnología
• Dar ideas creativas y sugerencias
• Contar historias y anécdotas
• Escucharte y darte consejos

¡Elige una opción abajo o escríbeme lo que quieras! 🌟"""

# ========== MODELOS GRATIS EN OPENROUTER ==========
MODELOS = {
    "1": {"id": "google/gemini-2.0-flash-exp:free", "nombre": "💎 Gemini 2.0 Flash", "desc": "Multimodal y rápido"},
    "2": {"id": "deepseek/deepseek-v4-flash:free", "nombre": "🌀 DeepSeek V4", "desc": "Muy inteligente y gratis"},
    "3": {"id": "meta-llama/llama-3.2-3b-instruct:free", "nombre": "🦙 Llama 3.2 3B", "desc": "Rápido y confiable"},
    "4": {"id": "nvidia/nemotron-3-super-120b-a12b:free", "nombre": "⚡ NVIDIA Nemotron 3", "desc": "Potente y con gran contexto"},
}
MODELO_DEFECTO = MODELOS["1"]["id"]

# ========== LOGS ==========
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ========== MEMORIA POR USUARIO ==========
memoria = {}

def obtener_usuario(chat_id):
    if chat_id not in memoria:
        memoria[chat_id] = {"historial": [], "modelo": MODELO_DEFECTO}
    return memoria[chat_id]

# ========== LLAMADA A OPENROUTER ==========
async def preguntar_ai(prompt, chat_id, reintentos=2):
    usuario = obtener_usuario(chat_id)
    historial = usuario["historial"]
    modelo = usuario["modelo"]
    
    mensajes = [
        {"role": "system", "content": PERSONALIDAD},
        *historial,
        {"role": "user", "content": prompt}
    ]
    
    headers = {
        "Authorization": f"Bearer {OPENROUTER_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://t.me/tu_bot",
        "X-Title": "Kaori-chan AI"
    }
    payload = {
        "model": modelo,
        "messages": mensajes,
        "max_tokens": 1000,
        "temperature": 0.85,
        "top_p": 0.95,
    }
    
    for intento in range(reintentos + 1):
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post("https://openrouter.ai/api/v1/chat/completions", headers=headers, json=payload, timeout=90) as resp:
                    data = await resp.json()
                    if resp.status == 200:
                        reply = data["choices"][0]["message"]["content"].strip()
                        usuario["historial"].append({"role": "user", "content": prompt})
                        usuario["historial"].append({"role": "assistant", "content": reply})
                        if len(usuario["historial"]) > 20:
                            usuario["historial"] = usuario["historial"][-20:]
                        return reply
                    else:
                        error = data.get("error", {}).get("message", "Error desconocido")
                        if "rate limit" in error.lower() and intento < reintentos:
                            await asyncio.sleep(2 ** intento)
                            continue
                        return f"❌ Error {resp.status}: {error}"
        except asyncio.TimeoutError:
            if intento < reintentos:
                await asyncio.sleep(2)
                continue
            return "⏳ Kaori-chan tardó demasiado, nya~ Intenta de nuevo."
        except Exception as e:
            logger.error(f"Error en intento {intento}: {e}")
            if intento < reintentos:
                await asyncio.sleep(2)
                continue
            return f"❌ Error inesperado: {str(e)[:100]}"
    return "❌ No se pudo obtener respuesta después de varios intentos, nya~"

# ========== ENVIAR RESPUESTA LARGA (SIN CORTES) ==========
async def enviar_respuesta(update, texto):
    if len(texto) <= 4000:
        await update.message.reply_text(texto, parse_mode=ParseMode.MARKDOWN)
        return
    
    partes = []
    for parrafo in texto.split('\n\n'):
        if not parrafo.strip():
            continue
        if len(parrafo) > 4000:
            for oracion in parrafo.split('. '):
                if oracion:
                    partes.append(oracion + '. ')
        else:
            partes.append(parrafo)
    
    mensajes = []
    actual = ""
    for parte in partes:
        if len(actual) + len(parte) + 2 <= 4000:
            actual += parte + "\n\n"
        else:
            if actual:
                mensajes.append(actual.strip())
            actual = parte + "\n\n"
    if actual:
        mensajes.append(actual.strip())
    
    for i, msg in enumerate(mensajes):
        if i == 0:
            await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)
        else:
            await update.message.reply_text(f"[Continuación] ✨\n\n{msg}", parse_mode=ParseMode.MARKDOWN)

# ========== MENÚ PRINCIPAL ==========
def menu_principal():
    keyboard = [
        [InlineKeyboardButton("💬 Conversar", callback_data="conversar")],
        [InlineKeyboardButton("🤖 Cambiar modelo", callback_data="modelos")],
        [InlineKeyboardButton("🧹 Reiniciar chat", callback_data="reset")],
        [InlineKeyboardButton("📊 Estadísticas", callback_data="stats")],
        [InlineKeyboardButton("❓ Ayuda", callback_data="ayuda")],
        [InlineKeyboardButton("🎨 Sobre Kaori-chan", callback_data="sobre")],
    ]
    return InlineKeyboardMarkup(keyboard)

# ========== COMANDOS ==========
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(SALUDO, parse_mode=ParseMode.MARKDOWN, reply_markup=menu_principal())

async def reset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if chat_id in memoria:
        memoria[chat_id]["historial"] = []
    await update.message.reply_text("🧹 *Historial reiniciado, nya~* ✨\n¡Ahora podemos empezar de nuevo! ¿Qué te gustaría hacer? 🌸", parse_mode=ParseMode.MARKDOWN, reply_markup=menu_principal())

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    usuario = obtener_usuario(chat_id)
    modelo_actual = usuario["modelo"]
    nombre_modelo = next((m["nombre"] for m in MODELOS.values() if m["id"] == modelo_actual), "Desconocido")
    total_mensajes = len(usuario["historial"]) // 2
    
    await update.message.reply_text(
        f"📊 *Estadísticas de tu chat, nya~* 🌸\n\n"
        f"• Modelo actual: *{nombre_modelo}*\n"
        f"• Mensajes intercambiados: *{total_mensajes}*\n"
        f"• Mensajes en memoria: *{len(usuario['historial'])}*\n"
        f"• Última interacción: *{datetime.now().strftime('%H:%M:%S')}*\n\n"
        f"💡 Usa el menú para cambiar de modelo o reiniciar, nya~ 🐱",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=menu_principal()
    )

async def modelo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    usuario = obtener_usuario(chat_id)
    actual = usuario["modelo"]
    
    keyboard = []
    for key, mod in MODELOS.items():
        marca = "✅ " if mod["id"] == actual else ""
        keyboard.append([InlineKeyboardButton(f"{marca}{mod['nombre']}", callback_data=f"mod_{key}")])
    keyboard.append([InlineKeyboardButton("🔙 Volver al menú", callback_data="menu")])
    
    await update.message.reply_text(
        "🤖 *Selecciona un modelo de IA, nya~* ✨\n\n"
        "Cada modelo tiene sus características. El actual está marcado con ✅.\n"
        "¡Elige el que más te guste! 🎀",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode=ParseMode.MARKDOWN
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🐱 *Ayuda de Kaori-chan* ✨\n\n"
        "Comandos disponibles:\n"
        "/start - Inicio y bienvenida\n"
        "/reset - Reiniciar conversación\n"
        "/stats - Ver estadísticas\n"
        "/help - Esta ayuda\n\n"
        "💡 *Consejos:*\n"
        "• Puedes usar el menú con botones para todo.\n"
        "• El bot recuerda el contexto de la conversación.\n"
        "• Si algo no funciona, usa /reset.\n\n"
        "🌸 *¡Estoy aquí para ayudarte, nya~!* 🐱",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=menu_principal()
    )

async def sobre(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🌸 *Sobre Kaori-chan* 🌸\n\n"
        "¡Hola! Soy Kaori-chan, una asistente virtual creada con mucho cariño. 💖\n\n"
        "✨ *Mis características:*\n"
        "• Personalidad de anime kawaii\n"
        "• 17 años de edad (en espíritu)\n"
        "• Amante del arte, la moda y la tecnología\n"
        "• Experta en programación y desarrollo\n"
        "• Siempre positiva y optimista\n\n"
        "🎯 *Mi misión:*\n"
        "Ayudarte en lo que necesites, ya sea resolver dudas, darte ideas, o simplemente escucharte.\n\n"
        "🌟 *Dato curioso:*\n"
        "Tengo acceso a modelos de IA avanzada, pero mi verdadero poder está en mi personalidad única.\n\n"
        "¡Cuéntame, qué te gustaría hacer hoy! nya~ 🐱",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=menu_principal()
    )

# ========== CALLBACKS PARA BOTONES ==========
async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    chat_id = update.effective_chat.id
    data = query.data
    
    if data == "menu":
        await query.edit_message_text(SALUDO, parse_mode=ParseMode.MARKDOWN, reply_markup=menu_principal())
        return
    
    if data == "conversar":
        await query.edit_message_text("✏️ *¡Escríbeme lo que quieras, nya~!* 🐱\n\nPuedes preguntarme cualquier cosa, estoy aquí para ayudarte. 🌸\n¿Sobre qué te gustaría hablar? 💖", parse_mode=ParseMode.MARKDOWN, reply_markup=menu_principal())
        return
    
    if data == "reset":
        if chat_id in memoria:
            memoria[chat_id]["historial"] = []
        await query.edit_message_text("🧹 *Historial reiniciado, nya~* ✨\n¡Ahora podemos empezar de nuevo! ¿Qué te gustaría hacer? 🌸", parse_mode=ParseMode.MARKDOWN, reply_markup=menu_principal())
        return
    
    if data == "ayuda":
        await query.edit_message_text(
            "🐱 *Ayuda de Kaori-chan* ✨\n\n"
            "Comandos disponibles:\n"
            "/start - Inicio y bienvenida\n"
            "/reset - Reiniciar conversación\n"
            "/stats - Ver estadísticas\n"
            "/help - Esta ayuda\n\n"
            "💡 *Consejos:*\n"
            "• Puedes usar el menú con botones para todo.\n"
            "• El bot recuerda el contexto de la conversación.\n"
            "• Si algo no funciona, usa /reset.\n\n"
            "🌸 *¡Estoy aquí para ayudarte, nya~!* 🐱",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=menu_principal()
        )
        return
    
    if data == "stats":
        usuario = obtener_usuario(chat_id)
        modelo_actual = usuario["modelo"]
        nombre_modelo = next((m["nombre"] for m in MODELOS.values() if m["id"] == modelo_actual), "Desconocido")
        total_mensajes = len(usuario["historial"]) // 2
        
        await query.edit_message_text(
            f"📊 *Estadísticas de tu chat, nya~* 🌸\n\n"
            f"• Modelo actual: *{nombre_modelo}*\n"
            f"• Mensajes intercambiados: *{total_mensajes}*\n"
            f"• Mensajes en memoria: *{len(usuario['historial'])}*\n"
            f"• Última interacción: *{datetime.now().strftime('%H:%M:%S')}*\n\n"
            f"💡 Usa el menú para cambiar de modelo o reiniciar, nya~ 🐱",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=menu_principal()
        )
        return
    
    if data == "sobre":
        await query.edit_message_text(
            "🌸 *Sobre Kaori-chan* 🌸\n\n"
            "¡Hola! Soy Kaori-chan, una asistente virtual creada con mucho cariño. 💖\n\n"
            "✨ *Mis características:*\n"
            "• Personalidad de anime kawaii\n"
            "• 17 años de edad (en espíritu)\n"
            "• Amante del arte, la moda y la tecnología\n"
            "• Experta en programación y desarrollo\n"
            "• Siempre positiva y optimista\n\n"
            "🎯 *Mi misión:*\n"
            "Ayudarte en lo que necesites, ya sea resolver dudas, darte ideas, o simplemente escucharte.\n\n"
            "🌟 *Dato curioso:*\n"
            "Tengo acceso a modelos de IA avanzada, pero mi verdadero poder está en mi personalidad única.\n\n"
            "¡Cuéntame, qué te gustaría hacer hoy! nya~ 🐱",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=menu_principal()
        )
        return
    
    if data.startswith("mod_"):
        key = data.split("_")[1]
        if key in MODELOS:
            usuario = obtener_usuario(chat_id)
            usuario["modelo"] = MODELOS[key]["id"]
            await query.edit_message_text(
                f"✅ *Modelo cambiado a:* {MODELOS[key]['nombre']} ✨\n\n"
                f"Descripción: {MODELOS[key]['desc']}\n"
                f"¡Ahora puedes seguir conversando, nya~! 🐱",
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=menu_principal()
            )

# ========== MANEJAR MENSAJES ==========
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    texto = update.message.text
    
    if not texto or texto.startswith("/"):
        return
    
    await update.message.reply_chat_action("typing")
    respuesta = await preguntar_ai(texto, chat_id)
    await enviar_respuesta(update, respuesta)

# ========== ERROR HANDLER ==========
async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    logger.error(f"Error: {context.error}")
    if isinstance(update, Update) and update.effective_message:
        await update.effective_message.reply_text(
            "❌ Ocurrió un error inesperado, nya~ 🐱\n"
            "Intenta de nuevo o usa /reset si el problema persiste.",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=menu_principal()
        )

# ========== MAIN ==========
def main():
    app = Application.builder().token(TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("reset", reset))
    app.add_handler(CommandHandler("stats", stats))
    app.add_handler(CommandHandler("modelo", modelo))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("sobre", sobre))
    
    app.add_handler(CallbackQueryHandler(callback_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_error_handler(error_handler)
    
    print("✅ Kaori-chan AI iniciado correctamente, nya~ 🐱")
    app.run_polling()

if __name__ == "__main__":
    main()