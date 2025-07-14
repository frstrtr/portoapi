# Логика генерации адресов из xPub

from bip_utils import Bip44, Bip44Coins, Bip44Changes


def generate_address_from_xpub(xpub, index, account=0):
    """
    Принимает xPub (str), индекс (int) и account (int, по умолчанию 0), возвращает Tron-адрес (str).
    Позволяет использовать account для группировки инвойсов по BIP44.
    """
    pub_ctx = Bip44.FromExtendedKey(xpub, Bip44Coins.TRON)
    # Перейти к нужному account (группе)
    account_ctx = pub_ctx.Purpose().Coin().Account(account)
    address = account_ctx.Change(Bip44Changes.CHAIN_EXT).AddressIndex(index).PublicKey().ToAddress()
    return address
