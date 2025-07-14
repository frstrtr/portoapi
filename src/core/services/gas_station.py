# Логика "Gas Station" (активация, делегирование)


from tronpy import Tron
import time

# Приватный ключ газового кошелька (замените на реальный способ хранения)
GAS_WALLET_PRIVATE_KEY = 'YOUR_GAS_WALLET_PRIVATE_KEY'


def prepare_for_sweep(invoice_address):
    """
    Активирует адрес invoice_address, делегирует энергию и bandwidth через Tronpy.
    Возвращает True при успехе.
    """
    try:
        client = Tron()
        gas_wallet = client.get_account(GAS_WALLET_PRIVATE_KEY)
        # 1. Отправить ~1.5 TRX для активации адреса (чтобы хватило на комиссии)
        txn = (
            client.trx.transfer(gas_wallet.address, invoice_address, int(1.5 * 1_000_000))
            .build()
            .sign(GAS_WALLET_PRIVATE_KEY)
        )
        result = txn.broadcast()
        txid = result['txid']
        # Ждать подтверждения
        for _ in range(30):
            receipt = client.get_transaction_info(txid)
            if receipt and receipt.get('receipt', {}).get('result') == 'SUCCESS':
                break
            time.sleep(2)
        else:
            print('TRX activation failed')
            return False
        # 2. Делегировать энергию (~70,000 Energy)
        delegate_energy_txn = (
            client.trx.delegate_resource(
                owner=gas_wallet.address,
                receiver=invoice_address,
                balance=int(1.1 * 1_000_000),
                resource='ENERGY'
            ).build().sign(GAS_WALLET_PRIVATE_KEY)
        )
        energy_result = delegate_energy_txn.broadcast()
        energy_txid = energy_result['txid']
        # Ждать подтверждения делегирования энергии
        for _ in range(30):
            receipt = client.get_transaction_info(energy_txid)
            if receipt and receipt.get('receipt', {}).get('result') == 'SUCCESS':
                break
            time.sleep(2)
        else:
            print('Delegate ENERGY failed')
            return False
        # 3. Делегировать bandwidth (~500 bandwidth, 1 TRX достаточно)
        delegate_bw_txn = (
            client.trx.delegate_resource(
                owner=gas_wallet.address,
                receiver=invoice_address,
                balance=int(1.0 * 1_000_000),
                resource='BANDWIDTH'
            ).build().sign(GAS_WALLET_PRIVATE_KEY)
        )
        bw_result = delegate_bw_txn.broadcast()
        bw_txid = bw_result['txid']
        # Ждать подтверждения делегирования bandwidth
        for _ in range(30):
            receipt = client.get_transaction_info(bw_txid)
            if receipt and receipt.get('receipt', {}).get('result') == 'SUCCESS':
                return True
            time.sleep(2)
        print('Delegate BANDWIDTH failed')
        return False
    except Exception as e:
        print(f'Error in prepare_for_sweep: {e}')
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
        if not acc_info or acc_info.get('address') is None:
            print(f'Address {invoice_address} not activated, activating...')
            return prepare_for_sweep(invoice_address)
        # Можно добавить проверку на наличие делегированных ресурсов
        return True
    except Exception as e:
        print(f'Error in auto_activate_on_usdt_receive: {e}')
        return False
