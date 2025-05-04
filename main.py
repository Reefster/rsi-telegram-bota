from telegram.ext import ApplicationBuilder, MessageHandler, filters
from telegram import Update
from telegram.ext import ContextTypes

# === BOT TOKEN ===
BOT_TOKEN = "7761091287:AAGEW8OcnfMFUt5_DmAIzBm2I63YgHAcia4"  # Kendi bot token'ını buraya yaz

# === Mesaj Geldiğinde Çalışacak Fonksiyon ===
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    print(f"Chat Title: {chat.title}")
    print(f"Chat ID: {chat.id}")
    
    msg = f"Bu grubun (veya kişinin) Chat ID'si:\n`{chat.id}`"
    await context.bot.send_message(chat_id=chat.id, text=msg, parse_mode="Markdown")

# === Botu Başlat ===
if __name__ == "__main__":
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(MessageHandler(filters.ALL, handle_message))
    print("Bot aktif. Gruba veya bota mesaj at, chat ID görünsün...")
    app.run_polling()