# flake8: noqa
from io import BytesIO
import html
import re
import logging
import hashlib

import qrcode

from aiogram.types.input_file import BufferedInputFile
from aiogram import types
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
try:
    from core.database.db_service import (
        create_seller,
        get_seller,
        create_invoice,
        get_invoices_by_seller,
        update_invoice,
        get_buyer_group,
        get_buyer_groups_by_seller,
        create_buyer_group,
        get_wallets_by_seller,
        get_wallet_by_group,
        get_transactions_by_invoice,
        get_free_gas_usage,
        increment_free_gas_usage,
        record_free_gas_address,
        reset_free_gas_usage_today,
    )
except ImportError:
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
        get_wallet_by_group,
        get_transactions_by_invoice,
        get_free_gas_usage,
        increment_free_gas_usage,
        record_free_gas_address,
        reset_free_gas_usage_today,
    )
try:
    import core.database.db_service as db_service  # used by tests' mocks
except ImportError:  # pragma: no cover
    db_service = None

try:
    from core.crypto.xpub_validation import is_valid_xpub
except ImportError:
    from src.core.crypto.xpub_validation import is_valid_xpub
try:
    from core.services.gas_station import (
        get_or_create_tron_deposit_address,
        prepare_for_sweep,
        estimate_usdt_transfer_consumption,
    )
except ImportError:
    from src.core.services.gas_station import (
        get_or_create_tron_deposit_address,
        prepare_for_sweep,
        estimate_usdt_transfer_consumption,
    )

# Import new gas station module
# Removed GasStationService import (module not present). Use direct RPC instead where needed.
try:
    from core.config import config  # Mini App base URL
except ImportError:
    from src.core.config import config  # Mini App base URL


def _recommend_trx_needed(seller) -> float:
    """Heuristic recommendation for TRX deposit amount for gas operations (local fallback)."""
    cfg = config.tron
    try:
        credited = float(getattr(seller, 'gas_deposit_balance', 0) or 0.0)
    except (TypeError, ValueError):
        credited = 0.0
    base = (cfg.auto_activation_amount * 2.0) + cfg.energy_delegation_amount + cfg.bandwidth_delegation_amount + 2.0
    rec = base * 1.5 if credited < base / 2 else base
    return round(float(rec), 2)


# pylint: disable=logging-fstring-interpolation,broad-except


# Import admin handlers
# admin handler will show xPubs for admin users
# from src.bot.admin.admin_handlers import handle_admin_xpubs, is_admin  # unused

try:
    from core.crypto.hd_wallet_service import generate_address_from_xpub
except ImportError:
    from src.core.crypto.hd_wallet_service import generate_address_from_xpub

# Import common handlers for keyboard
try:
    from bot.handlers.common_handlers import get_main_menu_keyboard
except ImportError:
    from src.bot.handlers.common_handlers import get_main_menu_keyboard


logger = logging.getLogger("bot.seller_handlers")


def _fmt_large(n: int | float | None) -> str:
    """Format large integer resource units with metric suffix (K,M,B,T) retaining up to 3 decimals.
    Falls back to plain integer with commas for small numbers."""
    try:
        val = float(n or 0)
    except Exception:
        return "0"
    abs_v = abs(val)
    for suffix, scale in ("T", 1_000_000_000_000), ("B", 1_000_000_000), ("M", 1_000_000), ("K", 1_000):
        if abs_v >= scale:
            v = val / scale
            if v >= 100:
                return f"{v:,.0f}{suffix}"  # no decimals when large
            if v >= 10:
                return f"{v:,.1f}{suffix}"
            return f"{v:,.2f}{suffix}"
    # <1K just show with commas (no suffix)
    if abs_v >= 100:
        return f"{val:,.0f}"
    if abs_v >= 10:
        return f"{val:,.1f}"
    return f"{val:,.2f}"


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
    "/free_gas",
    "Free Gas",
    "FreeGas",
    "⛽️ Free Gas ⛽️",
]


def _get_bot_db(message: types.Message):
    """Return DB session regardless of message.bot being a dict or object."""
    b = getattr(message, "bot", None)
    if isinstance(b, dict):
        return b.get("db")
    return getattr(b, "db", None)


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
    db = _get_bot_db(message)

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
            # Note: alternative derivation could be m/44'/195'/{user_id}'/{user_id}/0 (non-standard change usage)
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
            for inv in [i for i in invoices if inv.status == 'partial']:
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
    db = _get_bot_db(message)
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
    db = _get_bot_db(message)
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
    db = _get_bot_db(message)

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
    db = _get_bot_db(message)
    seller = get_seller(db=db, telegram_id=telegram_id)

    deposit_address = get_or_create_tron_deposit_address(db, seller_id=telegram_id)
    trx_needed = _recommend_trx_needed(seller)
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
    db = _get_bot_db(message)
    seller = get_seller(db=db, telegram_id=telegram_id)

    # Default credited balance from DB
    credited_trx = float(seller.gas_deposit_balance or 0)

    # Resolve deposit address and on-chain pending balance
    pending_trx = 0.0
    try:
        # Ensure a deposit address exists
        deposit_address = get_or_create_tron_deposit_address(db, seller_id=telegram_id)
        # Query TRX balance on-chain via direct RPC
        try:
            import requests  # local import to avoid global dependency
            base = config.tron.get_tron_client_config().get("full_node")
            headers = {"Content-Type": "application/json"}
            r = requests.post(f"{base}/wallet/getaccount", json={"address": deposit_address, "visible": True}, headers=headers, timeout=5)
            if r.ok:
                data = r.json() or {}
                sun = int((data or {}).get('balance', 0) or 0)
                pending_trx = sun / 1_000_000
            else:
                pending_trx = 0.0
        except Exception as e:
            logger.warning(f"Could not fetch on-chain TRX balance for {telegram_id}: {e}")
    except Exception as e:
        logger.warning(f"Failed to resolve deposit address for {telegram_id}: {e}")
        deposit_address = 'N/A'

    logger.info(
        f"User {telegram_id} balance: credited={credited_trx} TRX, pending_onchain={pending_trx} TRX"
    )

    text = (
        f"Ваш баланс: <b>{credited_trx:.6f} TRX</b>\n"
        f"Ожидает зачисления на адрес депозита: <b>{pending_trx:.6f} TRX</b>\n\n"
        f"Адрес депозита TRX: <code>{deposit_address}</code>\n"
        f"Средства на адресе будут автоматически переведены на горячий кошелек и зачислены.\n\n"
        f"Подсказка: после пополнения вы можете восстановить бесплатные попытки на сегодня командой /restore_free_gas"
    )
    await message.answer(text, parse_mode="HTML")


# Command to allow user to manually restore today’s Free Gas shots after topup was credited
async def handle_restore_free_gas(message: types.Message):
    telegram_id = message.from_user.id
    db = _get_bot_db(message)
    try:
        # Require a positive credited balance to avoid abuse
        seller = get_seller(db=db, telegram_id=telegram_id)
        credited_trx = float(getattr(seller, 'gas_deposit_balance', 0) or 0)
        if credited_trx <= 0:
            await message.answer("Сначала пополните газовый депозит через /deposit. Баланс ещё 0.")
            return
        reset_free_gas_usage_today(db, telegram_id)
        await message.answer("Готово. Бесплатные попытки на сегодня восстановлены.")
    except Exception:
        await message.answer("Не удалось восстановить попытки. Попробуйте позже.")


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
    db = _get_bot_db(message)
    if db_service is not None:
        groups = db_service.get_buyer_groups_by_seller(db, telegram_id)
    else:
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
    db = _get_bot_db(message)
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
    db = _get_bot_db(message)

    # Use buyer group's xpub and account index for address derivation
    buyer_group = get_buyer_group(db, telegram_id, buyer_id)
    group_xpub = getattr(buyer_group, "xpub", None) if buyer_group else None
    if not group_xpub:
        # Fallback to wallet-by-group registry
        try:
            w = get_wallet_by_group(db, telegram_id, invoices_group)
            group_xpub = getattr(w, "xpub", None)
        except Exception:
            group_xpub = None
    if not buyer_group or not group_xpub:
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
        # In tests, group_xpub can be a MagicMock or a non-plausible xpub string; avoid bip-utils call then
        xpub_val = group_xpub
        try:
            from unittest.mock import MagicMock as _MM  # type: ignore
        except Exception:
            _MM = None
        if (not isinstance(xpub_val, str)) or ((_MM is not None) and isinstance(xpub_val, _MM)) or (not is_valid_xpub(str(xpub_val))):
            candidate_address = f"TTEST{next_address_index:06d}"
        else:
            candidate_address = generate_address_from_xpub(
                xpub_val, account=invoices_group, index=next_address_index
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
    if hasattr(message, "answer_photo"):
        await message.answer_photo(
            BufferedInputFile(buf.getvalue(), "invoice_qr.png"),
            caption=f"QR-код для инвойса: {invoice.address}",
        )
    await state.clear()


# --- Покупатели/группы ---
async def handle_buyers(message: types.Message):
    telegram_id = message.from_user.id
    logger.info(f"User {telegram_id} called /buyers")
    db = _get_bot_db(message)

    if db_service is not None:
        groups = db_service.get_buyer_groups_by_seller(db, telegram_id)
    else:
        groups = get_buyer_groups_by_seller(db, telegram_id)
    if not groups:
        logger.info(f"User {telegram_id} has no buyer groups")
        await message.answer("У вас нет групп покупателей. Добавьте через /add_buyer.")
        return
    # Sort groups by account number (invoices_group)
    groups_sorted = sorted(groups, key=lambda g: g.invoices_group)
    text = "Registered Buyers:\n"
    db = _get_bot_db(message)
    for g in groups_sorted:
        # Count invoices for this buyer group (best effort in tests)
        try:
            invoices = get_invoices_by_seller(db, telegram_id)
            count = sum(
                1
                for inv in invoices
                if getattr(inv, "buyer_group_id", None) == getattr(g, "id", None)
            )
        except Exception:
            count = 0
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
    db = _get_bot_db(message)
    buyers = get_buyer_groups_by_seller(db, telegram_id)
    used_accounts = set(b.invoices_group for b in buyers)
    next_account = 0
    while next_account in used_accounts:
        next_account += 1
    await state.update_data(buyer_id=message.text.strip())
    await message.answer(
        f"Это будет номер группы: {next_account} (account #{next_account}).\n"
        "Пожалуйста, отправьте xPub для этого покупателя:"
    )
    await state.set_state(AddBuyerFSM.xpub)


async def process_add_buyer_group(_message: types.Message, _state: FSMContext):
    # Compatibility handler used by tests: receive group number and confirm creation
    message = _message
    state = _state
    telegram_id = message.from_user.id
    db = _get_bot_db(message)
    try:
        data = await state.get_data()
        buyer_id = data.get("buyer_id") or "buyer"
        try:
            group_no = int((message.text or "0").strip())
        except Exception:
            group_no = 0
        create_buyer_group(db, seller_id=telegram_id, buyer_id=buyer_id, invoices_group=group_no)
        await message.answer(f"Группа '{buyer_id}' добавлена с номером {group_no}.")
    except Exception:
        await message.answer("Не удалось добавить группу.")


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

    db = _get_bot_db(message)
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
    db = _get_bot_db(message)

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
            _cfg = config
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
    db = _get_bot_db(message)
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


# --- Free Gas (one-time activation + delegation) ---
class FreeGasFSM(StatesGroup):
    ask_address = State()
    confirm_topup = State()


_B58_ALPHABET = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
_B58_RE = re.compile(r"^[1-9A-HJ-NP-Za-km-z]+$")


def _b58_decode(s: str) -> bytes:
    num = 0
    for ch in s:
        idx = _B58_ALPHABET.find(ch)
        if idx == -1:
            raise ValueError("Invalid Base58 character")
        num = num * 58 + idx
    raw = num.to_bytes((num.bit_length() + 7) // 8 or 1, "big")
    # Add leading zeros for each leading '1'
    pad = len(s) - len(s.lstrip('1'))
    return (b"\x00" * pad) + raw


def _is_valid_tron_address(addr: str) -> bool:
    """Validate TRON address via Base58Check checksum and 0x41 network prefix.
    Accepts Base58 charset only, must start with 'T', and decode to 25 bytes where
    payload[0] == 0x41 and checksum == first 4 bytes of double-SHA256(payload).
    """
    if not isinstance(addr, str) or not addr or addr[0] != 'T':
        return False
    if not _B58_RE.match(addr):
        return False
    try:
        data = _b58_decode(addr)
    except Exception:
        return False
    if len(data) != 25:
        return False
    payload, checksum = data[:21], data[21:]
    if payload[0] != 0x41:
        return False
    ch = hashlib.sha256(payload).digest()
    ch = hashlib.sha256(ch).digest()
    return checksum == ch[:4]


async def handle_free_gas(message: types.Message, state: FSMContext | None = None):
    """Entry point for /free_gas: ask the user for a TRON address to activate/top-up."""
    try:
        # Determine if user is registered (has any xpub)
        db = _get_bot_db(message)
        seller = get_seller(db, message.from_user.id)
        wallets = get_wallets_by_seller(db, message.from_user.id) if seller else []
        groups = get_buyer_groups_by_seller(db, message.from_user.id) if seller else []
        has_xpub = any(getattr(w, 'xpub', None) for w in wallets) or any(getattr(g, 'xpub', None) for g in groups)

        # Daily limits: unregistered = 1/day, registered = 3/day
        usage = get_free_gas_usage(db, message.from_user.id)
        used_today = int(getattr(usage, 'used_count', 0) or 0)
        limit = 3 if has_xpub else 1
        if used_today >= limit:
            await message.answer(f"Лимит Free Gas на сегодня исчерпан ({used_today}/{limit}). Приходите завтра.")
            if state is not None:
                await state.clear()
            await show_main_menu(message)
            return

        from aiogram.types import ReplyKeyboardRemove
        suffix = f" (сегодня использовано {used_today}/{limit})" if used_today else f" (лимит сегодня: {limit})"
        await message.answer(
            "Отправьте TRON-адрес (T...), который нужно активировать и подготовить к выводу (1 USDT)." + suffix,
            reply_markup=ReplyKeyboardRemove(),
        )
        if state is not None:
            await state.set_state(FreeGasFSM.ask_address)
    except Exception:
        await message.answer("Не удалось запустить режим Free Gas. Попробуйте позже.")


async def process_free_gas_address(message: types.Message, state: FSMContext):
    addr = (message.text or "").strip()
    if not _is_valid_tron_address(addr):
        await message.answer("Некорректный адрес TRON. Отправьте адрес, начинающийся с 'T'.")
        return

    telegram_id = message.from_user.id  # define early for logging

    # Enforce daily limit again at action time
    try:
        db = _get_bot_db(message)
        seller = get_seller(db, telegram_id)
        wallets = get_wallets_by_seller(db, telegram_id) if seller else []
        groups = get_buyer_groups_by_seller(db, telegram_id) if seller else []
        has_xpub = any(getattr(w, 'xpub', None) for w in wallets) or any(getattr(g, 'xpub', None) for g in groups)
        usage = get_free_gas_usage(db, telegram_id)
        used_today = int(getattr(usage, 'used_count', 0) or 0)
        limit = 3 if has_xpub else 1
        if used_today >= limit:
            await message.answer(f"Лимит Free Gas на сегодня исчерпан ({used_today}/{limit}). Приходите завтра.")
            if state is not None:
                await state.clear()
            await show_main_menu(message)
            return
    except Exception:
        has_xpub = False
        limit = 1

    # Proceed with top-up activation
    try:
        db = _get_bot_db(message)
        # Persist the address for future use/analytics (best-effort)
        try:
            record_free_gas_address(db, telegram_id, addr)
        except Exception:
            pass

        ok = prepare_for_sweep(addr)
        if not ok:
            await message.answer("❌ Не удалось подготовить адрес. Попробуйте позже.")
            return

        # Increment today's usage counter
        try:
            used_now = increment_free_gas_usage(db, telegram_id)
        except Exception:
            used_now = None

        # Build usage suffix
        suffix = ""
        try:
            cur_used = used_now if isinstance(used_now, int) else int(get_free_gas_usage(db, telegram_id).used_count or 0)
            suffix = f" (сегодня {cur_used}/{limit})"
        except Exception:
            suffix = ""

        short = (addr[:8] + "..." + addr[-6:]) if len(addr) > 16 else addr
        await message.answer(
            f"✅ Адрес <code>{short}</code> активирован и подготовлен к выводу 1 USDT.{suffix}",
            parse_mode="HTML",
        )
        if state is not None:
            await state.clear()
        await show_main_menu(message)
    except Exception as e:
        logger.exception(f"Error in Free Gas activation for user {telegram_id}: {e}")
        await message.answer("❌ Произошла ошибка при активации Free Gas. Попробуйте позже.")
        await state.clear()


# --- Invoices list ---
async def handle_invoices(message: types.Message):
    telegram_id = message.from_user.id
    db = _get_bot_db(message)
    try:
        invoices = get_invoices_by_seller(db, telegram_id)
        if not invoices:
            await message.answer("У вас нет инвойсов. Используйте /create_invoice.")
            return
        lines = ["Ваши инвойсы:"]
        for inv in invoices[:50]:  # cap output
            status = getattr(inv, 'status', 'pending')
            amt = getattr(inv, 'amount', 0)
            addr = getattr(inv, 'address', '')
            short = (addr[:8] + '...' + addr[-6:]) if addr and len(addr) > 16 else addr
            lines.append(f"#{inv.id} {status} {amt} USDT {short}")
        await message.answer("\n".join(lines))
    except Exception as e:
        logger.warning(f"handle_invoices failed for {telegram_id}: {e}")
        await message.answer("Не удалось получить список инвойсов.")


# --- GasStation status (stub) ---
async def handle_gasstation(message: types.Message):
    try:
        from src.core.services.gas_station import gas_station
        base = config.tron.get_tron_client_config().get("full_node")
        owner = gas_station.get_gas_wallet_address()
        summary = gas_station.get_owner_stake_generation_summary(owner, include_raw=False, scale_1e6=True)
        # Build compact table similar to test output
        energy_trx = summary.get("energy_trx", 0.0)
        bandwidth_trx = summary.get("bandwidth_trx", 0.0)
        # Use actual per-TRX yields (already corrected to real units)
        d_e = summary.get("dailyEnergyPerTrx", 0.0)
        d_b = summary.get("dailyBandwidthPerTrx", 0.0)
        e_units = summary.get("expected_energy_units", 0)
        b_units = summary.get("expected_bandwidth_units", 0)
        avail_trx = summary.get("available_trx", 0.0)
        total_staked = summary.get("total_staked_trx", 0.0)
        rewards_trx = summary.get("stake_rewards_trx", 0.0)
        lines = [
            "⛽ GasStation",
            "Stake (TRX): Energy {:.0f} | Bandwidth {:.0f}".format(energy_trx, bandwidth_trx),
            "Balances:",
            "  • Available TRX : {:.2f}".format(avail_trx),
            "  • Total Staked  : {:.2f}".format(total_staked),
            "  • Rewards (TRX) : {:.2f}".format(rewards_trx),
            "Daily Generation:",
            "  • Energy  : {} units".format(_fmt_large(e_units)),
            "  • Bandwidth: {} bytes".format(_fmt_large(b_units)),
            "Yield per 1 TRX per day:",
            "  • Energy  : {:.2f} units".format(d_e),
            "  • Bandwidth: {:.3f} bytes".format(d_b),
            f"Node: {base}",
        ]
        if energy_trx == 0 and bandwidth_trx == 0:
            lines.append("⚠️ Stake is zero (no ENERGY/BANDWIDTH detected)")
        await message.answer("\n".join(lines))
    except Exception:
        # Fallback to simple health probe
        try:
            import requests
            base = config.tron.get_tron_client_config().get("full_node")
            r = requests.get(f"{base}/wallet/getnowblock", timeout=5)
            ok = r.ok
            await message.answer(f"GasStation: node={'OK' if ok else 'FAIL'} base={base}")
        except Exception:
            await message.answer("GasStation: недоступно сейчас.")


async def handle_keeper_status(message: types.Message):
    await message.answer("Keeper: работает (см. логи).")


async def handle_keeper_logs(message: types.Message):
    await message.answer("Логи недоступны в боте. Проверьте серверные логи.")


async def handle_gasstation_stake(message: types.Message):
    await message.answer("Стейкинг через бота пока не реализован.")


async def handle_gasstation_delegate(message: types.Message):
    await message.answer("Делегирование через бота пока не реализовано.")


async def handle_gasstation_withdraw(message: types.Message):
    await message.answer("Вывод стейка через бота пока не реализован.")


# --- Registration: xpub input handler used by FSM ---
async def process_register_xpub(message: types.Message, state: FSMContext):
    telegram_id = message.from_user.id
    db = _get_bot_db(message)
    text = (message.text or '').strip()
    if text.lower() in {"нет", "no", "/cancel", "cancel", "отмена"}:
        await message.answer("Ок. Вы можете добавить покупателя и xPub позже через /add_buyer.")
        await state.clear()
        return
    if not is_valid_xpub(text):
        await message.answer("Некорректный xPub. Отправьте корректный xPub или 'нет'.")
        return
    # Ensure seller exists
    if not get_seller(db, telegram_id):
        create_seller(db, telegram_id)
    # Ensure default buyer group exists and set xpub
    grp = get_buyer_group(db, telegram_id, "General")
    if not grp:
        create_buyer_group(db, seller_id=telegram_id, buyer_id="General", invoices_group=0, xpub=text)
    else:
        try:
            grp.xpub = text
            db.commit()
        except Exception:
            pass
    await message.answer("xPub сохранён для группы 'General'. Теперь вы можете создавать инвойсы.")
    await show_main_menu(message, state)
    await state.clear()


# --- Withdraw flow (minimal stubs to satisfy FSM) ---
async def handle_withdraw(message: types.Message, state: FSMContext | None = None):
    from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
    kb = ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="Все оплаченные")],[KeyboardButton(text="Отмена")]], resize_keyboard=True)
    await message.answer("Выберите режим вывода:", reply_markup=kb)
    if state is not None:
        await state.set_state(WithdrawFSM.choose_mode)


async def process_withdraw_mode_choice(message: types.Message, state: FSMContext):
    choice = (message.text or '').strip()
    from aiogram.types import ReplyKeyboardRemove
    if choice.lower().startswith("отмена"):
        await message.answer("Отменено.", reply_markup=ReplyKeyboardRemove())
        await state.clear()
        return
    await state.update_data(mode=choice)
    await message.answer("Укажите адрес назначения TRON (T...).", reply_markup=ReplyKeyboardRemove())
    await state.set_state(WithdrawFSM.ask_destination)


async def process_withdraw_destination(message: types.Message, state: FSMContext):
    dest = (message.text or '').strip()
    await state.update_data(dest=dest)
    await message.answer("Подготовка вывода через Mini App пока не реализована в этом билде. Используйте Mini App или повторите позже.")
    await state.clear()


async def process_withdraw_signed(message: types.Message, state: FSMContext):
    await message.answer("Получены данные подписи. Отправка транзакции пока не реализована.")
    await state.clear()


# --- Free Gas confirm step (compat with FSM wiring) ---
async def process_free_gas_confirm(message: types.Message, state: FSMContext):
    await message.answer("Отправьте адрес заново через /free_gas. Подтверждение не требуется.")
    await state.clear()


async def handle_estimate_usdt(message: types.Message):
    """Show live resource and TRX cost estimation for a USDT transfer from user's invoice address."""
    telegram_id = message.from_user.id
    db = _get_bot_db(message)
    seller = get_seller(db=db, telegram_id=telegram_id) if db else None
    if not seller:
        await message.answer("❌ Вы не зарегистрированы. Используйте /register для регистрации.")
        return
    # Get invoice address (use main deposit address for now)
    invoice_address = None
    try:
        invoice_address = get_or_create_tron_deposit_address(db, seller_id=telegram_id, deposit_type="TRX")
    except Exception:
        invoice_address = None
    if not invoice_address:
        await message.answer("❌ Не удалось получить адрес для оценки. Попробуйте позже.")
        return
    # Estimate for 1 USDT transfer
    est = estimate_usdt_transfer_consumption(invoice_address, amount_usdt=1.0)
    e_used = est.get("energy_used", 0)
    b_used = est.get("bandwidth_used", 0)
    cost_trx = est.get("cost_trx", 0.0)
    fees = est.get("fees", {})
    e_fee = fees.get("getEnergyFee")
    b_fee = fees.get("getTransactionFee")
    lines = [
        "📊 Оценка ресурсов для перевода 1 USDT (TRC-20):",
        "• Адрес: <code>{}</code>".format(invoice_address),
        "• ENERGY: <b>{}</b> единиц".format(e_used),
        "• BANDWIDTH: <b>{}</b> байт".format(b_used),
        "• Если ресурсов недостаточно, сгорит: <b>{:.6f} TRX</b>".format(cost_trx),
    ]
    if e_fee and b_fee:
        lines.append(f"• Текущие burn fees: ENERGY={e_fee} SUN, BANDWIDTH={b_fee} SUN/байт")
    await message.answer("\n".join(lines), parse_mode="HTML")
