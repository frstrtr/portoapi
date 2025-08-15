# Обработчики /start, /help


from aiogram import types
try:
    from core.database.db_service import get_seller, SessionLocal
except ImportError:
    from src.core.database.db_service import get_seller, SessionLocal


def get_main_menu_keyboard(is_registered: bool = True):
    """Generate main menu keyboard based on registration status"""
    if is_registered:
        keyboard = [
            [types.KeyboardButton(text="/help"), types.KeyboardButton(text="⛽️ Free Gas ⛽️")],
            [types.KeyboardButton(text="/myaccount"), types.KeyboardButton(text="/balance")],
            [types.KeyboardButton(text="/create_invoice"), types.KeyboardButton(text="/buyers")],
            [types.KeyboardButton(text="/invoices"), types.KeyboardButton(text="/sweep")],
            [types.KeyboardButton(text="/add_buyer"), types.KeyboardButton(text="/deposit")]
        ]
    else:
        keyboard = [
            [types.KeyboardButton(text="/register"), types.KeyboardButton(text="/help")],
			[types.KeyboardButton(text="⛽️ Free Gas ⛽️")]
        ]
    
    return types.ReplyKeyboardMarkup(
        keyboard=keyboard,
        resize_keyboard=True,
        one_time_keyboard=False
    )


async def handle_start(message: types.Message):
    user = message.from_user
    
    # Check if user is registered
    try:
        db = SessionLocal()
        seller = get_seller(db=db, telegram_id=user.id)
        # Check if user has any xPub configured
        try:
            from core.database.db_service import get_wallets_by_seller, get_buyer_groups_by_seller
        except ImportError:
            from src.core.database.db_service import get_wallets_by_seller, get_buyer_groups_by_seller
        wallets = get_wallets_by_seller(db, user.id)
        buyer_groups = get_buyer_groups_by_seller(db, user.id)
        has_xpub = any(w.xpub for w in wallets) or any(g.xpub for g in buyer_groups)
        is_registered = seller is not None and has_xpub
        db.close()
    except Exception:
        is_registered = False
    
    welcome_text = f"👋 Привет, {user.first_name}!\n\n"
    
    if is_registered:
        welcome_text += (
            "✅ Вы уже зарегистрированы в системе.\n\n"
            "📱 Используйте кнопки меню для управления:\n"
            "• /myaccount - информация об аккаунте\n"
            "• /create_invoice - создать инвойс\n"
            "• /buyers - управление покупателями\n"
            "• /balance - проверить баланс\n"
            "• /help - помощь и инструкции"
        )
    else:
        welcome_text += (
            "🚀 Добро пожаловать в PortoAPI!\n\n"
            "Это бот для приема криптоплатежей в TRON.\n\n"
            "📋 Для начала работы:\n"
            "1. Нажмите /register для регистрации\n"
            "2. Настройте xPub кошелек\n"
            "3. Начните принимать платежи!\n\n"
            "❓ Нужна помощь? Используйте /help"
        )
    
    keyboard = get_main_menu_keyboard(is_registered=is_registered)
    await message.answer(welcome_text, reply_markup=keyboard)


async def handle_help(message: types.Message):
    # Check if user is registered for appropriate help content
    try:
        db = SessionLocal()
        seller = get_seller(db=db, telegram_id=message.from_user.id)
        try:
            from core.database.db_service import get_wallets_by_seller, get_buyer_groups_by_seller
        except ImportError:
            from src.core.database.db_service import get_wallets_by_seller, get_buyer_groups_by_seller
        wallets = get_wallets_by_seller(db, message.from_user.id)
        buyer_groups = get_buyer_groups_by_seller(db, message.from_user.id)
        has_xpub = any(w.xpub for w in wallets) or any(g.xpub for g in buyer_groups)
        is_registered = seller is not None and has_xpub
        db.close()
    except Exception:
        is_registered = False
    
    if is_registered:
        help_text = """🔧 **Доступные команды:**

👤 **Аккаунт:**
• /myaccount - подробная информация об аккаунте
• /balance - баланс кошельков
• /deposit - газовый депозит

💰 **Инвойсы:**
• /create_invoice - создать новый инвойс
• /invoices - список всех инвойсов
• /sweep - вывод средств с оплаченных инвойсов

👥 **Покупатели:**
• /buyers - список покупателей
• /add_buyer - добавить нового покупателя

⛽ **Газовая станция:**
• /gasstation - статус и управление газовой станцией
• /gasstation_stake - управление стейкингом
• /gasstation_delegate - управление делегированием
• /free_gas - подготовка адреса (активация + ресурсы)

🔐 **Permission-Based активация:**
• /permission_activate [адрес] - современная активация через permissions
• /permission_status - статус permission-based системы

🤖 **Мониторинг:**
• /keeper_status - статус keeper bot
• /keeper_logs - логи keeper bot

❓ **Справка:**
• /help - эта справка
• /start - главное меню

🔍 **Понятия:**
• **Account** - номер счета в HD кошельке (m/44'/195'/account')
• **Gas Station** - система управления TRON ресурсами
• **Keeper Bot** - автоматический мониторинг платежей
• **Address Index** - номер адреса в рамках account
• **xPub** - публичный ключ для генерации адресов
• **Buyer ID** - идентификатор группы покупателей"""
    else:
        help_text = """🚀 **Начало работы:**

1. /register - регистрация в системе
2. Настройка xPub кошелька (офлайн)
3. Создание покупателей и инвойсов

⛽ **Free Gas:**
Нажмите кнопку "⛽️ Free Gas ⛽️" и отправьте адрес TRON (T...), чтобы активировать адрес и получить ресурсы для одной транзакции USDT.

🔐 **Permission-Based активация:**
Современный метод активации адресов через систему разрешений TRON:
• `/permission_activate [адрес]` - активировать адрес
• `/permission_status` - проверить статус системы

❓ **Что такое xPub?**
Это публичный ключ, который позволяет генерировать адреса для приема платежей без доступа к приватным ключам.

🔒 **Безопасность:**
Все операции с приватными ключами выполняются только на вашем устройстве."""
    
    keyboard = get_main_menu_keyboard(is_registered=is_registered)
    await message.answer(help_text, parse_mode="HTML", reply_markup=keyboard)
