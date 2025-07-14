# Точка входа для запуска Telegram-бота


from aiogram import Bot, Dispatcher, types
import asyncio
import os

API_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN', 'YOUR_BOT_TOKEN')

bot = Bot(token=API_TOKEN)
dp = Dispatcher()

@dp.message()
async def echo_handler(message: types.Message):
    await message.answer("Бот запущен и готов к работе!")

def main():
    print("Starting Telegram bot...")
    asyncio.run(dp.start_polling(bot))

if __name__ == "__main__":
    main()
