# Логика генерации адресов из xPub


from bip_utils import Bip44, Bip44Coins, Bip44Changes
import logging

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
        xpub, account, address_index
    )

    pub_ctx = Bip44.FromExtendedKey(xpub, Bip44Coins.TRON)
    # If xpub is at account level (depth=3), ignore account and only derive Change/AddressIndex
    if hasattr(pub_ctx, "Depth"):
        depth = pub_ctx.Depth()
    else:
        depth = getattr(pub_ctx, "_depth", None)
    if depth == 3:
        address = (
            pub_ctx.Change(Bip44Changes.CHAIN_EXT)
            .AddressIndex(address_index)
            .PublicKey()
            .ToAddress()
        )
    elif depth == 2 and account is not None:
        account_ctx = pub_ctx.Purpose().Coin().Account(account)
        address = (
            account_ctx.Change(Bip44Changes.CHAIN_EXT)
            .AddressIndex(address_index)
            .PublicKey()
            .ToAddress()
        )
    elif depth == 2:
        account_ctx = pub_ctx.Purpose().Coin().Account(0)
        address = (
            account_ctx.Change(Bip44Changes.CHAIN_EXT)
            .AddressIndex(address_index)
            .PublicKey()
            .ToAddress()
        )
    else:
        address = (
            pub_ctx.Change(Bip44Changes.CHAIN_EXT)
            .AddressIndex(address_index)
            .PublicKey()
            .ToAddress()
        )
    return address
