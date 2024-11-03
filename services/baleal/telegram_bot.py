import os
import traceback
from datetime import time
from functools import wraps
from dotenv import load_dotenv
from zoneinfo import ZoneInfo
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes, Application
from instagram_poster import get_oldest_link_from_waiting_list, save_posted_link, post_url, URL_FILE, add_back_to_waiting_list

# Load environment variables from the .env file
load_dotenv()

# Initialize Telegram bot with token from .env file
app = ApplicationBuilder().token(os.getenv("TELEGRAM_TOKEN")).build()

ADMIN_USER_IDS = [1064553139, 4502793438]


async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle errors and send them to admin users."""
    # Get the error from the context
    error = context.error

    # Create detailed error message
    tb_list = traceback.format_exception(None, error, error.__traceback__)
    tb_string = ''.join(tb_list)

    # Create the message to be sent
    update_str = update.to_dict() if isinstance(update, Update) else str(update)
    message = (
        f'An exception occurred:\n'
        f'Update: {update_str}\n'
        f'Error: {str(error)}\n'
        f'Traceback:\n{tb_string}'
    )

    # Send error message to each admin
    for admin_id in ADMIN_USER_IDS:
        try:
            await context.bot.send_message(
                chat_id=admin_id,
                text=message[:4000]  # Telegram message length limit
            )
        except Exception as e:
            print(f"Failed to send error message to admin {admin_id}: {e}")


def handle_errors(func):
    @wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        try:
            return await func(update, context, *args, **kwargs)
        except Exception as e:
            # Log the error
            await error_handler(update, context)
            # Optionally send a user-friendly message to the user
            await update.message.reply_text(
                "Sorry, an error occurred while processing your request. "
                "The administrators have been notified."
            )
            raise e

    return wrapper


@handle_errors
async def save_url(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    url = update.message.text
    if "instagram.com/reel/" in url or "instagram.com/p/" in url:
        with open(URL_FILE, "a+") as file:
            file.write(url + "\n")
        await update.message.reply_text(f'URL saved: {url}')
    else:
        await update.message.reply_text('Please send a valid Instagram reel or post URL.')


SCHEDULE_TIMES = [  # 24 hour format
    time(9, 13, tzinfo=ZoneInfo(os.getenv("TZ"))),
    time(15, 49, tzinfo=ZoneInfo(os.getenv("TZ"))),

    time(20, 45, tzinfo=ZoneInfo(os.getenv("TZ"))),
    time(20, 56, tzinfo=ZoneInfo(os.getenv("TZ"))),
    time(20, 57, tzinfo=ZoneInfo(os.getenv("TZ"))),
    time(20, 58, tzinfo=ZoneInfo(os.getenv("TZ"))),
]


async def posting_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    """ Insta posting job """
    link_to_post = get_oldest_link_from_waiting_list()

    try:
        post_url(link_to_post)
        save_posted_link(link_to_post)
        await context.bot.send_message(context.job.chat_id, text=f"Uploaded one reel: {link_to_post}")
    except Exception as e:
        add_back_to_waiting_list(link_to_post)
        await context.bot.send_message(context.job.chat_id, text=f"Failed to upload: {link_to_post}\n{str(e)}")



def remove_job_if_exists(name: str, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Remove job with given name. Returns whether job was removed."""
    current_jobs = context.job_queue.get_jobs_by_name(name)
    if not current_jobs:
        return False
    for job in current_jobs:
        job.schedule_removal()
    return True


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Start the daily schedule."""
    chat_id = update.effective_message.chat_id

    # Remove existing jobs if any
    job_removed = remove_job_if_exists(str(chat_id), context)

    # Schedule messages for each specified time
    for schedule_time in SCHEDULE_TIMES:
        context.job_queue.run_daily(
            posting_job,
            time=schedule_time,
            chat_id=chat_id,
            name=str(chat_id),
            data=None,
        )

    # Format times for display
    times_str = ', '.join(t.strftime('%H:%M') for t in SCHEDULE_TIMES)
    text = f"Daily schedule set! Messages will be sent at: {times_str}"
    if job_removed:
        text += "\nOld schedule was removed."

    await update.effective_message.reply_text(text)


async def stop(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Stop the daily schedule."""
    chat_id = update.message.chat_id
    job_removed = remove_job_if_exists(str(chat_id), context)
    text = "Daily schedule cancelled!" if job_removed else "You have no active schedule."
    await update.message.reply_text(text)


async def check(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Check if there's an active schedule and when the next message will be sent."""
    chat_id = update.effective_message.chat_id
    jobs = context.job_queue.get_jobs_by_name(str(chat_id))

    if not jobs:
        await update.effective_message.reply_text("You have no active schedule.")
        return

    # Find the next scheduled message
    next_job = min(jobs, key=lambda job: job.next_t.timestamp())
    next_time = next_job.next_t.strftime('%H:%M')

    # Get all scheduled times
    times_str = ', '.join(t.strftime('%H:%M') for t in SCHEDULE_TIMES)

    await update.effective_message.reply_text(
        f"Your schedule is active!\n"
        f"Messages are sent daily at: {times_str}\n"
        f"Next message will be sent at: {next_time}"
    )


def main():
    application = Application.builder().token(os.getenv("TELEGRAM_TOKEN")).build()
    application.add_error_handler(error_handler)

    application.add_handler(CommandHandler('start', start))
    application.add_handler(CommandHandler('stop', stop))
    application.add_handler(CommandHandler('check', check))

    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, save_url))

    application.run_polling()


# Run bot
if __name__ == "__main__":
    print("Starting telegram bot...")
    main()
