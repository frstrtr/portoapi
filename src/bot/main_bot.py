# Точка входа для запуска Telegram-бота



from aiogram import Bot, Dispatcher, types
from aiogram.fsm.storage.memory import MemoryStorage
import asyncio
import os
from handlers import seller_handlers, common_handlers

API_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN', 'YOUR_BOT_TOKEN')

bot = Bot(token=API_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

# Регистрация хендлеров
dp.message.register(common_handlers.handle_start, lambda m: m.text == "/start")
dp.message.register(common_handlers.handle_help, lambda m: m.text == "/help")
dp.message.register(seller_handlers.handle_register, lambda m: m.text == "/register")
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
