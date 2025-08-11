from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
try:
    from core.database.models import (
        Seller,
        Invoice,
        Transaction,
        Wallet,
        GasStation,
        BuyerGroup,
        FreeGasUsage,
        Base,
        FreeGasAddress,
    )
except ImportError:
    from src.core.database.models import (
    Seller,
    Invoice,
    Transaction,
    Wallet,
    GasStation,
    BuyerGroup,
    FreeGasUsage,
    Base,
    FreeGasAddress,
    )
import os
import logging
from typing import Optional
from datetime import datetime, timezone


logger = logging.getLogger(__name__)

BASE_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "../../../")
)  # points to project root
DATABASE_URL = f"sqlite:///{os.path.join(BASE_DIR, 'data', 'database.sqlite3')}"
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

logger.info("Full DATABASE_URL: %s", DATABASE_URL)
DB_PATH = DATABASE_URL.replace("sqlite:///", "")
logger.info("Resolved DB_PATH: %s", DB_PATH)


def init_db() -> Optional[str]:
    """Initialize the SQLite database on first run.
    - Ensures the data directory exists
    - Creates all tables defined in models.Base
    Returns the DB path or None on failure.
    """
    try:
        data_dir = os.path.dirname(DB_PATH)
        if data_dir and not os.path.exists(data_dir):
            os.makedirs(data_dir, exist_ok=True)
            logger.info("Created data directory: %s", data_dir)
        Base.metadata.create_all(bind=engine)
        logger.info("Database initialized (tables ensured)")
        return DB_PATH
    except Exception as e:
        logger.error("Failed to initialize database: %s", e)
        return None


# Ensure DB exists when this module is imported
init_db()


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
    # Backward-compat: map telegram_id->seller_id and invoices_group->account if provided
    mapped = dict(kwargs)
    if "seller_id" not in mapped and "telegram_id" in mapped:
        mapped["seller_id"] = mapped.pop("telegram_id")
    if "account" not in mapped and "invoices_group" in mapped:
        mapped["account"] = mapped.pop("invoices_group")
    wallet = Wallet(**mapped)
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


# --- FREE GAS USAGE CRUD ---
def get_free_gas_usage(db, seller_id):
    """Return today's Free Gas usage record for the given seller_id.
    If a record exists but last update was on a previous day, reset the counter to 0 for today.
    """
    rec = db.query(FreeGasUsage).filter(FreeGasUsage.seller_id == seller_id).first()
    now = datetime.now(timezone.utc)
    if rec:
        try:
            last = rec.updated_at or now
            # Compare dates in UTC; if day changed, reset counter
            if last.date() != now.date():
                rec.used_count = 0
                rec.updated_at = now
                db.commit()
                db.refresh(rec)
        except Exception:
            # On any parsing error, keep as-is
            pass
    return rec


def increment_free_gas_usage(db, seller_id) -> int:
    """Increment today's Free Gas usage counter and return today's used_count.
    Ensures the Seller row exists for unregistered users.
    Resets the counter if day changed.
    """
    # Ensure Seller exists (supports unregistered users using Free Gas)
    try:
        seller = db.query(Seller).filter(Seller.telegram_id == seller_id).first()
        if not seller:
            seller = Seller(telegram_id=seller_id)
            db.add(seller)
            db.commit()
            db.refresh(seller)
    except Exception:
        # Best-effort; in SQLite without FK enforcement this is fine
        pass

    rec = db.query(FreeGasUsage).filter(FreeGasUsage.seller_id == seller_id).first()
    now = datetime.now(timezone.utc)
    if not rec:
        rec = FreeGasUsage(seller_id=seller_id, used_count=1, updated_at=now)
        db.add(rec)
    else:
        try:
            last = rec.updated_at or now
            if last.date() != now.date():
                rec.used_count = 1  # first use today
            else:
                rec.used_count = int(rec.used_count or 0) + 1
            rec.updated_at = now
        except Exception:
            rec.used_count = int(rec.used_count or 0) + 1
            rec.updated_at = now
    db.commit()
    db.refresh(rec)
    return rec.used_count


def reset_free_gas_usage_today(db, seller_id: int) -> int:
    """Reset today's Free Gas usage for the seller to 0 and return the new value (0).
    Useful after a successful top-up to restore daily shots.
    """
    now = datetime.now(timezone.utc)
    rec = db.query(FreeGasUsage).filter(FreeGasUsage.seller_id == seller_id).first()
    if not rec:
        rec = FreeGasUsage(seller_id=seller_id, used_count=0, updated_at=now)
        db.add(rec)
    else:
        rec.used_count = 0
        rec.updated_at = now
    db.commit()
    db.refresh(rec)
    return rec.used_count


# --- FREE GAS ADDRESSES CRUD ---
def record_free_gas_address(db, telegram_id: int, address: str):
    """Insert or update a record of a TRON address submitted for Free Gas by a user.
    Increment uses and update last_used_at if it already exists.
    """
    rec = (
        db.query(FreeGasAddress)
        .filter(FreeGasAddress.telegram_id == telegram_id, FreeGasAddress.address == address)
        .first()
    )
    now = datetime.now(timezone.utc)
    if not rec:
        rec = FreeGasAddress(telegram_id=telegram_id, address=address, uses=1, created_at=now, last_used_at=now)
        db.add(rec)
    else:
        rec.uses = int(rec.uses or 0) + 1
        rec.last_used_at = now
    db.commit()
    return rec


def list_free_gas_addresses(db, telegram_id: int):
    return db.query(FreeGasAddress).filter(FreeGasAddress.telegram_id == telegram_id).all()
