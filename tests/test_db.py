import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from core.database import models
from core.database.db_service import (
    create_seller, get_seller, create_buyer_group, get_buyer_group, get_buyer_groups_by_seller,
    create_wallet, get_wallet_by_group, create_invoice, get_invoice, get_invoices_by_seller
)

@pytest.fixture(scope="function")
def db():
    engine = create_engine("sqlite:///:memory:")
    models.Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()

def test_seller_crud(db):
    seller = create_seller(db, telegram_id=111)
    assert seller.telegram_id == 111
    seller2 = get_seller(db, 111)
    assert seller2 is not None

def test_buyer_group_crud(db):
    seller = create_seller(db, telegram_id=222)
    group = create_buyer_group(db, seller_id=222, buyer_id="buyer1", invoices_group=0)
    assert group.buyer_id == "buyer1"
    found = get_buyer_group(db, 222, "buyer1")
    assert found is not None
    groups = get_buyer_groups_by_seller(db, 222)
    assert len(groups) == 1

def test_wallet_crud(db):
    seller = create_seller(db, telegram_id=333)
    group = create_buyer_group(db, seller_id=333, buyer_id="buyer2", invoices_group=1)
    wallet = create_wallet(db, telegram_id=333, buyer_group_id=group.id, invoices_group=1, xpub="xpub_test")
    found = get_wallet_by_group(db, 333, 1)
    assert found is not None
    assert found.xpub == "xpub_test"

def test_invoice_crud(db):
    seller = create_seller(db, telegram_id=444)
    group = create_buyer_group(db, seller_id=444, buyer_id="buyer3", invoices_group=2)
    wallet = create_wallet(db, telegram_id=444, buyer_group_id=group.id, invoices_group=2, xpub="xpub_test2")
    invoice = create_invoice(db, seller_id=444, buyer_group_id=group.id, derivation_index=0, address="addr1", amount=10, status="pending")
    found = get_invoice(db, invoice.id)
    assert found is not None
    invoices = get_invoices_by_seller(db, 444)
    assert len(invoices) == 1
