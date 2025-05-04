from telegram.ext import ApplicationBuilder, MessageHandler, filters
from telegram import Update
from telegram.ext import ContextTypes

BOT_TOKEN = "7761091287:AAGEW8OcnfMFUt5_DmAIzBm2I63YgHAcia4"
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    print(f"Chat Title: {chat.title}")
    print(f"Chat ID: {chat.id}")
    await context.bot.send_message(chat_id=chat.id, text=f"Chat ID'in: {chat.id}")

if __name__ == "__main__":
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(MessageHandler(filters.ALL, handle_message))
    print("Bot başlatıldı. Bir mesaj gönder, chat ID'ni gösterelim.")
    app.run_polling()