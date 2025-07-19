# Логика генерации адресов из xPub

import logging
from bip_utils import Bip44, Bip44Coins, Bip44Changes, Base58Decoder

logger = logging.getLogger("hd_wallet_service")


def generate_address_from_xpub(xpub, account=None, address_index=0):
    """
    Принимает xPub (str), индекс (int), и необязательный account (int).
    Если xPub на уровне account (depth=3), производит derivation только Change/AddressIndex.
    Если xPub на уровне coin (depth=2), производит derivation через Purpose/Coin/Account.
    Возвращает Tron-адрес (str).
    """
    logger.info(
        "generate_address_from_xpub called with xpub=%s, account=%s, address_index=%s",
        xpub,
        account,
        address_index,
    )

    pub_ctx = Bip44.FromExtendedKey(xpub, Bip44Coins.TRON)
    # Use Bip32Utils to decode xpub and get depth
    try:
        xpub_bytes = Base58Decoder.Decode(xpub)
        depth = xpub_bytes[4]  # depth is the 5th byte in xpub serialization
    except Exception as e:
        logger.warning(f"Could not decode xpub depth: {e}")
        depth = None
    depth_descriptor = {
        0: "Root",
        1: "Purpose",
        2: "Coin",
        3: "Account",
    }
    logger.info("Decoded xpub depth: %s (%s)", depth, depth_descriptor.get(depth, "Unknown"))

    if depth == 3:
        # xpub is at account level, derive Change/AddressIndex only
        address = (
            pub_ctx.Change(Bip44Changes.CHAIN_EXT)
            .AddressIndex(address_index)
            .PublicKey()
            .ToAddress()
        )
        logger.info(
            "Derived address with path m/44'/195'/<account>'/0/%d: %s (account xpub)",
            address_index,
            address,
        )
    else:
        # xpub is at coin level, derive full path
        if account is None:
            account = 0
        account_ctx = pub_ctx.Purpose().Coin().Account(account)
        address = (
            account_ctx.Change(Bip44Changes.CHAIN_EXT)
            .AddressIndex(address_index)
            .PublicKey()
            .ToAddress()
        )
        logger.info(
            "Derived address with path m/44'/195'/%d'/0/%d: %s",
            account,
            address_index,
            address,
        )
    return address
