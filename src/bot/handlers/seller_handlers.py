from aiogram.fsm.context import FSMContext


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
    get_wallets_by_seller,
    create_seller_wallet,
    update_seller,
)

from src.core.crypto.xpub_validation import is_valid_xpub
from src.core.services.gas_station import (
    get_or_create_tron_deposit_address,
    calculate_trx_needed,
    prepare_for_sweep,
)


# pylint: disable=logging-fstring-interpolation


# Import admin handlers
# admin handler will show xPubs for admin users
from src.bot.admin.admin_handlers import handle_admin_xpubs, is_admin

# Import database service functions
from src.core.database.db_service import get_wallets_by_seller

from src.core.crypto.hd_wallet_service import generate_address_from_xpub

# Import common handlers for keyboard
from src.bot.handlers.common_handlers import get_main_menu_keyboard


logger = logging.getLogger("bot.seller_handlers")


MAIN_COMMANDS = [
    "/register",
    "/myaccount",
    "/deposit",
    "/balance",
    "/create_invoice",
    "/buyers",
    "/add_buyer",
    "/sweep",
    "/invoices",
]


# FSM для создания инвойса с выбором группы
class InvoiceFSM(StatesGroup):
    amount = State()
    description = State()
    group = State()
    awaiting_group_name_for_invoice = State()


# FSM для добавления покупателя/группы
class AddBuyerFSM(StatesGroup):
    buyer_id = State()
    xpub = State()


# FSM для регистрации
class RegisterFSM(StatesGroup):
    ask_xpub = State()
    get_xpub = State()
    get_account = State()
    choose_account_action = State()
    select_existing_account = State()
    ask_address = State()


async def handle_main_command_interrupt(message: types.Message, state: FSMContext):
    telegram_id = message.from_user.id
    logger.info(
        f"User {telegram_id} sent main command '{message.text}' during active FSM flow. Cancelling FSM state."
    )
    await state.clear()
    await message.answer(
        "❗️ Вы отправили основную команду во время незавершённого процесса. Предыдущий процесс был отменён. Пожалуйста, повторите команду, если требуется."
    )
    await show_main_menu(message, state)


async def handle_myaccount(message: types.Message):
    """Show detailed account information for registered users"""
    telegram_id = message.from_user.id
    db = message.bot.db
    
    try:
        # Get seller information
        seller = get_seller(db=db, telegram_id=telegram_id)
        if not seller:
            await message.answer(
                "❌ Вы не зарегистрированы. Используйте /register для регистрации.",
                reply_markup=get_main_menu_keyboard(is_registered=False)
            )
            return
        
        # Get user info from Telegram
        user = message.from_user
        user_info = []
        user_info.append("👤 **Информация о пользователе:**")
        user_info.append(f"• ID: `{user.id}`")
        user_info.append(f"• Имя: {user.first_name or 'Не указано'}")
        if user.last_name:
            user_info.append(f"• Фамилия: {user.last_name}")
        if user.username:
            user_info.append(f"• Username: @{user.username}")
        else:
            user_info.append("• Username: Не указан")
        
        # Registration date
        if seller.date_created:
            reg_date = seller.date_created.strftime("%d.%m.%Y %H:%M")
            user_info.append(f"• Дата регистрации: {reg_date}")
        
        # Get buyer groups and xPubs
        buyer_groups = get_buyer_groups_by_seller(db, telegram_id)
        
        user_info.append("\n💳 **Кошельки (xPub):**")
        if buyer_groups:
            for group in buyer_groups:
                if group.xpub:
                    xpub_short = f"{group.xpub[:20]}...{group.xpub[-10:]}" if len(group.xpub) > 35 else group.xpub
                    user_info.append(f"• Account {group.invoices_group}: `{xpub_short}`")
                    if group.buyer_id:
                        user_info.append(f"  └ Покупатель: {group.buyer_id}")
                else:
                    user_info.append(f"• Account {group.invoices_group}: ⚠️ xPub не настроен")
        else:
            user_info.append("• Нет настроенных кошельков")
        
        # Get wallets information
        wallets = get_wallets_by_seller(db, telegram_id)
        if wallets:
            user_info.append("\n🔑 **Дополнительные кошельки:**")
            for wallet in wallets:
                if wallet.xpub:
                    xpub_short = f"{wallet.xpub[:20]}...{wallet.xpub[-10:]}" if len(wallet.xpub) > 35 else wallet.xpub
                    user_info.append(f"• Account {wallet.account}: `{xpub_short}`")
                    if wallet.label:
                        user_info.append(f"  └ Метка: {wallet.label}")
        
        # Get invoice statistics
        invoices = get_invoices_by_seller(db, telegram_id)
        total_invoices = len(invoices)
        paid_invoices = len([inv for inv in invoices if inv.status == 'paid'])
        pending_invoices = len([inv for inv in invoices if inv.status == 'pending'])
        
        user_info.append("\n📋 **Статистика инвойсов:**")
        user_info.append(f"• Всего: {total_invoices}")
        user_info.append(f"• Оплачено: {paid_invoices}")
        user_info.append(f"• В ожидании: {pending_invoices}")
        
        # Gas station balance
        user_info.append("\n⛽ **Газовый депозит:**")
        user_info.append(f"• Баланс: {seller.gas_deposit_balance:.2f} TRX")
        
        response_text = "\n".join(user_info)
        
        await message.answer(
            response_text,
            parse_mode="Markdown",
            reply_markup=get_main_menu_keyboard(is_registered=True)
        )
        
    except Exception as e:
        logger.exception(f"Error in handle_myaccount for user {telegram_id}: {e}")
        await message.answer(
            "❌ Произошла ошибка при получении информации об аккаунте.",
            reply_markup=get_main_menu_keyboard(is_registered=True)
        )


async def handle_register(message: types.Message, state: FSMContext = None):
    # Only handle /register command here
    logger.info(f"User {message.from_user.id} called /register")

    if message.text and message.text.strip() != "/register":
        return
    telegram_id = message.from_user.id
    db = message.bot.db
    seller = get_seller(db=db, telegram_id=telegram_id)

    # If seller does not exist, create and prompt for xPub
    if not seller:
        create_seller(db=db, telegram_id=telegram_id)
        await message.answer(
            "Вы новый пользователь. Пожалуйста, отправьте ваш xPub (или напишите 'нет', чтобы получить инструкцию).",
            reply_markup=get_main_menu_keyboard(is_registered=False)
        )
        if state is not None:
            await state.set_state(RegisterFSM.get_xpub)
        return

    # Check if seller has any xPub submitted (wallets or buyer groups with xPub)
    wallets = get_wallets_by_seller(db, telegram_id)
    buyer_groups = get_buyer_groups_by_seller(db, telegram_id)
    has_xpub = any(w.xpub for w in wallets) or any(g.xpub for g in buyer_groups)

    if has_xpub:
        # User is already registered with xPub, redirect to myaccount
        await message.answer(
            "✅ Вы уже зарегистрированы! Используйте /myaccount для просмотра информации об аккаунте.",
            reply_markup=get_main_menu_keyboard(is_registered=True)
        )
        return

    # No xPub found, continue with registration
    await message.answer(
        "У вас ещё не зарегистрирован ни один xPub. Пожалуйста, отправьте ваш xPub (или напишите 'нет', чтобы получить инструкцию).",
        reply_markup=get_main_menu_keyboard(is_registered=False)
    )
    if state is not None:
        await state.set_state(RegisterFSM.get_xpub)


# --- Registration FSM choice handlers ---
async def process_choose_account_action(message: types.Message, state: FSMContext):
    telegram_id = message.from_user.id
    db = message.bot.db
    choice = message.text.strip()

    wallets = get_wallets_by_seller(db, telegram_id)
    if choice == "Использовать существующий аккаунт":
        # Show list of accounts to choose from
        kb = types.ReplyKeyboardMarkup(keyboard=[], resize_keyboard=True)
        for w in wallets:
            short_xpub = f"...{w.xpub[-8:]}" if w.xpub else "(нет xPub)"
            kb.keyboard.append(
                [
                    types.KeyboardButton(
                        text=f"xPub: {short_xpub} | Account: {w.account}"
                    )
                ]
            )
        await message.answer("Выберите аккаунт для использования:", reply_markup=kb)
        await state.set_state(RegisterFSM.select_existing_account)
        return
    elif choice == "Create new wallet (new seed phrase)":
        await message.answer(
            "⚠️ To create a new wallet, you must use a new seed phrase. Generate a new seed phrase, get the xPub, and send it here. Never use your old seed phrase for a new wallet!"
        )
        await message.answer("Please send the new xPub:")
        await state.set_state(RegisterFSM.get_xpub)
        return
    else:
        await message.answer(
            "Некорректный выбор. Пожалуйста, выберите действие из списка."
        )
        return


async def process_select_existing_account(message: types.Message, state: FSMContext):
    telegram_id = message.from_user.id
    db = message.bot.db
    account_info = message.text.strip()
    # Parse xPub and account
    try:
        parts = account_info.replace("xPub:", "").replace("Account:", "").split("|")
        xpub = parts[0].strip()
        account = int(parts[1].strip())
    except Exception:
        await message.answer(
            "Некорректный формат аккаунта. Пожалуйста, выберите из списка."
        )
        return
    await message.answer(
        f"Вы выбрали аккаунт {account} для xPub {xpub}. Теперь вы можете использовать этот аккаунт."
    )
    await show_main_menu(message, state)
    await state.clear()
    return


async def show_main_menu(message: types.Message, state: FSMContext = None):
    """
    Show the main actions keyboard to the user.
    """
    telegram_id = message.from_user.id
    db = message.bot.db
    
    # Check if user is registered
    try:
        seller = get_seller(db=db, telegram_id=telegram_id)
        # Check if user has any xPub configured
        wallets = get_wallets_by_seller(db, telegram_id)
        buyer_groups = get_buyer_groups_by_seller(db, telegram_id)
        has_xpub = any(w.xpub for w in wallets) or any(g.xpub for g in buyer_groups)
        is_registered = seller is not None and has_xpub
    except Exception:
        is_registered = False
    
    keyboard = get_main_menu_keyboard(is_registered=is_registered)
    await message.answer("Вы вернулись в главное меню.", reply_markup=keyboard)
    # seller = get_seller(db=db, telegram_id=telegram_id)
    # if not seller:
    #     create_seller(db=db, telegram_id=telegram_id)
    #     msg = "Ваша ссылка для настройки кошелька:"
    # else:
    #     msg = "Вы уже зарегистрированы. Ваша ссылка для настройки кошелька:"
    # import os

    # base_url = os.getenv("SETUP_URL_BASE", "https://127.0.0.1:8000")
    # url = f"{base_url}/setup.html?token={token}"
    # logger.info(f"User {telegram_id} setup link: {url}")
    # await message.answer(f"{msg} {url}")


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
        or normalized == "general"
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
        f"Группа '{group_name}' создана. Выберите покупателя:", reply_markup=kb
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

    # Use buyer group's xpub and account index for address derivation
    buyer_group = get_buyer_group(db, telegram_id, buyer_id)
    if not buyer_group or not getattr(buyer_group, "xpub", None):
        await message.answer(
            "❌ Ошибка: не найден xPub для выбранной группы покупателя. Пожалуйста, добавьте группу с xPub."
        )
        await state.clear()
        return

    existing_invoices = get_invoices_by_seller(db, telegram_id)
    # Only consider used addresses for this xpub and this account index (buyer group)
    used_addresses = set(
        inv.address
        for inv in existing_invoices
        if inv.derivation_index is not None
        and getattr(inv, "buyer_group_id", None) == buyer_group.id
    )
    # Find the first unused address index for this account (buyer group)
    next_address_index = 0
    while True:
        candidate_address = generate_address_from_xpub(
            buyer_group.xpub, account=invoices_group, address_index=next_address_index
        )
        if candidate_address not in used_addresses:
            derived_address = candidate_address
            break
        next_address_index += 1
    # Log full derivation path
    derivation_path = f"m/44'/195'/{invoices_group}'/0/{next_address_index}"
    invoice = create_invoice(
        db=db,
        seller_id=telegram_id,
        buyer_group_id=buyer_group.id,
        derivation_index=next_address_index,
        address=derived_address,
        amount=float(data["amount"]),
        status="pending",
    )
    logger.info(
        f"User {telegram_id} created invoice: address={invoice.address}, amount={data['amount']}, group={buyer_id}, derivation_index={next_address_index}, derivation_path={derivation_path}"
    )
    # Generate QR code for invoice address
    qr = qrcode.QRCode(box_size=6, border=2)
    qr.add_data(invoice.address)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buf = BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    await message.answer(
        f"Инвойс создан!\nАдрес: <code>{invoice.address}</code>\n"
        f"Сумма: <b>{data['amount']}</b>\nОписание: {data['description']}\n"
        f"Группа: {buyer_id}\n\nПуть деривации: <code>{derivation_path}</code>",
        parse_mode="HTML",
    )
    await message.answer_photo(
        BufferedInputFile(buf.getvalue(), "invoice_qr.png"),
        caption=f"QR-код для инвойса: {invoice.address}",
    )
    await show_main_menu(message, state)
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
    # Sort groups by account number (invoices_group)
    groups_sorted = sorted(groups, key=lambda g: g.invoices_group)
    text = "Registered Buyers:\n"
    db = message.bot.db
    for g in groups_sorted:
        # Count invoices for this buyer group
        invoices = get_invoices_by_seller(db, telegram_id)
        count = sum(
            1
            for inv in invoices
            if getattr(inv, "buyer_group_id", None) == getattr(g, "id", None)
        )
        text += f"- {g.buyer_id} | Account: {g.invoices_group} | {count} invoice(s)\n"
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
    db = message.bot.db
    buyers = get_buyer_groups_by_seller(db, telegram_id)
    used_accounts = set(b.invoices_group for b in buyers)
    next_account = 0
    while next_account in used_accounts:
        next_account += 1
    await state.update_data(buyer_id=message.text.strip())
    await message.answer(
        f"Для этого покупателя используйте account #{next_account} при генерации xPub с вашим seed phrase.\n"
        "Пожалуйста, отправьте xPub для этого покупателя:"
    )
    await state.set_state(AddBuyerFSM.xpub)


async def process_add_buyer_group(message: types.Message, state: FSMContext):
    # No longer needed, merged with xpub step
    pass


# New FSM state handler for buyer xPUB
async def process_add_buyer_xpub(message: types.Message, state: FSMContext):
    telegram_id = message.from_user.id
    data = await state.get_data()
    buyer_id = data.get("buyer_id")
    xpub = message.text.strip()
    db = message.bot.db
    # Find next available account index for this seller
    buyers = get_buyer_groups_by_seller(db, telegram_id)
    used_accounts = set(b.invoices_group for b in buyers)
    next_account = 0
    while next_account in used_accounts:
        next_account += 1
    create_buyer_group(
        db,
        seller_id=telegram_id,
        buyer_id=buyer_id,
        invoices_group=next_account,
        xpub=xpub,
    )
    logger.info(
        f"User {telegram_id} added buyer: {buyer_id} | account: {next_account} | xpub: {xpub}"
    )
    await message.answer(
        f"Покупатель {buyer_id} с аккаунтом {next_account} и xPub добавлен."
    )
    await show_main_menu(message, state)
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
        await message.answer(
            "Для генерации xPub используйте офлайн-страницу (xpub_offline.html) на вашем компьютере. Сгенерируйте xPub и отправьте его сюда. Никогда не делитесь seed-фразой или приватным ключом!"
        )
        await state.clear()
        return
    # Only validate xPub if the user is registering a new wallet, not when choosing an existing account
    # If FSM state is RegisterFSM.get_xpub, validate xPub
    current_state = await state.get_state()
    if current_state == RegisterFSM.get_xpub.state:
        xpub = text
        if not is_valid_xpub(xpub):
            logger.warning(f"User {telegram_id} provided invalid xPub: {xpub}")
            await message.answer(
                "Некорректный xPub. Пожалуйста, проверьте и отправьте корректный xPub."
            )
            return
    db = message.bot.db
    buyers = get_buyer_groups_by_seller(db, telegram_id)
    if not buyers:
        # First xPub, assign to default buyer 'General' with account 0
        create_buyer_group(
            db,
            seller_id=telegram_id,
            buyer_id="General",
            invoices_group=0,
            xpub=xpub,
        )
        logger.info(
            f"User {telegram_id} registered first xPub for default buyer 'General'"
        )
        await message.answer(
            "Ваш xPub успешно зарегистрирован для покупателя 'General' (аккаунт 0)."
        )
        await show_main_menu(message, state)
        await state.clear()
        return
    # If buyers exist, ask user for buyer name or use next available account, with buttons
    kb = types.ReplyKeyboardMarkup(
        keyboard=[
            [types.KeyboardButton(text="General")],
            [types.KeyboardButton(text="Указать имя покупателя")],
        ],
        resize_keyboard=True,
    )
    await message.answer("Выберите действие для нового xPub:", reply_markup=kb)
    await state.update_data(xpub=xpub)
    await state.set_state("register_buyer_name")


async def process_register_account(message: types.Message, state: FSMContext):
    # This registration logic is now handled in process_register_xpub
    pass
    register_buyer_name = State()


# --- Handler for /invoices command: show all invoices with details ---
async def handle_invoices(message: types.Message):
    telegram_id = message.from_user.id
    logger.info(f"User {telegram_id} called /invoices")
    db = message.bot.db
    invoices = get_invoices_by_seller(db, telegram_id)
    if not invoices:
        await message.answer("У вас нет инвойсов.")
        return
    text = "Ваши инвойсы:\n"
    for inv in invoices:
        # Use buyer_group_id to lookup correct buyer group and account index
        buyer_group_id = getattr(inv, "buyer_group_id", None)
        buyer_group = None
        if buyer_group_id is not None:
            # get_buyer_groups_by_seller returns all groups, find by id
            all_groups = get_buyer_groups_by_seller(db, telegram_id)
            for g in all_groups:
                if getattr(g, "id", None) == buyer_group_id:
                    buyer_group = g
                    break
        account_index = (
            getattr(buyer_group, "invoices_group", "-") if buyer_group else "-"
        )
        buyer_id = getattr(buyer_group, "buyer_id", "-") if buyer_group else "-"
        address_index = getattr(inv, "derivation_index", "-")
        derivation_path = (
            f"m/44'/195'/{account_index}'/0/{address_index}"
            if account_index != "-" and address_index != "-"
            else "-"
        )
        text += (
            f"\nID: {inv.id}\n"
            f"Статус: {inv.status}\n"
            f"Сумма: {inv.amount}\n"
            f"Адрес: {inv.address}\n"
            f"Группа покупателя: {buyer_id}\n"
            f"Индекс деривации: {address_index}\n"
            f"Путь деривации: {derivation_path}\n"
            f"Описание: {getattr(inv, 'description', '-') }\n"
            f"Дата создания: {getattr(inv, 'created_at', '-') }\n"
            "----------------------"
        )
    await message.answer(text)


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


# --- Help command handler ---
async def handle_help(message: types.Message):
    help_text = (
        "<b>Help & Definitions</b>\n\n"
        "<b>Wallet:</b> In this platform, a wallet is defined by an xPub (extended public key) generated from a UNIQUE seed phrase (mnemonic). Each wallet can have multiple accounts.\n\n"
        "<b>xPub:</b> The extended public key is generated from your seed phrase and allows you to derive addresses for all accounts and invoices without exposing your private keys.\n\n"
        "<b>Seed Phrase:</b> A sequence of words used to generate your wallet and all its accounts. Never share your seed phrase.\n\n"
        "<b>Account:</b> An account is a logical sub-wallet within your xPub. Each buyer is assigned a unique account number.\n"
        "The account number is used to separate funds and addresses for different buyers.\n\n"
        "<b>Address Index:</b> Within each account, addresses are generated using an incrementing address index. Each invoice gets a unique address by increasing this index.\n\n"
        "<b>Buyer:</b> Represents a customer or group. Each buyer is linked to a specific account in your wallet.\n\n"
        "<b>Invoice:</b> A payment request generated for a buyer. Each invoice uses a unique address derived from your wallet's xPub, account, and address index.\n\n"
        "<b>Difference between Wallet, Account, and Address Index:</b>\n"
        "- <b>Wallet</b> is the whole structure generated from your seed phrase (mnemonic).\n"
        "- <b>xPub</b> is the extended public key for your wallet, used to derive all addresses.\n"
        "- <b>Account</b> is a logical partition inside your wallet, used for buyers.\n"
        "- <b>Address Index</b> is the number of the address within an account, incremented for each invoice.\n"
        "- <b>Derivation Path:</b> m/44'/195'/account'/0/address_index\n\n"
        "<b>Key commands:</b>\n"
        "/register - Register or manage your wallets (xPub)\n"
        "/buyers - List your buyers and their accounts\n"
        "/add_buyer - Add a new buyer (creates a new account in your wallet)\n"
        "/create_invoice - Create a new invoice for a buyer\n"
        "/invoices - List all invoices\n"
        "/deposit - Get your TRON deposit address for gas\n"
        "/balance - Show your TRON gas balance\n"
        "/sweep - Sweep paid invoices\n"
        "/help - Show this help message\n\n"
        "<b>Important:</b> To create a new wallet, you must use a new seed phrase and generate a new xPub. Never reuse a seed phrase for multiple wallets.\n"
        "Each account is unique for each buyer. Addresses are derived as: m/44'/195'/account'/0/address_index."
    )
    await message.answer(help_text, parse_mode="HTML")


def register_registration_fsm_handlers(dp, seller_handlers):
    dp.message.register(
        seller_handlers.process_choose_account_action,
        seller_handlers.RegisterFSM.choose_account_action,
    )
    dp.message.register(
        seller_handlers.process_select_existing_account,
        seller_handlers.RegisterFSM.select_existing_account,
    )
    dp.message.register(
        seller_handlers.process_register_xpub, seller_handlers.RegisterFSM.get_xpub
    )
    dp.message.register(
        seller_handlers.process_register_account,
        seller_handlers.RegisterFSM.get_account,
    )
    dp.message.register(
        seller_handlers.process_add_buyer_xpub,
        "add_buyer_xpub",
    )


def register_help_handler(dp, seller_handlers):
    dp.message.register(seller_handlers.handle_help, commands=["help"])


# Handler to cancel FSM state if main command is sent during an active FSM flow
