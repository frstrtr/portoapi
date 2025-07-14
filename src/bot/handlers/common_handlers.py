# Обработчики /start, /help


from aiogram import types

async def handle_start(message: types.Message):
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add("/register", "/deposit", "/balance", "/create_invoice", "/sweep")
    await message.answer(
        "Добро пожаловать в платформу! Выберите действие:",
        reply_markup=kb
    )

async def handle_help(message: types.Message):
    await message.answer("Доступные команды: /register, /deposit, /balance, /create_invoice, /sweep")
