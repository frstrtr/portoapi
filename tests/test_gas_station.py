import pytest
from unittest.mock import patch, MagicMock

from core.services import gas_station

@pytest.fixture
def mock_tron():
    with patch('core.services.gas_station.Tron') as mock_tron_cls:
        mock_client = MagicMock()
        mock_gas_wallet = MagicMock()
        mock_gas_wallet.address = 'GAS_WALLET_ADDRESS'
        mock_client.get_account.return_value = mock_gas_wallet

        # Mock transfer/build/sign/broadcast chain
        mock_txn = MagicMock()
        mock_txn.broadcast.return_value = {'txid': 'trxid1'}
        mock_client.trx.transfer.return_value.build.return_value.sign.return_value = mock_txn

        # Mock delegate_resource/build/sign/broadcast chain for ENERGY
        mock_delegate_energy_txn = MagicMock()
        mock_delegate_energy_txn.broadcast.return_value = {'txid': 'energyid1'}
        mock_client.trx.delegate_resource.return_value.build.return_value.sign.return_value = mock_delegate_energy_txn

        # Mock delegate_resource/build/sign/broadcast chain for BANDWIDTH
        mock_delegate_bw_txn = MagicMock()
        mock_delegate_bw_txn.broadcast.return_value = {'txid': 'bwid1'}
        # For BANDWIDTH, return the same mock as ENERGY for simplicity
        mock_client.trx.delegate_resource.return_value.build.return_value.sign.return_value = mock_delegate_bw_txn

        # Mock get_transaction_info to simulate confirmations
        def get_transaction_info_side_effect(txid):
            return {'receipt': {'result': 'SUCCESS'}}
        mock_client.get_transaction_info.side_effect = get_transaction_info_side_effect

        mock_tron_cls.return_value = mock_client
        yield mock_client

def test_prepare_for_sweep_success(mock_tron):
    result = gas_station.prepare_for_sweep('INVOICE_ADDRESS')
    assert result is True

def test_prepare_for_sweep_failure_on_activation(mock_tron):
    # Simulate activation failure
    def get_transaction_info_side_effect(txid):
        return None  # Never returns success
    mock_tron.get_transaction_info.side_effect = get_transaction_info_side_effect
    result = gas_station.prepare_for_sweep('INVOICE_ADDRESS')
    assert result is False

def test_auto_activate_on_usdt_receive_activated(mock_tron):
    # Simulate account is already activated
    mock_tron.get_account.return_value = {'address': 'INVOICE_ADDRESS'}
    result = gas_station.auto_activate_on_usdt_receive('INVOICE_ADDRESS')
    assert result is True

def test_auto_activate_on_usdt_receive_not_activated(mock_tron):
    # Simulate account is not activated
    mock_tron.get_account.return_value = None
    with patch('core.services.gas_station.prepare_for_sweep', return_value=True) as mock_prepare:
        result = gas_station.auto_activate_on_usdt_receive('INVOICE_ADDRESS')
        assert result is True
        mock_prepare.assert_called_once_with('INVOICE_ADDRESS')