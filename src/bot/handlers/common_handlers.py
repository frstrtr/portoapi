# Обработчики /start, /help


from aiogram import types


async def handle_start(message: types.Message):
    kb = types.ReplyKeyboardMarkup(
        keyboard=[
            [
                types.KeyboardButton(text="/help"),
                types.KeyboardButton(text="/register")
            ],
            [
                types.KeyboardButton(text="/deposit"),
                types.KeyboardButton(text="/balance")
            ],
            [
                types.KeyboardButton(text="/create_invoice"),
                types.KeyboardButton(text="/sweep")
            ],
            [
                types.KeyboardButton(text="/buyers"),
                types.KeyboardButton(text="/add_buyer")
            ]
        ],
        resize_keyboard=True
    )
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
