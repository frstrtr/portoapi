# Обработчики /start, /help


from aiogram import types


async def handle_start(message: types.Message):
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add("/register", "/deposit", "/balance")
    kb.add("/create_invoice", "/sweep")
    kb.add("/buyers", "/add_buyer")
    await message.answer(
        "Добро пожаловать в платформу! Выберите действие:",
        reply_markup=kb
    )


async def handle_help(message: types.Message):
    await message.answer(
        "Доступные команды:\n"
        "/register — регистрация продавца\n"
        "/deposit — баланс газа\n"
        "/balance — общий баланс\n"
        "/create_invoice — создать инвойс\n"
        "/sweep — вывести средства\n"
        "/buyers — список покупателей/групп\n"
        "/add_buyer — добавить покупателя/группу"
    )
