
# PortoAPI

Многофункциональная платформа для приема криптоплатежей через Telegram-бота и API с поддержкой TRON, xPub, группировки инвойсов по покупателям.

## Архитектура
- **src/api/** — REST API (FastAPI), эндпоинты для инвойсов, вебхуков и регистрации.
- **src/bot/** — Telegram-бот на aiogram, FSM для создания инвойсов, обработка команд продавца.
- **src/core/** — бизнес-логика: HD Wallet, работа с БД (SQLAlchemy), сервисы газа и уведомлений.
- **src/services/** — keeper-бот для мониторинга блокчейна и автоматизации выплат.
- **src/static_web/** — offline-страницы для генерации xPub, безопасной настройки кошелька.

## Основные возможности
- Генерация и хранение xPub для TRON (BIP44, m/44'/195'/account').
- Группировка инвойсов по покупателям (buyer_id) у каждого продавца (seller_id).
- Автоматическая активация адресов и делегирование ресурсов (ENERGY/BANDWIDTH).
- Keeper-бот: мониторинг статуса инвойсов, автоматизация выплат.
- Безопасная регистрация через offline-страницу (setup.html/xpub_offline.html).

## Быстрый старт
1. Установите зависимости:
   ```bash
   pip install -r src/requirements.txt
   ```
2. Запустите API:
   ```bash
   uvicorn src.api.v1.main:app --reload
   ```
3. Запустите Telegram-бота:
   ```bash
   python src/bot/main_bot.py
   ```
4. Запустите keeper-бота:
   ```bash
   python src/services/keeper_bot.py
   ```

## Настройка кошелька продавца
- Перейдите на `/src/static_web/setup.html` или используйте `xpub_offline.html` для генерации xPub.
- Следуйте инструкциям на странице, сохраните seed-фразу, подтвердите и отправьте xPub на сервер.

## Структура БД (основное)
- sellers: telegram_id, ...
- buyer_groups: id, seller_id, buyer_id, invoices_group, xpub
- invoices: id, seller_id, buyer_group_id, ...
- wallets: id, telegram_id, buyer_group_id, invoices_group, xpub

## Безопасность
- Все операции с seed/xPub выполняются на клиенте (offline-страницы).
- Приватные ключи не передаются на сервер.

## Лицензия
MIT
