# Architecture Document - NoTocBot

**Version:** 1.0
**Status:** Approved
**Author:** Winston (Architect)

## 1. High-Level Architecture

Hệ thống sử dụng mô hình **Webhook** để hoạt động ổn định trên Render Free Tier (tránh bị sleep mode làm mất kết nối như Polling).

**Data Flow:**
User (Telegram) -> Telegram Cloud -> Webhook (JSON) -> **NoTocBot (Render)** -> PostgreSQL

* **NoTocBot App:** Python Monolith (FastAPI + python-telegram-bot).
* **Database:** PostgreSQL Cloud.

## 2. Tech Stack

* **Language:** Python 3.11+
* **Bot Framework:** `python-telegram-bot` (Async)
* **Web Server:** `FastAPI` + `uvicorn` (Để hứng Webhook)
* **ORM:** `SQLAlchemy` (Async)
* **Migration:** `Alembic`
* **NLP:** `Regular Expressions (Regex)` (Nhẹ, nhanh, chi phí thấp)

## 3. Database Schema (ERD)

### Table: `users`
Lưu thông tin người dùng Telegram (Chủ nợ).
* `id`: BigInt, PK
* `telegram_id`: BigInt, Unique, Index
* `full_name`: String
* `created_at`: Timestamp

### Table: `debtors`
Danh sách con nợ của từng User.
* `id`: BigInt, PK
* `user_id`: BigInt, FK -> users.id (Phân quyền dữ liệu)
* `name`: String (Tên hiển thị chuẩn, vd: "Khánh Duy")
* `created_at`: Timestamp

### Table: `aliases`
Các tên gọi tắt (Biệt danh).
* `id`: BigInt, PK
* `debtor_id`: BigInt, FK -> debtors.id
* `alias_name`: String (vd: "KDuy", "Béo")

### Table: `transactions`
Lịch sử giao dịch (Ghi bù trừ).
* `id`: BigInt, PK
* `debtor_id`: BigInt, FK -> debtors.id
* `amount`: Decimal (Luôn dương)
* `type`: Enum ('DEBT', 'CREDIT')
* `note`: String
* `group_id`: BigInt (Nullable - Future proof)
* `created_at`: Timestamp

## 4. Source Tree Structure

```text
src/
├── bot/
│   ├── __init__.py
│   ├── handlers.py      # Bot commands (/start, /help, /alias)
│   ├── middleware.py    # Auth middleware
│   └── nlp_engine.py    # Regex logic
├── database/
│   ├── __init__.py
│   ├── config.py        # SQLAlchemy setup
│   └── models.py        # User, Debtor, Transaction models
├── services/
│   ├── __init__.py
│   ├── debtor_service.py # Logic Fuzzy search, Alias
│   └── debt_service.py   # Logic Transaction, Balance
├── config.py            # Env vars loading
└── main.py              # Entry point (FastAPI + Webhook setup)
5. Bot Commands SpecificationCommandHandlerDescription/startstart_commandRegister User, Welcome msg/helphelp_commandShow usage instructions(Text)nlp_message_handlerParse text -> Detect Debt/Credit -> Save/aliasset_alias_commandMap alias to debtor/balanceget_balance_commandShow net balance for a debtor/historyget_history_commandShow recent transactions
6. Deployment (Render.com)
Build Command: pip install -r requirements.txt

Start Command: uvicorn src.main:app --host 0.0.0.0 --port $PORT

Env Vars: TELEGRAM_TOKEN, DATABASE_URL, WEBHOOK_URL


---