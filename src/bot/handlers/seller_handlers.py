# Обработчики всех команд продавца


from aiogram import types
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
import secrets
from core.database.db_service import create_seller, get_seller, get_wallet_by_group, create_invoice, get_invoices_by_seller, update_invoice
from core.services.gas_station import prepare_for_sweep

class InvoiceFSM(StatesGroup):
    amount = State()
    description = State()

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
    data = await state.get_data()
    amount = float(data['amount'])
    description = message.text
    # Генерация адреса (упрощённо)
    telegram_id = message.from_user.id
    wallet = get_wallet_by_group(db=message.bot['db'], telegram_id=telegram_id, invoices_group=0)
    invoice = create_invoice(db=message.bot['db'], seller_id=telegram_id, invoices_group=0, derivation_index=0, address=wallet.xpub, amount=amount, status='pending')
    await message.answer(f"Инвойс создан! Адрес: {invoice.address}\nСумма: {amount}\nОписание: {description}")
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
