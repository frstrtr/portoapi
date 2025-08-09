# flake8: noqa
from io import BytesIO
import html
import re
import asyncio
import logging

import qrcode

from aiogram.types.input_file import BufferedInputFile
from aiogram import types
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from src.core.database.db_service import (
    create_seller,
    get_seller,
    create_invoice,
    get_invoices_by_seller,
    update_invoice,
    get_buyer_group,
    get_buyer_groups_by_seller,
    create_buyer_group,
    get_wallets_by_seller,
    get_transactions_by_invoice,
)

from src.core.crypto.xpub_validation import is_valid_xpub
from src.core.services.gas_station import (
    get_or_create_tron_deposit_address,
    calculate_trx_needed,
    prepare_for_sweep,
)

# Import new gas station module
from src.core.services.gasstation import (
    GasStationService,
)
from src.core.config import config  # Mini App base URL


# pylint: disable=logging-fstring-interpolation,broad-except


# Import admin handlers
# admin handler will show xPubs for admin users
# from src.bot.admin.admin_handlers import handle_admin_xpubs, is_admin  # unused

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
    "/withdraw",
    "/invoices",
    "/gasstation",
    "/keeper_status",
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


# FSM для /sweep выбора режима
class SweepFSM(StatesGroup):
    choose_mode = State()  # пользователь выбирает что именно вывести


# FSM для /withdraw
class WithdrawFSM(StatesGroup):
    choose_mode = State()      # выбрать какие инвойсы выводить
    ask_destination = State()  # спросить адрес назначения
    await_signed = State()     # ожидание подписанных транзакций для броадкаста


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
                reply_markup=get_main_menu_keyboard(is_registered=False),
            )
            return

        # Get user info from Telegram
        user = message.from_user
        user_info = []
        user_info.append("👤 <b>Информация о пользователе:</b>")
        user_info.append(f"• ID: <code>{user.id}</code>")
        fn = html.escape(user.first_name) if user.first_name else "Не указано"
        user_info.append(f"• Имя: {fn}")
        if user.last_name:
            user_info.append(f"• Фамилия: {html.escape(user.last_name)}")
        if user.username:
            user_info.append(f"• Username: @{html.escape(user.username)}")
        else:
            user_info.append("• Username: Не указан")

        # Registration date
        if seller.date_created:
            reg_date = seller.date_created.strftime("%d.%m.%Y %H:%M")
            user_info.append(f"• Дата регистрации: {reg_date}")

        # Get buyer groups and xPubs
        buyer_groups = get_buyer_groups_by_seller(db, telegram_id)

        user_info.append("\n💳 <b>Кошельки (xPub):</b>")
        if buyer_groups:
            for group in buyer_groups:
                if group.xpub:
                    xpub_short = (
                        f"{group.xpub[:20]}...{group.xpub[-10:]}"

                        if len(group.xpub) > 35
                        else group.xpub
                    )
                    user_info.append(
                        f"• Account {group.invoices_group}: <code>{html.escape(xpub_short)}</code>"
                    )
                    if group.buyer_id:
                        user_info.append(f"  └ Покупатель: {html.escape(group.buyer_id)}")
                else:
                    user_info.append(
                        f"• Account {group.invoices_group}: ⚠️ xPub не настроен"
                    )
        else:
            user_info.append("• Нет настроенных кошельков")

        # Get wallets information
        wallets = get_wallets_by_seller(db, telegram_id)
        if wallets:
            # Personal wallet with derivation path m/44'/195'/{user_id}'/0/0
            # May conflict with other wallets or buyer groups
            # XXX better m/44'/195'/{user_id}'/{user_id}/0 - non standard change usage!!! but Unique
            user_info.append("\n🔑 <b>Дополнительные кошельки:</b>")
            for wallet in wallets:
                if wallet.xpub:
                    xpub_short = (
                        f"{wallet.xpub[:20]}...{wallet.xpub[-10:]}"

                        if len(wallet.xpub) > 35
                        else wallet.xpub
                    )
                    derivation_path = getattr(wallet, 'derivation_path', None) or "—"
                    deposit_type = getattr(wallet, 'deposit_type', None)
                    line = f"• Account {wallet.account} (path: {html.escape(derivation_path)})"
                    if deposit_type:
                        line += f" [{deposit_type}]"
                    line += f": <code>{html.escape(xpub_short)}</code>"
                    user_info.append(line)
                    if wallet.label:
                        user_info.append(f"  └ Метка: {html.escape(wallet.label)}")

        # Get invoice statistics
        invoices = get_invoices_by_seller(db, telegram_id)
        total_invoices = len(invoices)
        paid_invoices = len([inv for inv in invoices if inv.status == "paid"])
        pending_invoices = len([inv for inv in invoices if inv.status == "pending"])
        partial_invoices = len([inv for inv in invoices if inv.status == "partial"])

        user_info.append("\n📋 <b>Статистика инвойсов:</b>")
        user_info.append(f"• Всего: {total_invoices}")
        user_info.append(f"• Оплачено: {paid_invoices}")
        user_info.append(f"• Частично оплачено: {partial_invoices}")
        user_info.append(f"• В ожидании: {pending_invoices}")

        # Details for partially paid invoices
        if partial_invoices:
            user_info.append("\n🟡 <b>Частично оплаченные инвойсы:</b>")
            for inv in [i for i in invoices if i.status == 'partial']:
                try:
                    txs = get_transactions_by_invoice(db, inv.id)
                    total_received = sum(float(t.amount_received or 0) for t in txs)
                except Exception:
                    total_received = 0.0
                remaining = max(0.0, float(inv.amount) - total_received)
                addr_short = html.escape(inv.address[:8] + '...' + inv.address[-6:]) if inv.address and len(inv.address) > 15 else html.escape(getattr(inv, 'address', ''))
                user_info.append(
                    f"• #{inv.id} {total_received:.2f}/{float(inv.amount):.2f} USDT (осталось {remaining:.2f}) <code>{addr_short}</code>"
                )

        # Gas station balance
        user_info.append("\n⛽ <b>Газовый депозит:</b>")
        user_info.append(f"• Баланс: {seller.gas_deposit_balance:.2f} TRX")

        response_text = "\n".join(user_info)

        await message.answer(
            response_text,
            parse_mode="HTML",
            reply_markup=get_main_menu_keyboard(is_registered=True),
        )

    except Exception as e:
        logger.exception(f"Error in handle_myaccount for user {telegram_id}: {e}")
        await message.answer(
            "❌ Произошла ошибка при получении информации об аккаунте.",
            reply_markup=get_main_menu_keyboard(is_registered=True),
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
            reply_markup=get_main_menu_keyboard(is_registered=False),
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
            reply_markup=get_main_menu_keyboard(is_registered=True),
        )
        return

    # No xPub found, continue with registration
    await message.answer(
        "У вас ещё не зарегистрирован ни один xPub. Пожалуйста, отправьте ваш xPub (или напишите 'нет', чтобы получить инструкцию).",
        reply_markup=get_main_menu_keyboard(is_registered=False),
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


async def show_main_menu(message: types.Message, state: FSMContext | None = None):
    """
    Show the main actions keyboard to the user.
    """
    # mark state as used to satisfy linters
    if state is not None:
        _ = state
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
    db = message.bot.db
    seller = get_seller(db=db, telegram_id=telegram_id)

    # Default credited balance from DB
    credited_trx = float(seller.gas_deposit_balance or 0)

    # Resolve deposit address and on-chain pending balance
    pending_trx = 0.0
    try:
        from src.core.config import config
        # Ensure a deposit address exists
        deposit_address = get_or_create_tron_deposit_address(db, seller_id=telegram_id)
        # Query TRX balance on-chain via GasStationService's client
        gs = GasStationService(config.tron)
        acc_info = gs.tron.get_account(deposit_address)
        sun = int((acc_info or {}).get('balance', 0) or 0)
        pending_trx = sun / 1_000_000
    except Exception as e:
        logger.warning(f"Could not fetch on-chain TRX balance for {telegram_id}: {e}")
        deposit_address = deposit_address if 'deposit_address' in locals() else 'N/A'

    logger.info(
        f"User {telegram_id} balance: credited={credited_trx} TRX, pending_onchain={pending_trx} TRX"
    )

    # Build user-friendly response
    text = (
        f"Ваш баланс: <b>{credited_trx:.6f} TRX</b>\n"
        f"Ожидает зачисления на адрес депозита: <b>{pending_trx:.6f} TRX</b>\n\n"
        f"Адрес депозита TRX: <code>{deposit_address}</code>\n"
        f"Средства на адресе будут автоматически переведены на горячий кошелек и зачислены."
    )
    await message.answer(text, parse_mode="HTML")


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


async def process_add_buyer_group(_message: types.Message, _state: FSMContext):
    # No longer needed, merged with xpub step
    pass


# New FSM state handler for buyer xPUB
async def process_add_buyer_xpub(message: types.Message, state: FSMContext):
    telegram_id = message.from_user.id
    data = await state.get_data()
    buyer_id = data.get("buyer_id")
    xpub_text = message.text.strip()

    # Allow user to cancel
    if xpub_text.lower() in {"/cancel", "отмена", "cancel"}:
        await message.answer("Операция добавления покупателя отменена.")
        await state.clear()
        return

    if not buyer_id:
        await message.answer("Контекст утерян. Пожалуйста, начните сначала: /add_buyer")
        await state.clear()
        return

    # Validate xPub format strictly to avoid accepting other keyboard texts
    if not is_valid_xpub(xpub_text):
        await message.answer(
            "Некорректный xPub. Отправьте корректный xPub (начинается обычно с 'xpub', 'ypub', 'zpub') или /cancel для отмены."
        )
        return

    db = message.bot.db
    # Find next available account index for this seller
    buyers = get_buyer_groups_by_seller(db, telegram_id)
    used_accounts = set(b.invoices_group for b in buyers)
    next_account = 0
    while next_account in used_accounts:
        next_account += 1
    try:
        create_buyer_group(
            db,
            seller_id=telegram_id,
            buyer_id=buyer_id,
            invoices_group=next_account,
            xpub=xpub_text,
        )
    except Exception as e:
        logger.warning(f"Failed to create buyer group for user {telegram_id}: {e}")
        await message.answer("Ошибка при сохранении покупателя. Попробуйте позже или /cancel.")
        return

    logger.info(
        f"User {telegram_id} added buyer: {buyer_id} | account: {next_account} | xpub: {xpub_text}"
    )
    await message.answer(
        f"Покупатель {buyer_id} с аккаунтом {next_account} и xPub добавлен."
    )
    await show_main_menu(message, state)
    await state.clear()


async def handle_sweep(message: types.Message, state: FSMContext = None):
    """Initiate sweep process with option for partial invoices.
    Always resets any previous FSM state to avoid conflicts with other flows (/add_buyer etc)."""
    telegram_id = message.from_user.id
    logger.info(f"User {telegram_id} called /sweep")
    db = message.bot.db

    # Clear any previous state to prevent handlers (like add_buyer xpub) from intercepting reply buttons
    if state is not None:
        prev = await state.get_state()
        if prev:
            logger.debug(f"/sweep clearing previous FSM state {prev} for user {telegram_id}")
            await state.clear()

    invoices = get_invoices_by_seller(db=db, seller_id=telegram_id)

    # Determine paid/partial based on actual received amounts (transactions),
    # not only the stored invoice.status. This allows sweeping when funds arrived
    # but the status hasn't been updated yet (e.g., during activation).
    paid_invoices: list = []
    partial_invoices: list = []
    for inv in invoices:
        try:
            txs = get_transactions_by_invoice(db, inv.id)
            total_received = sum(float(t.amount_received or 0) for t in txs)
        except Exception:
            total_received = 0.0
        try:
            amount_required = float(getattr(inv, "amount", 0) or 0)
        except Exception:
            amount_required = 0.0

        if amount_required > 0 and total_received >= amount_required:
            paid_invoices.append(inv)
        elif total_received > 0:
            partial_invoices.append(inv)

    if not paid_invoices and not partial_invoices:
        logger.info(f"User {telegram_id} sweep: no paid or partial invoices (by tx analysis)")
        await message.answer("Нет оплаченных или частично оплаченных инвойсов для вывода.")
        return

    total_paid = 0.0
    for inv in paid_invoices:
        try:
            total_paid += float(getattr(inv, "amount", 0) or 0)
        except Exception:
            pass

    total_partial_received = 0.0
    for inv in partial_invoices:
        try:
            txs = get_transactions_by_invoice(db, inv.id)
            total_partial_received += sum(float(t.amount_received or 0) for t in txs)
        except Exception:
            pass

    # Helper: fetch technical state for an address (best effort)
    def _fetch_invoice_tech_state(addr: str) -> dict:
        try:
            from src.core.config import config as _cfg
            import requests  # local import
            from datetime import datetime, timezone
            base = _cfg.tron.get_tron_client_config().get("full_node")
            headers = {"Content-Type": "application/json"}

            def _post(path: str, payload: dict):
                try:
                    r = requests.post(f"{base}{path}", json=payload, headers=headers, timeout=5)
                    if r.ok:
                        return r.json() or {}
                except Exception:
                    return {}
                return {}

            # Account and balance
            acc = _post("/wallet/getaccount", {"address": addr, "visible": True})
            activated = bool(acc)
            balance_sun = int((acc or {}).get("balance", 0) or 0)
            balance_trx = balance_sun / 1_000_000

            # Resources
            res = _post("/wallet/getaccountresource", {"address": addr, "visible": True}) or {}
            try:
                energy_avail = max(0, int(res.get("EnergyLimit", 0)) - int(res.get("EnergyUsed", 0)))
            except Exception:
                energy_avail = 0
            try:
                free_bw_avail = max(0, int(res.get("freeNetLimit", 0)) - int(res.get("freeNetUsed", 0)))
                paid_bw_avail = max(0, int(res.get("NetLimit", 0)) - int(res.get("NetUsed", 0)))
                bw_avail = free_bw_avail + paid_bw_avail
            except Exception:
                free_bw_avail = 0
                paid_bw_avail = 0
                bw_avail = 0

            # Delegation reclaim ETA (nearest expiry among incoming delegations)
            eta_str = "—"
            try:
                dr = _post("/wallet/getdelegatedresourcev2", {"toAddress": addr, "visible": True}) or {}
                items = dr.get("delegatedResource", []) or dr.get("delegated_resource", [])
                soonest = None
                now_ms = int(datetime.now(tz=timezone.utc).timestamp() * 1000)
                for it in items or []:
                    # look for expire_time in ms
                    exp = it.get("expire_time") or it.get("expireTime")
                    if isinstance(exp, (int, float)) and exp > now_ms:
                        if soonest is None or exp < soonest:
                            soonest = exp
                if soonest:
                    delta_s = max(0, int((soonest - now_ms) / 1000))
                    days = delta_s // 86400
                    hours = (delta_s % 86400) // 3600
                    mins = (delta_s % 3600) // 60
                    if days > 0:
                        eta_str = f"{days}д {hours}ч"
                    elif hours > 0:
                        eta_str = f"{hours}ч {mins}м"
                    else:
                        eta_str = f"{mins}м"
            except Exception:
                eta_str = "—"

            return {
                "activated": activated,
                "trx": balance_trx,
                "energy": energy_avail,
                "bw": bw_avail,
                "bw_free": free_bw_avail,
                "bw_paid": paid_bw_avail,
                "delegation_eta": eta_str,
            }
        except Exception:
            return {"activated": False, "trx": 0.0, "energy": 0, "bw": 0, "bw_free": 0, "bw_paid": 0, "delegation_eta": "—"}

    keyboard_rows = []
    if paid_invoices:
        keyboard_rows.append([types.KeyboardButton(text="Снять только оплаченные")])
    if paid_invoices or partial_invoices:
        keyboard_rows.append([types.KeyboardButton(text="Снять включая частичные")])
    keyboard_rows.append([types.KeyboardButton(text="Отмена")])
    kb = types.ReplyKeyboardMarkup(keyboard=keyboard_rows, resize_keyboard=True)

    text_lines = ["Запуск процедуры вывода:"]
    if paid_invoices:
        text_lines.append(f"• Полностью оплачено: {len(paid_invoices)} шт. на сумму {total_paid:.2f} USDT")
    if partial_invoices:
        text_lines.append(
            f"• Частично оплачено: {len(partial_invoices)} шт., получено суммарно {total_partial_received:.2f} USDT"
        )
        text_lines.append(
            "Вы можете вывести средства с адресов частичных инвойсов (будут помечены как 'swept') или подождать полного платежа."
        )

    # Append technical state for involved invoices
    try:
        text_lines.append("\nТехническое состояние адресов:")
        for inv in paid_invoices + partial_invoices:
            addr = getattr(inv, "address", "") or ""
            state_info = _fetch_invoice_tech_state(addr)
            short_addr = (addr[:8] + "..." + addr[-6:]) if addr and len(addr) > 16 else addr
            act = "да" if state_info.get("activated") else "нет"
            trx = state_info.get("trx", 0.0)
            en = state_info.get("energy", 0)
            bw_free = state_info.get("bw_free", 0)
            bw_paid = state_info.get("bw_paid", 0)
            eta = state_info.get("delegation_eta", "—")
            text_lines.append(
                f"• #{inv.id} {short_addr}: активирован: {act}, TRX: {trx:.3f}, Energy: {en}, BW: free {bw_free} / paid {bw_paid}, возврат делегации через: {eta}"
            )
    except Exception:
        # Non-fatal; skip details if node not reachable
        pass

    text_lines.append("Выберите действие:")

    await message.answer("\n".join(text_lines), reply_markup=kb)
    if state is not None:
        await state.set_state(SweepFSM.choose_mode)
        await state.update_data(paid_ids=[inv.id for inv in paid_invoices], partial_ids=[inv.id for inv in partial_invoices])


async def process_sweep_mode_choice(message: types.Message, state: FSMContext):
    telegram_id = message.from_user.id
    choice = message.text.strip()
    db = message.bot.db
    data = await state.get_data()
    paid_ids = data.get("paid_ids", [])
    partial_ids = data.get("partial_ids", [])

    if choice.lower().startswith("отмена"):
        from aiogram.types import ReplyKeyboardRemove
        await message.answer("Операция отменена.", reply_markup=ReplyKeyboardRemove())
        await show_main_menu(message, state)
        await state.clear()
        return

    if choice not in {"Снять только оплаченные", "Снять включая частичные"}:
        await message.answer("Пожалуйста, выберите вариант из клавиатуры.")
        return

    sweep_partial = choice == "Снять включая частичные"

    to_sweep_ids = paid_ids + (partial_ids if sweep_partial else [])
    if not to_sweep_ids:
        from aiogram.types import ReplyKeyboardRemove
        await message.answer("Нет выбранных инвойсов для вывода.", reply_markup=ReplyKeyboardRemove())
        await state.clear()
        return

    success_count = 0
    failed_ids = []
    for inv in get_invoices_by_seller(db, telegram_id):
        if inv.id in to_sweep_ids:
            try:
                ok = prepare_for_sweep(inv.address)
                if ok:
                    update_invoice(db=db, invoice_id=inv.id, status="swept")
                    success_count += 1
                else:
                    failed_ids.append(inv.id)
                    logger.warning(f"Sweep preparation returned False for invoice {inv.id} (address {inv.address})")
            except Exception as e:
                failed_ids.append(inv.id)
                logger.warning(f"Sweep failed for invoice {inv.id}: {e}")

    from aiogram.types import ReplyKeyboardRemove
    details = ""
    if failed_ids:
        details = f"\nНе удалось подготовить: {len(failed_ids)} (ID: {', '.join(map(str, failed_ids[:10]))}{'...' if len(failed_ids)>10 else ''})"
    await message.answer(
        f"Готово. Успешно подготовлено {success_count} инвойсов. Частично оплаченные были {'включены' if sweep_partial else 'пропущены'}.{details}",
        reply_markup=ReplyKeyboardRemove(),
    )
    await show_main_menu(message, state)
    await state.clear()


# --- Withdrawal helpers ---

def _is_tron_address(addr: str) -> bool:
    return isinstance(addr, str) and addr.startswith("T") and 26 <= len(addr) <= 36


def _broadcast_signed_hex(hexstr: str) -> dict:
    """Broadcast a signed TRON transaction hex via HTTP. Returns response dict."""
    try:
        from src.core.config import config as _cfg
        import requests  # local import
        base = _cfg.tron.get_tron_client_config().get("full_node") or _cfg.tron.get_fallback_client_config().get("full_node")
        if not base:
            raise RuntimeError("No TRON node endpoint configured")
        headers = {"Content-Type": "application/json"}
        payload = {"transaction": hexstr}
        resp = requests.post(f"{base}/wallet/broadcasthex", json=payload, headers=headers, timeout=20)
        return resp.json() if resp.ok else {"result": False, "error": resp.text}
    except Exception as e:
        return {"result": False, "error": str(e)}


# --- Withdrawal FSM handlers ---
async def handle_withdraw(message: types.Message, state: FSMContext):
    """Start withdrawal flow: user chooses whether to include partial invoices."""
    telegram_id = message.from_user.id
    db = message.bot.db
    # Reset FSM
    prev = await state.get_state()
    if prev:
        await state.clear()

    invoices = get_invoices_by_seller(db=db, seller_id=telegram_id)
    paid_invoices, partial_invoices = [], []
    for inv in invoices:
        try:
            txs = get_transactions_by_invoice(db, inv.id)
            total_received = sum(float(t.amount_received or 0) for t in txs)
        except Exception:
            total_received = 0.0
        amount_required = float(getattr(inv, "amount", 0) or 0)
        if amount_required > 0 and total_received >= amount_required:
            paid_invoices.append(inv)
        elif total_received > 0:
            partial_invoices.append(inv)

    if not paid_invoices and not partial_invoices:
        await message.answer("Нет оплаченных или частично оплаченных инвойсов для вывода.")
        return

    kb_rows = []
    if paid_invoices:
        kb_rows.append([types.KeyboardButton(text="Вывести только оплаченные")])
    kb_rows.append([types.KeyboardButton(text="Вывести включая частичные")])
    kb_rows.append([types.KeyboardButton(text="Отмена")])
    kb = types.ReplyKeyboardMarkup(keyboard=kb_rows, resize_keyboard=True)

    total_paid = sum(float(getattr(i, "amount", 0) or 0) for i in paid_invoices)
    total_partial = 0.0
    for inv in partial_invoices:
        try:
            txs = get_transactions_by_invoice(db, inv.id)
            total_partial += sum(float(t.amount_received or 0) for t in txs)
        except Exception:
            pass

    lines = ["Выберите режим вывода средств:"]
    if paid_invoices:
        lines.append(f"• Полностью оплачено: {len(paid_invoices)} на {total_paid:.2f} USDT")
    if partial_invoices:
        lines.append(f"• Частично оплачено: {len(partial_invoices)} на {total_partial:.2f} USDT")

    await message.answer("\n".join(lines), reply_markup=kb)
    # Offer Mini App signer as a one-click option
    try:
        import os
        from urllib.parse import urlsplit
        base = getattr(config, 'api', None)
        configured = getattr(base, 'base_url', None) or "http://localhost:8000"
        # Prefer explicit SETUP_URL_BASE if present in env
        setup_base = os.getenv('SETUP_URL_BASE')
        if setup_base:
            root_base = setup_base.rstrip('/')
        else:
            parts = urlsplit(configured)
            root_base = f"{parts.scheme}://{parts.netloc}"
        miniapp_url = f"{root_base}/miniapp/?seller_id={telegram_id}"
        ikb = types.InlineKeyboardMarkup(
            inline_keyboard=[[types.InlineKeyboardButton(text="Открыть Mini App (подписать)", web_app=types.WebAppInfo(url=miniapp_url))]]
        )
        await message.answer("Или используйте Mini App для подписи и отправки:", reply_markup=ikb)
    except Exception:
        pass

    await state.set_state(WithdrawFSM.choose_mode)
    await state.update_data(paid_ids=[i.id for i in paid_invoices], partial_ids=[i.id for i in partial_invoices])


async def process_withdraw_mode_choice(message: types.Message, state: FSMContext):
    choice = message.text.strip()
    if choice.lower().startswith("отмена"):
        from aiogram.types import ReplyKeyboardRemove
        await message.answer("Операция отменена.", reply_markup=ReplyKeyboardRemove())
        await show_main_menu(message, state)
        await state.clear()
        return
    if choice not in {"Вывести только оплаченные", "Вывести включая частичные"}:
        await message.answer("Пожалуйста, выберите вариант из клавиатуры.")
        return

    data = await state.get_data()
    paid_ids = data.get("paid_ids", [])
    partial_ids = data.get("partial_ids", [])
    include_partial = choice == "Вывести включая частичные"
    selected_ids = paid_ids + (partial_ids if include_partial else [])

    if not selected_ids:
        from aiogram.types import ReplyKeyboardRemove
        await message.answer("Нет выбранных инвойсов для вывода.", reply_markup=ReplyKeyboardRemove())
        await state.clear()
        return

    await state.update_data(selected_invoice_ids=selected_ids)
    from aiogram.types import ReplyKeyboardRemove
    await message.answer(
        "Укажите адрес назначения TRON (T...): все выбранные суммы USDT будут отправлены на этот адрес.",
        reply_markup=ReplyKeyboardRemove(),
    )
    await state.set_state(WithdrawFSM.ask_destination)


async def process_withdraw_destination(message: types.Message, state: FSMContext):
    to_addr = message.text.strip()
    if not _is_tron_address(to_addr):
        await message.answer("Некорректный адрес TRON. Отправьте адрес, начинающийся с 'T'.")
        return

    db = message.bot.db
    data = await state.get_data()
    selected_ids = data.get("selected_invoice_ids", [])
    invoices_index = {inv.id: inv for inv in get_invoices_by_seller(db, message.from_user.id)}

    # Prepare unsigned TRC20 transfers
    try:
        from src.core.config import config
        gs = GasStationService(config.tron)
        contract = gs.tron.get_contract(gs.usdt_contract)
    except Exception:
        await message.answer("Ошибка инициализации TRON-клиента. Попробуйте позже.")
        await state.clear()
        return

    pending = []
    lines = [
        "Сформированы транзакции для вывода USDT. Подпишите каждую приватным ключом адреса инвойса и пришлите в формате:",
        "ID <invoice_id> <SIGNED_HEX>",
    ]
    for inv_id in selected_ids:
        inv = invoices_index.get(inv_id)
        if not inv:
            continue
        try:
            txs = get_transactions_by_invoice(db, inv.id)
            total_received = sum(float(t.amount_received or 0) for t in txs)
        except Exception:
            total_received = 0.0
        amount_required = float(getattr(inv, "amount", 0) or 0)
        amount_usdt = min(amount_required if amount_required > 0 else total_received, total_received)
        if amount_usdt <= 0:
            continue
        amount_6 = int(round(amount_usdt * 1_000_000))
        try:
            txn = (
                contract.functions.transfer(to_addr, amount_6)
                .with_owner(inv.address)
                .fee_limit(10_000_000)
                .build()
            )
            # Store minimal reference for user-side signing
            try:
                tx_obj = txn.to_json()
            except Exception:
                tx_obj = getattr(txn, "raw_data", {})
        except Exception:
            continue
        pending.append({"invoice_id": inv.id, "from": inv.address, "to": to_addr, "amount_usdt": amount_usdt, "tx": tx_obj})
        short_addr = inv.address[:8] + "..." + inv.address[-6:]
        lines.append(f"• ID {inv.id}: {amount_usdt:.6f} USDT с {short_addr} → {to_addr}")
    if not pending:
        await message.answer("Нет транзакций для подготовки вывода.")
        await state.clear()
        return

    await state.update_data(pending_withdrawals=pending)
    await message.answer("\n".join(lines))
    await state.set_state(WithdrawFSM.await_signed)


async def process_withdraw_signed(message: types.Message, state: FSMContext):
    text = (message.text or "").strip()
    if text.lower().startswith("отмена"):
        await state.clear()
        await show_main_menu(message, state)
        return

    data = await state.get_data()
    pending = data.get("pending_withdrawals", [])
    if not pending:
        await message.answer("Нет ожидающих транзакций для отправки.")
        await state.clear()
        return

    m = re.match(r"^ID\s+(\d+)\s+([0-9a-fA-F]+)$", text)
    if not m:
        await message.answer("Формат неверен. Используйте: ID <invoice_id> <SIGNED_HEX>")
        return
    inv_id = int(m.group(1))
    signed_hex = m.group(2)

    entry = next((p for p in pending if int(p.get("invoice_id")) == inv_id), None)
    if not entry:
        await message.answer("Неизвестный ID инвойса или он уже обработан.")
        return

    resp = _broadcast_signed_hex(signed_hex)
    if not resp.get("result"):
        err = resp.get("message") or resp.get("error") or str(resp)
        await message.answer(f"❌ Ошибка отправки транзакции: {err}")
        return

    txid = resp.get("txid") or resp.get("transaction", {}).get("txID")
    try:
        update_invoice(db=message.bot.db, invoice_id=inv_id, status="withdrawn")
    except Exception:
        pass

    pending = [p for p in pending if int(p.get("invoice_id")) != inv_id]
    await state.update_data(pending_withdrawals=pending)
    await message.answer(f"✅ Транзакция отправлена. TXID: {txid or '—'}")

    if not pending:
        await message.answer("Все подготовленные выводы обработаны.")
        await state.clear()
        await show_main_menu(message, state)


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


# Register sweep FSM handler

def register_sweep_handlers(dp, seller_handlers):
    dp.message.register(
        seller_handlers.process_sweep_mode_choice, seller_handlers.SweepFSM.choose_mode
    )


# Gas Station and Keeper Bot handlers
async def handle_gasstation(message: types.Message):
    """Handle gas station status and management"""
    try:
        from src.core.config import config
        processing_msg = await message.answer("⏳ Getting gas station status...")
        gas_station = GasStationService(config.tron)
        try:
            status = await asyncio.wait_for(asyncio.to_thread(gas_station.get_status), timeout=30.0)
        except asyncio.TimeoutError:
            await processing_msg.delete()
            await message.answer("❌ Gas station request timed out. TRON network connection might be slow. Please try again.")
            return

        response = "⛽ **Gas Station Status**\n\n"
        response += f"🏦 **Address:** `{status['address']}`\n"
        response += f"💰 **TRX Balance:** {status['balance']:.2f} TRX\n\n"
        response += "📊 **Staked Resources:**\n"
        if status["resources"]["energy"]["staked"] > 0:
            response += f"⚡ **Energy:** {status['resources']['energy']['staked']:,.0f} TRX\n"
            response += f"   Available: {status['resources']['energy']['available']:,} units\n"
        if status["resources"]["bandwidth"]["staked"] > 0:
            response += f"📡 **Bandwidth:** {status['resources']['bandwidth']['staked']:,.0f} TRX\n"
            response += f"   Available: {status['resources']['bandwidth']['available']:,} units\n"
        response += f"\n🔗 **Network:** {status['network']}\n"
        response += f"✅ **Status:** {'Online' if status.get('operational', {}).get('can_process_100_tx', False) else 'Offline'}\n"
        try:
            energy_eff = status.get("efficiency", {}).get("energy", 0)
            bandwidth_eff = status.get("efficiency", {}).get("bandwidth", 0)
            avg_eff = (energy_eff + bandwidth_eff) / 2 if (energy_eff or bandwidth_eff) else 0
            response += f"\n📈 **Efficiency:** {avg_eff:.1f}%\n"
        except Exception:
            response += "\n📈 **Efficiency:** Not available\n"
        response += "\n🔧 **Management Commands:**\n"
        response += "• `/gasstation_stake` - Manage staking\n"
        response += "• `/gasstation_delegate` - Manage delegation\n"
        response += "• `/gasstation_withdraw` - Withdraw resources\n"
        await processing_msg.delete()
        await message.answer(response, parse_mode="Markdown")
    except ValueError:
        if 'processing_msg' in locals():
            try:
                await processing_msg.delete()
            except Exception:
                pass
        await message.answer("❌ Gas station configuration error. Please check gas wallet config.")
    except Exception:
        if 'processing_msg' in locals():
            try:
                await processing_msg.delete()
            except Exception:
                pass
        await message.answer("❌ Error retrieving gas station status. Try again later.")


async def handle_keeper_status(message: types.Message):
    """Handle keeper bot status monitoring"""
    try:
        # Check if keeper bot process is running by checking log activity
        import subprocess

        keeper_running = False

        # Try to check if process is running via ps command (Linux/Unix)
        try:
            result = subprocess.run(
                ["pgrep", "-f", "keeper_bot.py"],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
            keeper_running = bool(result.stdout.strip())
        except (subprocess.TimeoutExpired, FileNotFoundError):
            # Fallback: check recent log activity
            try:
                with open("bot.log", "r", encoding="utf-8") as f:
                    lines = f.readlines()
                    keeper_logs = [line for line in lines[-20:] if "keeper_bot" in line]
                    if keeper_logs:
                        # Check if last log is recent (within last 5 minutes)
                        # This is a simple heuristic - if we see recent logs, assume it's running
                        keeper_running = True
            except Exception:
                pass

        response = "🤖 **Keeper Bot Status**\n\n"

        if keeper_running:
            response += "✅ **Status:** Running\n"

            # Try to get recent log entries
            try:
                with open("bot.log", "r", encoding="utf-8") as f:
                    lines = f.readlines()
                    keeper_logs = [line for line in lines[-50:] if "keeper_bot" in line]
                    if keeper_logs:
                        last_log = keeper_logs[-1].strip()
                        # Extract timestamp and message
                        if "Checking pending invoices" in last_log:
                            response += "🔍 **Last Activity:** Checking invoices\n"
                        elif "Invoice" in last_log and "paid" in last_log:
                            response += (
                                "💰 **Last Activity:** Invoice payment detected\n"
                            )
                        elif "connected to local TRON node" in last_log:
                            response += (
                                "🔗 **Last Activity:** Connected to local node\n"
                            )
                        elif "connected to remote TRON" in last_log:
                            response += (
                                "🌐 **Last Activity:** Connected to remote API\n"
                            )
                        else:
                            response += "📝 **Last Activity:** Processing...\n"
            except Exception:
                pass

        else:
            response += "❌ **Status:** Not Running\n"
            response += "ℹ️ The keeper bot monitors pending invoices and handles automatic account activation.\n"

        response += "\n📊 **Functions:**\n"
        response += "• Monitor pending invoice payments\n"
        response += "• Auto-activate TRON accounts\n"
        response += "• Handle USDT transfer detection\n"
        response += "• Manage payment notifications\n"
        response += "• Local TRON node support with fallback\n"

        if keeper_running:
            response += "\n🔧 **Management:**\n"
            response += "• `/keeper_logs` - View recent logs\n"

        await message.answer(response, parse_mode="Markdown")

    except Exception as e:
        logger.error(f"Error in keeper status handler: {e}")
        await message.answer(
            "❌ Error retrieving keeper bot status. Please try again later."
        )


async def handle_keeper_logs(message: types.Message):
    """Show recent keeper bot logs"""
    try:
        with open("bot.log", "r", encoding="utf-8") as f:
            lines = f.readlines()
            keeper_logs = [line for line in lines[-100:] if "keeper_bot" in line]

        if not keeper_logs:
            await message.answer("📝 No recent keeper bot logs found.")
            return

        recent_logs = keeper_logs[-10:]
        response = "📋 **Recent Keeper Bot Logs:**\n\n"
        for log in recent_logs:
            clean_log = log.strip()
            if len(clean_log) > 100:
                clean_log = clean_log[:97] + "..."
            response += f"`{clean_log}`\n"

        response += f"\n📊 **Total entries:** {len(keeper_logs)}"
        await message.answer(response, parse_mode="Markdown")

    except Exception as e:
        logger.error(f"Error reading keeper logs: {e}")
        await message.answer("❌ Error reading keeper bot logs.")


async def handle_gasstation_stake(message: types.Message):
    """Handle gas station staking management"""
    await message.answer("🚧 Gas station staking management coming soon!")


async def handle_gasstation_delegate(message: types.Message):
    """Handle gas station delegation management"""
    await message.answer("🚧 Gas station delegation management coming soon!")


async def handle_gasstation_withdraw(message: types.Message):
    """Handle gas station withdrawal management"""
    await message.answer("🚧 Gas station withdrawal management coming soon!")


# --- Invoices list handler ---
async def handle_invoices(message: types.Message):
    telegram_id = message.from_user.id
    db = message.bot.db
    invoices = get_invoices_by_seller(db, telegram_id)
    if not invoices:
        await message.answer("У вас пока нет инвойсов.")
        return
    lines = ["Ваши инвойсы:"]
    for inv in sorted(invoices, key=lambda i: getattr(i, 'id', 0))[:50]:
        addr = getattr(inv, "address", "") or "—"
        short = (addr[:8] + "..." + addr[-6:]) if addr and len(addr) > 16 else addr
        lines.append(
            f"• #{inv.id}: {getattr(inv, 'amount', 0)} USDT | статус: {getattr(inv, 'status', '—')} | {short}"
        )
    if len(invoices) > 50:
        lines.append(f"… и ещё {len(invoices) - 50} инвойсов")
    await message.answer("\n".join(lines))


# --- Registration handlers (xPub flow) ---
async def process_register_xpub(message: types.Message, state: FSMContext):
    telegram_id = message.from_user.id
    db = message.bot.db
    xpub_text = (message.text or "").strip()

    if xpub_text.lower() in {"/cancel", "отмена", "cancel"}:
        await message.answer("Регистрация отменена.")
        await state.clear()
        return

    if not is_valid_xpub(xpub_text):
        await message.answer("Некорректный xPub. Отправьте корректный xPub или /cancel для отмены.")
        return

    # Choose next available account index
    buyers = get_buyer_groups_by_seller(db, telegram_id)
    used_accounts = set(b.invoices_group for b in buyers)
    account = 0
    while account in used_accounts:
        account += 1

    # Create default buyer group (General) with this xPub
    buyer_id = "General" if not any(b.buyer_id == "General" for b in buyers) else f"General-{account}"
    try:
        create_buyer_group(
            db,
            seller_id=telegram_id,
            buyer_id=buyer_id,
            invoices_group=account,
            xpub=xpub_text,
        )
    except Exception:
        await message.answer("Ошибка при сохранении xPub. Попробуйте позже.")
        return

    await message.answer(f"xPub сохранён. Создан покупатель '{buyer_id}' (account {account}).")
    await state.clear()
    await show_main_menu(message, state)


async def process_register_account(message: types.Message, state: FSMContext):
    """Optional handler to accept custom account index, then ask for xPub"""
    text = (message.text or "").strip()
    try:
        account = int(text)
        await state.update_data(selected_account=account)
        await message.answer(f"Выбран account {account}. Теперь отправьте xPub для этого аккаунта.")
        await state.set_state(RegisterFSM.get_xpub)
    except Exception:
        await message.answer("Укажите номер аккаунта числом, например 0.")
        return


# Handler to cancel FSM state if main command is sent during an active FSM flow
