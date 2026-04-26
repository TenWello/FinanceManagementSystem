# 💰 Business Finance Manager

> O'zbekistondagi kichik va o'rta bizneslar uchun moliyaviy boshqaruv tizimi.
> Telegram bot + Web dashboard.

---

## 🚀 Tezkor ishga tushirish (5 daqiqa)

### Talablar
- Python 3.10+
- Node.js 18+
- Telegram bot tokeni (@BotFather dan oling)

---

## 1️⃣ Backend va Bot sozlash

```bash
# Reponi clone qiling
git clone https://github.com/YOUR_USERNAME/finance-bot.git
cd finance-bot

# Virtual muhit yarating
python -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate

# Kutubxonalarni o'rnating
pip install -r requirements.txt

# .env faylini yarating
cp .env.example .env
# .env faylini oching va BOT_TOKEN ni kiriting
```

**`.env` faylini tahrirlang:**
```env
BOT_TOKEN=7123456789:AAHxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
API_URL=http://localhost:8000
DB_PATH=finance.db
```

### Backend ishga tushirish (Terminal 1)
```bash
cd backend
uvicorn main:app --reload --port 8000
```

API tayyor: http://localhost:8000/docs

### Bot ishga tushirish (Terminal 2)
```bash
cd bot
python bot.py
```

---

## 2️⃣ Frontend (Web Dashboard) sozlash

```bash
cd frontend

# Dependencylarni o'rnating
npm install

# Development server
npm run dev
```

Dashboard: http://localhost:3000

---

## 🤖 Bot testlash

Telegram da botingizni toping va quyidagilarni yuboring:

```
Sotuv 500 000 so'm tushdi
```
```
Ijara uchun 2 000 000 to'ladik
```
```
Bu oylik hisobot
```
```
Bugungi balans qancha?
```

**Ovozli xabar:** Yuqoridagilarni ovozda ham yuboring! 🎙

---

## 📁 Project tuzilmasi

```
finance-bot/
├── backend/
│   └── main.py          # FastAPI backend, SQLite DB
├── bot/
│   └── bot.py           # Telegram bot
├── frontend/
│   ├── src/
│   │   ├── App.jsx       # Router + Sidebar
│   │   ├── pages/
│   │   │   ├── Overview.jsx      # Bosh sahifa
│   │   │   ├── Transactions.jsx  # Tranzaksiyalar
│   │   │   ├── Analytics.jsx     # Tahlil
│   │   │   └── Categories.jsx    # Kategoriyalar
│   ├── package.json
│   └── vite.config.js
├── requirements.txt
└── README.md
```

---

## 🌐 Deploy (Production)

### Backend → Railway
```bash
# railway.toml
[build]
command = "pip install -r requirements.txt"

[deploy]
command = "uvicorn backend.main:app --host 0.0.0.0 --port $PORT"
```

### Frontend → Vercel
```bash
cd frontend
npm run build
# vercel.json ga upload qiling
```

**Frontend `.env.production`:**
```env
VITE_API_URL=https://your-railway-app.up.railway.app
```

### Bot → Railway (yoki VPS)
```bash
# Alohida service sifatida
python bot/bot.py
```

---

## 💡 Bot imkoniyatlari

| Buyruq | Natija |
|--------|--------|
| `500 000 tushdi` | Kirim qo'shadi (kategoria so'raydi) |
| `Ijara 2 mln to'ladik` | Chiqim qayd etadi |
| `Bu oylik hisobot` | Daromad/xarajat ko'rsatadi |
| `Oxirgi tranzaksiyalar` | So'nggi 5 tasini ko'rsatadi |
| `/ochir_42` | ID=42 tranzaksiyani o'chiradi |
| `/balans` | Joriy oy balansi |
| `/hisobot` | Oylik to'liq hisobot |
| Ovozli xabar 🎙 | Avtomatik transkriptsiya |

---

## 📊 API Endpoints

| Method | URL | Tavsif |
|--------|-----|--------|
| GET | `/transactions` | Tranzaksiyalar ro'yxati (filter bilan) |
| POST | `/transactions` | Yangi tranzaksiya |
| PUT | `/transactions/{id}` | Tahrirlash |
| DELETE | `/transactions/{id}` | O'chirish |
| GET | `/report?period=month` | Hisobot (today/week/month/year) |
| GET | `/analytics` | Tahlil ma'lumotlari |
| GET | `/categories` | Kategoriyalar |
| POST | `/categories` | Yangi kategoriya |

---

## 🎬 Demo oqimi

1. Bot ga ovozli xabar yuboring: *"Bugün mijozdan ikki million so'm tushdi"*
2. Bot avtomatik transkript qiladi va kirim sifatida saqlaydi
3. Dashboard da (localhost:3000) real vaqtda ko'rinadi
4. Analytics sahifasida kategoriya bo'yicha tahlil ko'rish mumkin

---

## 📝 Mahsulot qisqacha

**Kim uchun:** O'zbekistondagi kichik va o'rta bizneslar (do'konlar, xizmat ko'rsatuvchi kompaniyalar)

**Qanday muammo hal qiladi:** WhatsApp, daftar va Excel o'rniga — bitta qulay joy: Telegram orqali tranzaksiya, dashboard orqali tahlil.

**V2 nima bo'ladi:** Ko'p foydalanuvchi (ruxsat tizimi), bank API integratsiyasi, avtomatik oylik hisobot PDF, byudjet rejalashtirish.

**3 kun yana bo'lsa nima qo'shardim:**
Bank API (Kapital Bank, Uzcard) integratsiyasi — tranzaksiyalar avtomatik import bo'lsa, qo'lda kiritish zaruriyati yo'qoladi. Shuningdek, AI orqali oylik xarajat bashorati va "bu kategoriya o'tgan oyga nisbatan 30% oshdi" kabi smart alertlar qo'shardim.

---

*Built with ❤️ for data365 agency assessment*
