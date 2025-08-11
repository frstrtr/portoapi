from sqlalchemy.orm import declarative_base
from sqlalchemy import UniqueConstraint


from sqlalchemy import Column, Integer, Text, Float, DateTime, ForeignKey, String
from sqlalchemy.orm import relationship
import datetime

try:
    UTC = datetime.UTC
except AttributeError:
    from datetime import timezone
    UTC = timezone.utc


Base = declarative_base()


class Balance(Base):
    __tablename__ = "balances"
    id = Column(Integer, primary_key=True)
    wallet_id = Column(Integer, ForeignKey("wallets.id"))
    asset = Column(String(32), nullable=False)  # например, 'USDT', 'TRX'
    amount = Column(Float, default=0)
    updated_at = Column(DateTime, default=lambda: datetime.datetime.now(UTC))
    wallet = relationship("Wallet", back_populates="balances")


class BuyerGroup(Base):
    __tablename__ = "buyer_groups"
    id = Column(Integer, primary_key=True)
    seller_id = Column(Integer, ForeignKey("sellers.telegram_id"))
    buyer_id = Column(Text, nullable=False)
    invoices_group = Column(Integer, nullable=False)  # BIP44 account
    xpub = Column(Text, nullable=True)
    __table_args__ = (
        UniqueConstraint("seller_id", "buyer_id", name="uix_seller_buyer"),
    )
    seller = relationship("Seller", back_populates="buyer_groups")
    invoices = relationship("Invoice", back_populates="buyer_group")


# Модели таблиц БД (SQLAlchemy/SQLModel)


class Seller(Base):
    __tablename__ = "sellers"
    telegram_id = Column(Integer, primary_key=True)
    # xpub removed: now stored in Wallets table per invoices_group
    gas_deposit_balance = Column(Float, default=0)
    date_created = Column(DateTime, default=lambda: datetime.datetime.now(UTC))
    date_last_interacted = Column(DateTime, default=lambda: datetime.datetime.now(UTC))
    score = Column(Float, default=0)
    invoices = relationship("Invoice", back_populates="seller")
    wallets = relationship("Wallet", back_populates="seller")
    buyer_groups = relationship("BuyerGroup", back_populates="seller")
    gas_station = relationship("GasStation", back_populates="seller", uselist=False)


class Invoice(Base):
    __tablename__ = "invoices"
    id = Column(Integer, primary_key=True)
    seller_id = Column(Integer, ForeignKey("sellers.telegram_id"))
    buyer_group_id = Column(Integer, ForeignKey("buyer_groups.id"))
    derivation_index = Column(Integer, nullable=False)
    address = Column(Text, nullable=False)
    amount = Column(Float, nullable=False)
    status = Column(
        String(16), nullable=False, default="pending"
    )  # 'pending', 'paid', 'expired'
    created_at = Column(DateTime, default=lambda: datetime.datetime.now(UTC))
    seller = relationship("Seller", back_populates="invoices")
    buyer_group = relationship("BuyerGroup", back_populates="invoices")
    transactions = relationship("Transaction", back_populates="invoice")
    __table_args__ = (
        UniqueConstraint("buyer_group_id", "derivation_index", name="uix_buyer_group_derivation_index"),
    )


class Transaction(Base):
    __tablename__ = "transactions"
    id = Column(Integer, primary_key=True)
    invoice_id = Column(Integer, ForeignKey("invoices.id"))
    tx_hash = Column(Text, unique=True, nullable=False)
    sender_address = Column(Text, nullable=False)
    amount_received = Column(Float, nullable=False)
    received_at = Column(DateTime, default=lambda: datetime.datetime.now(UTC))
    invoice = relationship("Invoice", back_populates="transactions")


class GasStation(Base):
    __tablename__ = "gas_stations"
    id = Column(Integer, primary_key=True)
    telegram_id = Column(Integer, ForeignKey("sellers.telegram_id"), unique=True)
    is_active = Column(Integer, default=0)  # 0 - inactive, 1 - active
    seller = relationship("Seller", back_populates="gas_station", uselist=False)


class FreeGasUsage(Base):
    __tablename__ = "free_gas_usage"
    seller_id = Column(Integer, ForeignKey("sellers.telegram_id"), primary_key=True)
    used_count = Column(Integer, default=0)
    updated_at = Column(DateTime, default=lambda: datetime.datetime.now(UTC))
    seller = relationship("Seller")


class FreeGasAddress(Base):
    __tablename__ = "free_gas_addresses"
    id = Column(Integer, primary_key=True)
    telegram_id = Column(Integer, nullable=False, index=True)
    address = Column(Text, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.datetime.now(UTC))
    last_used_at = Column(DateTime, default=lambda: datetime.datetime.now(UTC))
    uses = Column(Integer, default=1)
    __table_args__ = (
        UniqueConstraint("telegram_id", "address", name="uix_freegas_user_addr"),
    )


class Wallet(Base):
    __tablename__ = "wallets"
    id = Column(Integer, primary_key=True)
    seller_id = Column(Integer, ForeignKey("sellers.telegram_id"))
    xpub = Column(Text, nullable=False)
    account = Column(Integer, nullable=False, default=0)  # BIP44 account (group)
    label = Column(String(64), nullable=True)  # Optional: wallet label/name
    address = Column(Text, nullable=True)  # Main address for this wallet/account
    derivation_path = Column(Text, nullable=True)
    deposit_type = Column(String(16), nullable=True)
    buyer_group_id = Column(Integer, ForeignKey("buyer_groups.id"), nullable=True)
    seller = relationship("Seller", back_populates="wallets")
    buyer_group = relationship("BuyerGroup")
    balances = relationship("Balance", back_populates="wallet")
    porto_token_balance = Column(Float, default=0)
    USDT_tron_balance = Column(Float, default=0)
    __table_args__ = (
        UniqueConstraint("seller_id", "xpub", "account", name="uix_seller_xpub_account"),
    )
