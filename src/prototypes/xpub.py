"""This script generates a Tron xPub (extended public key) and addresses
using a BIP39 mnemonic. It derives the first address and allows generating
additional addresses from the xPub.
"""

from bip_utils import Bip39SeedGenerator, Bip44, Bip44Coins, Bip44Changes

# Ask user for mnemonic, use default if empty
default_mnemonic = "abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon about"
mnemonic = input(
    "Enter BIP39 mnemonic 12 or 24 words (leave empty for default): "
).strip()
if not mnemonic:
    mnemonic = default_mnemonic

print(f"Using mnemonic: {mnemonic}")


def derive_private_key_from_xprv():
    """
    Prompts user for a derivation path, then derives and prints the private key for that path using the current mnemonic.
    """
    try:
        account_idx = int(input("Enter account number (default 0): ").strip() or 0)
        addr_idx = int(input("Enter address index (default 0): ").strip() or 0)
        # Always use external addresses for Tron
        change = Bip44Changes.CHAIN_EXT
        seed = Bip39SeedGenerator(mnemonic).Generate()
        ctx = Bip44.FromSeed(seed, Bip44Coins.TRON)
        account_ctx = ctx.Purpose().Coin().Account(account_idx)
        xprv = account_ctx.PrivateKey().ToExtended()
        print(f"xprv for m/44'/195'/{account_idx}' : {xprv}")
        priv_ctx = account_ctx.Change(change).AddressIndex(addr_idx)
        privkey = priv_ctx.PrivateKey().Raw().ToHex()
        print(f"Private key for m/44'/195'/{account_idx}'/0/{addr_idx}: {privkey}")
    except Exception as e:
        print(f"Error: {e}")


"""This script generates a Tron xPub (extended public key) and addresses
using a BIP39 mnemonic. It derives the first address and allows generating
additional addresses from the xPub.
"""


# Generate seed from mnemonic
seed_bytes = Bip39SeedGenerator(mnemonic).Generate()

# Derive BIP44 account for Tron (coin type 195)
bip44_ctx = Bip44.FromSeed(seed_bytes, Bip44Coins.TRON)
account = bip44_ctx.Purpose().Coin().Account(0)

# Derive the first address (m/44'/195'/0'/0/0)
address = (
    bip44_ctx.Purpose()
    .Coin()
    .Account(0)
    .Change(Bip44Changes.CHAIN_EXT)
    .AddressIndex(0)
    .PublicKey()
    .ToAddress()
)
print("Tron address (m/44'/195'/0'/0/0):", address)

# Get xpub at account level (m/44'/195'/0')
xpub = account.PublicKey().ToExtended()


print("Tron xpub:", xpub)


# Ask user how many addresses to generate from xpub
try:
    count = int(
        input("How many Tron addresses to generate from xpub? (default 3): ").strip()
        or 3
    )
except ValueError:
    count = 3

# Create a Bip44 context from the xpub
pub_ctx = Bip44.FromExtendedKey(xpub, Bip44Coins.TRON)
print(f"First {count} Tron addresses from xpub (m/44'/195'/0'/0/i):")

for i in range(count):
    addr = (
        pub_ctx.Change(Bip44Changes.CHAIN_EXT).AddressIndex(i).PublicKey().ToAddress()
    )
    print(f"  Address {i}: {addr}")

# Optionally, let user derive a private key from a supplied xprv and path
if (
    input(
        "Do you want to derive a private key from a master private key and path? (y/N): "
    )
    .strip()
    .lower()
    == "y"
):
    derive_private_key_from_xprv()


"""

### BIP44 Derivation Path Structure

A standard BIP44 path looks like:
```
m / purpose' / coin_type' / account' / change / address_index
```
- `m` — master node (from your seed)
- `purpose'` — always `44'` for BIP44
- `coin_type'` — identifies the blockchain (e.g., `195'` for Tron)
- `account'` — lets you have multiple independent accounts/wallets
- `change` — `0` for external (receiving) addresses, `1` for internal (change) addresses
- `address_index` — increments for each new address

Example for Tron:
```
m/44'/195'/0'/0/0
```
---

### xPUB Generation

- The xPUB (extended public key) is generated at the **account** level:  
  For example, at `m/44'/195'/0'`.
- The xPUB allows you (or a wallet) to derive all public addresses for that account (for any change and address index), but **not** private keys.
- Changing the account number gives you a completely different xPUB and address set.

---

### How Addresses Are Derived

- **External addresses** (`change = 0`): Used for receiving funds; these are the addresses you share.
- **Internal addresses** (`change = 1`): Used for change when sending funds (not typically used in Tron).
- **Address index**: Incremented for each new address.

---

### Special Notes for Tron

- Tron wallets almost always use only the external branch (`change = 0`).
- Internal/change addresses (`change = 1`) and non-standard branches (`change > 1`) are not used in normal Tron operations.

---

**Summary:**  
The BIP44 path organizes your wallet into accounts and addresses. The xPUB at the account level lets you generate all public addresses for that account. For Tron, you typically use only the external addresses (`change = 0`). Each part of the path has a specific purpose for wallet structure and privacy.
"""
