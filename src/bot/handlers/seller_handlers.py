# Обработчики всех команд продавца


from aiogram import types
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
import secrets
from src.core.database.db_service import (
    create_seller,
    get_seller,
    get_wallet_by_group,
    create_invoice,
    get_invoices_by_seller,
    update_invoice,
)
from src.core.services.gas_station import prepare_for_sweep
from src.core.database.db_service import (
    get_buyer_groups_by_seller,
    get_wallet_by_group,
    get_buyer_group,
    get_buyer_groups_by_seller,
    create_buyer_group,
)
from src.core.services.gas_station import (
    get_or_create_tron_deposit_address,
    calculate_trx_needed,
)

import qrcode
from io import BytesIO
from aiogram.types import InputFile


# FSM для создания инвойса с выбором группы
class InvoiceFSM(StatesGroup):
    amount = State()
    description = State()
    group = State()


# FSM для добавления покупателя/группы
class AddBuyerFSM(StatesGroup):
    buyer_id = State()
    group_name = State()


# FSM для регистрации
class RegisterFSM(StatesGroup):
    ask_xpub = State()
    get_xpub = State()


async def handle_register(message: types.Message):
    telegram_id = message.from_user.id
    token = secrets.token_urlsafe(16)
    db = message.bot.db
    # Проверяем, существует ли продавец
    seller = get_seller(db=db, telegram_id=telegram_id)
    if not seller:
        create_seller(db=db, telegram_id=telegram_id)
        msg = "Ваша ссылка для настройки кошелька:"
    else:
        msg = "Вы уже зарегистрированы. Ваша ссылка для настройки кошелька:"
    # Получаем базовый URL из .env
    import os

    base_url = os.getenv("SETUP_URL_BASE", "https://127.0.0.1:8000")
    url = f"{base_url}/setup.html?token={token}"
    await message.answer(f"{msg} {url}")


async def handle_deposit(message: types.Message):
    telegram_id = message.from_user.id
    db = message.bot.db
    seller = get_seller(db=db, telegram_id=telegram_id)

    # 1. Получить или создать уникальный TRON-адрес для депозита продавца
    # (пример: функция create_or_get_gas_deposit_address должна быть реализована в db_service)

    deposit_address = get_or_create_tron_deposit_address(db, seller_id=telegram_id)
    trx_needed = calculate_trx_needed(
        seller
    )  # функция должна возвращать нужную сумму TRX

    # 2. Генерируем QR-код для адреса
    qr = qrcode.QRCode(box_size=6, border=2)
    qr.add_data(deposit_address)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buf = BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)

    # 3. Отправляем сообщение с адресом, QR-кодом и суммой
    await message.answer(
        f"Ваш уникальный TRON-адрес для депозита газа:\n<code>{deposit_address}</code>\n"
        f"Рекомендуемая сумма для депозита: <b>{trx_needed} TRX</b>",
        parse_mode="HTML",
    )
    await message.answer_photo(InputFile(buf), caption="QR-код для депозита TRX")

    # 4. Сохраняем адрес в базе (если не был сохранён ранее)
    # (реализуйте логику в get_or_create_tron_deposit_address/db_service)


async def handle_balance(message: types.Message):
    telegram_id = message.from_user.id
    seller = get_seller(db=message.bot.db, telegram_id=telegram_id)
    await message.answer(f"Ваш баланс: {seller.gas_deposit_balance} TRX")


async def handle_create_invoice(message: types.Message, state: FSMContext):
    await message.answer("Введите сумму для инвойса:")
    await state.set_state(InvoiceFSM.amount)


async def process_invoice_amount(message: types.Message, state: FSMContext):
    await state.update_data(amount=message.text)
    await message.answer("Введите описание инвойса:")
    await state.set_state(InvoiceFSM.description)


async def process_invoice_description(message: types.Message, state: FSMContext):
    await state.update_data(description=message.text)
    telegram_id = message.from_user.id
    # Получить группы продавца
    db = message.bot.db
    groups = get_buyer_groups_by_seller(db, telegram_id)
    if not groups:
        await message.answer(
            "У вас нет групп покупателей. Сначала создайте группу через /add_buyer."
        )
        await state.clear()
        return
    kb = types.ReplyKeyboardMarkup(keyboard=[], resize_keyboard=True)
    for g in groups:
        kb.keyboard.append(
            [types.KeyboardButton(text=f"{g.buyer_id} | {g.invoices_group}")]
        )
    await message.answer("Выберите покупателя/группу:", reply_markup=kb)
    await state.set_state(InvoiceFSM.group)


async def process_invoice_group(message: types.Message, state: FSMContext):
    data = await state.get_data()
    group_str = message.text.strip()
    try:
        buyer_id, invoices_group = group_str.split("|")
        buyer_id = buyer_id.strip()
        invoices_group = int(invoices_group.strip())
    except Exception:
        await message.answer("Некорректный формат. Выберите из списка.")
        return
    telegram_id = message.from_user.id
    db = message.bot.db

    wallet = get_wallet_by_group(db, telegram_id, invoices_group)

    buyer_group = get_buyer_group(db, telegram_id, buyer_id)
    invoice = create_invoice(
        db=db,
        seller_id=telegram_id,
        buyer_group_id=buyer_group.id,
        derivation_index=0,
        address=wallet.xpub,
        amount=float(data["amount"]),
        status="pending",
    )
    await message.answer(
        f"Инвойс создан! Адрес: {invoice.address}\nСумма: {data['amount']}\nОписание: {data['description']}\nГруппа: {buyer_id}"
    )
    await state.clear()


# --- Покупатели/группы ---
async def handle_buyers(message: types.Message):
    telegram_id = message.from_user.id
    db = message.bot.db

    groups = get_buyer_groups_by_seller(db, telegram_id)
    if not groups:
        await message.answer("У вас нет групп покупателей. Добавьте через /add_buyer.")
        return
    text = "Ваши группы покупателей:\n"
    for g in groups:
        text += f"- {g.buyer_id} | {g.invoices_group}\n"
    await message.answer(text)


async def handle_add_buyer(message: types.Message, state: FSMContext):
    await message.answer(
        "Введите buyer_id (например, email или уникальный идентификатор покупателя):"
    )
    await state.set_state(AddBuyerFSM.buyer_id)


async def process_add_buyer_id(message: types.Message, state: FSMContext):
    await state.update_data(buyer_id=message.text.strip())
    await message.answer("Введите номер группы (BIP44 account, например 0, 1, 2...):")
    await state.set_state(AddBuyerFSM.group_name)


async def process_add_buyer_group(message: types.Message, state: FSMContext):
    data = await state.get_data()
    buyer_id = data["buyer_id"]
    try:
        invoices_group = int(message.text.strip())
    except Exception:
        await message.answer("Некорректный номер группы. Введите целое число.")
        return
    telegram_id = message.from_user.id
    db = message.bot.db

    create_buyer_group(
        db, seller_id=telegram_id, buyer_id=buyer_id, invoices_group=invoices_group
    )
    await message.answer(
        f"Группа для покупателя {buyer_id} с номером {invoices_group} добавлена."
    )
    await state.clear()


async def handle_sweep(message: types.Message):
    telegram_id = message.from_user.id
    paid_invoices = [
        inv
        for inv in get_invoices_by_seller(db=message.bot.db, seller_id=telegram_id)
        if inv.status == "paid"
    ]
    total = sum(inv.amount for inv in paid_invoices)
    count = len(paid_invoices)
    if not paid_invoices:
        await message.answer("Нет оплаченных инвойсов для вывода.")
        return
    await message.answer(
        f"Будет обработано {count} инвойсов на сумму {total} TRX. Подтвердите выполнение? (да/нет)"
    )
    # Здесь можно реализовать FSM для подтверждения
    # После подтверждения:
    for inv in paid_invoices:
        prepare_for_sweep(inv.address)
        update_invoice(db=message.bot.db, invoice_id=inv.id, status="swept")
    await message.answer("Все оплаченные инвойсы обработаны и выведены.")


async def handle_register(message: types.Message, state: FSMContext):
    await message.answer(
        "У вас уже есть xPub ключ?\n\n"
        "Если да — отправьте его сюда.\n"
        "Если нет — напишите 'нет', и я дам вам инструкцию, как его создать безопасно."
    )
    await state.set_state(RegisterFSM.ask_xpub)


async def process_register_xpub(message: types.Message, state: FSMContext):
    text = message.text.strip()
    if text.lower() == "нет":
        await message.answer(
            "Для генерации xPub используйте офлайн-страницу (xpub_offline.html) на вашем компьютере. "
            "Сгенерируйте xPub и отправьте его сюда. "
            "Никогда не делитесь seed-фразой или приватным ключом!"
        )
        await state.set_state(RegisterFSM.get_xpub)
    else:
        xpub = text
        # Здесь можно добавить валидацию xPub
        # Сохраните xPub в БД, привязав к seller
        await message.answer("Ваш xPub сохранён. Регистрация завершена!")
        await state.clear()
