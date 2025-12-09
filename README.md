# 🤖 NoTocBot - Telegram Debt Tracking Bot

<div align="center">

![Python](https://img.shields.io/badge/Python-3.11+-3776AB?style=for-the-badge&logo=python&logoColor=white)
![Telegram](https://img.shields.io/badge/Telegram_Bot-26A5E4?style=for-the-badge&logo=telegram&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-009688?style=for-the-badge&logo=fastapi&logoColor=white)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-4169E1?style=for-the-badge&logo=postgresql&logoColor=white)
![SQLAlchemy](https://img.shields.io/badge/SQLAlchemy-D71F00?style=for-the-badge&logo=sqlalchemy&logoColor=white)

**A Vietnamese Telegram bot for personal debt tracking with natural language processing**

[Features](#-features) • [Demo](#-demo) • [Architecture](#-architecture) • [Installation](#-installation) • [Deployment](#-deployment)

</div>

---

## 📋 Overview

**NoTocBot** (Vietnamese: "Nợ Tộc Bot" - Debt Tracker Bot) is a personal finance assistant that helps users track who owes them money and manage repayments through natural Vietnamese conversations. Instead of manually maintaining spreadsheets, users can simply chat with the bot using everyday language.

### 🎯 Problem Statement

Keeping track of informal debts (coffee money, lunch splits, borrowed cash) is tedious:
- Forgetting who owes what amount
- No easy way to record transactions on-the-go
- Calculating balances manually is error-prone

### 💡 Solution

NoTocBot provides a conversational interface where users can:
- Record debts naturally: `"Tuấn nợ 50k tiền cafe"`
- Track repayments: `"Tuấn trả 20k"`
- View balances and history with simple commands

---

## ✨ Features

### 🗣️ Natural Language Processing (Vietnamese)

The bot understands Vietnamese debt phrases using regex-based NLP:

```
📝 Recording Debt:
   "Tuấn nợ 50k tiền cafe"      → Records 50,000đ debt from Tuấn
   "Lan vay 100000"             → Records 100,000đ debt from Lan
   
💰 Recording Payment:
   "Tuấn trả 20k"               → Records 20,000đ repayment from Tuấn
   "Minh đưa 30000"             → Records 30,000đ repayment from Minh

❓ Balance Inquiry:
   "Tuấn nợ bao nhiêu?"         → Shows Tuấn's current balance
   "xem nợ Lan"                 → Shows Lan's current balance
   "tổng nợ"                    → Shows summary of all debtors
```

### 🔍 Fuzzy Name Matching

Using `thefuzz` library (Levenshtein distance), the bot handles:
- Typos: "Tuan" matches "Tuấn"
- Partial names: "Duy" matches "Khánh Duy"
- Similar spellings: "Béo" alias for "Tuấn"

When multiple matches are found, interactive buttons let users select the correct person.

### 📱 Commands

| Command | Description |
|---------|-------------|
| `/start` | Register and get welcome message |
| `/help` | Show usage instructions |
| `/add [name] [amount] [note]` | Record a debt |
| `/paid [name] [amount]` | Record a repayment |
| `/balance [name]` | Check individual balance |
| `/summary` | View all debtors with balances |
| `/history [name]` | View transaction history |
| `/alias [nick] = [name]` | Create nickname alias |
| `/link [name] [@user]` | Link debtor to Telegram account |
| `/xoagiaodich [ID]` | Delete a single transaction |
| `/xoano [name]` | Delete all data for a person |
| `/xoatatca` | Delete ALL debt data |

### 🔔 Real-time Notifications

When a debtor is linked to their Telegram account via `/link`, they receive automatic notifications when:
- A new debt is recorded against them
- A payment is logged

### 🏷️ Alias System

Create nicknames for frequently mentioned debtors:
```
/alias Béo = Tuấn
```
Now `"Béo nợ 50k"` automatically records under Tuấn.

---

## 🎬 Demo

### Recording a Debt (Natural Language)
```
User: Tuấn nợ 50k tiền cafe
Bot:  ✅ Đã ghi: Tuấn nợ thêm 50,000đ (tiền cafe)
      📊 Tổng dư nợ: 50,000đ
```

### Fuzzy Name Matching
```
User: /add Tuan 30k
Bot:  🔍 Tôi tìm thấy những tên gần giống:
      [1. Tuấn (95%)]
      [2. Tuấn Anh (80%)]
      [➕ Tạo mới "Tuan"]
```

### Balance Summary
```
User: /summary
Bot:  📊 Tổng kết nợ của bạn:
      
      1. Tuấn: 150,000đ
      2. Lan: 75,000đ
      3. Minh: 30,000đ
      
      💰 Tổng: 255,000đ (3 người)
```

---

## 🏗️ Architecture

```
NoTocBot/
├── src/
│   ├── main.py                 # Entry point (Polling/Webhook modes)
│   ├── config.py               # Environment configuration
│   ├── bot/
│   │   ├── handlers/
│   │   │   ├── commands.py     # /command handlers
│   │   │   ├── callbacks.py    # Inline button handlers
│   │   │   ├── nlp_handlers.py # Natural language processing
│   │   │   └── shared.py       # Shared utilities
│   │   └── nlp_engine.py       # Regex-based NLP engine
│   ├── database/
│   │   ├── config.py           # Async SQLAlchemy setup
│   │   └── models.py           # ORM models
│   ├── services/
│   │   ├── debt_service.py     # Transaction business logic
│   │   ├── debtor_service.py   # Debtor management
│   │   └── user_service.py     # User management
│   ├── security/
│   │   ├── webhook_auth.py     # Telegram webhook verification
│   │   └── rate_limiter.py     # Token bucket rate limiting
│   └── utils/
│       └── formatters.py       # Currency formatting
├── migrations/                  # Alembic migrations
├── tests/                       # pytest-asyncio tests
├── requirements.txt
├── Dockerfile
└── render.yaml                  # Render deployment config
```

### Data Flow

```mermaid
sequenceDiagram
    participant U as User
    participant T as Telegram
    participant B as NoTocBot
    participant DB as PostgreSQL
    
    U->>T: "Tuấn nợ 50k cafe"
    T->>B: Webhook/Polling
    B->>B: NLP Parse Message
    B->>B: Fuzzy Match "Tuấn"
    B->>DB: INSERT Transaction
    DB-->>B: Success
    B->>T: "✅ Đã ghi: Tuấn nợ 50,000đ"
    T-->>U: Reply Message
```

### Database Schema

```mermaid
erDiagram
    User ||--o{ Debtor : owns
    Debtor ||--o{ Transaction : has
    Debtor ||--o{ Alias : has
    
    User {
        bigint id PK
        bigint telegram_id UK
        varchar username
        varchar full_name
        datetime created_at
    }
    
    Debtor {
        bigint id PK
        bigint user_id FK
        varchar name
        bigint telegram_id
        datetime created_at
    }
    
    Transaction {
        bigint id PK
        bigint debtor_id FK
        decimal amount
        enum type
        varchar note
        datetime created_at
    }
    
    Alias {
        bigint id PK
        bigint debtor_id FK
        varchar alias_name
    }
```

---

## 🛠️ Technical Highlights

### Async Everything
- **Async SQLAlchemy 2.0** with `asyncpg`/`aiosqlite` drivers
- **python-telegram-bot v21+** async API
- **FastAPI** with async lifespan management

### Dual-Mode Operation
```python
# Automatically selects mode based on environment
if WEBHOOK_URL:
    # Production: FastAPI + Uvicorn webhook server
    uvicorn.run(app, host=HOST, port=PORT)
else:
    # Development: Long polling mode
    asyncio.run(run_polling())
```

### Security Features
- **Webhook Secret Token**: Validates incoming Telegram requests
- **Token Bucket Rate Limiting**: 60 requests per user per minute
- **User Data Isolation**: All queries filtered by `user_id`
- **Ownership Verification**: Delete operations verify ownership

### NLP Engine
Custom regex-based parser for Vietnamese phrases:
```python
# Debt patterns: "Tuấn nợ 50k tiền cafe"
DEBT_PATTERN = re.compile(
    r"^(?P<name>\S+(?:\s+\S+){0,3})\s+(?:nợ|vay|muộn)\s+"
    r"(?P<amount>\d+(?:[.,]\d+)?k?)(?:\s+(?P<note>.*))?$",
    re.IGNORECASE | re.UNICODE
)
```

### Fuzzy Matching
```python
from thefuzz import fuzz, process

# Find best matches with confidence scores
candidates = process.extract(
    query, 
    debtor_names, 
    scorer=fuzz.WRatio,
    limit=5
)
# Returns: [("Tuấn", 95), ("Tuấn Anh", 80), ...]
```

---

## 🚀 Installation

### Prerequisites
- Python 3.11+
- Telegram Bot Token (from [@BotFather](https://t.me/BotFather))
- PostgreSQL (production) or SQLite (local)

### Local Development

```bash
# Clone repository
git clone https://github.com/hoangduy0308/notocbot.git
cd notocbot

# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # Linux/Mac
.venv\Scripts\activate     # Windows

# Install dependencies
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Edit .env with your TELEGRAM_TOKEN

# Run migrations
alembic upgrade head

# Start bot (polling mode)
python -m src.main
```

### Environment Variables

```env
# Required
TELEGRAM_TOKEN=your_bot_token_here

# Database (optional, defaults to SQLite)
DATABASE_URL=postgresql+asyncpg://user:pass@localhost/notocbot

# Production (webhook mode)
WEBHOOK_URL=https://your-app.onrender.com
WEBHOOK_SECRET_TOKEN=your_secret_token

# Rate limiting (optional)
RATE_LIMIT_MAX_TOKENS=60
RATE_LIMIT_REFILL_SECONDS=60
```

---

## 🌐 Deployment

### Render.com (Recommended)

The project includes `render.yaml` for one-click deployment:

```yaml
services:
  - type: web
    name: notocbot
    runtime: docker
    plan: free
    envVars:
      - key: TELEGRAM_TOKEN
        sync: false
      - key: WEBHOOK_URL
        sync: false
      - key: DATABASE_URL
        fromDatabase:
          name: notocbot-db
          property: connectionString
```

**Steps:**
1. Fork this repository
2. Connect to Render.com
3. Create a new "Blueprint" from `render.yaml`
4. Set environment variables
5. Deploy!

### Docker

```bash
docker build -t notocbot .
docker run -e TELEGRAM_TOKEN=xxx -e DATABASE_URL=xxx notocbot
```

---

## 🧪 Testing

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=src

# Run specific test file
pytest tests/test_nlp_engine.py -v
```

### Test Structure
```
tests/
├── test_nlp_engine.py      # NLP parsing tests
├── test_rate_limiter.py    # Rate limiting tests
├── test_webhook_auth.py    # Security tests
└── test_delete_service.py  # Delete operation tests
```

---

## 📈 Future Roadmap

- [ ] Group chat support (multi-user debt splitting)
- [ ] Monthly summary reports
- [ ] Export to CSV/PDF
- [ ] Payment reminders
- [ ] Multi-currency support
- [ ] Web dashboard

---

## 🧑‍💻 Author

**Hoang Duy**

- GitHub: [@hoangduy0308](https://github.com/hoangduy0308)

---

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

---

<div align="center">

**Built with ❤️ for the Vietnamese community**

</div>
