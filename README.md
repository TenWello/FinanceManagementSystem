# 💰 Business Finance Manager

> O'zbekistondagi kichik va o'rta bizneslar uchun moliyaviy boshqaruv tizimi.
> Telegram bot orqali ovoz va matn bilan tranzaksiya kiritish, web dashboard orqali tahlil va boshqaruv.

🔗 **Live Demo:** https://financemanagementsystem-production.up.railway.app
🤖 **Telegram Bot:** @your_bot_username

---

## 🌟 Imkoniyatlar

### 🤖 Telegram Bot
| Funksiya | Tavsif |
|----------|--------|
| 💰 Kirim / 💸 Chiqim | Matn va ovoz orqali (RU/EN/UZ) |
| 📊 Hisobotlar | Bugun / hafta / oy / yil — kategoriya va foiz bilan |
| ✏️ Tahrirlash | So'nggi 10 ta tranzaksiyani tahrirlash |
| 🗑 O'chirish | Sana yoki ID bo'yicha |
| 📤 Export | CSV fayl (Excel da ochiladi) |
| 📥 Import | CSV fayl — ustiga yoki o'rniga |
| 🔒 Kirish nazorati | Rol asosida — faqat ruxsat berilganlar |

### 🌐 Web Dashboard
| Sahifa | Tavsif |
|--------|--------|
| 🏠 Bosh sahifa | Statistika, grafik, tez qo'shish |
| ↕️ Tranzaksiyalar | Filter, qidirish, tahrirlash, kim qo'shgani |
| 📈 Tahlil | Oylik grafik, kategoriya taqsimoti |
| 🏷️ Kategoriyalar | Qo'shish, o'chirish, rang tanlash |
| 👑 Admin panel | Faqat super admin — adminlar boshqaruvi |

---

## 👥 Rol tizimi

| Rol | Kirim/Chiqim | Hisobot | O'chirish/Import | Admin panel |
|-----|:---:|:---:|:---:|:---:|
| 👑 Super Admin | ✅ | ✅ | ✅ | ✅ |
| 3️⃣ To'liq (full) | ✅ | ✅ | ✅ | ❌ |
| 2️⃣ Hisobot (report_only) | ❌ | ✅ | ❌ | ❌ |
| 1️⃣ Kirim/Chiqim (tx_only) | ✅ | ❌ | ❌ | ❌ |

---

## 🚀 O'rnatish

### Talablar
- Python 3.10+
- Telegram bot tokeni ([@BotFather](https://t.me/BotFather))
- Telegram ID ([@userinfobot](https://t.me/userinfobot))

### 1. Loyihani yuklab olish
```bash
git clone https://github.com/TenWello/FinanceManagementSystem.git
cd FinanceManagementSystem
```

### 2. Virtual muhit va paketlar
```bash
python -m venv .venv

# Windows
.venv\Scripts\Activate.ps1

# Linux/Mac
source .venv/bin/activate

pip install -r requirements.txt
```

### 3. .env fayli
```bash
cp .env.example .env
```

`.env` faylini tahrirlang:
```env
BOT_TOKEN=your_telegram_bot_token
API_URL=http://localhost:8000
DB_PATH=finance.db
SUPER_ADMIN_ID=your_telegram_id
JWT_SECRET=kamida-32-belgili-maxfiy-kalit
SUPER_WEB_PASSWORD=your_password
```

### 4. Ishga tushirish

**Terminal 1 — Backend:**
```bash
cd backend
uvicorn main:app --reload --port 8000
```

**Terminal 2 — Bot:**
```bash
cd bot
python bot.py
```

**Dashboard:** http://localhost:8000

---

## 🌐 Deploy (Railway.app)

### Backend
1. [railway.app](https://railway.app) → **New Project** → **GitHub** → repo
2. Root Directory: `backend`
3. Start Command: `uvicorn main:app --host 0.0.0.0 --port $PORT`
4. **Variables** qo'shing:
```
SUPER_ADMIN_ID      = your_telegram_id
JWT_SECRET          = random_32_char_string
SUPER_WEB_PASSWORD  = your_password
DB_PATH             = /data/finance.db
```
5. **Volume** qo'shing: Mount Path `/data`

### Bot
1. Yangi Railway service → Root Directory: `bot`
2. Start Command: `pip install -r requirements.txt && python bot.py`
3. **Variables:**
```
BOT_TOKEN      = your_bot_token
API_URL        = https://your-backend.up.railway.app
SUPER_ADMIN_ID = your_telegram_id
```

---

## 🤖 Bot — foydalanish

### Matn orqali
```
500 000 tushdi          → 💰 Kirim: 500,000
Ijara 2 mln to'ladik    → 💸 Chiqim: 2,000,000
50000 received today    → 💰 Kirim: 50,000
20 тысяч расход         → 💸 Chiqim: 20,000
oylik hisobot           → 📊 Hisobot
```

### Admin qo'shish
1. Bot: `⚙️ Admin panel` → `👥 Adminlar boshqaruvi` → `➕ Yangi admin`
2. Telegram ID kiriting → Rol tanlang
3. Web uchun parol: Dashboard → Adminlar → 🔑

### Web login
- **Super admin:** username = `superadmin`, parol = `.env` dagi `SUPER_WEB_PASSWORD`
- **Boshqa adminlar:** username = Telegram ID, parol = super admin bergan parol

---

## 📁 Loyiha tuzilmasi

```
FinanceManagementSystem/
├── backend/
│   ├── main.py           # FastAPI — barcha API endpointlar + auth
│   ├── dashboard.html    # Web dashboard (SPA, npm kerak emas)
│   ├── setup.py          # DB initialization script
│   └── requirements.txt
├── bot/
│   ├── bot.py            # Telegram bot (python-telegram-bot)
│   └── requirements.txt
├── requirements.txt      # Umumiy paketlar
├── nixpacks.toml         # Railway build config
├── Procfile
├── render.yaml           # Render.com deploy config
├── .env.example
└── README.md
```

---

## 🛠 Texnologiyalar

| Qism | Texnologiya |
|------|-------------|
| Bot | Python, python-telegram-bot 21.3 |
| Backend | FastAPI, SQLite, uvicorn |
| Frontend | Vanilla JS, Tailwind CSS CDN, Chart.js |
| Auth | JWT (HMAC-SHA256, 7 kun) |
| Deploy | Railway.app |
| DB | SQLite + Volume (persistent) |

---

## 📝 Mahsulot haqida

**Kim uchun:** O'zbekistondagi kichik va o'rta bizneslar — savdo do'konlari, xizmat ko'rsatuvchi kompaniyalar, restoran va kafeler.

**Qanday muammo hal qiladi:** Kompaniya moliyasi WhatsApp, daftar va Excel orqali boshqariladi. Bir joyda ko'rish, tahlil qilish, jamoaviy boshqarish imkoni yo'q. Ushbu yechim Telegram bot orqali tez kiritish + web dashboard orqali to'liq nazoratni ta'minlaydi.

**V2 rejasi:** Bank API integratsiyasi (Kapital Bank, Uzcard), byudjet rejalashtirish, avtomatik oylik PDF hisobot, AI asosida xarajat bashorati va anomaliyalarni aniqlash.

---

*Built for data365 agency assessment · 2025*
