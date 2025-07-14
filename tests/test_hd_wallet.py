import pytest
from unittest.mock import patch, MagicMock
from src.core.crypto.hd_wallet_service import generate_address_from_xpub

# src/core/crypto/test_hd_wallet_service.py


@patch("src.core.crypto.hd_wallet_service.Bip44")
@patch("src.core.crypto.hd_wallet_service.Bip44Coins")
@patch("src.core.crypto.hd_wallet_service.Bip44Changes")
def test_generate_address_from_xpub_basic(mock_changes, mock_coins, mock_bip44):
    # Setup mocks
    mock_pub_ctx = MagicMock()
    mock_account_ctx = MagicMock()
    mock_change_ctx = MagicMock()
    mock_address_ctx = MagicMock()
    mock_pubkey_ctx = MagicMock()
    mock_pubkey_ctx.ToAddress.return_value = "TMockedAddress"
    mock_address_ctx.PublicKey.return_value = mock_pubkey_ctx
    mock_change_ctx.AddressIndex.return_value = mock_address_ctx
    mock_account_ctx.Change.return_value = mock_change_ctx
    mock_pub_ctx.Purpose.return_value = mock_pub_ctx
    mock_pub_ctx.Coin.return_value = mock_pub_ctx
    mock_pub_ctx.Account.return_value = mock_account_ctx
    mock_bip44.FromExtendedKey.return_value = mock_pub_ctx

    # Call function
    xpub = "xpubDummy"
    index = 5
    account = 2
    result = generate_address_from_xpub(xpub, index, account)

    # Assertions
    mock_bip44.FromExtendedKey.assert_called_once_with(xpub, mock_coins.TRON)
    mock_pub_ctx.Account.assert_called_once_with(account)
    mock_account_ctx.Change.assert_called_once_with(mock_changes.CHAIN_EXT)
    mock_change_ctx.AddressIndex.assert_called_once_with(index)
    assert result == "TMockedAddress"

@patch("src.core.crypto.hd_wallet_service.Bip44")
@patch("src.core.crypto.hd_wallet_service.Bip44Coins")
@patch("src.core.crypto.hd_wallet_service.Bip44Changes")
def test_generate_address_from_xpub_default_account(mock_changes, mock_coins, mock_bip44):
    # Setup mocks as above
    mock_pub_ctx = MagicMock()
    mock_account_ctx = MagicMock()
    mock_change_ctx = MagicMock()
    mock_address_ctx = MagicMock()
    mock_pubkey_ctx = MagicMock()
    mock_pubkey_ctx.ToAddress.return_value = "TDefaultAccount"
    mock_address_ctx.PublicKey.return_value = mock_pubkey_ctx
    mock_change_ctx.AddressIndex.return_value = mock_address_ctx
    mock_account_ctx.Change.return_value = mock_change_ctx
    mock_pub_ctx.Purpose.return_value = mock_pub_ctx
    mock_pub_ctx.Coin.return_value = mock_pub_ctx
    mock_pub_ctx.Account.return_value = mock_account_ctx
    mock_bip44.FromExtendedKey.return_value = mock_pub_ctx

    xpub = "xpubDummy"
    index = 0
    result = generate_address_from_xpub(xpub, index)

    mock_pub_ctx.Account.assert_called_once_with(0)
    assert result == "TDefaultAccount"

@patch("src.core.crypto.hd_wallet_service.Bip44")
@patch("src.core.crypto.hd_wallet_service.Bip44Coins")
@patch("src.core.crypto.hd_wallet_service.Bip44Changes")
def test_generate_address_from_xpub_invalid_xpub(mock_changes, mock_coins, mock_bip44):
    # Simulate FromExtendedKey raising an exception
    mock_bip44.FromExtendedKey.side_effect = ValueError("Invalid xpub")
    with pytest.raises(ValueError, match="Invalid xpub"):
        generate_address_from_xpub("badxpub", 0)