from telegram import Update
from telegram.ext import ContextTypes


async def reply(update: Update, text: str) -> None:
    message = update.effective_message
    if message is None:
        return

    await message.reply_text(text)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await reply(
        update,
        "Hi! I run score voting polls. Use /scorepoll in a group to start one.",
    )


async def scorepoll(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await reply(
        update,
        "scorepoll received — voting logic not implemented yet.",
    )