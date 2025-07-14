import pytest
from unittest.mock import MagicMock
from aiogram.fsm.context import FSMContext

# Импортируем хендлеры
from src.bot.handlers import seller_handlers

class DummyMessage:
    def __init__(self, text, user_id=123):
        self.text = text
        self.from_user = MagicMock(id=user_id)
        self.bot = {'db': MagicMock()}
        self.answers = []
    async def answer(self, text, **kwargs):
        self.answers.append(text)

class DummyState(FSMContext):
    def __init__(self):
        self._data = {}
        self._state = None
    async def set_state(self, state):
        self._state = state
    async def update_data(self, **kwargs):
        self._data.update(kwargs)
    async def get_data(self):
        return self._data
    async def clear(self):
        self._data = {}
        self._state = None

@pytest.mark.asyncio
async def test_add_buyer_and_create_invoice_flow():
    # Добавление группы
    msg = DummyMessage("/add_buyer")
    state = DummyState()
    await seller_handlers.handle_add_buyer(msg, state)
    assert "buyer_id" in msg.answers[-1]
    # Ввод buyer_id
    msg2 = DummyMessage("client1")
    await seller_handlers.process_add_buyer_id(msg2, state)
    assert "номер группы" in msg2.answers[-1]
    # Ввод номера группы
    msg3 = DummyMessage("0")
    # Мокаем create_buyer_group
    seller_handlers.create_buyer_group = MagicMock()
    await seller_handlers.process_add_buyer_group(msg3, state)
    # Проверяем ответ
    assert "добавлена" in msg3.answers[-1]

@pytest.mark.asyncio
async def test_buyers_list():
    msg = DummyMessage("/buyers")
    # Мокаем get_buyer_groups_by_seller
    seller_handlers.get_buyer_groups_by_seller = MagicMock(return_value=[MagicMock(buyer_id="client1", invoices_group=0)])
    await seller_handlers.handle_buyers(msg)
    assert "client1" in msg.answers[-1]

@pytest.mark.asyncio
async def test_create_invoice_group_choice():
    msg = DummyMessage("/create_invoice")
    state = DummyState()
    await seller_handlers.handle_create_invoice(msg, state)
    assert "сумму" in msg.answers[-1]
    # Ввод суммы
    msg2 = DummyMessage("10")
    await seller_handlers.process_invoice_amount(msg2, state)
    assert "описание" in msg2.answers[-1]
    # Ввод описания
    msg3 = DummyMessage("Test invoice")
    # Мокаем группы
    seller_handlers.get_buyer_groups_by_seller = MagicMock(return_value=[MagicMock(buyer_id="client1", invoices_group=0)])
    await seller_handlers.process_invoice_description(msg3, state)
    assert "Выберите покупателя" in msg3.answers[-1]
    # Выбор группы
    msg4 = DummyMessage("client1 | 0")
    seller_handlers.get_wallet_by_group = MagicMock(return_value=MagicMock(xpub="xpub_test"))
    seller_handlers.get_buyer_group = MagicMock(return_value=MagicMock(id=1))
    seller_handlers.create_invoice = MagicMock(return_value=MagicMock(address="T...", amount=10))
    await seller_handlers.process_invoice_group(msg4, state)
    assert "Инвойс создан" in msg4.answers[-1]
