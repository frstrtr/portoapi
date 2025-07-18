# Логика генерации адресов из xPub


from bip_utils import Bip44, Bip44Coins, Bip44Changes


def generate_address_from_xpub(xpub, index, account=None):
    """
    Принимает xPub (str), индекс (int), и необязательный account (int).
    Если xPub на уровне account (depth=3), производит derivation только Change/AddressIndex.
    Если xPub на уровне coin (depth=2), производит derivation через Purpose/Coin/Account.
    Возвращает Tron-адрес (str).
    """
    pub_ctx = Bip44.FromExtendedKey(xpub, Bip44Coins.TRON)
    # Always use full derivation path if account index is provided
    if account is not None:
        account_ctx = pub_ctx.Purpose().Coin().Account(account)
        address = (
            account_ctx.Change(Bip44Changes.CHAIN_EXT)
            .AddressIndex(index)
            .PublicKey()
            .ToAddress()
        )
    else:
        # Fallback to legacy behavior if account is not provided
        # Detect depth
        if hasattr(pub_ctx, "Depth"):
            depth = pub_ctx.Depth()
        else:
            depth = getattr(pub_ctx, "_depth", None)
        if depth == 3:
            address = (
                pub_ctx.Change(Bip44Changes.CHAIN_EXT)
                .AddressIndex(index)
                .PublicKey()
                .ToAddress()
            )
        elif depth == 2:
            account_ctx = pub_ctx.Purpose().Coin().Account(0)
            address = (
                account_ctx.Change(Bip44Changes.CHAIN_EXT)
                .AddressIndex(index)
                .PublicKey()
                .ToAddress()
            )
        else:
            address = (
                pub_ctx.Change(Bip44Changes.CHAIN_EXT)
                .AddressIndex(index)
                .PublicKey()
                .ToAddress()
            )
    return address
