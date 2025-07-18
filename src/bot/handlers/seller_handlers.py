# Обработчики всех команд продавца

import logging
import secrets
from io import BytesIO

import qrcode

from aiogram.types.input_file import BufferedInputFile

from aiogram import types
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from src.core.database.db_service import (
    create_seller,
    get_seller,
    get_wallet_by_group,
    create_invoice,
    get_invoices_by_seller,
    update_invoice,
    get_buyer_group,
    get_buyer_groups_by_seller,
    create_buyer_group,
    create_seller_wallet,
    update_seller,
)
from src.core.services.gas_station import prepare_for_sweep
from src.core.crypto.xpub_validation import is_valid_xpub
from src.core.services.gas_station import (
    get_or_create_tron_deposit_address,
    calculate_trx_needed,
)


logger = logging.getLogger("bot.seller_handlers")

# pylint: disable=logging-fstring-interpolation


# Import admin handlers
from src.bot.admin.admin_handlers import handle_admin_xpubs, is_admin


# FSM для создания инвойса с выбором группы
class InvoiceFSM(StatesGroup):
    amount = State()
    description = State()
    group = State()
    awaiting_group_name_for_invoice = State()


# FSM для добавления покупателя/группы
class AddBuyerFSM(StatesGroup):
    buyer_id = State()
    group_name = State()


# FSM для регистрации
class RegisterFSM(StatesGroup):
    ask_xpub = State()
    get_xpub = State()
    get_account = State()


async def handle_register(message: types.Message, state: FSMContext = None):
    # Register admin command handler (should be in main_bot.py, but for demo, add here)
    if message.text and message.text.startswith("/admin_xpubs"):
        await handle_admin_xpubs(message)
        return
    telegram_id = message.from_user.id
    db = message.bot.db
    seller = get_seller(db=db, telegram_id=telegram_id)

    await message.answer(
        "Регистрация нового HD кошелька.\n\n"
        "Пожалуйста, отправьте ваш xPub (или напишите 'нет', чтобы получить инструкцию)."
    )
    if state is not None:
        await state.set_state(RegisterFSM.get_xpub)
    return

    # Non-FSM registration flow
    token = secrets.token_urlsafe(16)
    seller = get_seller(db=db, telegram_id=telegram_id)
    if not seller:
        create_seller(db=db, telegram_id=telegram_id)
        msg = "Ваша ссылка для настройки кошелька:"
    else:
        msg = "Вы уже зарегистрированы. Ваша ссылка для настройки кошелька:"
    import os

    base_url = os.getenv("SETUP_URL_BASE", "https://127.0.0.1:8000")
    url = f"{base_url}/setup.html?token={token}"
    logger.info(f"User {telegram_id} setup link: {url}")
    await message.answer(f"{msg} {url}")


async def handle_deposit(message: types.Message):
    telegram_id = message.from_user.id
    logger.info(f"User {telegram_id} called /deposit")
    db = message.bot.db
    seller = get_seller(db=db, telegram_id=telegram_id)

    deposit_address = get_or_create_tron_deposit_address(db, seller_id=telegram_id)
    trx_needed = calculate_trx_needed(seller)
    logger.info(
        f"User {telegram_id} deposit address: {deposit_address}, TRX needed: {trx_needed}"
    )

    qr = qrcode.QRCode(box_size=6, border=2)
    qr.add_data(deposit_address)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buf = BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)

    await message.answer(
        f"Ваш уникальный TRON-адрес для депозита газа:\n<code>{deposit_address}</code>\n"
        f"Рекомендуемая сумма для депозита: <b>{trx_needed} TRX</b>",
        parse_mode="HTML",
    )
    await message.answer_photo(
        BufferedInputFile(buf.getvalue(), "deposit_qr.png"),
        caption="QR-код для депозита TRX",
    )


async def handle_balance(message: types.Message):
    telegram_id = message.from_user.id
    logger.info(f"User {telegram_id} called /balance")
    seller = get_seller(db=message.bot.db, telegram_id=telegram_id)
    logger.info(f"User {telegram_id} balance: {seller.gas_deposit_balance} TRX")
    await message.answer(f"Ваш баланс: {seller.gas_deposit_balance} TRX")


async def handle_create_invoice(message: types.Message, state: FSMContext):
    """Handle the /create_invoice command and start the invoice creation FSM."""

    telegram_id = message.from_user.id
    logger.info(f"User {telegram_id} called /create_invoice")
    await message.answer("Введите сумму для инвойса:")
    await state.set_state(InvoiceFSM.amount)


async def process_invoice_amount(message: types.Message, state: FSMContext):
    """Process the invoice amount input from the user."""

    telegram_id = message.from_user.id
    logger.info(f"User {telegram_id} entered invoice amount: {message.text}")
    await state.update_data(amount=message.text)
    await message.answer("Введите описание инвойса:")
    await state.set_state(InvoiceFSM.description)


async def process_invoice_description(message: types.Message, state: FSMContext):
    """Process the invoice description input from the user."""
    print("Processing invoice description...")

    telegram_id = message.from_user.id
    logger.info(f"User {telegram_id} entered invoice description: {message.text}")
    await state.update_data(description=message.text)
    db = message.bot.db
    groups = get_buyer_groups_by_seller(db, telegram_id)
    if not groups:
        logger.info(f"User {telegram_id} has no buyer groups")
        kb = types.ReplyKeyboardMarkup(
            keyboard=[[types.KeyboardButton(text="Использовать группу по умолчанию")]],
            resize_keyboard=True,
        )
        await message.answer(
            "У вас нет групп покупателей. Хотите создать группу?\n"
            "Введите название для группы или нажмите кнопку ниже для использования названия по умолчанию (General):",
            reply_markup=kb,
        )
        await state.update_data(description=message.text)
        await state.set_state(InvoiceFSM.awaiting_group_name_for_invoice)
        return
    kb = types.ReplyKeyboardMarkup(keyboard=[], resize_keyboard=True)
    for g in groups:
        kb.keyboard.append(
            [types.KeyboardButton(text=f"{g.buyer_id} | {g.invoices_group}")]
        )
    await message.answer("Выберите покупателя/группу:", reply_markup=kb)
    await state.set_state(InvoiceFSM.group)


# --- Handler for group name after no groups found ---
async def process_group_name_for_invoice(message: types.Message, state: FSMContext):
    """
    Process the group name input when no buyer groups are found."""
    print("Processing group name for invoice creation...")

    telegram_id = message.from_user.id
    db = message.bot.db
    group_name = message.text.strip()
    normalized = group_name.lower().strip()
    if (
        normalized == "нет"
        or normalized == "использовать группу по умолчанию"
        or not normalized
    ):
        group_name = "General"
    logger.info(f"User {telegram_id} creating default buyer group: {group_name}")
    # Create the group for this seller
    create_buyer_group(db, seller_id=telegram_id, buyer_id=group_name, invoices_group=0)
    # Continue invoice creation as if group now exists
    groups = get_buyer_groups_by_seller(db, telegram_id)
    kb = types.ReplyKeyboardMarkup(keyboard=[], resize_keyboard=True)
    for g in groups:
        kb.keyboard.append(
            [types.KeyboardButton(text=f"{g.buyer_id} | {g.invoices_group}")]
        )
    await message.answer(
        f"Группа '{group_name}' создана. Выберите покупателя/группу:", reply_markup=kb
    )
    await state.set_state(InvoiceFSM.group)


async def process_invoice_group(message: types.Message, state: FSMContext):
    telegram_id = message.from_user.id
    logger.info(f"User {telegram_id} selected invoice group: {message.text}")
    data = await state.get_data()
    group_str = message.text.strip()
    try:
        buyer_id, invoices_group = group_str.split("|")
        buyer_id = buyer_id.strip()
        invoices_group = int(invoices_group.strip())
    except Exception:
        logger.warning(
            f"User {telegram_id} provided invalid group format: {message.text}"
        )
        await message.answer("Некорректный формат. Выберите из списка.")
        return
    db = message.bot.db

    wallet = get_wallet_by_group(db, telegram_id, invoices_group)
    if wallet is None:
        logger.error(
            f"User {telegram_id} tried to create invoice but has no wallet/xpub for group {invoices_group}."
        )
        # Show main actions keyboard including /register
        kb = types.ReplyKeyboardMarkup(
            keyboard=[
                [types.KeyboardButton(text="/register")],
                [types.KeyboardButton(text="/deposit")],
                [types.KeyboardButton(text="/balance")],
                [types.KeyboardButton(text="/create_invoice")],
                [types.KeyboardButton(text="/buyers")],
                [types.KeyboardButton(text="/add_buyer")],
                [types.KeyboardButton(text="/sweep")],
            ],
            resize_keyboard=True,
        )
        await message.answer(
            "❌ Ошибка: не найден xPub для вашего аккаунта или выбранной группы. Пожалуйста, зарегистрируйте xPub через /register.",
            reply_markup=kb,
        )
        await state.clear()
        return
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
    logger.info(
        f"User {telegram_id} created invoice: address={invoice.address}, amount={data['amount']}, group={buyer_id}"
    )
    await message.answer(
        f"Инвойс создан! Адрес: {invoice.address}\nСумма: {data['amount']}\nОписание: {data['description']}\nГруппа: {buyer_id}"
    )
    await state.clear()


# --- Покупатели/группы ---
async def handle_buyers(message: types.Message):
    telegram_id = message.from_user.id
    logger.info(f"User {telegram_id} called /buyers")
    db = message.bot.db

    groups = get_buyer_groups_by_seller(db, telegram_id)
    if not groups:
        logger.info(f"User {telegram_id} has no buyer groups")
        await message.answer("У вас нет групп покупателей. Добавьте через /add_buyer.")
        return
    text = "Ваши группы покупателей:\n"
    for g in groups:
        text += f"- {g.buyer_id} | {g.invoices_group}\n"
    logger.info(f"User {telegram_id} buyer groups listed")
    await message.answer(text)


async def handle_add_buyer(message: types.Message, state: FSMContext):
    telegram_id = message.from_user.id
    logger.info(f"User {telegram_id} called /add_buyer")
    await message.answer(
        "Введите buyer_id (например, email или уникальный идентификатор покупателя):"
    )
    await state.set_state(AddBuyerFSM.buyer_id)


async def process_add_buyer_id(message: types.Message, state: FSMContext):
    telegram_id = message.from_user.id
    logger.info(f"User {telegram_id} entered buyer_id: {message.text.strip()}")
    await state.update_data(buyer_id=message.text.strip())
    await message.answer("Введите номер группы (BIP44 account, например 0, 1, 2...):")
    await state.set_state(AddBuyerFSM.group_name)


async def process_add_buyer_group(message: types.Message, state: FSMContext):
    telegram_id = message.from_user.id
    data = await state.get_data()
    buyer_id = data["buyer_id"]
    logger.info(
        f"User {telegram_id} entered group number: {message.text.strip()} for buyer_id: {buyer_id}"
    )
    try:
        invoices_group = int(message.text.strip())
    except Exception:
        logger.warning(
            f"User {telegram_id} provided invalid group number: {message.text.strip()}"
        )
        await message.answer("Некорректный номер группы. Введите целое число.")
        return
    db = message.bot.db

    create_buyer_group(
        db, seller_id=telegram_id, buyer_id=buyer_id, invoices_group=invoices_group
    )
    logger.info(f"User {telegram_id} added buyer group: {buyer_id} | {invoices_group}")
    await message.answer(
        f"Группа для покупателя {buyer_id} с номером {invoices_group} добавлена."
    )
    await state.clear()


async def handle_sweep(message: types.Message):
    telegram_id = message.from_user.id
    logger.info(f"User {telegram_id} called /sweep")
    paid_invoices = [
        inv
        for inv in get_invoices_by_seller(db=message.bot.db, seller_id=telegram_id)
        if inv.status == "paid"
    ]
    total = sum(inv.amount for inv in paid_invoices)
    count = len(paid_invoices)
    logger.info(f"User {telegram_id} sweep: {count} invoices, total {total} TRX")
    if not paid_invoices:
        await message.answer("Нет оплаченных инвойсов для вывода.")
        return
    await message.answer(
        f"Будет обработано {count} инвойсов на сумму {total} TRX. Подтвердите выполнение? (да/нет)"
    )
    # Здесь можно реализовать FSM для подтверждения
    # После подтверждения:
    for inv in paid_invoices:
        logger.info(
            f"User {telegram_id} sweeping invoice {inv.id} address {inv.address}"
        )
        prepare_for_sweep(inv.address)
        update_invoice(db=message.bot.db, invoice_id=inv.id, status="swept")
    await message.answer("Все оплаченные инвойсы обработаны и выведены.")


async def process_register_xpub(message: types.Message, state: FSMContext):
    telegram_id = message.from_user.id
    text = message.text.strip()
    logger.info(f"User {telegram_id} process_register_xpub: {text}")
    if text.lower() == "нет":
        await message.answer("Для генерации xPub используйте офлайн-страницу (xpub_offline.html) на вашем компьютере. Сгенерируйте xPub и отправьте его сюда. Никогда не делитесь seed-фразой или приватным ключом!")
        await state.clear()
        return
    xpub = text
    if not is_valid_xpub(xpub):
        logger.warning(f"User {telegram_id} provided invalid xPub: {xpub}")
        await message.answer("Некорректный xPub. Пожалуйста, проверьте и отправьте корректный xPub.")
        return
    await state.update_data(xpub=xpub)
    await message.answer("Теперь укажите номер аккаунта (BIP44 account, например 0, 1, 2...) для этого xPub:")
    await state.set_state(RegisterFSM.get_account)
async def process_register_account(message: types.Message, state: FSMContext):
    telegram_id = message.from_user.id
    account_text = message.text.strip()
    logger.info(f"User {telegram_id} process_register_account: {account_text}")
    try:
        account = int(account_text)
    except Exception:
        await message.answer("Некорректный номер аккаунта. Введите целое число.")
        return
    data = await state.get_data()
    xpub = data.get("xpub")
    db = message.bot.db
    from src.core.database.db_service import get_wallet_by_group, create_seller_wallet
    wallet = get_wallet_by_group(db, telegram_id, account)
    if wallet and wallet.xpub == xpub:
        await message.answer("Этот xPub уже зарегистрирован для выбранного аккаунта. Регистрация пропущена.")
        await state.clear()
        return
    if wallet:
        wallet.xpub = xpub
        db.commit()
        logger.info(f"User {telegram_id} xPub updated in wallet: {xpub} (account {account})")
    else:
        create_seller_wallet(
            db,
            seller_id=telegram_id,
            xpub=xpub,
            account=account,
            address=None,
            derivation_path=None,
            deposit_type=None
        )
        logger.info(f"User {telegram_id} registered new xPub and wallet created: {xpub} (account {account})")
    kb = types.ReplyKeyboardMarkup(
        keyboard=[
            [types.KeyboardButton(text="/deposit")],
            [types.KeyboardButton(text="/balance")],
            [types.KeyboardButton(text="/create_invoice")],
            [types.KeyboardButton(text="/buyers")],
            [types.KeyboardButton(text="/add_buyer")],
            [types.KeyboardButton(text="/sweep")],
        ],
        resize_keyboard=True,
    )
    await message.answer("Ваш xPub и аккаунт успешно зарегистрированы/обновлены!\nВыберите действие:", reply_markup=kb)
    await state.clear()
def register_registration_fsm_handlers(dp, seller_handlers):
    dp.message.register(seller_handlers.process_register_xpub, seller_handlers.RegisterFSM.get_xpub)
    dp.message.register(seller_handlers.process_register_account, seller_handlers.RegisterFSM.get_account)


# # --- Admin command: /admin_xpubs <seller_id> ---
# async def handle_admin_xpubs(message: types.Message):
#     telegram_id = message.from_user.id
#     if not is_admin(telegram_id):
#         await message.answer("⛔️ Нет доступа. Только для админов.")
#         return
#     args = message.text.strip().split()
#     if len(args) != 2:
#         await message.answer("Использование: /admin_xpubs <seller_id>")
#         return
#     try:
#         seller_id = int(args[1])
#     except Exception:
#         await message.answer("seller_id должен быть числом.")
#         return
#     db = message.bot.db
#     from src.core.database.db_service import SessionLocal

#     wallets = (
#         db.query(create_seller_wallet.__globals__["Wallet"])
#         .filter_by(seller_id=seller_id)
#         .all()
#     )
#     if not wallets:
#         await message.answer(f"Нет xPub-кошельков для seller_id {seller_id}.")
#         return
#     text = f"xPubs для seller_id {seller_id}:\n"
#     for w in wallets:
#         text += f"- group: {w.invoices_group}, xpub: {w.xpub}\n"
#     await message.answer(text)
