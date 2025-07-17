# Main entrance point to start Telegram-bot

import logging
from aiogram import Bot, Dispatcher, types
from aiogram.fsm.storage.memory import MemoryStorage
import asyncio
from dotenv import load_dotenv
import os
from src.bot.handlers import seller_handlers, common_handlers
from src.core.database.db_service import SessionLocal
import functools
# import signal
from aiogram.fsm.state import State


# --- Logging setup ---
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.FileHandler("bot.log", encoding="utf-8"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("bot")

# --- DB auto-creation logic ---
from src.core.database.db_service import engine
from src.core.database.models import Base

# Path to SQLite file (relative to project root)
DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'core', 'database', 'database.sqlite3')
if not os.path.exists(DB_PATH):
    logger.info('Database file not found, creating tables...')
    Base.metadata.create_all(bind=engine)

load_dotenv()

API_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
API_BASE_URL = os.getenv('API_BASE_URL')
BOT_SECRET_TOKEN = os.getenv('BOT_SECRET_TOKEN')

bot = Bot(token=API_TOKEN)
dp = Dispatcher(storage=MemoryStorage())
bot.db = SessionLocal()

def log_user_action(user: types.User, action: str, extra: str = ""):
    logger.info(f"User {user.id} ({user.username}): action={action} {extra}")

# --- Logging middleware for all messages ---
# @dp.message()
# async def log_message(message: types.Message, *args, **kwargs):
#     log_user_action(message.from_user, "message", f"text='{message.text}'")

# Регистрация хендлеров с логированием
def log_and_handle(handler, action_name):
    @functools.wraps(handler)
    async def wrapper(message: types.Message, *args, **kwargs):
        log_user_action(message.from_user, action_name, f"text='{message.text}'")
        return await handler(message, *args, **kwargs)
    return wrapper

async def main():
    logger.info("Starting Telegram bot...")

    # Register handlers with logging
    dp.message.register(log_and_handle(common_handlers.handle_start, "/start"), lambda m: m.text == "/start")
    dp.message.register(log_and_handle(common_handlers.handle_help, "/help"), lambda m: m.text == "/help")
    dp.message.register(log_and_handle(seller_handlers.handle_register, "/register"), lambda m: m.text == "/register")
    dp.message.register(log_and_handle(seller_handlers.process_register_xpub, "register_xpub_ask"), seller_handlers.RegisterFSM.ask_xpub)
    dp.message.register(log_and_handle(seller_handlers.process_register_xpub, "register_xpub_get"), seller_handlers.RegisterFSM.get_xpub)
    dp.message.register(log_and_handle(seller_handlers.handle_deposit, "/deposit"), lambda m: m.text == "/deposit")
    dp.message.register(log_and_handle(seller_handlers.handle_balance, "/balance"), lambda m: m.text == "/balance")
    dp.message.register(log_and_handle(seller_handlers.handle_create_invoice, "/create_invoice"), lambda m: m.text == "/create_invoice")
    dp.message.register(log_and_handle(seller_handlers.handle_sweep, "/sweep"), lambda m: m.text == "/sweep")
    dp.message.register(log_and_handle(seller_handlers.handle_buyers, "/buyers"), lambda m: m.text == "/buyers")
    dp.message.register(log_and_handle(seller_handlers.handle_add_buyer, "/add_buyer"), lambda m, state: m.text == "/add_buyer")
    dp.message.register(log_and_handle(seller_handlers.process_invoice_amount, "invoice_amount"), seller_handlers.InvoiceFSM.amount)
    dp.message.register(log_and_handle(seller_handlers.process_invoice_description, "invoice_description"), seller_handlers.InvoiceFSM.description)
    dp.message.register(log_and_handle(seller_handlers.process_invoice_group, "invoice_group"), seller_handlers.InvoiceFSM.group)
    # Register handler for custom state awaiting_group_name_for_invoice
    dp.message.register(
        log_and_handle(seller_handlers.process_group_name_for_invoice, "group_name_for_invoice"),
        State("awaiting_group_name_for_invoice")
    )
    dp.message.register(log_and_handle(seller_handlers.process_add_buyer_id, "add_buyer_id"), seller_handlers.AddBuyerFSM.buyer_id)
    dp.message.register(log_and_handle(seller_handlers.process_add_buyer_group, "add_buyer_group"), seller_handlers.AddBuyerFSM.group_name)

    try:
        await dp.start_polling(bot)
    except (KeyboardInterrupt, asyncio.CancelledError):
        logger.info("Bot shutdown requested. Shutting down gracefully...")
    finally:
        await bot.session.close()
        logger.info("Bot stopped.")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Bot stopped by user.")
