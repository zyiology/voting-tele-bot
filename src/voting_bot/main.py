import logging

from telegram.ext import Application, CommandHandler

from voting_bot.config import load_config
from voting_bot.handlers.commands import scorepoll, start


def main() -> None:
    config = load_config()
    logging.basicConfig(
        level=config.log_level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    app = Application.builder().token(config.telegram_bot_token).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("scorepoll", scorepoll))

    app.run_polling()


if __name__ == "__main__":
    main()
