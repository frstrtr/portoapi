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


# pylint: disable=logging-fstring-interpolation


# Import admin handlers
# admin handler will show xPubs for admin users
from src.bot.admin.admin_handlers import handle_admin_xpubs, is_admin

# Import database service functions
from src.core.database.db_service import get_wallets_by_seller

from src.core.crypto.hd_wallet_service import generate_address_from_xpub


logger = logging.getLogger("bot.seller_handlers")


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
    choose_account_action = State()
    select_existing_account = State()
    ask_address = State()


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
            "Вы новый пользователь. Пожалуйста, отправьте ваш xPub (или напишите 'нет', чтобы получить инструкцию)."
        )
        if state is not None:
            await state.set_state(RegisterFSM.get_xpub)
        return

    # Check if seller has any xPub submitted (wallets with seller_id)
    wallets = get_wallets_by_seller(db, telegram_id)
    has_xpub = any(w.xpub for w in wallets)

    if not has_xpub:
        await message.answer(
            "У вас ещё не зарегистрирован ни один xPub. Пожалуйста, отправьте ваш xPub (или напишите 'нет', чтобы получить инструкцию)."
        )
        if state is not None:
            await state.set_state(RegisterFSM.get_xpub)
        return

    if wallets:
        kb = types.ReplyKeyboardMarkup(
            keyboard=[
                [types.KeyboardButton(text="Использовать существующий аккаунт")],
                [types.KeyboardButton(text="Создать новый аккаунт в этом xPub")],
                [types.KeyboardButton(text="Создать новый кошелек (новый xPub)")],
            ],
            resize_keyboard=True,
        )
        logger.info(
            f"User {telegram_id} has wallets, prompting for registration choice."
        )
        try:
            await message.answer(
                "У вас уже есть зарегистрированные кошельки. Выберите действие:",
                reply_markup=kb,
            )
            await state.set_state(RegisterFSM.choose_account_action)
            logger.info(
                f"FSM state set to choose_account_action for user {telegram_id}"
            )
        except Exception as e:
            logger.error(f"Error in registration choice prompt: {e}")
            await message.answer(
                "Ошибка при обработке выбора. Попробуйте ещё раз или обратитесь к администратору."
            )
        return


# --- Registration FSM choice handlers ---
async def process_choose_account_action(message: types.Message, state: FSMContext):
    telegram_id = message.from_user.id
    db = message.bot.db
    choice = message.text.strip()
    from src.core.database.db_service import get_wallets_by_seller

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
    elif choice == "Создать новый аккаунт в этом xPub":
        # Ask for xPub to use (show list)
        xpubs = list(set([w.xpub for w in wallets]))
        kb = types.ReplyKeyboardMarkup(keyboard=[], resize_keyboard=True)
        for xpub in xpubs:
            kb.keyboard.append([types.KeyboardButton(text=f"{xpub}")])
        await message.answer(
            "Выберите xPub для создания нового аккаунта:", reply_markup=kb
        )
        await state.update_data(wallets=wallets)
        await state.set_state(RegisterFSM.get_xpub)
        return
    elif choice == "Создать новый кошелек (новый xPub)":
        await message.answer("Пожалуйста, отправьте новый xPub:")
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
        f"Вы выбрали аккаунт {account} для xPub {xpub}. Регистрация пропущена, можно использовать этот аккаунт."
    )
    await show_main_menu(message, state)
    await state.clear()
    return


async def show_main_menu(message: types.Message, state: FSMContext = None):
    """
    Show the main actions keyboard to the user.
    """
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
    await message.answer("Вы вернулись в главное меню.", reply_markup=kb)
    await message.answer(
        "Регистрация нового HD кошелька.\n\n"
        "Пожалуйста, отправьте ваш xPub (или напишите 'нет', чтобы получить инструкцию)."
    )
    if state is not None:
        await state.set_state(RegisterFSM.get_xpub)
    return

    # # Non-FSM registration flow
    # token = secrets.token_urlsafe(16)
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

    # Always use master wallet (first wallet for seller) and derive address using buyer group as account index
    wallets = get_wallets_by_seller(db, telegram_id)
    if not wallets:
        logger.error(
            f"User {telegram_id} tried to create invoice but has no master wallet/xpub."
        )
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
            "❌ Ошибка: не найден xPub для вашего аккаунта. Пожалуйста, зарегистрируйте xPub через /register.",
            reply_markup=kb,
        )
        await state.clear()
        return
    wallet = wallets[0]
    logger.info(f"Using master wallet xPub: {wallet.xpub} for buyer group/account {invoices_group}")
    buyer_group = get_buyer_group(db, telegram_id, buyer_id)
    # Always use buyer group as account index, and use a unique derivation index for each invoice (address index)
    from src.core.database.db_service import get_invoices_by_seller
    existing_invoices = get_invoices_by_seller(db, telegram_id)
    # Only consider used addresses for this xpub and this account index (buyer group)
    used_addresses = set(
        inv.address for inv in existing_invoices
        if inv.derivation_index is not None and getattr(inv, "buyer_group_id", None) == buyer_group.id
    )
    # Find the first unused address index for this account (buyer group)
    next_address_index = 0
    while True:
        candidate_address = generate_address_from_xpub(wallet.xpub, next_address_index, account=invoices_group)
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
        f"Инвойс создан!\nАдрес: <code>{invoice.address}</code>\nСумма: <b>{data['amount']}</b>\nОписание: {data['description']}\nГруппа: {buyer_id}\n\nПуть деривации: <code>{derivation_path}</code>",
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
    xpub = text
    if not is_valid_xpub(xpub):
        logger.warning(f"User {telegram_id} provided invalid xPub: {xpub}")
        await message.answer(
            "Некорректный xPub. Пожалуйста, проверьте и отправьте корректный xPub."
        )
        return
    await state.update_data(xpub=xpub)
    db = message.bot.db
    # Find max account for this xpub and seller
    from src.core.database.db_service import get_wallets_by_seller

    wallets = get_wallets_by_seller(db, telegram_id)
    same_xpub_wallets = [w for w in wallets if w.xpub == xpub]
    if same_xpub_wallets:
        next_account = (
            max(
                [w.account for w in same_xpub_wallets if w.account is not None],
                default=-1,
            )
            + 1
        )
    else:
        next_account = 0
    await state.update_data(account=next_account)
    await message.answer(
        f"Аккаунт BIP44 для этого xPub будет автоматически назначен: {next_account}. Продолжаем регистрацию..."
    )
    await process_register_account(message, state)


async def process_register_account(message: types.Message, state: FSMContext):
    telegram_id = message.from_user.id
    # If called from auto mode, get account from state
    data = await state.get_data()
    xpub = data.get("xpub")
    db = message.bot.db
    account = data.get("account")
    from src.core.database.db_service import get_wallet_by_group, create_seller_wallet

    wallet = get_wallet_by_group(db, telegram_id, account)
    if wallet and wallet.xpub == xpub:
        await message.answer(
            f"Этот xPub уже зарегистрирован для аккаунта {account}. Регистрация пропущена."
        )
        await state.clear()
        return
    if wallet:
        wallet.xpub = xpub
        wallet.account = account
        db.commit()
        logger.info(
            f"User {telegram_id} xPub updated in wallet: {xpub} (account {account})"
        )
    else:
        create_seller_wallet(
            db,
            seller_id=telegram_id,
            xpub=xpub,
            account=account,
            address=None,
            derivation_path=None,
            deposit_type=None,
        )
        logger.info(
            f"User {telegram_id} registered new xPub and wallet created: {xpub} (account {account})"
        )
    await state.update_data(account=account)
    # ---
    # The following prompt asks the user to provide a public receiving address for the registered account.
    # By default, the bot will derive this address from the xPub and BIP44 account index.
    # However, the user can override it by specifying a custom address (for advanced integrations, external wallets, or business needs).
    # The public address is safe to share and is used to receive funds for this account.
    # If not needed, the user can reply 'нет' and the bot will use the default derived address.
    # ---
    await message.answer(
        f"Аккаунт BIP44 {account} успешно сохранён для xPub!"
    )
    await show_main_menu(message, state)
    await message.answer(
        "Теперь укажите адрес для этого аккаунта (или напишите 'нет', если не требуется):\n\n"
        "Адрес — это публичный адрес для получения средств, который будет связан с этим аккаунтом. Если не требуется, напишите 'нет'."
    )
    await state.set_state(RegisterFSM.ask_address)


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
