import os

from dotenv import load_dotenv
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes

# Load environment variables from the .env file
load_dotenv()

# Initialize Telegram bot with token from .env file
app = ApplicationBuilder().token(os.getenv("TELEGRAM_TOKEN")).build()


async def save_url(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    url = update.message.text
    if "instagram.com/reel/" in url or "instagram.com/p/" in url:
        with open("urls_collection.txt", "a") as file:
            file.write(url + "\n")
        await update.message.reply_text(f'URL saved: {url}')
    else:
        await update.message.reply_text('Please send a valid Instagram reel or post URL.')


async def hello(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(f'Hello {update.effective_user.first_name}! You can send me Instagram reel or post URLs.')


# Add handlers
app.add_handler(CommandHandler("hello", hello))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, save_url))

# Run bot
if __name__ == "__main__":
    print("Starting telegram bot...")

    app.run_polling()
