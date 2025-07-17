import pytest
from unittest.mock import patch, MagicMock

from core.database.models import Invoice
from services.keeper_bot import check_pending_invoices

# --- Test: Activation fires on first USDT receive (account not activated) ---
@patch("services.keeper_bot.Tron")
@patch("services.keeper_bot.HTTPProvider")
@patch("services.keeper_bot.get_db")
@patch("services.keeper_bot.get_invoices_by_seller")
@patch("services.keeper_bot.get_invoice")
@patch("services.keeper_bot.update_invoice")
@patch("services.keeper_bot.create_transaction")
@patch("services.keeper_bot.auto_activate_on_usdt_receive")
@patch("services.keeper_bot.notify_invoice_paid")
def test_check_pending_invoices_first_usdt_receive(
    mock_notify,
    mock_auto_activate,
    mock_create_tx,
    mock_update_invoice,
    mock_get_invoice,
    mock_get_invoices_by_seller,
    mock_get_db,
    mock_http_provider,
    mock_tron,
):
    mock_db = MagicMock()
    mock_get_db.return_value = iter([mock_db])
    invoice = MagicMock(spec=Invoice)
    invoice.status = 'pending'
    invoice.address = 'TTestAddress'
    invoice.id = 1
    invoice.amount = 10
    mock_get_invoices_by_seller.return_value = [invoice]
    mock_db.query.return_value.filter.return_value.distinct.return_value = [MagicMock(seller_id=123)]

    mock_contract = MagicMock()
    mock_contract.functions.balanceOf = MagicMock(return_value=20_000_000)
    mock_contract.functions.transferEvent = MagicMock(return_value=[
        {
            'to': 'TTestAddress',
            'from': 'TSender',
            'value': 20_000_000,
            'transaction_id': 'txid123',
            'block_timestamp': 1234567890,
        }
    ])
    mock_tron_instance = mock_tron.return_value
    mock_tron_instance.get_contract.return_value = mock_contract
    # Simulate NOT activated: None
    mock_tron_instance.get_account.return_value = None
    check_pending_invoices()

    mock_auto_activate.assert_called_once_with('TTestAddress')
    mock_update_invoice.assert_called_once_with(mock_db, invoice.id, status='paid')
    mock_create_tx.assert_called_once()
    mock_notify.assert_called_once_with(invoice.id, 'txid123', 20.0)

# --- Test: Activation does NOT fire if account is activated (even with zero TRX balance) ---
@patch("services.keeper_bot.Tron")
@patch("services.keeper_bot.HTTPProvider")
@patch("services.keeper_bot.get_db")
@patch("services.keeper_bot.get_invoices_by_seller")
@patch("services.keeper_bot.get_invoice")
@patch("services.keeper_bot.update_invoice")
@patch("services.keeper_bot.create_transaction")
@patch("services.keeper_bot.auto_activate_on_usdt_receive")
@patch("services.keeper_bot.notify_invoice_paid")
def test_check_pending_invoices_zero_trx_balance_but_activated(
    mock_notify,
    mock_auto_activate,
    mock_create_tx,
    mock_update_invoice,
    mock_get_invoice,
    mock_get_invoices_by_seller,
    mock_get_db,
    mock_http_provider,
    mock_tron,
):
    mock_db = MagicMock()
    mock_get_db.return_value = iter([mock_db])
    invoice = MagicMock(spec=Invoice)
    invoice.status = 'pending'
    invoice.address = 'TTestAddress'
    invoice.id = 3
    invoice.amount = 10
    mock_get_invoices_by_seller.return_value = [invoice]
    mock_db.query.return_value.filter.return_value.distinct.return_value = [MagicMock(seller_id=123)]

    mock_contract = MagicMock()
    mock_contract.functions.balanceOf = MagicMock(return_value=20_000_000)
    mock_contract.functions.transferEvent = MagicMock(return_value=[
        {
            'to': 'TTestAddress',
            'from': 'TSender',
            'value': 20_000_000,
            'transaction_id': 'txid789',
            'block_timestamp': 1234567892,
        }
    ])
    mock_tron_instance = mock_tron.return_value
    mock_tron_instance.get_contract.return_value = mock_contract
    # Simulate activated account with zero TRX balance (as dict)
    mock_tron_instance.get_account.return_value = {'address': 'TTestAddress', 'balance': 0}
    check_pending_invoices()

    mock_auto_activate.assert_not_called()
    mock_update_invoice.assert_called_once_with(mock_db, invoice.id, status='paid')
    mock_create_tx.assert_called_once()
    mock_notify.assert_called_once_with(invoice.id, 'txid789', 20.0)

# --- Test: Activation does NOT fire if invoice already paid ---
@patch("services.keeper_bot.Tron")
@patch("services.keeper_bot.HTTPProvider")
@patch("services.keeper_bot.get_db")
@patch("services.keeper_bot.get_invoices_by_seller")
@patch("services.keeper_bot.get_invoice")
@patch("services.keeper_bot.update_invoice")
@patch("services.keeper_bot.create_transaction")
@patch("services.keeper_bot.auto_activate_on_usdt_receive")
@patch("services.keeper_bot.notify_invoice_paid")
def test_check_pending_invoices_already_paid(
    mock_notify,
    mock_auto_activate,
    mock_create_tx,
    mock_update_invoice,
    mock_get_invoice,
    mock_get_invoices_by_seller,
    mock_get_db,
    mock_http_provider,
    mock_tron,
):
    mock_db = MagicMock()
    mock_get_db.return_value = iter([mock_db])
    invoice = MagicMock(spec=Invoice)
    invoice.status = 'paid'  # Already paid
    invoice.address = 'TTestAddress'
    invoice.id = 2
    invoice.amount = 10
    mock_get_invoices_by_seller.return_value = [invoice]
    mock_db.query.return_value.filter.return_value.distinct.return_value = [MagicMock(seller_id=123)]

    mock_contract = MagicMock()
    mock_contract.functions.balanceOf = MagicMock(return_value=20_000_000)
    mock_contract.functions.transferEvent = MagicMock(return_value=[
        {
            'to': 'TTestAddress',
            'from': 'TSender',
            'value': 20_000_000,
            'transaction_id': 'txid456',
            'block_timestamp': 1234567891,
        }
    ])
    mock_tron_instance = mock_tron.return_value
    mock_tron_instance.get_contract.return_value = mock_contract
    # Simulate activated account with nonzero TRX balance
    mock_tron_instance.get_account.return_value = {'address': 'TTestAddress', 'balance': 100_000_000}
    check_pending_invoices()

    mock_auto_activate.assert_not_called()