from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from .models import Seller, Invoice, Transaction, Wallet, GasStation
import os
import logging
from .models import BuyerGroup


logger = logging.getLogger(__name__)

BASE_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "../../../")
)  # points to project root
DATABASE_URL = f"sqlite:///{os.path.join(BASE_DIR, 'data', 'database.sqlite3')}"
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

logger.info(f"Full DATABASE_URL: {DATABASE_URL}")
DB_PATH = DATABASE_URL.replace("sqlite:///", "")
logger.info(f"Resolved DB_PATH: {DB_PATH}")


# --- BUYER GROUPS CRUD ---
def get_buyer_groups_by_seller(db, seller_id):

    return db.query(BuyerGroup).filter(BuyerGroup.seller_id == seller_id).all()


def get_buyer_group(db, seller_id, buyer_id):

    return (
        db.query(BuyerGroup)
        .filter(BuyerGroup.seller_id == seller_id, BuyerGroup.buyer_id == buyer_id)
        .first()
    )


def create_buyer_group(db, seller_id, buyer_id, invoices_group, xpub=None):

    group = BuyerGroup(
        seller_id=seller_id, buyer_id=buyer_id, invoices_group=invoices_group, xpub=xpub
    )
    db.add(group)
    db.commit()
    db.refresh(group)
    return group


# Функции для работы с базой данных


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# --- SELLERS CRUD ---
def create_seller(db, telegram_id, **kwargs):
    seller = Seller(telegram_id=telegram_id, **kwargs)
    db.add(seller)
    db.commit()
    db.refresh(seller)
    return seller


def get_seller(db, telegram_id):
    return db.query(Seller).filter(Seller.telegram_id == telegram_id).first()


def update_seller(db, telegram_id, **kwargs):
    """Update seller information by telegram_id.
    Accepts any field from the Seller model."""

    seller = get_seller(db, telegram_id)
    for k, v in kwargs.items():
        setattr(seller, k, v)
    db.commit()
    db.refresh(seller)
    return seller


def delete_seller(db, telegram_id):
    seller = get_seller(db, telegram_id)
    db.delete(seller)
    db.commit()


# --- INVOICES CRUD ---
def create_invoice(db, **kwargs):
    invoice = Invoice(**kwargs)
    db.add(invoice)
    db.commit()
    db.refresh(invoice)
    return invoice


def get_invoice(db, invoice_id):
    return db.query(Invoice).filter(Invoice.id == invoice_id).first()


def get_invoices_by_seller(db, seller_id):
    return db.query(Invoice).filter(Invoice.seller_id == seller_id).all()


def update_invoice(db, invoice_id, **kwargs):
    invoice = get_invoice(db, invoice_id)
    for k, v in kwargs.items():
        setattr(invoice, k, v)
    db.commit()
    db.refresh(invoice)
    return invoice


def delete_invoice(db, invoice_id):
    invoice = get_invoice(db, invoice_id)
    db.delete(invoice)
    db.commit()


# --- TRANSACTIONS CRUD ---
def create_transaction(db, **kwargs):
    tx = Transaction(**kwargs)
    db.add(tx)
    db.commit()
    db.refresh(tx)
    return tx


def get_transaction(db, tx_id):
    return db.query(Transaction).filter(Transaction.id == tx_id).first()


def get_transactions_by_invoice(db, invoice_id):
    return db.query(Transaction).filter(Transaction.invoice_id == invoice_id).all()


def update_transaction(db, tx_id, **kwargs):
    tx = get_transaction(db, tx_id)
    for k, v in kwargs.items():
        setattr(tx, k, v)
    db.commit()
    db.refresh(tx)
    return tx


def delete_transaction(db, tx_id):
    tx = get_transaction(db, tx_id)
    db.delete(tx)
    db.commit()


# --- WALLETS CRUD ---
def create_wallet(db, **kwargs):
    wallet = Wallet(**kwargs)
    db.add(wallet)
    db.commit()
    db.refresh(wallet)
    return wallet


def get_wallet(db, wallet_id):
    return db.query(Wallet).filter(Wallet.id == wallet_id).first()


def get_wallets_by_seller(db, telegram_id):
    return db.query(Wallet).filter(Wallet.seller_id == telegram_id).all()


def get_wallet_by_group(db, telegram_id, invoices_group):
    return (
        db.query(Wallet)
        .filter(Wallet.seller_id == telegram_id, Wallet.account == invoices_group)
        .first()
    )


def update_wallet(db, wallet_id, **kwargs):
    wallet = get_wallet(db, wallet_id)
    for k, v in kwargs.items():
        setattr(wallet, k, v)
    db.commit()
    db.refresh(wallet)
    return wallet


def delete_wallet(db, wallet_id):
    wallet = get_wallet(db, wallet_id)
    db.delete(wallet)
    db.commit()


def get_seller_wallet(db, seller_id, deposit_type):
    return (
        db.query(Wallet)
        .filter_by(seller_id=seller_id, deposit_type=deposit_type)
        .first()
    )


def create_seller_wallet(
    db, seller_id, address, derivation_path, deposit_type, xpub, account
):
    wallet = Wallet(
        seller_id=seller_id,
        address=address,
        derivation_path=derivation_path,
        deposit_type=deposit_type,
        xpub=xpub,
        account=account,
    )
    db.add(wallet)
    db.commit()
    db.refresh(wallet)
    return wallet


# --- GAS STATION CRUD ---
def create_gas_station(db, **kwargs):
    gs = GasStation(**kwargs)
    db.add(gs)
    db.commit()
    db.refresh(gs)
    return gs


def get_gas_station(db, gs_id):
    return db.query(GasStation).filter(GasStation.id == gs_id).first()


def get_gas_station_by_seller(db, telegram_id):
    return db.query(GasStation).filter(GasStation.telegram_id == telegram_id).first()


def update_gas_station(db, gs_id, **kwargs):
    gs = get_gas_station(db, gs_id)
    for k, v in kwargs.items():
        setattr(gs, k, v)
    db.commit()
    db.refresh(gs)
    return gs


def delete_gas_station(db, gs_id):
    gs = get_gas_station(db, gs_id)
    db.delete(gs)
    db.commit()
