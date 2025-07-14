# Основной скрипт воркера для мониторинга блокчейна


import time
from tronpy import Tron
from tronpy.providers import HTTPProvider


from core.database.db_service import get_db, get_invoices_by_seller, get_invoice, update_invoice, create_transaction
from core.database.models import Invoice, Transaction
from core.services.gas_station import auto_activate_on_usdt_receive

USDT_CONTRACT = 'TXLAQ63Xg1NAzckPwKHvzw7CSEmLMEqcdj'  # Mainnet USDT

def notify_invoice_paid(invoice_id, tx_hash, amount):
    # TODO: реализовать отправку уведомления (например, через Redis или очередь)
    print(f"Notify: Invoice {invoice_id} paid, tx: {tx_hash}, amount: {amount}")


def check_pending_invoices():
    tron = Tron(HTTPProvider())
    with next(get_db()) as db:
        # Группируем по продавцам для примера использования get_invoices_by_seller
        sellers = db.query(Invoice.seller_id).filter(Invoice.status == 'pending').distinct()
        for seller_row in sellers:
            seller_id = seller_row.seller_id
            pending_invoices = get_invoices_by_seller(db, seller_id)
            for invoice in pending_invoices:
                if invoice.status != 'pending':
                    continue
                address = invoice.address
                try:
                    contract = tron.get_contract(USDT_CONTRACT)
                    balance = contract.functions.balanceOf(address)
                    balance = balance / 1_000_000
                except Exception as e:
                    print(f"Error checking balance for {address}: {e}")
                    continue
                if balance > 0:
                    # Автоматическая активация адреса при первом поступлении USDT
                    auto_activate_on_usdt_receive(address)
                    # Используем get_invoice для получения актуального объекта
                    inv = get_invoice(db, invoice.id)
                    update_invoice(db, inv.id, status='paid')
                    try:
                        txs = contract.functions.transferEvent(address)
                        for tx in txs:
                            if tx['to'] == address and float(tx['value'])/1_000_000 >= inv.amount:
                                create_transaction(db,
                                    invoice_id=inv.id,
                                    tx_hash=tx['transaction_id'],
                                    sender_address=tx['from'],
                                    amount_received=float(tx['value'])/1_000_000,
                                    received_at=tx['block_timestamp']
                                )
                                notify_invoice_paid(inv.id, tx['transaction_id'], float(tx['value'])/1_000_000)
                                break
                    except Exception as e:
                        print(f"Error fetching txs for {address}: {e}")

def main():
    print("Keeper Bot started. Monitoring pending invoices...")
    while True:
        check_pending_invoices()
        time.sleep(60)

if __name__ == "__main__":
    main()
