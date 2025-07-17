# Логика "Gas Station" (активация, делегирование)


from tronpy import Tron
import time
from src.core.database.db_service import get_seller_wallet, create_seller_wallet
from bip_utils import Bip44, Bip44Coins, Bip44Changes, Bip39SeedGenerator

# Приватный ключ газового кошелька (замените на реальный способ хранения)
GAS_WALLET_PRIVATE_KEY = "YOUR_GAS_WALLET_PRIVATE_KEY"


def prepare_for_sweep(invoice_address):
    """
    Активирует адрес invoice_address, делегирует энергию и bandwidth через Tronpy.
    Возвращает True при успехе.
    """
    # Now resources delegated immideately upon USDT reception
    # and after activation, but in real case scenario
    # we can delegate resources on seller's request
    # so we can have some free bandwidth generation
    # and calculate how much we need
    # to delegate for each invoice
    try:
        client = Tron()
        gas_wallet = client.get_account(GAS_WALLET_PRIVATE_KEY)
        # 1. Отправить ~1.5 TRX для активации адреса (чтобы хватило на комиссии)
        txn = (
            client.trx.transfer(
                gas_wallet.address, invoice_address, int(1.5 * 1_000_000)
            )
            .build()
            .sign(GAS_WALLET_PRIVATE_KEY)
        )
        result = txn.broadcast()
        txid = result["txid"]
        # Ждать подтверждения
        for _ in range(30):
            receipt = client.get_transaction_info(txid)
            if receipt and receipt.get("receipt", {}).get("result") == "SUCCESS":
                break
            time.sleep(2)
        else:
            print("TRX activation failed")
            return False
        # 2. Делегировать энергию (~70,000 Energy)
        delegate_energy_txn = (
            client.trx.delegate_resource(
                owner=gas_wallet.address,
                receiver=invoice_address,
                balance=int(1.1 * 1_000_000),
                resource="ENERGY",
            )
            .build()
            .sign(GAS_WALLET_PRIVATE_KEY)
        )
        energy_result = delegate_energy_txn.broadcast()
        energy_txid = energy_result["txid"]
        # Ждать подтверждения делегирования энергии
        for _ in range(30):
            receipt = client.get_transaction_info(energy_txid)
            if receipt and receipt.get("receipt", {}).get("result") == "SUCCESS":
                break
            time.sleep(2)
        else:
            print("Delegate ENERGY failed")
            return False
        # 3. Делегировать bandwidth (~500 bandwidth, 1 TRX достаточно)
        delegate_bw_txn = (
            client.trx.delegate_resource(
                owner=gas_wallet.address,
                receiver=invoice_address,
                balance=int(1.0 * 1_000_000),
                resource="BANDWIDTH",
            )
            .build()
            .sign(GAS_WALLET_PRIVATE_KEY)
        )
        bw_result = delegate_bw_txn.broadcast()
        bw_txid = bw_result["txid"]
        # Ждать подтверждения делегирования bandwidth
        for _ in range(30):
            receipt = client.get_transaction_info(bw_txid)
            if receipt and receipt.get("receipt", {}).get("result") == "SUCCESS":
                return True
            time.sleep(2)
        print("Delegate BANDWIDTH failed")
        return False
    except Exception as e:
        print(f"Error in prepare_for_sweep: {e}")
        return False


# Автоматическая активация адреса при первом поступлении USDT
def auto_activate_on_usdt_receive(invoice_address):
    """
    Проверяет, активирован ли адрес, и если нет — вызывает prepare_for_sweep.
    Вызывать из keeper-бота при обнаружении первого поступления USDT.
    """
    try:
        client = Tron()
        acc_info = client.get_account(invoice_address)
        # Tron semantics: account is not activated ONLY if get_account returns None
        if acc_info is None:
            print(f"Address {invoice_address} not activated, activating...")
            return prepare_for_sweep(invoice_address)
        # Можно добавить проверку на наличие делегированных ресурсов
        return True
    except Exception as e:
        print(f"Error in auto_activate_on_usdt_receive: {e}")
        return False


def get_or_create_tron_deposit_address(
    db, seller_id, deposit_type="TRX", xpub=None, account=None
):
    # 1. Check if address already exists for this seller and deposit_type
    wallet = get_seller_wallet(db, seller_id, deposit_type)
    if wallet:
        return wallet.address

    # 2. Derive new address (account = seller_id or custom)
    if account is None:
        account = seller_id  # or another unique per-seller value


    # Use xpub if provided, else derive from gas station mnemonic/seed (for admin/gas wallet)
    if xpub:
        # Derive address from xpub using bip_utils
        pub_ctx = Bip44.FromExtendedKey(xpub, Bip44Coins.TRON)
        # Always use external chain (0), address index 0 for deposit
        address = pub_ctx.Change(Bip44Changes.CHAIN_EXT).AddressIndex(0).PublicKey().ToAddress()
        path = f"m/44'/195'/{account}'/0/0"
    else:
        # For admin/gas wallet, you must have a mnemonic or xprv, not just a private key
        # Example: use a mnemonic from env/config (replace with your secure storage)
        import os
        mnemonic = os.getenv("GAS_WALLET_MNEMONIC", "")
        if not mnemonic:
            raise Exception("GAS_WALLET_MNEMONIC not set in environment!")
        seed_bytes = Bip39SeedGenerator(mnemonic).Generate()
        bip44_ctx = Bip44.FromSeed(seed_bytes, Bip44Coins.TRON)
        account_ctx = bip44_ctx.Purpose().Coin().Account(account)
        # Get xpub for storage if needed
        xpub = account_ctx.PublicKey().ToExtended()
        # Derive address for deposit
        address = account_ctx.Change(Bip44Changes.CHAIN_EXT).AddressIndex(0).PublicKey().ToAddress()
        path = f"m/44'/195'/{account}'/0/0"

    # 3. Save to DB
    create_seller_wallet(
        db=db,
        seller_id=seller_id,
        address=address,
        derivation_path=path,
        deposit_type=deposit_type,
        xpub=xpub,
        account=account,
    )
    return address


def calculate_trx_needed(seller):
    # Example: use seller.subscription or seller.tariff_plan
    # You can expand this logic as needed
    base_amount = 5  # Minimum for activation
    if hasattr(seller, 'tariff_plan'):
        if seller.tariff_plan == 'premium':
            return 20
        elif seller.tariff_plan == 'standard':
            return 10
    return base_amount
