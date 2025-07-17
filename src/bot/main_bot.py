# Main entrance point to start Telegram-bot

from aiogram import Bot, Dispatcher, types
from aiogram.fsm.storage.memory import MemoryStorage
import asyncio
from dotenv import load_dotenv
import os
from src.bot.handlers import seller_handlers, common_handlers
from src.core.database.db_service import SessionLocal

# --- DB auto-creation logic ---
from src.core.database.db_service import engine
from src.core.database.models import Base

# Path to SQLite file (relative to project root)
DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'core', 'database', 'database.sqlite3')
if not os.path.exists(DB_PATH):
    print('Database file not found, creating tables...')
    Base.metadata.create_all(bind=engine)

load_dotenv()

API_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
API_BASE_URL = os.getenv('API_BASE_URL')
BOT_SECRET_TOKEN = os.getenv('BOT_SECRET_TOKEN')

bot = Bot(token=API_TOKEN)
dp = Dispatcher(storage=MemoryStorage())
bot.db = SessionLocal()

# Регистрация хендлеров
dp.message.register(common_handlers.handle_start, lambda m: m.text == "/start")
dp.message.register(common_handlers.handle_help, lambda m: m.text == "/help")
dp.message.register(seller_handlers.handle_register, lambda m: m.text == "/register")
dp.message.register(seller_handlers.process_register_xpub, seller_handlers.RegisterFSM.ask_xpub)
dp.message.register(seller_handlers.process_register_xpub, seller_handlers.RegisterFSM.get_xpub)
dp.message.register(seller_handlers.handle_deposit, lambda m: m.text == "/deposit")
dp.message.register(seller_handlers.handle_balance, lambda m: m.text == "/balance")
dp.message.register(seller_handlers.handle_create_invoice, lambda m: m.text == "/create_invoice")
dp.message.register(seller_handlers.handle_sweep, lambda m: m.text == "/sweep")
dp.message.register(seller_handlers.handle_buyers, lambda m: m.text == "/buyers")
dp.message.register(seller_handlers.handle_add_buyer, lambda m, state: m.text == "/add_buyer")

# FSM для создания инвойса
dp.message.register(seller_handlers.process_invoice_amount, seller_handlers.InvoiceFSM.amount)
dp.message.register(seller_handlers.process_invoice_description, seller_handlers.InvoiceFSM.description)
dp.message.register(seller_handlers.process_invoice_group, seller_handlers.InvoiceFSM.group)

# FSM для добавления покупателя/группы
dp.message.register(seller_handlers.process_add_buyer_id, seller_handlers.AddBuyerFSM.buyer_id)
dp.message.register(seller_handlers.process_add_buyer_group, seller_handlers.AddBuyerFSM.group_name)

def main():
    print("Starting Telegram bot...")
    asyncio.run(dp.start_polling(bot))

if __name__ == "__main__":
    main()
