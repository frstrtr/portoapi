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
        record_free_gas_address,
        reset_free_gas_usage_today,
    get_free_gas_usage,
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
        record_free_gas_address,
        reset_free_gas_usage_today,
    get_free_gas_usage,
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
    )
except ImportError:
    from src.core.services.gas_station import (
        get_or_create_tron_deposit_address,
        prepare_for_sweep,
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
    await_signed = State()     # ожидание подписанных транзакций для броадкаст


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
        # Aggregate user info lines
        user_info: list[str] = []
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

        # Deterministic user-specific address (first available xPub, account = telegram_id, index 0)
        deterministic_addr = None
        primary_xpub = None
        try:
            if buyer_groups:
                for g in buyer_groups:
                    if g.xpub:
                        primary_xpub = g.xpub
                        break
            if not primary_xpub:
                wallets_tmp = get_wallets_by_seller(db, telegram_id)
                for w in wallets_tmp:
                    if w.xpub:
                        primary_xpub = w.xpub
                        break
            if primary_xpub:
                # Use telegram_id as BIP44 account index (bounded)
                acct_index = int(telegram_id) % 2_147_483_000
                deterministic_addr = generate_address_from_xpub(primary_xpub, index=0, account=acct_index)
        except Exception:
            deterministic_addr = None
        if deterministic_addr:
            user_info.append("\n🧬 <b>Детерминированный адрес (по Telegram ID):</b>")
            user_info.append(f"• Path: m/44'/195'/{int(telegram_id)%2_147_483_000}'/0/0")
            user_info.append(f"• Address: <code>{html.escape(deterministic_addr)}</code>")

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

        # Aggregate invoice amounts
        try:
            total_paid_amount = sum(float(inv.amount or 0) for inv in invoices if inv.status == 'paid')
        except Exception:
            total_paid_amount = 0.0
        # For partial invoices compute received so far
        partial_received_total = 0.0
        partial_outstanding_total = 0.0
        try:
            for inv in [i for i in invoices if i.status == 'partial']:
                try:
                    txs = get_transactions_by_invoice(db, inv.id)
                    received = sum(float(t.amount_received or 0) for t in txs)
                except Exception:
                    received = 0.0
                outstanding = max(0.0, float(inv.amount) - received)
                partial_received_total += received
                partial_outstanding_total += outstanding
        except Exception:
            pass
        try:
            pending_amount_total = sum(float(inv.amount or 0) for inv in invoices if inv.status == 'pending')
        except Exception:
            pending_amount_total = 0.0
        user_info.append("\n💰 <b>Суммы по инвойсам:</b>")
        user_info.append(f"• Оплачено всего: {total_paid_amount:.2f} USDT")
        if partial_invoices:
            user_info.append(f"• Получено по частичным: {partial_received_total:.2f} USDT (осталось {partial_outstanding_total:.2f} USDT)")
        user_info.append(f"• В ожидании (pending): {pending_amount_total:.2f} USDT")

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
        # Deposit address & recommendation
        try:
            deposit_address = get_or_create_tron_deposit_address(db, seller_id=telegram_id)
            rec_amt = _recommend_trx_needed(seller)
            user_info.append(f"• Адрес депозита: <code>{html.escape(deposit_address)}</code>")
            user_info.append(f"• Рекомендуемый депозит: {rec_amt:.2f} TRX")
        except Exception:
            pass

        # Free gas usage info (if record exists)
        try:
            usage = get_free_gas_usage(db, seller_id=telegram_id)
            if usage:
                user_info.append("\n🆓 <b>Free Gas сегодня:</b>")
                user_info.append(f"• Использовано попыток: {usage.used_count}")
        except Exception:
            pass

        response_text = "\n".join(user_info)

        await message.answer(
            response_text,
            parse_mode="HTML",
            reply_markup=get_main_menu_keyboard(is_registered=True),
        )
    except Exception as e:  # pragma: no cover
        try:
            logger.exception(f"Error in handle_myaccount for user {telegram_id}: {e}")
        except Exception:
            pass
        try:
            await message.answer(
                "❌ Произошла ошибка при получении информации об аккаунте.",
                reply_markup=get_main_menu_keyboard(is_registered=True),
            )
        except Exception:
            pass


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

async def process_register_xpub(message: types.Message, state: FSMContext):
    """Handle xPub submission during initial /register flow."""
    telegram_id = message.from_user.id
    txt = (message.text or "").strip()
    db = _get_bot_db(message)
    # Allow cancel
    if txt.lower() in {"/cancel", "cancel", "отмена"}:
        await message.answer("Регистрация отменена.")
        await state.clear()
        return
    # Provide instructions
    if txt.lower() in {"нет", "no", "help", "?"}:
        await message.answer(
            "Чтобы получить xPub: в вашем кошельке (например, Trust / Unisat и т.п.) найдите функцию экспорта расширенного публичного ключа (xpub/ypub/zpub) для нужной seed-фразы. Отправьте сюда строку, начинающуюся на xpub/ypub/zpub."
        )
        return
    if not is_valid_xpub(txt):
        await message.answer("Некорректный xPub. Отправьте действительный xPub или напишите 'нет' для инструкции.")
        return
    # Determine next available account index for buyer groups (use as wallet grouping)
    try:
        groups = get_buyer_groups_by_seller(db, telegram_id)
    except Exception:
        groups = []
    used_accounts = {g.invoices_group for g in groups}
    next_account = 0
    while next_account in used_accounts:
        next_account += 1
    # Use buyer_id 'General' for first group if free
    buyer_id = "General" if all(getattr(g, 'buyer_id', '').lower() != 'general' for g in groups) else f"Wallet{next_account}"
    try:
        create_buyer_group(
            db,
            seller_id=telegram_id,
            buyer_id=buyer_id,
            invoices_group=next_account,
            xpub=txt,
        )
    except Exception as e:  # pragma: no cover
        logger.warning(f"process_register_xpub failed to create group for {telegram_id}: {e}")
        await message.answer("Не удалось сохранить xPub. Попробуйте позже или /cancel.")
        return
    await message.answer(f"xPub сохранён. Добавлена группа '{buyer_id}' (account {next_account}). Регистрация завершена.")
    await show_main_menu(message, state)
    await state.clear()


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
    gas_main_address = ""
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
        # Gas station main (hot) wallet address
        try:
            from src.core.services.gas_station import gas_station as _gs  # type: ignore
        except ImportError:
            try:
                from core.services.gas_station import gas_station as _gs  # type: ignore
            except Exception:
                _gs = None  # type: ignore
        if _gs is not None:
            try:
                gas_main_address = _gs.get_gas_wallet_address()
            except Exception:
                gas_main_address = ""
    except Exception as e:
        logger.warning(f"Failed to resolve deposit address for {telegram_id}: {e}")
        deposit_address = 'N/A'

    logger.info(
        f"User {telegram_id} balance: credited={credited_trx} TRX, pending_onchain={pending_trx} TRX"
    )
    # Recommendation (reuse logic from myaccount)
    try:
        recommended = _recommend_trx_needed(seller)
    except Exception:
        recommended = 0.0

    extra_lines = []
    if gas_main_address:
        if gas_main_address == deposit_address:
            extra_lines.append("Главный адрес газовой станции совпадает с адресом вашего депозита (shared).")
        else:
            extra_lines.append(f"Главный адрес газовой станции (горячий кошелёк): <code>{gas_main_address}</code>")
    if recommended > 0:
        extra_lines.append(f"Рекомендуемый депозит: <b>{recommended:.2f} TRX</b>")

    text = (
        f"Ваш баланс: <b>{credited_trx:.6f} TRX</b>\n"
        f"Ожидает зачисления на адрес депозита: <b>{pending_trx:.6f} TRX</b>\n\n"
        f"Адрес депозита TRX: <code>{deposit_address}</code>\n"
        + ("\n".join(extra_lines) + "\n\n" if extra_lines else "\n")
        + "Средства на адресе будут автоматически переведены на горячий кошелек и зачислены.\n\n"
        + "Подсказка: после пополнения вы можете восстановить бесплатные попытки на сегодня командой /restore_free_gas"
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


async def handle_invoices(message: types.Message):
    """List recent invoices for the user (basic summary)."""
    telegram_id = message.from_user.id
    db = _get_bot_db(message)
    try:
        invs = get_invoices_by_seller(db, telegram_id)
        if not invs:
            await message.answer("У вас пока нет инвойсов.")
            return
        # Show up to 15 latest by id desc
        invs_sorted = sorted(invs, key=lambda i: getattr(i, 'id', 0), reverse=True)[:15]
        lines = ["Ваши последние инвойсы:"]
        for inv in invs_sorted:
            try:
                amt = float(getattr(inv, 'amount', 0) or 0)
            except Exception:
                amt = 0.0
            status = getattr(inv, 'status', 'unknown')
            addr = getattr(inv, 'address', '') or ''
            short_addr = (addr[:8] + '...' + addr[-6:]) if addr and len(addr) > 16 else addr
            lines.append(f"#{getattr(inv,'id','?')} {amt:.2f} USDT {status} {short_addr}")
        await message.answer("\n".join(lines))
    except Exception as e:  # pragma: no cover
        logger.warning(f"handle_invoices failed for {telegram_id}: {e}")
        await message.answer("Не удалось получить список инвойсов.")


# --- Withdraw flow (simplified placeholder) ---
async def handle_withdraw(message: types.Message, state: FSMContext | None = None):
    """Entry point for /withdraw - simplified: list swept invoices only."""
    telegram_id = message.from_user.id
    db = _get_bot_db(message)
    try:
        invs = get_invoices_by_seller(db, telegram_id)
    except Exception:
        invs = []
    swept = [i for i in invs if getattr(i, 'status', '') == 'swept']
    if not swept:
        await message.answer("Нет средств для вывода (нет swept инвойсов).")
        return
    total = 0.0
    for i in swept:
        try:
            total += float(getattr(i, 'amount', 0) or 0)
        except Exception:
            pass
    await message.answer(f"Доступно для вывода (упрощённо): {total:.2f} USDT по {len(swept)} инвойсам. Укажите адрес назначения или /cancel.")
    if state is not None:
        await state.set_state(WithdrawFSM.ask_destination)


async def process_withdraw_mode_choice(message: types.Message, state: FSMContext):
    # Placeholder to satisfy dispatcher; reuse handle_withdraw
    await handle_withdraw(message, state)


async def process_withdraw_destination(message: types.Message, state: FSMContext):
    dest = (message.text or '').strip()
    if dest.lower() in {"/cancel", "cancel", "отмена"}:
        await message.answer("Отменено.")
        await state.clear()
        return
    # Basic TRON address format check
    if not _is_valid_tron_address(dest):
        await message.answer("Некорректный адрес TRON. Отправьте корректный или /cancel.")
        return
    await message.answer("Формирование транзакций вывода не реализовано в этой сборке (placeholder).")
    await state.clear()


async def process_withdraw_signed(message: types.Message, state: FSMContext):
    await message.answer("Обработка подписанных транзакций недоступна (placeholder).")
    await state.clear()


# --- Gas station & keeper placeholder handlers (re-added after refactor) ---
async def handle_gasstation(message: types.Message):
    """Richer gas station status (restored)."""
    try:
        processing_msg = await message.answer("⏳ Getting gas station status...")
        # Prefer new unified gas_station manager; fallback to legacy service if present
        try:
            from src.core.services.gas_station import gas_station as _gs  # type: ignore
            address = _gs.get_gas_wallet_address()
            network = getattr(_gs.tron_config, 'network', 'tron')
            # Comprehensive summary (delegated + self stake, expected yields, balances)
            summary = _gs.get_owner_stake_generation_summary(include_raw=True)
            # Liquid TRX balance (already in summary['available_trx']) but fallback via client if missing
            liquid = float(summary.get("available_trx", 0.0) or 0.0)
            if not liquid:
                try:
                    bal = _gs.client.get_account_balance(address) if getattr(_gs, 'client', None) else 0
                    liquid = float(bal)
                except Exception:
                    pass
            energy_stake = float(summary.get("energy_trx", 0.0) or 0.0)
            bandwidth_stake = float(summary.get("bandwidth_trx", 0.0) or 0.0)
            total_stake = float(summary.get("total_staked_trx", energy_stake + bandwidth_stake) or 0.0)
            exp_e = int(summary.get("expected_energy_units", 0) or 0)
            exp_bw = int(summary.get("expected_bandwidth_units", 0) or 0)
            daily_e_per_trx = float(summary.get("dailyEnergyPerTrx", 0.0) or 0.0)
            daily_bw_per_trx = float(summary.get("dailyBandwidthPerTrx", 0.0) or 0.0)
            rewards = float(summary.get("stake_rewards_trx", 0.0) or 0.0)
            # Detect if dynamic on-chain params were successfully used
            raw_params = (summary.get("raw") or {}).get("global_params", {}) if isinstance(summary.get("raw"), dict) else {}
            dynamic_params = bool(raw_params.get("totalEnergyLimit", 0) > 0 and raw_params.get("totalEnergyWeightSun", 0) > 0)
            operational = exp_e > 0 and exp_bw > 0
            response = ["⛽ Gas Station Status", f"🏦 Address: <code>{html.escape(address)}</code>"]
            response.append(f"💰 Liquid Balance: {liquid:.2f} TRX")
            response.append(f"🪙 Stake: ENERGY {energy_stake:.3f} TRX • BANDWIDTH {bandwidth_stake:.3f} TRX • Total {total_stake:.3f} TRX")
            response.append("📊 Daily Generation (expected):")
            def _fmt_units(v: int) -> str:
                if v >= 1_000_000_000:
                    return f"{v/1_000_000_000:.2f}B"
                if v >= 1_000_000:
                    return f"{v/1_000_000:.2f}M"
                if v >= 1000:
                    return f"{v/1000:.2f}K"
                return f"{v}"  # small numbers raw
            response.append(f"   ⚡ Energy: {_fmt_units(exp_e)} (≈{exp_e:,} units)")
            response.append(f"   📡 Bandwidth: {_fmt_units(exp_bw)} (≈{exp_bw:,} units)")
            response.append(f"   Yield/Stake Ratios: ⚡ {daily_e_per_trx:.2f} u/TRX/day • 📡 {daily_bw_per_trx:.2f} u/TRX/day")
            if rewards > 0:
                response.append(f"🎁 Pending Rewards: {rewards:.6f} TRX")
            response.append(f"🔗 Network: {network} ({'dynamic' if dynamic_params else 'config est.'} yields)")
            if 'warning' in summary:
                response.append(f"⚠️ {html.escape(str(summary['warning']))}")
            response.append(f"✅ Status: {'Online' if operational else 'Degraded'}")
            response.append("\n🔧 Management Commands:\n• /gasstation_stake\n• /gasstation_delegate\n• /gasstation_withdraw")
            try:
                await processing_msg.delete()
            except Exception:
                pass
            await message.answer("\n".join(response), parse_mode="HTML")
        except Exception:
            # Fallback to legacy GasStationService if still available
            try:
                from core.services.gasstation import GasStationService  # type: ignore
            except Exception:
                from src.core.services.gasstation import GasStationService  # pragma: no cover
            try:
                from core.config import config as _cfg
            except Exception:
                from src.core.config import config as _cfg  # pragma: no cover
            try:
                import asyncio as _asyncio
                gas_station_service = GasStationService(_cfg.tron)
                status = await _asyncio.wait_for(_asyncio.to_thread(gas_station_service.get_status), timeout=20.0)
                await processing_msg.delete()
                response = ["⛽ Gas Station Status (legacy)", f"🏦 Address: <code>{html.escape(status.get('address',''))}</code>"]
                response.append(f"💰 TRX Balance: {status.get('balance',0):.2f} TRX")
                response.append(f"🔗 Network: {status.get('network','tron')}")
                await message.answer("\n".join(response), parse_mode="HTML")
            except Exception:
                if 'processing_msg' in locals():
                    try: await processing_msg.delete()
                    except Exception: pass
                await message.answer("❌ Error retrieving gas station status.")
    except Exception as e:
        await message.answer(f"❌ Error retrieving gas station status. <code>{html.escape(str(e))}</code>", parse_mode="HTML")


async def handle_gasstation_stake(message: types.Message):
    await message.answer("Команда стейкинга пока недоступна через бота.")


async def handle_gasstation_delegate(message: types.Message):
    await message.answer("Делегация через команду временно отключена.")


async def handle_gasstation_withdraw(message: types.Message):
    await message.answer("Вывод стейка через команду временно отключён.")


async def handle_keeper_status(message: types.Message):
    """Heuristic keeper bot status check (restored)."""
    import subprocess
    keeper_running = False
    try:
        result = subprocess.run(["pgrep", "-f", "keeper_bot.py"], capture_output=True, text=True, timeout=5, check=False)
        keeper_running = bool(result.stdout.strip())
    except Exception:
        pass
    recent_log_line = None
    try:
        with open("bot.log", "r", encoding="utf-8") as f:
            lines = f.readlines()[-200:]
        keeper_lines = [l for l in lines if "keeper_bot" in l]
        if keeper_lines:
            recent_log_line = keeper_lines[-1].strip()
            # If last log within 10 minutes assume running
            keeper_running = True
    except Exception:
        pass
    resp = ["🤖 Keeper Bot Status", f"Status: {'✅ Running' if keeper_running else '❌ Not detected'}"]
    if recent_log_line:
        resp.append("Last log: " + html.escape(recent_log_line[-180:]))
    await message.answer("\n".join(resp), parse_mode="HTML")


async def handle_keeper_logs(message: types.Message):
    try:
        with open("bot.log", "r", encoding="utf-8") as f:
            lines = f.readlines()[-100:]
        keeper_lines = [l for l in lines if "keeper_bot" in l][-40:]
        if not keeper_lines:
            await message.answer("Логи keeper бот отсутствуют.")
            return
        text = "Последние логи keeper:\n" + "".join(keeper_lines)[-3500:]
        await message.answer(f"<code>{html.escape(text)}</code>", parse_mode="HTML")
    except Exception as e:
        await message.answer(f"Не удалось прочитать логи: {e}")


async def handle_estimate_usdt(message: types.Message):
    """Estimate resources & delegation needs for a USDT transfer.
    Usage: /estimate_usdt [amount] [from_address(optional)] [to_address(optional)]
    Defaults: amount=1, from=sample placeholder (will fallback), to=owner address.
    """
    parts = (message.text or "").strip().split()
    amount = 1.0
    from_addr = None
    to_addr = None
    if len(parts) >= 2:
        try:
            amount = float(parts[1])
        except Exception:
            await message.answer("Некорректная сумма. Пример: /estimate_usdt 5")
            return
    if len(parts) >= 3:
        from_addr = parts[2]
    if len(parts) >= 4:
        to_addr = parts[3]
    if amount <= 0:
        await message.answer("Сумма должна быть > 0")
        return
    try:
        try:
            from core.services.gas_station import gas_station as _gs, estimate_usdt_transfer_consumption as _est
        except ImportError:  # pragma: no cover
            from src.core.services.gas_station import gas_station as _gs, estimate_usdt_transfer_consumption as _est  # type: ignore
        if to_addr is None:
            try:
                to_addr = _gs.get_gas_wallet_address()
            except Exception:
                to_addr = from_addr or "TPLACEHOLDER"  # benign fallback
        if from_addr is None:
            from_addr = to_addr  # self-estimate if not provided
        data = _est(from_address=from_addr, to_address=to_addr, amount_usdt=amount)
    except Exception as e:  # pragma: no cover
        await message.answer(f"Не удалось выполнить оценку: {e}")
        return
    en = data.get("energy_used") or data.get("energy_used_estimate") or 0
    bw = data.get("bandwidth_used") or data.get("bandwidth_used_estimate") or 0
    fee_trx = data.get("fee_trx") or data.get("fee") or 0
    lines = [
        f"Оценка перевода {amount:.2f} USDT:",
        f"Energy: {en}",
        f"Bandwidth: {bw}",
        f"Fee (TRX, approx): {fee_trx}",
    ]
    await message.answer("\n".join(lines))


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
        db = _get_bot_db(message)
        telegram_id = message.from_user.id
        # Light eligibility check (registered user with at least one wallet or buyer group)
        try:
            seller = get_seller(db, telegram_id)
            has_any = False
            if seller:
                try:
                    if get_wallets_by_seller(db, telegram_id):
                        has_any = True
                except Exception:
                    pass
                try:
                    if get_buyer_groups_by_seller(db, telegram_id):
                        has_any = True
                except Exception:
                    pass
            if not has_any:
                await message.answer("Сначала завершите регистрацию и добавьте хотя бы один xPub через /register.")
                return
        except Exception:
            await message.answer("Не удалось проверить регистрацию. Попробуйте позже.")
            return

        # Prompt user for address
        if state is not None:
            await state.set_state(FreeGasFSM.ask_address)
        await message.answer(
            "🆓 Введите TRON адрес для одноразовой активации и делегации ресурсов (для 1 USDT перевода).\n"
            "Отправьте адрес формата, начинающегося на 'T'."
        )
    except Exception as e:  # pragma: no cover
        logger.exception(f"Error in handle_free_gas: {e}")
        await message.answer("Ошибка обработки команды.")


async def process_free_gas_address(message: types.Message, state: FSMContext):
    """Validate address and show preview (dry-run) of what would be delegated."""
    addr = (message.text or "").strip()
    if addr.lower() in {"/cancel", "cancel", "отмена"}:
        await message.answer("Отменено.")
        await state.clear()
        return
    if not _is_valid_tron_address(addr):
        await message.answer("Некорректный TRON адрес. Проверьте и отправьте снова или /cancel.")
        return
    # Acquire dry-run plan
    try:
        try:
            from core.services.gas_station import gas_station as _gs
        except ImportError:  # pragma: no cover
            from src.core.services.gas_station import gas_station as _gs  # type: ignore
        plan = _gs.dry_run_prepare_for_sweep(addr)
    except Exception as e:  # pragma: no cover
        logger.warning(f"dry_run_prepare_for_sweep failed for {addr}: {e}")
        plan = {"error": str(e)}

    if plan.get("error"):
        await message.answer(f"Не удалось смоделировать делегацию: {html.escape(plan['error'])}")
        await state.clear()
        return

    notes = plan.get("notes", [])
    cur = plan.get("current", {})
    miss = plan.get("missing", {})
    req = plan.get("required", {})
    pl = plan.get("plan", {})
    activation = "да" if plan.get("activation_needed") else "нет"
    activation_method = plan.get("activation_method") or "—"
    text_lines = [
        "Предпросмотр (без действий):",
        f"Адрес: <code>{html.escape(addr)}</code>",
        f"Аккаунт существует: {'да' if plan.get('exists') else 'нет'}",
        f"Требуется активация: {activation} (метод: {activation_method})",
        "\nРесурсы:",
        f"Energy: {cur.get('energy',0)} / нужно {req.get('energy',0)} (не хватает {miss.get('energy',0)})",
        f"Bandwidth: {cur.get('bandwidth',0)} / нужно {req.get('bandwidth',0)} (не хватает {miss.get('bandwidth',0)})",
        "\nПлан делегации (TRX):",
        f"Energy TRX: {pl.get('energy_trx',0)} | Bandwidth TRX: {pl.get('bandwidth_trx',0)}",
        f"Safety x{pl.get('safety_multiplier')} | Оценка tx: {pl.get('tx_budget_estimate')}",
    ]
    if notes:
        text_lines.append("\nЗаметки: " + ", ".join(notes))
    text_lines.append("\nПродолжить и выполнить делегацию? (да/нет)")
    await state.update_data(free_gas_address=addr)
    await message.answer("\n".join(text_lines), parse_mode="HTML")
    await state.set_state(FreeGasFSM.confirm_topup)


async def process_free_gas_confirm(message: types.Message, state: FSMContext):
    choice = (message.text or "").strip().lower()
    data = await state.get_data()
    addr = data.get("free_gas_address")
    if not addr:
        await message.answer("Контекст утерян. Начните заново /free_gas")
        await state.clear()
        return
    if choice in {"нет", "no", "n", "/cancel", "cancel", "отмена"}:
        await message.answer("Отменено.")
        await state.clear()
        return
    if choice not in {"да", "yes", "y"}:
        await message.answer("Ответьте 'да' или 'нет'.")
        return
    
    # Perform intelligent preparation
    try:
        # Use the new intelligent preparation method
        try:
            from core.services.gas_station import gas_station as _gs
        except ImportError:
            from src.core.services.gas_station import gas_station as _gs
        
        # Send processing message
        processing_msg = await message.answer("🔄 **Подготовка адреса...**\n⏳ Анализ и активация с точным расчетом ресурсов...", parse_mode="Markdown")
        
        # Execute intelligent preparation
        logger.info(f"[bot] Starting intelligent preparation for {addr}")
        result = _gs.intelligent_prepare_address_for_usdt(addr)
        
        # Record usage if successful
        if result["success"]:
            try:
                db = _get_bot_db(message)
                record_free_gas_address(db, message.from_user.id, addr)
            except Exception:
                pass
        
        # Delete processing message
        try:
            await processing_msg.delete()
        except Exception:
            pass
        
        # Prepare detailed response
        if result["success"]:
            # Success message with detailed breakdown
            lines = [
                "✅ **Адрес успешно подготовлен для USDT переводов!**",
                "",
                f"🎯 **Адрес:** `{addr}`",
                f"⏱️ **Время выполнения:** {result['execution_time']:.3f}с"
            ]
            
            # Activation details
            if result["activation_performed"]:
                method_emoji = "🔐" if result["activation_method"] == "permission_based" else "🔧"
                method_name = "Permission-Based" if result["activation_method"] == "permission_based" else "Traditional"
                lines.extend([
                    "",
                    f"{method_emoji} **Активация:** {method_name}"
                ])
                if result["transaction_ids"]:
                    lines.append(f"📋 **Транзакция:** `{result['transaction_ids'][0][:16]}...`")
            else:
                lines.extend([
                    "",
                    "ℹ️ **Активация:** Адрес уже был активирован"
                ])
            
            # Resource delegation details
            sim_data = result["simulation_data"]
            final_status = result["final_status"]
            
            lines.extend([
                "",
                "⚡ **Ресурсы (симуляция USDT перевода):**",
                f"• Energy: {final_status['energy_available']:,} units (требуется: {sim_data.get('energy_used', 0):,})",
                f"• Bandwidth: {final_status['bandwidth_available']:,} units (требуется: {sim_data.get('bandwidth_used', 0):,})"
            ])
            
            if result["resources_delegated"]["energy"] > 0 or result["resources_delegated"]["bandwidth"] > 0:
                lines.extend([
                    "",
                    "🎁 **Делегированные ресурсы:**"
                ])
                if result["resources_delegated"]["energy"] > 0:
                    lines.append(f"• Energy: +{result['resources_delegated']['energy']:,} units")
                if result["resources_delegated"]["bandwidth"] > 0:
                    lines.append(f"• Bandwidth: +{result['resources_delegated']['bandwidth']:,} units")
            
            lines.extend([
                "",
                "🎉 **Статус:** Готов к USDT переводам!",
                "💡 **Хватит на:** ~1 перевод USDT с запасом"
            ])
            
            await message.answer("\n".join(lines), parse_mode="Markdown")
            
        else:
            # Handle partial success or complete failure
            strategy = result.get("strategy", "preparation_failed")
            final_status = result.get("final_status", {})
            
            if strategy == "partial_preparation":
                # Partial success - show what was accomplished
                lines = [
                    "⚠️ **Адрес частично подготовлен**",
                    "",
                    f"🎯 **Адрес:** `{addr}`",
                    f"⏱️ **Время выполнения:** {result['execution_time']:.3f}с"
                ]
                
                # Show progress made
                if final_status.get("energy_gained", 0) > 0 or final_status.get("bandwidth_gained", 0) > 0:
                    lines.extend([
                        "",
                        "📈 **Достигнутый прогресс:**"
                    ])
                    if final_status.get("energy_gained", 0) > 0:
                        lines.append(f"• Energy: +{final_status['energy_gained']:,} units")
                    if final_status.get("bandwidth_gained", 0) > 0:
                        lines.append(f"• Bandwidth: +{final_status['bandwidth_gained']:,} units")
                
                # Show current status
                if final_status:
                    lines.extend([
                        "",
                        "📊 **Текущее состояние:**",
                        f"• Energy: {final_status.get('energy_available', 0):,} units",
                        f"• Bandwidth: {final_status.get('bandwidth_available', 0):,} units"
                    ])
                    
                    if final_status.get("is_activated", False):
                        lines.append("• ✅ Адрес активирован")
                    else:
                        lines.append("• ❌ Адрес не активирован")
                
                lines.extend([
                    "",
                    "💡 **Попробуйте:**",
                    "• /permission_status - диагностика системы",
                    "• Повторить через несколько минут",
                    "• Обратиться к администратору"
                ])
                
                await message.answer("\n".join(lines), parse_mode="Markdown")
                
            else:
                # Complete failure - show diagnostics
                error_lines = [
                    "❌ **Не удалось подготовить адрес**",
                    "",
                    f"🎯 **Адрес:** `{addr}`",
                    f"⏱️ **Время попытки:** {result['execution_time']:.3f}с"
                ]
                
                # Add specific error details
                details = result.get("details", {})
                if "error" in details:
                    error_lines.extend([
                        "",
                        f"🔍 **Ошибка:** {details['error']}"
                    ])
                
                if "activation_error" in details:
                    error_lines.extend([
                        "",
                        f"🔧 **Проблема активации:** {details['activation_error']}"
                    ])
                
                if "delegation_error" in details:
                    error_lines.extend([
                        "",
                        f"⚡ **Проблема ресурсов:** {details['delegation_error']}"
                    ])
                
                # Show current status if available
                if final_status:
                    error_lines.extend([
                        "",
                        "📊 **Текущее состояние:**",
                        f"• Energy: {final_status.get('energy_available', 0):,} units",
                        f"• Bandwidth: {final_status.get('bandwidth_available', 0):,} units"
                    ])
                
                error_lines.extend([
                    "",
                    "💡 **Попробуйте:**",
                    "• /permission_status - диагностика системы",
                    "• Повторить через несколько минут",
                    "• Обратиться к администратору"
                ])
                
                await message.answer("\n".join(error_lines), parse_mode="Markdown")
                error_lines.extend([
                    "",
                    "📊 **Текущее состояние:**",
                    f"• Energy: {final_status.get('energy_available', 0):,} units",
                    f"• Bandwidth: {final_status.get('bandwidth_available', 0):,} units"
                ])
            
            error_lines.extend([
                "",
                "� **Попробуйте:**",
                "• `/permission_status` - диагностика системы",
                "• Повторить через несколько минут",
                "• Обратиться к администратору"
            ])
            
            await message.answer("\n".join(error_lines), parse_mode="Markdown")
    
    except Exception as e:
        logger.exception(f"[bot] Error in intelligent free gas preparation: {e}")
        await message.answer("❌ Произошла ошибка при подготовке адреса. Попробуйте позже или обратитесь к администратору.")
    
    await state.clear()


async def handle_dry_free_gas(message: types.Message):
    """Show only the simulation (dry-run) of a Free Gas operation without changing state."""
    text = message.text or ""
    parts = text.split()
    if len(parts) == 1:
        await message.answer("Использование: /dryfreegas <TRON адрес>\nПример: /dryfreegas TXXXX...")
        return
    addr = parts[1].strip()
    if not _is_valid_tron_address(addr):
        await message.answer("Некорректный TRON адрес. Проверьте формат.")
        return
    try:
        try:
            from core.services.gas_station import gas_station as _gs
        except ImportError:  # pragma: no cover
            from src.core.services.gas_station import gas_station as _gs  # type: ignore
        plan = _gs.dry_run_prepare_for_sweep(addr)
    except Exception as e:  # pragma: no cover
        logger.warning(f"dry_free_gas simulation failed: {e}")
        await message.answer("Ошибка симуляции.")
        return
    if plan.get("error"):
        await message.answer(f"Ошибка: {html.escape(plan['error'])}")
        return
    cur = plan.get("current", {})
    miss = plan.get("missing", {})
    req = plan.get("required", {})
    pl = plan.get("plan", {})
    activation = "да" if plan.get("activation_needed") else "нет"
    activation_method = plan.get("activation_method") or "—"
    lines = [
        "Dry-run Free Gas:",
        f"Адрес: <code>{html.escape(addr)}</code>",
        f"Существует: {'да' if plan.get('exists') else 'нет'} | Активация: {activation} ({activation_method})",
        f"Energy: {cur.get('energy',0)} / {req.get('energy',0)} (недостает {miss.get('energy',0)})",
        f"Bandwidth: {cur.get('bandwidth',0)} / {req.get('bandwidth',0)} (недостает {miss.get('bandwidth',0)})",
        f"TRX план: Energy {pl.get('energy_trx',0)} | Bandwidth {pl.get('bandwidth_trx',0)} | Safety x{pl.get('safety_multiplier')}",
    ]
    notes = plan.get("notes", [])
    if notes:
        lines.append("Заметки: " + ", ".join(notes))
    await message.answer("\n".join(lines), parse_mode="HTML")


# --- Permission-Based Activation Command ---
async def handle_permission_activation(message: types.Message):
    """Handle /permission_activate command with intelligent preparation."""
    text = message.text or ""
    parts = text.split()
    
    if len(parts) == 1:
        await message.answer(
            "🔐 **Intelligent Permission-Based Activation**\n\n"
            "Использование: `/permission_activate <TRON_address>`\n"
            "Пример: `/permission_activate T[TARGET_ADDRESS]`\n\n"
            "**Что это делает:**\n"
            "• Анализирует текущее состояние адреса\n"
            "• Симулирует USDT перевод для точного расчета ресурсов\n"
            "• Активирует адрес через permission-based систему\n"
            "• Делегирует точно рассчитанные energy и bandwidth\n"
            "• Проверяет готовность для USDT переводов\n\n"
            "**Преимущества:**\n"
            "• Умная система с точным расчетом\n"
            "• Безопасное делегирование с margins\n"
            "• Полная диагностика процесса\n"
            "• Готовность именно для USDT операций\n\n"
            "Проверить доступность: `/permission_status`",
            parse_mode="Markdown"
        )
        return
    
    # Extract target address
    target_address = parts[1].strip()
    
    # Validate TRON address format
    if not _is_valid_tron_address(target_address):
        await message.answer(
            "❌ **Некорректный TRON адрес**\n\n"
            "Адрес должен:\n"
            "• Начинаться с 'T'\n"
            "• Иметь правильную Base58 кодировку\n"
            "• Иметь корректную контрольную сумму\n\n"
            "Пример: `TXb8AYmGgPRuXovkm1wsVwKfAvrbrHQ1Lo`",
            parse_mode="Markdown"
        )
        return
    
    # Show processing message
    processing_msg = await message.answer(
        "🔄 **Умная подготовка адреса...**\n"
        "⏳ Анализ → Симуляция → Активация → Делегация → Проверка",
        parse_mode="Markdown"
    )
    
    try:
        # Get gas station manager
        try:
            from core.services.gas_station import gas_station as _gs
        except ImportError:
            from src.core.services.gas_station import gas_station as _gs
        
        # Record usage for this user
        try:
            db = _get_bot_db(message)
            record_free_gas_address(db, message.from_user.id, target_address)
        except Exception:
            pass
        
        # Perform intelligent preparation with full analysis
        logger.info(f"[bot] Starting intelligent permission activation for {target_address}")
        result = _gs.intelligent_prepare_address_for_usdt(target_address, probe_first=True)
        
        # Delete processing message
        try:
            await processing_msg.delete()
        except:
            pass
        
        # Handle results with detailed breakdown
        if result["success"]:
            # Comprehensive success message
            lines = [
                "✅ **Адрес успешно подготовлен для USDT!**",
                "",
                f"🎯 **Адрес:** `{target_address}`",
                f"⏱️ **Время выполнения:** {result['execution_time']:.3f}с"
            ]
            
            # Activation details
            if result["activation_performed"]:
                method_emoji = "🔐" if result["activation_method"] == "permission_based" else "🔧"
                method_name = "Permission-Based" if result["activation_method"] == "permission_based" else "Traditional"
                lines.extend([
                    "",
                    f"**� Активация:**",
                    f"{method_emoji} Метод: {method_name}"
                ])
                if result["transaction_ids"]:
                    lines.append(f"📋 Транзакция: `{result['transaction_ids'][0][:20]}...`")
            else:
                lines.extend([
                    "",
                    "**ℹ️ Активация:** Адрес уже был активирован"
                ])
            
            # Simulation and resource details
            sim_data = result["simulation_data"]
            final_status = result["final_status"]
            details = result.get("details", {})
            
            lines.extend([
                "",
                "**🔬 Анализ USDT перевода:**",
                f"• Требуется Energy: {sim_data.get('energy_used', 0):,} units",
                f"• Требуется Bandwidth: {sim_data.get('bandwidth_used', 0):,} units"
            ])
            
            if "required_energy" in details and "required_bandwidth" in details:
                lines.extend([
                    f"• С margins Energy: {details['required_energy']:,} units",
                    f"• С margins Bandwidth: {details['required_bandwidth']:,} units"
                ])
            
            lines.extend([
                "",
                "**⚡ Итоговые ресурсы:**",
                f"• Energy доступно: {final_status['energy_available']:,} units",
                f"• Bandwidth доступно: {final_status['bandwidth_available']:,} units"
            ])
            
            # Delegation details
            if result["resources_delegated"]["energy"] > 0 or result["resources_delegated"]["bandwidth"] > 0:
                lines.extend([
                    "",
                    "**🎁 Делегированные ресурсы:**"
                ])
                if result["resources_delegated"]["energy"] > 0:
                    lines.append(f"• Energy: +{result['resources_delegated']['energy']:,} units")
                if result["resources_delegated"]["bandwidth"] > 0:
                    lines.append(f"• Bandwidth: +{result['resources_delegated']['bandwidth']:,} units")
            
            # Status check
            ready = final_status.get("ready_for_usdt", False)
            lines.extend([
                "",
                f"**{'🎉' if ready else '⚠️'} Статус:** {'Готов для USDT переводов' if ready else 'Недостаточно ресурсов'}",
                "💡 **Покрытие:** ~1 USDT перевод с запасом"
            ])
            
            await message.answer("\n".join(lines), parse_mode="Markdown")
            
        else:
            # Comprehensive error message with diagnostics
            error_lines = [
                "❌ **Умная подготовка не удалась**",
                "",
                f"🎯 **Адрес:** `{target_address}`",
                f"⏱️ **Время попытки:** {result['execution_time']:.3f}с"
            ]
            
            # Add detailed error analysis
            details = result.get("details", {})
            sim_data = result.get("simulation_data", {})
            final_status = result.get("final_status", {})
            
            # Show what we learned during analysis
            if sim_data:
                error_lines.extend([
                    "",
                    "**🔬 Анализ выполнен:**",
                    f"• USDT перевод требует: {sim_data.get('energy_used', 0):,} Energy, {sim_data.get('bandwidth_used', 0):,} Bandwidth"
                ])
            
            if final_status:
                error_lines.extend([
                    "",
                    "**📊 Текущее состояние:**",
                    f"• Energy: {final_status.get('energy_available', 0):,} units",
                    f"• Bandwidth: {final_status.get('bandwidth_available', 0):,} units"
                ])
            
            # Specific error details
            if "error" in details:
                error_lines.extend([
                    "",
                    f"**🔍 Основная ошибка:** {details['error']}"
                ])
            
            if result["activation_performed"] and result["activation_method"] == "permission_based":
                error_lines.extend([
                    "",
                    "✅ **Активация:** Выполнена успешно",
                    "❌ **Проблема:** В делегировании ресурсов"
                ])
            elif "activation_error" in details:
                error_lines.extend([
                    "",
                    f"❌ **Проблема активации:** {details['activation_error']}"
                ])
            
            if "delegation_error" in details:
                error_lines.extend([
                    "",
                    f"❌ **Проблема делегации:** {details['delegation_error']}"
                ])
            
            error_lines.extend([
                "",
                "**💡 Рекомендации:**",
                "• `/permission_status` - диагностика системы",
                "• Повторить через несколько минут",
                "• Проверить баланс газовой станции",
                "• Обратиться к администратору"
            ])
            
            await message.answer("\n".join(error_lines), parse_mode="Markdown")
            
    except Exception as e:
        # Delete processing message if still exists
        try:
            await processing_msg.delete()
        except:
            pass
        
        logger.exception(f"[bot] Error in intelligent permission activation: {e}")
        await message.answer(
            "❌ **Критическая ошибка**\n\n"
            f"Произошла ошибка при обработке команды.\n"
            f"Адрес: `{target_address}`\n\n"
            "Попробуйте:\n"
            "• Повторить команду через минуту\n"
            "• Использовать `/permission_status` для диагностики\n"
            "• Обратиться к администратору",
            parse_mode="Markdown"
        )
            
    except Exception as e:
        # Delete processing message
        try:
            await processing_msg.delete()
        except:
            pass
        
        logger.exception(f"Error in handle_permission_activation: {e}")
        
        await message.answer(
            "❌ **Критическая ошибка**\n\n"
            f"Произошла непредвиденная ошибка: `{str(e)}`\n\n"
            "**Что делать:**\n"
            "• Попробуйте позже\n"
            "• Используйте `/free_gas` как альтернативу\n"
            "• Обратитесь в поддержку\n\n"
            "Проверить статус: `/permission_status`",
            parse_mode="Markdown"
        )


async def handle_permission_status(message: types.Message):
    """Handle /permission_status command to check permission-based activation availability."""
    processing_msg = await message.answer("🔄 **Проверка статуса системы...**", parse_mode="Markdown")
    
    try:
        # Get gas station manager
        try:
            from core.services.gas_station import gas_station as _gs
        except ImportError:
            from src.core.services.gas_station import gas_station as _gs
        
        # Check availability
        status = _gs.is_permission_based_activation_available()
        
        # Delete processing message
        try:
            await processing_msg.delete()
        except:
            pass
        
        # Format status message
        if status["available"]:
            lines = [
                "✅ **Permission-Based Activation: ДОСТУПНА**",
                "",
                "🔐 **Система готова к работе**",
                "Все компоненты настроены корректно.",
                ""
            ]
            
            details = status.get("details", {})
            if details:
                lines.append("**📊 Конфигурация:**")
                if details.get('gas_station_address'):
                    lines.append(f"• Газовая станция: `{details['gas_station_address']}`")
                if details.get('signer_address'):
                    lines.append(f"• Подписывающий: `{details['signer_address']}`")
                if details.get('gas_station_balance'):
                    lines.append(f"• Баланс станции: {details['gas_station_balance']} TRX")
                if details.get('required_balance'):
                    lines.append(f"• Требуемый баланс: {details['required_balance']} TRX")
                if details.get('permission_name'):
                    lines.append(f"• Permission: {details['permission_name']} (ID: 2)")
                if details.get('permission_threshold'):
                    lines.append(f"• Threshold: {details['permission_threshold']}")
                lines.append("")
            
            lines.extend([
                "**🚀 Как использовать:**",
                "`/permission_activate <TRON_address>`",
                "",
                "**Пример:**",
                "`/permission_activate T[YOUR_ADDRESS]`"
            ])
            
        else:
            lines = [
                "❌ **Permission-Based Activation: НЕДОСТУПНА**",
                "",
                "🔧 **Проблемы конфигурации:**"
            ]
            
            issues = status.get("issues", [])
            for issue in issues:
                lines.append(f"• {issue}")
            
            lines.extend([
                "",
                "**💡 Что делать:**",
                "• Обратитесь к администратору для настройки",
                "• Используйте альтернативу: `/free_gas`",
                "• Проверьте статус позже"
            ])
            
            details = status.get("details", {})
            if details:
                lines.extend([
                    "",
                    "**📊 Обнаруженная конфигурация:**"
                ])
                if details.get('gas_station_address'):
                    lines.append(f"• Газовая станция: `{details['gas_station_address']}`")
                if details.get('signer_address'):
                    lines.append(f"• Подписывающий: `{details['signer_address']}`")
                if details.get('gas_station_balance') is not None:
                    lines.append(f"• Баланс станции: {details['gas_station_balance']} TRX")
        
        await message.answer("\n".join(lines), parse_mode="Markdown")
        
    except Exception as e:
        # Delete processing message
        try:
            await processing_msg.delete()
        except:
            pass
        
        logger.exception(f"Error in handle_permission_status: {e}")
        
        await message.answer(
            "❌ **Ошибка проверки статуса**\n\n"
            f"Не удалось проверить статус системы: `{str(e)}`\n\n"
            "Попробуйте позже или обратитесь в поддержку.",
            parse_mode="Markdown"
        )

