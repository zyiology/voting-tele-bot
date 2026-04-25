import logging

from telegram.ext import Application, CallbackQueryHandler, CommandHandler

from voting_bot.config import load_config
from voting_bot.db import Database
from voting_bot.handlers.callbacks import handle_callback
from voting_bot.handlers.commands import closepoll, help_command, scorepoll, start


def main() -> None:
    config = load_config()
    logging.basicConfig(
        level=config.log_level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)

    db = Database(config.database_url)

    async def post_init(app: Application) -> None:
        await db.connect()
        app.bot_data["db"] = db
        app.bot_data["config"] = config

    async def post_shutdown(app: Application) -> None:
        await db.close()

    app = (
        Application.builder()
        .token(config.telegram_bot_token)
        .post_init(post_init)
        .post_shutdown(post_shutdown)
        .build()
    )
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("scorepoll", scorepoll))
    app.add_handler(CommandHandler("closepoll", closepoll))
    app.add_handler(CallbackQueryHandler(handle_callback))

    app.run_polling()


if __name__ == "__main__":
    main()
