import logging
from aiogram import types
from src.core.database.db_service import create_seller_wallet

# --- Admins list (replace with your real admin Telegram IDs) ---
ADMINS = {44816530}  # Example: set of Telegram IDs

def is_admin(user_id):
    return user_id in ADMINS

# --- Admin command: /admin_xpubs <seller_id> ---
async def handle_admin_xpubs(message: types.Message):
    telegram_id = message.from_user.id
    if not is_admin(telegram_id):
        await message.answer("⛔️ Нет доступа. Только для админов.")
        return
    args = message.text.strip().split()
    if len(args) != 2:
        await message.answer("Использование: /admin_xpubs <seller_id>")
        return
    try:
        seller_id = int(args[1])
    except Exception:
        await message.answer("seller_id должен быть числом.")
        return
    db = message.bot.db
    wallets = (
        db.query(create_seller_wallet.__globals__["Wallet"])
        .filter_by(seller_id=seller_id)
        .all()
    )
    if not wallets:
        await message.answer(f"Нет xPub-кошельков для seller_id {seller_id}.")
        return
    text = f"xPubs для seller_id {seller_id}:\n"
    for w in wallets:
        text += f"- group: {w.invoices_group}, xpub: {w.xpub}\n"
    await message.answer(text)
