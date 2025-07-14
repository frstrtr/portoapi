# Обработчики всех команд продавца


from aiogram import types
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
import secrets
from core.database.db_service import create_seller, get_seller, get_wallet_by_group, create_invoice, get_invoices_by_seller, update_invoice
from core.services.gas_station import prepare_for_sweep


# FSM для создания инвойса с выбором группы
class InvoiceFSM(StatesGroup):
    amount = State()
    description = State()
    group = State()

# FSM для добавления покупателя/группы
class AddBuyerFSM(StatesGroup):
    buyer_id = State()
    group_name = State()

async def handle_register(message: types.Message):
    telegram_id = message.from_user.id
    token = secrets.token_urlsafe(16)
    # Сохраняем seller и токен в БД (упрощённо)
    create_seller(db=message.bot['db'], telegram_id=telegram_id)
    # В реальном проекте — создать отдельную таблицу токенов
    url = f"https://your-platform.com/setup.html?token={token}"
    await message.answer(f"Ваша ссылка для настройки кошелька: {url}")

async def handle_deposit(message: types.Message):
    telegram_id = message.from_user.id
    seller = get_seller(db=message.bot['db'], telegram_id=telegram_id)
    await message.answer(f"Ваш депозит для газа: {seller.gas_deposit_balance} TRX")

async def handle_balance(message: types.Message):
    telegram_id = message.from_user.id
    seller = get_seller(db=message.bot['db'], telegram_id=telegram_id)
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
    db = message.bot['db']
    from core.database.db_service import get_buyer_groups_by_seller
    groups = get_buyer_groups_by_seller(db, telegram_id)
    if not groups:
        await message.answer("У вас нет групп покупателей. Сначала создайте группу через /add_buyer.")
        await state.clear()
        return
    kb = types.ReplyKeyboardMarkup(keyboard=[], resize_keyboard=True)
    for g in groups:
        kb.keyboard.append([types.KeyboardButton(text=f"{g.buyer_id} | {g.invoices_group}")])
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
    db = message.bot['db']
    from core.database.db_service import get_wallet_by_group
    wallet = get_wallet_by_group(db, telegram_id, invoices_group)
    from core.database.db_service import get_buyer_group
    buyer_group = get_buyer_group(db, telegram_id, buyer_id)
    invoice = create_invoice(
        db=db,
        seller_id=telegram_id,
        buyer_group_id=buyer_group.id,
        derivation_index=0,
        address=wallet.xpub,
        amount=float(data['amount']),
        status='pending'
    )
    await message.answer(f"Инвойс создан! Адрес: {invoice.address}\nСумма: {data['amount']}\nОписание: {data['description']}\nГруппа: {buyer_id}")
    await state.clear()
# --- Покупатели/группы ---
async def handle_buyers(message: types.Message):
    telegram_id = message.from_user.id
    db = message.bot['db']
    from core.database.db_service import get_buyer_groups_by_seller
    groups = get_buyer_groups_by_seller(db, telegram_id)
    if not groups:
        await message.answer("У вас нет групп покупателей. Добавьте через /add_buyer.")
        return
    text = "Ваши группы покупателей:\n"
    for g in groups:
        text += f"- {g.buyer_id} | {g.invoices_group}\n"
    await message.answer(text)

async def handle_add_buyer(message: types.Message, state: FSMContext):
    await message.answer("Введите buyer_id (например, email или уникальный идентификатор покупателя):")
    await state.set_state(AddBuyerFSM.buyer_id)

async def process_add_buyer_id(message: types.Message, state: FSMContext):
    await state.update_data(buyer_id=message.text.strip())
    await message.answer("Введите номер группы (BIP44 account, например 0, 1, 2...):")
    await state.set_state(AddBuyerFSM.group_name)

async def process_add_buyer_group(message: types.Message, state: FSMContext):
    data = await state.get_data()
    buyer_id = data['buyer_id']
    try:
        invoices_group = int(message.text.strip())
    except Exception:
        await message.answer("Некорректный номер группы. Введите целое число.")
        return
    telegram_id = message.from_user.id
    db = message.bot['db']
    from core.database.db_service import create_buyer_group
    create_buyer_group(db, seller_id=telegram_id, buyer_id=buyer_id, invoices_group=invoices_group)
    await message.answer(f"Группа для покупателя {buyer_id} с номером {invoices_group} добавлена.")
    await state.clear()

async def handle_sweep(message: types.Message):
    telegram_id = message.from_user.id
    paid_invoices = [inv for inv in get_invoices_by_seller(db=message.bot['db'], seller_id=telegram_id) if inv.status == 'paid']
    total = sum(inv.amount for inv in paid_invoices)
    count = len(paid_invoices)
    if not paid_invoices:
        await message.answer("Нет оплаченных инвойсов для вывода.")
        return
    await message.answer(f"Будет обработано {count} инвойсов на сумму {total} TRX. Подтвердите выполнение? (да/нет)")
    # Здесь можно реализовать FSM для подтверждения
    # После подтверждения:
    for inv in paid_invoices:
        prepare_for_sweep(inv.address)
        update_invoice(db=message.bot['db'], invoice_id=inv.id, status='swept')
    await message.answer("Все оплаченные инвойсы обработаны и выведены.")
