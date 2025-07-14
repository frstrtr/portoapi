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


def handle_invoice_payment(db, contract, inv, address, not_activated):
    # Prevent repeated activation attempts by marking the invoice as 'activating'
    if not_activated and inv.status != 'activating':
        update_invoice(db, inv.id, status='activating')
        try:
            auto_activate_on_usdt_receive(address)
        except Exception as e:
            print(f"Activation failed for {address}: {e}")
            return
    update_invoice(db, inv.id, status='paid')
    try:
        txs = contract.functions.transferEvent(address)
        for tx in txs:
            if tx['to'] == address and float(tx['value'])/1_000_000 >= inv.amount:
                # Convert block_timestamp to datetime if needed
                received_at = tx['block_timestamp']
                if isinstance(received_at, int) or isinstance(received_at, float):
                    from datetime import datetime
                    received_at = datetime.fromtimestamp(received_at / 1000.0)
                create_transaction(
                    db,
                    invoice_id=inv.id,
                    tx_hash=tx['transaction_id'],
                    sender_address=tx['from'],
                    amount_received=float(tx['value'])/1_000_000,
                    received_at=received_at
                )
                notify_invoice_paid(inv.id, tx['transaction_id'], float(tx['value'])/1_000_000)
                break
    except Exception as e:
        print(f"Error fetching txs for {address}: {e}")

def process_invoice(tron, db, contract, invoice):
    if invoice.status != 'pending':
        return
    address = invoice.address
    try:
        balance = contract.functions.balanceOf(address)()
        balance = balance / 1_000_000
    except Exception as e:
        print(f"Error checking balance for {address}: {e}")
        return

    try:
        account_info = tron.get_account(address)
        not_activated = account_info is None
    except Exception as e:
        print(f"Error checking TRX account for {address}: {e}")
        not_activated = True

    if balance > 0:
        print(f"Invoice {invoice.id} paid with {balance} USDT at address {address}")
        inv = get_invoice(db, invoice.id)
        handle_invoice_payment(db, contract, inv, address, not_activated)

def check_pending_invoices():
    tron = Tron(HTTPProvider())
    with next(get_db()) as db:
        # Группируем по продавцам для примера использования get_invoices_by_seller
        sellers = db.query(Invoice.seller_id).filter(Invoice.status == 'pending').distinct()
        contract = tron.get_contract(USDT_CONTRACT)
        for seller_row in sellers:
            seller_id = seller_row.seller_id
            pending_invoices = get_invoices_by_seller(db, seller_id)
            for invoice in pending_invoices:
                process_invoice(tron, db, contract, invoice)
    db.close()

def main():
    print("Keeper Bot started. Monitoring pending invoices...")
    while True:
        check_pending_invoices()
        time.sleep(60)

if __name__ == "__main__":
    main()
