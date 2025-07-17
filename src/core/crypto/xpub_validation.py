from bip_utils import Bip44, Bip44Coins
from bip_utils.base58.base58_ex import Base58ChecksumError


def is_valid_xpub(xpub: str) -> bool:
    """
    Robustly validate if the given string is a valid Tron xPub (BIP32 extended public key).
    Tries to parse the xpub using bip_utils for Tron. If parsing fails, it's invalid.
    """
    if not isinstance(xpub, str):
        return False
    try:
        # Try to create a Bip44 context from the xpub for Tron
        Bip44.FromExtendedKey(xpub, Bip44Coins.TRON)
        return True
    except (ValueError, Base58ChecksumError) as e:
        # print(f"Validation error: {e}")
        # If any ValueError or Base58ChecksumError occurs during parsing, the xpub is invalid
        return False
