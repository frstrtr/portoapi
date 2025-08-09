# Main entrance point to start Telegram-bot

import logging
from aiogram import Bot, Dispatcher, types
from aiogram.fsm.storage.memory import MemoryStorage
import asyncio
from dotenv import load_dotenv
import os
import sys

# Add project root to Python path
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, project_root)

from src.bot.admin.admin_handlers import ADMINS, handle_admin_xpubs
import aiohttp
from aiogram.exceptions import TelegramNetworkError
from src.bot.handlers import seller_handlers, common_handlers
from src.core.database.db_service import SessionLocal
import functools

# import signal
from aiogram.fsm.state import State

# --- DB auto-creation logic ---
from src.core.database.db_service import engine, DATABASE_URL
from src.core.database.models import Base
import re

# --- Logging setup ---
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.FileHandler("bot.log", encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger("bot")

# Extract DB file path from DATABASE_URL
logger.info(f"Full DATABASE_URL: {DATABASE_URL}")
DB_PATH = DATABASE_URL.replace("sqlite:///", "")
logger.info(f"Resolved DB_PATH: {DB_PATH}")
if DB_PATH and not os.path.exists(DB_PATH):
    logger.info("Database file not found, creating tables...")
    Base.metadata.create_all(bind=engine)

load_dotenv()

API_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
API_BASE_URL = os.getenv("API_BASE_URL")
BOT_SECRET_TOKEN = os.getenv("BOT_SECRET_TOKEN")

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
        # Deduplication: Only handle each update_id once per process lifetime
        if not hasattr(wrapper, "handled_updates"):
            wrapper.handled_updates = set()
        update_id = getattr(message, "update_id", None)
        # If update_id is not available, fallback to message_id
        unique_id = (
            update_id if update_id is not None else getattr(message, "message_id", None)
        )
        if unique_id is not None:
            if unique_id in wrapper.handled_updates:
                logger.debug(
                    f"[Deduplication] Skipping duplicate update/message: {unique_id}"
                )
                return
            wrapper.handled_updates.add(unique_id)
        log_user_action(message.from_user, action_name, f"text='{message.text}'")
        try:
            return await handler(message, *args, **kwargs)
        except (
            TelegramNetworkError,
            aiohttp.client_exceptions.ClientConnectorError,
        ) as net_err:
            logger.error(
                f"[NetworkError] Handler '{action_name}' failed for user {message.from_user.id}: {net_err}"
            )
            # Optionally, notify admins here if desired
        except Exception as e:
            logger.exception(
                f"[HandlerError] Unexpected error in handler '{action_name}' for user {message.from_user.id}: {e}"
            )
        # Do not re-raise, so bot continues processing other updates

    return wrapper


async def main():
    dp.message.register(
        log_and_handle(seller_handlers.handle_invoices, "/invoices"),
        lambda m: m.text == "/invoices",
    )
    # Register admin commands globally
    dp.message.register(
        handle_admin_xpubs, lambda m: m.text and m.text.startswith("/admin_xpubs")
    )
    
    # Register /myaccount handler
    dp.message.register(
        log_and_handle(seller_handlers.handle_myaccount, "/myaccount"),
        lambda m: m.text == "/myaccount",
    )
    
    # Register gas station and keeper bot handlers
    dp.message.register(
        log_and_handle(seller_handlers.handle_gasstation, "/gasstation"),
        lambda m: m.text == "/gasstation",
    )
    dp.message.register(
        log_and_handle(seller_handlers.handle_keeper_status, "/keeper_status"),
        lambda m: m.text == "/keeper_status",
    )
    # Add alias without underscore for better UX
    dp.message.register(
        log_and_handle(seller_handlers.handle_keeper_status, "/keeperstatus"),
        lambda m: m.text == "/keeperstatus",
    )
    dp.message.register(
        log_and_handle(seller_handlers.handle_keeper_logs, "/keeper_logs"),
        lambda m: m.text == "/keeper_logs",
    )
    # Add alias without underscore for better UX
    dp.message.register(
        log_and_handle(seller_handlers.handle_keeper_logs, "/keeperlogs"),
        lambda m: m.text == "/keeperlogs",
    )
    dp.message.register(
        log_and_handle(seller_handlers.handle_gasstation_stake, "/gasstation_stake"),
        lambda m: m.text == "/gasstation_stake",
    )
    dp.message.register(
        log_and_handle(seller_handlers.handle_gasstation_delegate, "/gasstation_delegate"),
        lambda m: m.text == "/gasstation_delegate",
    )
    dp.message.register(
        log_and_handle(seller_handlers.handle_gasstation_withdraw, "/gasstation_withdraw"),
        lambda m: m.text == "/gasstation_withdraw",
    )
    
    logger.info("Starting Telegram bot...")


    # Register handler to cancel FSM state if main command is sent during an active FSM flow
    async def main_command_interrupt_predicate(message, state):
        if message.text in seller_handlers.MAIN_COMMANDS and state:
            current_state = await state.get_state()
            return current_state is not None
        return False

    dp.message.register(
        seller_handlers.handle_main_command_interrupt,
        main_command_interrupt_predicate,
    )

    # Register handlers with logging
    dp.message.register(
        log_and_handle(common_handlers.handle_start, "/start"),
        lambda m: m.text == "/start",
    )
    dp.message.register(
        log_and_handle(common_handlers.handle_help, "/help"),
        lambda m: m.text == "/help",
    )
    dp.message.register(
        log_and_handle(seller_handlers.handle_register, "/register"),
        lambda m: m.text == "/register",
    )
    dp.message.register(
        log_and_handle(seller_handlers.process_choose_account_action, "register_choose_account_action"),
        seller_handlers.RegisterFSM.choose_account_action,
    )
    dp.message.register(
        log_and_handle(seller_handlers.process_select_existing_account, "register_select_existing_account"),
        seller_handlers.RegisterFSM.select_existing_account,
    )
    dp.message.register(
        log_and_handle(seller_handlers.process_register_xpub, "register_xpub_ask"),
        seller_handlers.RegisterFSM.ask_xpub,
    )
    dp.message.register(
        log_and_handle(seller_handlers.process_register_xpub, "register_xpub_get"),
        seller_handlers.RegisterFSM.get_xpub,
    )
    dp.message.register(
        log_and_handle(seller_handlers.handle_deposit, "/deposit"),
        lambda m: m.text == "/deposit",
    )
    dp.message.register(
        log_and_handle(seller_handlers.handle_balance, "/balance"),
        lambda m: m.text == "/balance",
    )
    dp.message.register(
        log_and_handle(seller_handlers.handle_create_invoice, "/create_invoice"),
        lambda m: m.text == "/create_invoice",
    )
    dp.message.register(
        log_and_handle(seller_handlers.handle_sweep, "/sweep"),
        lambda m: m.text == "/sweep",
    )
    dp.message.register(
        log_and_handle(seller_handlers.handle_buyers, "/buyers"),
        lambda m: m.text == "/buyers",
    )
    dp.message.register(
        log_and_handle(seller_handlers.handle_add_buyer, "/add_buyer"),
        lambda m, state: m.text == "/add_buyer",
    )
    dp.message.register(
        log_and_handle(seller_handlers.process_invoice_amount, "invoice_amount"),
        seller_handlers.InvoiceFSM.amount,
    )
    dp.message.register(
        log_and_handle(
            seller_handlers.process_invoice_description, "invoice_description"
        ),
        seller_handlers.InvoiceFSM.description,
    )
    dp.message.register(
        log_and_handle(seller_handlers.process_invoice_group, "invoice_group"),
        seller_handlers.InvoiceFSM.group,
    )
    # Register handler for custom state awaiting_group_name_for_invoice
    dp.message.register(
        log_and_handle(
            seller_handlers.process_group_name_for_invoice, "group_name_for_invoice"
        ),
        seller_handlers.InvoiceFSM.awaiting_group_name_for_invoice,
    )
    dp.message.register(
        log_and_handle(seller_handlers.process_add_buyer_id, "add_buyer_id"),
        seller_handlers.AddBuyerFSM.buyer_id,
    )
    dp.message.register(
        log_and_handle(seller_handlers.process_add_buyer_xpub, "add_buyer_xpub"),
        seller_handlers.AddBuyerFSM.xpub,
    )
    # Register sweep mode choice FSM handler
    dp.message.register(
        log_and_handle(seller_handlers.process_sweep_mode_choice, "sweep_mode_choice"),
        seller_handlers.SweepFSM.choose_mode,
    )

    max_retries = 10
    base_delay = 5  # seconds
    attempt = 0
    notified_admins = False
    while True:
        try:
            logger.info(f"Starting polling (attempt {attempt + 1})...")
            await dp.start_polling(bot)
            break  # Exit loop if polling ends normally
        except (KeyboardInterrupt, asyncio.CancelledError):
            logger.info("Bot shutdown requested. Shutting down gracefully...")
            break
        except (
            aiohttp.client_exceptions.ClientConnectorError,
            TelegramNetworkError,
        ) as e:
            attempt += 1
            delay = min(base_delay * (2 ** (attempt - 1)), 300)  # Cap at 5 min
            logger.error(
                f"[RETRY] Network error: Cannot connect to Telegram API (attempt {attempt}/{max_retries}): {e}"
            )
            print(
                f"[ERROR] Cannot connect to Telegram API. Retry {attempt}/{max_retries} in {delay} seconds."
            )
            if attempt >= 3 and not notified_admins:
                # Notify admins after 3 failed attempts
                try:
                    for admin_id in ADMINS:
                        try:
                            await bot.send_message(
                                admin_id,
                                "❗️ Бот не может подключиться к Telegram API после нескольких попыток. Проверьте сервер или интернет.",
                            )
                        except Exception as notify_err:
                            logger.error(
                                f"Failed to notify admin {admin_id}: {notify_err}"
                            )
                    notified_admins = True
                except Exception as notify_outer:
                    logger.error(f"Failed to notify admins: {notify_outer}")
            if attempt >= max_retries:
                logger.critical(f"Max retries ({max_retries}) reached. Stopping bot.")
                break
            await asyncio.sleep(delay)
        except Exception as e:
            logger.exception(f"Unexpected error in polling: {e}")
            break
    await bot.session.close()
    logger.info("Bot stopped.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Bot stopped by user.")
