import os, re, io, csv, logging
from datetime import datetime, date
from pathlib import Path
from telegram import (Update, InlineKeyboardButton, InlineKeyboardMarkup,
                      ReplyKeyboardMarkup, KeyboardButton)
from telegram.ext import (Application, CommandHandler, MessageHandler,
                           CallbackQueryHandler, filters, ContextTypes, ConversationHandler)
import httpx
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

BOT_TOKEN      = os.getenv("BOT_TOKEN")
API_URL        = os.getenv("API_URL", "http://localhost:8000")
SUPER_ADMIN_ID = int(os.getenv("SUPER_ADMIN_ID", "0"))

logging.basicConfig(format="%(asctime)s %(levelname)s %(message)s", level=logging.INFO)
log = logging.getLogger(__name__)

# ─── States ───────────────────────────────────────────────────────────────────
(ST_MENU, ST_AMOUNT, ST_CATEGORY, ST_CUSTOM_CAT, ST_NOTE, ST_CONFIRM,
 ST_DEL_MAIN, ST_DEL_DATE_INPUT, ST_DEL_PICK_ID,
 ST_IMPORT_FILE, ST_IMPORT_CONFIRM,
 ST_EDIT_CAT_NAME, ST_ADD_ADMIN_ROLE,
 ST_EDIT_TX_AMOUNT, ST_EDIT_TX_CATEGORY, ST_EDIT_TX_NOTE) = range(16)

# ─── Roles ────────────────────────────────────────────────────────────────────
# tx_only     → faqat kirim/chiqim qo'shish va ko'rish
# report_only → faqat hisobotlarni ko'rish
# full        → hamma narsa
ROLE_LABELS = {
    "tx_only":     "1️⃣ Kirim/Chiqim",
    "report_only": "2️⃣ Hisobot",
    "full":        "3️⃣ To'liq",
}

def can_add_tx(r):   return r in ("tx_only","full","super_admin")
def can_view(r):     return r in ("tx_only","report_only","full","super_admin")
def can_report(r):   return r in ("report_only","full","super_admin")
def can_manage(r):   return r in ("full","super_admin")
def is_super(r):     return r == "super_admin"

# ─── Helpers ──────────────────────────────────────────────────────────────────
def fmt(n): return f"{n:,.0f} so'm".replace(",", " ")

def extract_amount(text: str):
    """Raqam yoki so'z ko'rinishidagi summani ajratadi (uz/ru/en)"""
    # 1. Raqam + ko'paytiruvchi (har qanday tilda)
    MULTIPLIERS = [
        # O'zbek
        (r"(\d+[\d.\s]*)\s*mlrd",            1_000_000_000),
        (r"(\d+[\d.\s]*)\s*(?:mln|million)",  1_000_000),
        (r"(\d+[\d.\s]*)\s*(?:ming|min\b)",  1_000),
        (r"(\d+[\d.\s]*)\s*k\b",             1_000),
        # Rus
        (r"(\d+[\d.\s]*)\s*(?:млрд)",              1_000_000_000),
        (r"(\d+[\d.\s]*)\s*(?:млн\.?|миллион)",   1_000_000),
        (r"(\d+[\d.\s]*)\s*(?:тысяч[аи]?|тыс\.?)",1_000),
        # English
        (r"(\d+[\d.\s]*)\s*(?:billion)",      1_000_000_000),
        (r"(\d+[\d.\s]*)\s*(?:million)",      1_000_000),
        (r"(\d+[\d.\s]*)\s*(?:thousand)",     1_000),
        (r"(\d+[\d.\s]*)\s*(?:hundred)",      100),
        # Sof raqam (oxirida)
        (r"(\d[\d\s]*\d|\d)",                1),
    ]
    for pat, mult in MULTIPLIERS:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            try:
                raw = m.group(1).replace(" ","").replace(",",".")
                v = float(raw) * mult
                if v > 0: return v
            except: pass

    # 2. So'z ko'rinishi: "dvadsat tysyach", "twenty thousand" va h.k.
    v = parse_word_number(text)
    if v: return v

    return parse_uz_number_words(text)

def parse_word_number(text: str):
    """Rus va ingliz raqam so'zlari"""
    RU = {
        "odin":1,"dva":2,"tri":3,"chetyre":4,"pyat":5,
        "shest":6,"sem":7,"vosem":8,"devyat":9,"desyat":10,
        "odinnadtsat":11,"dvenadtsat":12,"trinadtsat":13,
        "dvadtsat":20,"tridtsat":30,"sorok":40,"pyatdesyat":50,
        "shestdesyat":60,"semdesyat":70,"vosemdesyat":80,"devyanosto":90,
        "sto":100,"dvesti":200,"trista":300,"chetyresta":400,
        "pyatset":500,"shestset":600,"semset":700,"vosemset":800,
        "devyatset":900,
        "tysyacha":1000,"tysyach":1000,"tysyachi":1000,
        "million":1_000_000,"milliona":1_000_000,
    }
    EN = {
        "one":1,"two":2,"three":3,"four":4,"five":5,
        "six":6,"seven":7,"eight":8,"nine":9,"ten":10,
        "eleven":11,"twelve":12,"thirteen":13,"fourteen":14,"fifteen":15,
        "sixteen":16,"seventeen":17,"eighteen":18,"nineteen":19,
        "twenty":20,"thirty":30,"forty":40,"fifty":50,
        "sixty":60,"seventy":70,"eighty":80,"ninety":90,
        "hundred":100,"thousand":1000,"million":1_000_000,"billion":1_000_000_000,
    }
    words = re.sub(r"[^a-zA-Z]", " ", text.lower()).split()
    if not words: return None

    # Try RU then EN
    for VOCAB in (RU, EN):
        total = 0; current = 0
        matched = False
        for w in words:
            val = VOCAB.get(w)
            if val is None: continue
            matched = True
            if val >= 1_000_000:
                if current == 0: current = 1
                total += current * val; current = 0
            elif val >= 1000:
                if current == 0: current = 1
                total += current * val; current = 0
            elif val == 100:
                if current == 0: current = 1
                current *= 100
            else:
                current += val
        total += current
        if matched and total > 0:
            return total
    return None

# ─── API ──────────────────────────────────────────────────────────────────────
async def api(method, path, **kw):
    try:
        async with httpx.AsyncClient() as c:
            r = await getattr(c, method)(f"{API_URL}{path}", timeout=20, **kw)
            r.raise_for_status()
            return r.json()
    except httpx.ConnectError:
        log.error(f"CONNECT ERROR: {API_URL}{path}")
        raise Exception(f"Backend bilan ulanib bo'lmadi: {API_URL}")
    except httpx.TimeoutException:
        log.error(f"TIMEOUT: {API_URL}{path}")
        raise Exception("Server javob bermadi (timeout)")
    except Exception as e:
        log.error(f"API ERROR {method.upper()} {path}: {e}")
        raise

async def get_cats(tx_type):
    try:
        all_cats = await api("get", "/categories")
        return [c["name"] for c in all_cats if c["type"] in (tx_type,"both")]
    except:
        return ["sotuv","xizmat"] if tx_type=="income" else ["maosh","ijara","boshqa"]

# ─── Access control ───────────────────────────────────────────────────────────
async def get_role(uid: int) -> str:
    """Returns role string. Empty string = not allowed."""
    if uid == SUPER_ADMIN_ID:
        return "super_admin"
    try:
        r = await api("get", f"/users/{uid}/check")
        if r.get("open_mode"):   return ""   # open_mode OFF — ruxsat yo'q
        if r.get("allowed"):     return r.get("role","tx_only")
        return ""
    except:
        return ""

async def guard(update: Update):
    """Returns role or sends denied message and returns ''"""
    uid = update.effective_user.id
    role = await get_role(uid)
    if not role:
        txt = (f"🔒 *Kirish taqiqlangan.*\n\n"
               f"Botga kirish uchun super admin bilan bog'laning.\n"
               f"Sizning ID: `{uid}`")
        if update.message:
            await update.message.reply_text(txt, parse_mode="Markdown")
        elif update.callback_query:
            await update.callback_query.answer("🔒 Kirish taqiqlangan!", show_alert=True)
    return role

# ─── Keyboards ────────────────────────────────────────────────────────────────
def bottom_kb(role=""):
    rows = [[KeyboardButton("🏠 Bosh menyu"), KeyboardButton("👤 Profil")]]
    if can_manage(role) or is_super(role):
        rows.append([KeyboardButton("⚙️ Admin panel")])
    return ReplyKeyboardMarkup(rows, resize_keyboard=True)

def main_menu_ikb(role=""):
    rows = []
    if can_add_tx(role):
        rows.append([InlineKeyboardButton("💰 Kirim", callback_data="add_income"),
                     InlineKeyboardButton("💸 Chiqim", callback_data="add_expense")])
    if can_view(role):
        rows.append([InlineKeyboardButton("📋 Oxirgi 5 ta", callback_data="list_last"),
                     InlineKeyboardButton("💼 Balans",       callback_data="balance")])
    if can_add_tx(role):
        rows.append([InlineKeyboardButton("✏️ So'nggi 10 ni tahrirlash", callback_data="edit_last10")])
    if can_report(role):
        rows.append([InlineKeyboardButton("📊 Bugun", callback_data="report_today"),
                     InlineKeyboardButton("📈 Bu oy",  callback_data="report_month")])
        rows.append([InlineKeyboardButton("📅 Hafta",  callback_data="report_week"),
                     InlineKeyboardButton("📆 Yil",    callback_data="report_year")])
    if can_manage(role):
        rows.append([InlineKeyboardButton("🗑 O'chirish",           callback_data="del_main"),
                     InlineKeyboardButton("✏️ Kategoriyalar",        callback_data="edit_cats")])
        rows.append([InlineKeyboardButton("📤 Export", callback_data="export_menu"),
                     InlineKeyboardButton("📥 Import", callback_data="import_start")])
    if is_super(role):
        rows.append([InlineKeyboardButton("👥 Adminlar boshqaruvi", callback_data="super_users")])
    return InlineKeyboardMarkup(rows)

def back_ikb(role=""):
    return InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Bosh menyu", callback_data="main_menu")]])

async def cat_ikb(tx_type):
    cats = await get_cats(tx_type)
    rows = []
    row = []
    for c in cats:
        row.append(InlineKeyboardButton(c.capitalize(), callback_data=f"cat_{c}"))
        if len(row)==2: rows.append(row); row=[]
    if row: rows.append(row)
    rows.append([InlineKeyboardButton("✏️ O'zim yozaman", callback_data="cat_custom")])
    rows.append([InlineKeyboardButton("❌ Bekor", callback_data="cancel")])
    return InlineKeyboardMarkup(rows)

def confirm_ikb():
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ Saqlash", callback_data="confirm_yes"),
        InlineKeyboardButton("❌ Bekor",   callback_data="confirm_no"),
    ]])

def export_ikb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📊 Bugun", callback_data="export_today"),
         InlineKeyboardButton("📅 Hafta", callback_data="export_week")],
        [InlineKeyboardButton("📈 Bu oy", callback_data="export_month"),
         InlineKeyboardButton("📆 Bu yil",callback_data="export_year")],
        [InlineKeyboardButton("🏠 Orqaga",callback_data="main_menu")],
    ])

def import_conflict_ikb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ Ustiga qo'shish",             callback_data="import_append")],
        [InlineKeyboardButton("🔄 O'rniga qo'yish (o'chiradi)", callback_data="import_replace")],
        [InlineKeyboardButton("❌ Bekor",                        callback_data="cancel")],
    ])

# ─── Report formatter ─────────────────────────────────────────────────────────
def fmt_report(rep, period):
    names = {"today":"Bugun","week":"Bu hafta","month":"Bu oy","year":"Bu yil"}
    inc,exp,net = rep.get("income",0), rep.get("expense",0), rep.get("net",0)
    lines = [
        f"📊 *{names.get(period,'Hisobot')}*\n",
        f"💰 Kirim:  *{fmt(inc)}*",
        f"💸 Chiqim: *{fmt(exp)}*",
        "─"*22,
        f"{'📈' if net>=0 else '📉'} Balans: *{fmt(net)}*",
    ]
    for label,key in [("💰 Kirim","income_categories"),("💸 Chiqim","expense_categories")]:
        cats = rep.get(key,[])
        if cats:
            lines.append(f"\n{label} *kategoriyalar:*")
            for c in cats:
                filled = int(c['pct']/10); empty = 10-filled
                lines.append(f"  • {c['name']}: *{fmt(c['amount'])}* ({c['pct']}%)")
                lines.append(f"  `{'█'*filled}{'░'*empty}`")
    return "\n".join(lines)

# ─── /start ───────────────────────────────────────────────────────────────────
async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    role = await guard(update)
    if not role: return ConversationHandler.END
    ctx.user_data.clear()
    ctx.user_data["role"] = role
    uid  = update.effective_user.id
    user = update.effective_user
    name = user.first_name or "Do'st"
    full = f"{user.first_name or ''} {user.last_name or ''}".strip()
    uname = user.username or ""
    # Update name info in DB (except super admin — hardcoded)
    if role != "super_admin":
        try:
            await api("patch", f"/users/{uid}/name", json={"username":uname,"full_name":full})
        except: pass
    ctx.user_data["full_name"] = full
    await update.message.reply_text(f"👋 *Salom, {name}!*", parse_mode="Markdown",
                                    reply_markup=bottom_kb(role))
    await update.message.reply_text("Amalni tanlang:", reply_markup=main_menu_ikb(role))
    return ST_MENU

# ─── Role cache helper ────────────────────────────────────────────────────────
async def get_ctx_role(update, ctx):
    role = ctx.user_data.get("role")
    if not role:
        role = await get_role(update.effective_user.id)
        ctx.user_data["role"] = role
    return role

# ─── Profile ──────────────────────────────────────────────────────────────────
async def show_profile(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    role = await guard(update)
    if not role: return
    uid  = update.effective_user.id
    user = update.effective_user
    name = f"{user.first_name or ''} {user.last_name or ''}".strip()
    role_map = {
        "super_admin": "👑 Super Admin",
        "full":        "3️⃣ To'liq admin",
        "report_only": "2️⃣ Hisobot admin",
        "tx_only":     "1️⃣ Kirim/Chiqim admin",
    }
    role_txt = role_map.get(role,"👤 Foydalanuvchi")
    try:
        txs = await api("get", f"/transactions?added_by_id={uid}&limit=1000")
        inc = sum(t["amount"] for t in txs if t["type"]=="income")
        exp = sum(t["amount"] for t in txs if t["type"]=="expense")
        stats = f"\n\n📥 Qo'shgan: *{len(txs)}* ta\n💰 Kirim: *{fmt(inc)}*\n💸 Chiqim: *{fmt(exp)}*"
    except: stats = ""

    text = f"👤 *Profil*\n\nIsm: *{name}*\nID: `{uid}`\nRol: {role_txt}{stats}"

    if is_super(role):
        try:
            all_stats = await api("get", "/admin/stats")
            if all_stats:
                text += "\n\n👑 *Barcha adminlar statistikasi:*"
                for s in all_stats:
                    text += (f"\n\n👤 {s['added_by_name']} (`{s['added_by_id']}`)"
                             f"\n  📋 {s['tx_count']} ta | 💰 {fmt(s['income'])} | 💸 {fmt(s['expense'])}"
                             f"\n  📅 Oxirgi: {s['last_date']}")
        except: pass

    kb = back_ikb(role)
    if update.message:
        await update.message.reply_text(text, parse_mode="Markdown", reply_markup=kb)
    elif update.callback_query:
        await update.callback_query.edit_message_text(text, parse_mode="Markdown", reply_markup=kb)

# ─── Main button handler ──────────────────────────────────────────────────────
async def btn(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    role = await guard(update)
    if not role: return ConversationHandler.END
    ctx.user_data["role"] = role
    q = update.callback_query
    await q.answer()
    d = q.data
    uid = update.effective_user.id

    # ── Bosh menyu ──
    if d == "main_menu":
        ctx.user_data.clear(); ctx.user_data["role"] = role
        await q.edit_message_text("Amalni tanlang:", reply_markup=main_menu_ikb(role))
        return ST_MENU

    # ── Kirim/Chiqim ──
    if d in ("add_income","add_expense"):
        if not can_add_tx(role):
            await q.answer("❌ Ruxsat yo'q!", show_alert=True); return ST_MENU
        ctx.user_data["tx_type"] = "income" if d=="add_income" else "expense"
        label = "💰 Kirim" if ctx.user_data["tx_type"]=="income" else "💸 Chiqim"

        # Agar summa allaqachon saqlangan bo'lsa (voice/text orqali) — kategoriyaga o'tamiz
        stored = ctx.user_data.get("amount")
        if stored:
            await q.edit_message_text(
                f"{label}: *{fmt(stored)}*\n\n📂 Kategoriyani tanlang:",
                parse_mode="Markdown",
                reply_markup=await cat_ikb(ctx.user_data["tx_type"]))
            return ST_CATEGORY

        # Summa yo'q — so'raymiz
        await q.edit_message_text(
            f"{label} — *summani yozing:*\n\nMisol: `500000` | `1.5mln` | `200k`",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Bekor",callback_data="cancel")]]))
        return ST_AMOUNT

    # ── Kategoriya ──
    if d.startswith("cat_"):
        cat = d[4:]
        if cat == "custom":
            await q.edit_message_text(
                "✏️ *Kategoriya nomini yozing:*\n_(keyingi safar tugma sifatida chiqadi)_",
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Bekor",callback_data="cancel")]]))
            return ST_CUSTOM_CAT
        ctx.user_data["category"] = cat
        await q.edit_message_text(
            "📝 *Izoh yozing* (ixtiyoriy):",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⏭ O'tkazish",callback_data="skip_note")]]))
        return ST_NOTE

    if d == "skip_note":
        ctx.user_data["note"] = ""
        return await _show_confirm(q, ctx)

    if d == "confirm_yes":
        return await _save_tx(q, ctx, uid, update.effective_user, role)

    if d in ("confirm_no","cancel"):
        ctx.user_data.clear(); ctx.user_data["role"] = role
        await q.edit_message_text("❌ Bekor.", reply_markup=main_menu_ikb(role))
        return ST_MENU

    # ── Hisobotlar ──
    if d.startswith("report_"):
        if not can_report(role):
            await q.answer("❌ Ruxsat yo'q!", show_alert=True); return ST_MENU
        period = d[7:]
        try:
            rep = await api("get", f"/report?period={period}")
            await q.edit_message_text(fmt_report(rep,period), parse_mode="Markdown", reply_markup=back_ikb(role))
        except Exception as _e:
            log.error(f"BTN ERROR: {_e}")
            await q.edit_message_text(f"❌ Xatolik: {str(_e)[:100]}", reply_markup=back_ikb(role))
        return ST_MENU

    if d == "balance":
        try:
            rep = await api("get", "/report?period=month")
            net = rep.get("net",0)
            await q.edit_message_text(
                f"{'📈' if net>=0 else '📉'} *Bu oylik balans:*\n\n*{fmt(net)}*",
                parse_mode="Markdown", reply_markup=back_ikb(role))
        except Exception as _e:
            log.error(f"BTN ERROR: {_e}")
            await q.edit_message_text(f"❌ Xatolik: {str(_e)[:100]}", reply_markup=back_ikb(role))
        return ST_MENU

    if d == "list_last":
        try:
            txs = await api("get", "/transactions?limit=5")
            if not txs:
                await q.edit_message_text("📭 Tranzaksiyalar yo'q.", reply_markup=back_ikb(role))
                return ST_MENU
            lines = ["📋 *Oxirgi tranzaksiyalar:*\n"]
            for tx in txs:
                e = "💰" if tx["type"]=="income" else "💸"
                who = f" [{tx.get('added_by_name','?')}]" if tx.get("added_by_name") else ""
                lines.append(f"{e} #{tx['id']} — {fmt(tx['amount'])} | {tx['category']} ({tx['date']}){who}")
            await q.edit_message_text("\n".join(lines), parse_mode="Markdown", reply_markup=back_ikb(role))
        except Exception as _e:
            log.error(f"BTN ERROR: {_e}")
            await q.edit_message_text(f"❌ Xatolik: {str(_e)[:100]}", reply_markup=back_ikb(role))
        return ST_MENU

    # ── Export ──
    if d == "export_menu":
        if not can_manage(role):
            await q.answer("❌ Ruxsat yo'q!", show_alert=True); return ST_MENU
        await q.edit_message_text("📤 *Qaysi davr?*", parse_mode="Markdown", reply_markup=export_ikb())
        return ST_MENU

    if d.startswith("export_"):
        period = d[7:]
        try:
            async with httpx.AsyncClient() as c:
                r = await c.get(f"{API_URL}/export?period={period}", timeout=30)
                r.raise_for_status()
            cd = r.headers.get("content-disposition","")
            fname = cd.split("filename=")[-1].strip() if "filename=" in cd else "export.csv"
            await ctx.bot.send_document(chat_id=update.effective_chat.id,
                                        document=io.BytesIO(r.content), filename=fname,
                                        caption=f"📊 {period} davri export")
            await q.edit_message_text("✅ Fayl yuborildi!", reply_markup=back_ikb(role))
        except Exception as e:
            log.error(e); await q.edit_message_text("❌ Export xatolik.", reply_markup=back_ikb(role))
        return ST_MENU

    # ── Edit last 10 ──
    if d == "edit_last10":
        try:
            txs = await api("get", "/transactions?limit=10")
            if not txs:
                await q.edit_message_text("📭 Tranzaksiyalar yo'q.", reply_markup=back_ikb(role))
                return ST_MENU
            lines = ["✏️ *So'nggi 10 ta tranzaksiya:*\n_Tahrirlash uchun tanlang_\n"]
            rows = []
            for tx in txs:
                e = "💰" if tx["type"]=="income" else "💸"
                lbl = f"{e} {fmt(tx['amount'])} | {tx['category']} ({tx['date']})"
                lines.append(f"{e} *{fmt(tx['amount'])}* — {tx['category']} ({tx['date']})")
                rows.append([InlineKeyboardButton(
                    f"✏️ {e} {fmt(tx['amount'])} | {tx['category']}",
                    callback_data=f"edittx_{tx['id']}")])
            rows.append([InlineKeyboardButton("🏠 Bosh menyu", callback_data="main_menu")])
            await q.edit_message_text("\n".join(lines), parse_mode="Markdown",
                                      reply_markup=InlineKeyboardMarkup(rows))
        except Exception as e:
            log.error(e); await q.edit_message_text("❌ Xatolik.", reply_markup=back_ikb(role))
        return ST_MENU

    if d.startswith("edittx_"):
        tx_id = int(d[7:])
        try:
            txs = await api("get", f"/transactions?limit=100")
            tx = next((t for t in (txs or []) if t["id"]==tx_id), None)
            if not tx:
                await q.edit_message_text("❌ Tranzaksiya topilmadi.", reply_markup=back_ikb(role))
                return ST_MENU
            ctx.user_data["edit_tx"] = tx
            ctx.user_data["edit_type"] = tx["type"]
            label = "💰 Kirim" if tx["type"]=="income" else "💸 Chiqim"
            await q.edit_message_text(
                f"✏️ *Tahrirlash:*\n\n{label}: *{fmt(tx['amount'])}*\n"
                f"📂 {tx['category']} | 📅 {tx['date']}\n"
                f"📝 {tx['note'] or '—'}\n\n"
                f"Nimani o'zgartirish kerak?",
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("💵 Summani o'zgartir", callback_data=f"editfield_amount_{tx_id}"),
                     InlineKeyboardButton("📂 Kategoriya",          callback_data=f"editfield_cat_{tx_id}")],
                    [InlineKeyboardButton("↕️ Kirim↔Chiqim",        callback_data=f"editfield_type_{tx_id}"),
                     InlineKeyboardButton("📝 Izoh",                callback_data=f"editfield_note_{tx_id}")],
                    [InlineKeyboardButton("🗑 O'chirish",           callback_data=f"deletetx_{tx_id}"),
                     InlineKeyboardButton("◀️ Orqaga",              callback_data="edit_last10")],
                ]))
        except Exception as e:
            log.error(e); await q.edit_message_text("❌ Xatolik.", reply_markup=back_ikb(role))
        return ST_MENU

    if d.startswith("editfield_"):
        parts = d.split("_")
        field, tx_id = parts[1], int(parts[2])
        tx = ctx.user_data.get("edit_tx", {})
        if field == "amount":
            await q.edit_message_text(
                f"💵 Yangi summani yozing:\n_(hozir: {fmt(tx.get('amount',0))})_",
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Bekor", callback_data=f"edittx_{tx_id}")]]))
            ctx.user_data["edit_field"] = "amount"
            return ST_EDIT_TX_AMOUNT
        elif field == "cat":
            tx_type = ctx.user_data.get("edit_type", tx.get("type","expense"))
            cats = await get_cats(tx_type)
            rows = []
            row = []
            for c in cats:
                row.append(InlineKeyboardButton(c.capitalize(), callback_data=f"seteditcat_{tx_id}_{c}"))
                if len(row)==2: rows.append(row); row=[]
            if row: rows.append(row)
            rows.append([InlineKeyboardButton("◀️ Orqaga", callback_data=f"edittx_{tx_id}")])
            await q.edit_message_text("📂 Yangi kategoriyani tanlang:", reply_markup=InlineKeyboardMarkup(rows))
            return ST_MENU
        elif field == "type":
            old_type = tx.get("type","expense")
            new_type = "expense" if old_type=="income" else "income"
            ctx.user_data["edit_type"] = new_type
            ctx.user_data["edit_tx"] = {**tx, "type": new_type}
            await api("put", f"/transactions/{tx_id}", {**tx, "type": new_type, "amount": float(tx["amount"])})
            label = "💰 Kirim" if new_type=="income" else "💸 Chiqim"
            await q.edit_message_text(f"✅ Tur o'zgardi → {label}", reply_markup=back_ikb(role))
            return ST_MENU
        elif field == "note":
            await q.edit_message_text(
                f"📝 Yangi izoh yozing:\n_(hozir: {tx.get('note','—')})_",
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⏭ Tozalash", callback_data=f"seteditnote_{tx_id}_")]]))
            ctx.user_data["edit_field"] = "note"
            ctx.user_data["edit_tx_id"] = tx_id
            return ST_EDIT_TX_NOTE
        return ST_MENU

    if d.startswith("seteditcat_"):
        parts = d.split("_", 3)  # seteditcat_ID_catname
        tx_id = int(parts[1])
        new_cat = parts[2]
        tx = ctx.user_data.get("edit_tx", {})
        try:
            await api("put", f"/transactions/{tx_id}", {**tx, "category": new_cat, "amount": float(tx["amount"])})
            await q.edit_message_text(f"✅ Kategoriya → *{new_cat}*", parse_mode="Markdown", reply_markup=back_ikb(role))
        except Exception as e:
            await q.edit_message_text("❌ Xatolik.", reply_markup=back_ikb(role))
        return ST_MENU

    if d.startswith("seteditnote_"):
        parts = d.split("_", 3)
        tx_id = int(parts[1])
        new_note = parts[2] if len(parts)>2 else ""
        tx = ctx.user_data.get("edit_tx", {})
        try:
            await api("put", f"/transactions/{tx_id}", {**tx, "note": new_note, "amount": float(tx["amount"])})
            await q.edit_message_text(f"✅ Izoh tozalandi.", reply_markup=back_ikb(role))
        except Exception as _e:
            log.error(f"BTN ERROR: {_e}")
            await q.edit_message_text(f"❌ Xatolik: {str(_e)[:100]}", reply_markup=back_ikb(role))
        return ST_MENU

    if d.startswith("deletetx_"):
        tx_id = int(d[9:])
        try:
            await api("post", "/transactions/bulk-delete", json=[tx_id])
            await q.edit_message_text(f"🗑 #{tx_id} o'chirildi.", reply_markup=back_ikb(role))
        except Exception as _e:
            log.error(f"BTN ERROR: {_e}")
            await q.edit_message_text(f"❌ Xatolik: {str(_e)[:100]}", reply_markup=back_ikb(role))
        return ST_MENU

        # ══════════════════════════════════════════════════════════════════════════
    # ── O'CHIRISH BOSH MENYU ──
    # ══════════════════════════════════════════════════════════════════════════
    if d == "del_main":
        if not can_manage(role):
            await q.answer("❌ Ruxsat yo'q!", show_alert=True); return ST_MENU
        await q.edit_message_text(
            "🗑 *O'chirish usulini tanlang:*",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("📅 Sanalar ro'yxatidan tanlash", callback_data="del_show_dates")],
                [InlineKeyboardButton("✍️ Sana qo'lda kiritish",        callback_data="del_manual_date")],
                [InlineKeyboardButton("🔢 ID bo'yicha o'chirish",        callback_data="del_by_id")],
                [InlineKeyboardButton("🏠 Orqaga",                       callback_data="main_menu")],
            ]))
        return ST_DEL_MAIN

    # ── Sanalar ro'yxati ──
    if d == "del_show_dates":
        try:
            txs = await api("get", "/transactions?limit=500")
            dates = sorted(set(t["date"] for t in txs), reverse=True)
            if not dates:
                await q.edit_message_text("📭 Tranzaksiya yo'q.", reply_markup=back_ikb(role))
                return ST_MENU
            rows = []
            row = []
            for dt in dates[:20]:  # max 20 sana
                row.append(InlineKeyboardButton(dt, callback_data=f"del_date_{dt}"))
                if len(row)==2: rows.append(row); row=[]
            if row: rows.append(row)
            rows.append([InlineKeyboardButton("🏠 Orqaga", callback_data="del_main")])
            await q.edit_message_text(
                "📅 *Sanani tanlang:*",
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup(rows))
        except Exception as e:
            log.error(e); await q.edit_message_text("❌ Xatolik.", reply_markup=back_ikb(role))
        return ST_DEL_MAIN

    # ── Sana tanlanganda tranzaksiyalar ──
    if d.startswith("del_date_"):
        target = d[9:]
        return await _show_date_txs(q, ctx, target, role)

    # ── O'chirish amallar (income/expense/all/id) ──
    if d.startswith("del_all_"):      return await _delete_by_filter(q, ctx, d[8:], "all",     role)
    if d.startswith("del_income_"):   return await _delete_by_filter(q, ctx, d[11:], "income", role)
    if d.startswith("del_expense_"):  return await _delete_by_filter(q, ctx, d[12:], "expense",role)
    if d.startswith("delidconfirm_"): return await _delete_single(q, ctx, d[13:], role)

    # ── Qo'lda sana kiritish ──
    if d == "del_manual_date":
        await q.edit_message_text(
            "✍️ *Sanani yozing:*\n\nFormat: `YYYY-MM-DD`\nMisol: `2025-01-15`",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Bekor",callback_data="del_main")]]))
        return ST_DEL_DATE_INPUT

    # ── ID bo'yicha o'chirish ──
    if d == "del_by_id":
        await q.edit_message_text(
            "🔢 *ID ni yozing:*\n\nMisol: `42`  yoki bir nechta: `42 55 78`",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Bekor",callback_data="del_main")]]))
        return ST_DEL_PICK_ID

    # ── Kategoriya tahrirlash ──
    if d == "edit_cats":
        if not can_manage(role):
            await q.answer("❌ Ruxsat yo'q!", show_alert=True); return ST_MENU
        return await _show_edit_cats(q, role)

    if d.startswith("editcat_"):
        cat_name = d[8:]
        ctx.user_data["editing_cat"] = cat_name
        await q.edit_message_text(
            f"✏️ *'{cat_name}'* → yangi nomini yozing:",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🗑 O'chirish", callback_data=f"deletecat_{cat_name}")],
                [InlineKeyboardButton("❌ Bekor",     callback_data="edit_cats")],
            ]))
        return ST_EDIT_CAT_NAME

    if d.startswith("deletecat_"):
        cat_name = d[10:]
        try:
            await api("delete", f"/categories/{cat_name}")
            await q.edit_message_text(f"✅ '{cat_name}' o'chirildi.", reply_markup=back_ikb(role))
        except Exception as _e:
            log.error(f"BTN ERROR: {_e}")
            await q.edit_message_text(f"❌ Xatolik: {str(_e)[:100]}", reply_markup=back_ikb(role))
        return ST_MENU

    if d == "newcat":
        ctx.user_data["editing_cat"] = None
        await q.edit_message_text(
            "➕ *Yangi kategoriya nomi:*",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Bekor",callback_data="edit_cats")]]))
        return ST_EDIT_CAT_NAME

    if d.startswith("newcat_type_"):
        tx_type = d[12:]
        name = ctx.user_data.get("new_cat_name","yangi")
        try:
            await api("post","/categories",json={"name":name,"type":tx_type,"color":"#6366f1"})
            await q.edit_message_text(f"✅ '{name}' qo'shildi!", reply_markup=back_ikb(role))
        except Exception as _e:
            log.error(f"BTN ERROR: {_e}")
            await q.edit_message_text(f"❌ Xatolik: {str(_e)[:100]}", reply_markup=back_ikb(role))
        ctx.user_data.clear(); ctx.user_data["role"]=role
        return ST_MENU

    # ── Import ──
    if d == "import_start":
        if not can_manage(role):
            await q.answer("❌ Ruxsat yo'q!", show_alert=True); return ST_MENU
        await q.edit_message_text(
            "📥 *CSV fayl yuboring*\n\nUstunlar: `Tur, Summa (so'm), Kategoriya, Izoh, Sana`",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Bekor",callback_data="cancel")]]))
        return ST_IMPORT_FILE

    if d in ("import_append","import_replace"):
        mode = "append" if d=="import_append" else "replace"
        file_data = ctx.user_data.get("import_file_data")
        file_name = ctx.user_data.get("import_file_name","import.csv")
        if not file_data:
            await q.edit_message_text("❌ Fayl topilmadi.", reply_markup=back_ikb(role))
            return ST_MENU
        try:
            async with httpx.AsyncClient() as c:
                r = await c.post(f"{API_URL}/import?mode={mode}",
                                 files={"file":(file_name,io.BytesIO(file_data),"text/csv")}, timeout=30)
                r.raise_for_status(); res=r.json()
            mode_txt = "qo'shildi ✅" if mode=="append" else "o'rniga qo'yildi 🔄"
            await q.edit_message_text(
                f"✅ *Import tugadi!*\n\n📥 *{res['inserted']}* ta {mode_txt}",
                parse_mode="Markdown", reply_markup=back_ikb(role))
        except: await q.edit_message_text("❌ Import xatolik.", reply_markup=back_ikb(role))
        ctx.user_data.clear(); ctx.user_data["role"]=role
        return ST_MENU

    # ══════════════════════════════════════════════════════════════════════════
    # ── SUPER ADMIN — foydalanuvchilar boshqaruvi ──
    # ══════════════════════════════════════════════════════════════════════════
    if d == "super_users":
        if not is_super(role):
            await q.answer("❌ Faqat super admin!", show_alert=True); return ST_MENU
        return await _show_users(q, role)

    if d.startswith("user_del_"):
        if not is_super(role):
            await q.answer("❌ Faqat super admin!", show_alert=True); return ST_MENU
        uid2 = int(d[9:])
        await api("delete", f"/users/{uid2}")
        await q.edit_message_text(f"✅ `{uid2}` o'chirildi.", parse_mode="Markdown", reply_markup=back_ikb(role))
        return ST_MENU

    if d.startswith("user_changerole_"):
        if not is_super(role):
            await q.answer("❌ Faqat super admin!", show_alert=True); return ST_MENU
        uid2 = int(d[16:])
        ctx.user_data["changing_role_uid"] = uid2
        await q.edit_message_text(
            f"✏️ `{uid2}` uchun yangi rol tanlang:",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("1️⃣ Kirim/Chiqim",    callback_data=f"rp|{uid2}|tx_only")],
                [InlineKeyboardButton("2️⃣ Faqat hisobot",   callback_data=f"rp|{uid2}|report_only")],
                [InlineKeyboardButton("3️⃣ To'liq huquq",   callback_data=f"rp|{uid2}|full")],
                [InlineKeyboardButton("❌ Bekor",            callback_data="super_users")],
            ]))
        return ST_MENU

    if d == "user_add":
        if not is_super(role):
            await q.answer("❌ Faqat super admin!", show_alert=True); return ST_MENU
        await q.edit_message_text(
            "👤 *Yangi admin qo'shish*\n\nAdmin Telegram ID sini yuboring:\n\nMisol: `123456789`",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Bekor",callback_data="super_users")]]))
        ctx.user_data["adding_user"] = True
        return ST_ADD_ADMIN_ROLE

    if d.startswith("rp|"):
        # format: rp|USERID|ROLE
        parts = d.split("|")
        if len(parts)==3:
            uid2, picked_role = int(parts[1]), parts[2]
            uname = ctx.user_data.get("new_user_name","")
            try:
                await api("post","/users",json={"user_id":uid2,"username":uname,"full_name":"","role":picked_role})
                role_label = ROLE_LABELS.get(picked_role, picked_role)
                await q.edit_message_text(
                    f"✅ `{uid2}` qo'shildi\nRol: {role_label}",
                    parse_mode="Markdown", reply_markup=back_ikb(role))
            except Exception as _e:
                log.error(f"BTN ERROR: {_e}")
                await q.edit_message_text(f"❌ Xatolik: {str(_e)[:80]}", reply_markup=back_ikb(role))
            await q.edit_message_text(f"❌ Xatolik: {str(_e)[:100]}", reply_markup=back_ikb(role))
            ctx.user_data.pop("adding_user",None)
            ctx.user_data.pop("new_user_name",None)
            ctx.user_data.pop("new_user_id",None)
        return ST_MENU

    if d == "admin_users_list":
        return await _show_users(q, role)

    return ST_MENU

# ─── Delete helpers ───────────────────────────────────────────────────────────
async def _show_date_txs(q, ctx, target_date, role):
    try:
        txs = await api("get", f"/transactions/by-date/{target_date}")
        if not txs:
            await q.edit_message_text(
                f"📭 *{target_date}* da tranzaksiya yo'q.",
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Orqaga",callback_data="del_show_dates")]]))
            return ST_DEL_MAIN

        income_txs  = [t for t in txs if t["type"]=="income"]
        expense_txs = [t for t in txs if t["type"]=="expense"]
        total_inc   = sum(t["amount"] for t in income_txs)
        total_exp   = sum(t["amount"] for t in expense_txs)

        lines = [f"📅 *{target_date}* sanasidagi tranzaksiyalar:\n"]
        for tx in txs:
            e = "💰" if tx["type"]=="income" else "💸"
            who = f" [{tx.get('added_by_name','?')}]" if tx.get("added_by_name") else ""
            note = f" _{tx['note']}_" if tx.get("note") else ""
            lines.append(f"{e} #{tx['id']} — *{fmt(tx['amount'])}* | {tx['category']}{who}{note}")

        lines.append(f"\n💰 Kirim jami: *{fmt(total_inc)}* ({len(income_txs)} ta)")
        lines.append(f"💸 Chiqim jami: *{fmt(total_exp)}* ({len(expense_txs)} ta)")

        # Build delete buttons
        ids_all     = ",".join(str(t["id"]) for t in txs)
        ids_income  = ",".join(str(t["id"]) for t in income_txs)
        ids_expense = ",".join(str(t["id"]) for t in expense_txs)

        rows = []
        rows.append([InlineKeyboardButton(f"🗑 Hammasini o'chirish ({len(txs)} ta)",
                                          callback_data=f"del_all_{ids_all}")])
        if income_txs:
            rows.append([InlineKeyboardButton(f"💰 Faqat kirimni o'chirish ({len(income_txs)} ta)",
                                              callback_data=f"del_income_{ids_income}")])
        if expense_txs:
            rows.append([InlineKeyboardButton(f"💸 Faqat chiqimni o'chirish ({len(expense_txs)} ta)",
                                              callback_data=f"del_expense_{ids_expense}")])
        rows.append([InlineKeyboardButton("🔢 Faqat bitta ID o'chirish", callback_data="del_by_id")])
        rows.append([InlineKeyboardButton("◀️ Sanalar ro'yxati",         callback_data="del_show_dates")])
        rows.append([InlineKeyboardButton("🏠 Bosh menyu",               callback_data="main_menu")])

        await q.edit_message_text("\n".join(lines), parse_mode="Markdown",
                                  reply_markup=InlineKeyboardMarkup(rows))
    except Exception as e:
        log.error(e)
        await q.edit_message_text("❌ Xatolik.", reply_markup=back_ikb(role))
    return ST_DEL_MAIN

async def _delete_by_filter(q, ctx, ids_str, filter_type, role):
    ids = [int(x) for x in ids_str.split(",") if x.isdigit()]
    if not ids:
        await q.edit_message_text("❌ ID topilmadi.", reply_markup=back_ikb(role))
        return ST_MENU
    try:
        result = await api("post", "/transactions/bulk-delete", json=ids)
        deleted = result.get("deleted",0)
        label_map = {"all":"Hammasi","income":"Kirimlar","expense":"Chiqimlar"}
        await q.edit_message_text(
            f"✅ *{label_map.get(filter_type,'')}* o'chirildi: *{deleted}* ta",
            parse_mode="Markdown", reply_markup=back_ikb(role))
    except Exception as e:
        log.error(e); await q.edit_message_text("❌ Xatolik.", reply_markup=back_ikb(role))
    return ST_MENU

async def _delete_single(q, ctx, id_str, role):
    try:
        tx_id = int(id_str)
        result = await api("post", "/transactions/bulk-delete", json=[tx_id])
        deleted = result.get("deleted",0)
        if deleted:
            await q.edit_message_text(f"✅ #{tx_id} o'chirildi.", reply_markup=back_ikb(role))
        else:
            await q.edit_message_text(f"❌ #{tx_id} topilmadi.", reply_markup=back_ikb(role))
    except Exception as e:
        log.error(e); await q.edit_message_text("❌ Xatolik.", reply_markup=back_ikb(role))
    return ST_MENU

# ─── Category editor helper ───────────────────────────────────────────────────
async def _show_edit_cats(q, role):
    try:
        cats = await api("get", "/categories")
        rows=[]; row=[]
        for c in cats:
            row.append(InlineKeyboardButton(c["name"].capitalize(), callback_data=f"editcat_{c['name']}"))
            if len(row)==2: rows.append(row); row=[]
        if row: rows.append(row)
        rows.append([InlineKeyboardButton("➕ Yangi", callback_data="newcat")])
        rows.append([InlineKeyboardButton("🏠 Orqaga", callback_data="main_menu")])
        await q.edit_message_text("✏️ *Kategoriyani tanlang:*", parse_mode="Markdown",
                                  reply_markup=InlineKeyboardMarkup(rows))
    except Exception as _e:
            log.error(f"BTN ERROR: {_e}")
            await q.edit_message_text(f"❌ Xatolik: {str(_e)[:100]}", reply_markup=back_ikb(role))
    return ST_MENU

# ─── Super admin users list ───────────────────────────────────────────────────
async def _show_users(q, role):
    try:
        users = await api("get", "/users")
        # Also get stats to find added_by_name from transactions
        try:
            stats = await api("get", "/admin/stats")
            stats_map = {s["added_by_id"]: s for s in stats}
        except:
            stats_map = {}

        lines = ["👥 *Adminlar ro'yxati:*\n"]
        rows = []
        if not users:
            lines.append("_(hech kim yo'q — hamma kira oladi)_")
        for u in users:
            role_e = {"full":"3️⃣","report_only":"2️⃣","tx_only":"1️⃣"}.get(u["role"],"👤")
            role_label = ROLE_LABELS.get(u["role"], u["role"])
            uid2 = u["user_id"]
            # Name priority: full_name → username → added_by_name from stats → ID
            name = (u.get("full_name") or "").strip()
            if not name:
                name = (u.get("username") or "").strip()
            if not name and uid2 in stats_map:
                name = stats_map[uid2].get("added_by_name","").strip()
            if not name:
                name = f"ID:{uid2}"
            stat = stats_map.get(uid2)
            stat_txt = ""
            if stat:
                stat_txt = f" | 📋{stat['tx_count']}ta"
            lines.append(f"{role_e} *{name}*")
            lines.append(f"   🆔 `{uid2}` | {role_label}{stat_txt}")
            rows.append([
                InlineKeyboardButton(f"✏️ {name[:12]} roli", callback_data=f"user_changerole_{uid2}"),
                InlineKeyboardButton("🗑 O'chirish",         callback_data=f"user_del_{uid2}"),
            ])
        rows.append([InlineKeyboardButton("➕ Yangi admin qo'shish", callback_data="user_add")])
        rows.append([InlineKeyboardButton("🏠 Orqaga", callback_data="main_menu")])
        await q.edit_message_text("\n".join(lines), parse_mode="Markdown",
                                  reply_markup=InlineKeyboardMarkup(rows))
    except Exception as e:
        log.error(e); await q.edit_message_text("❌ Xatolik.", reply_markup=back_ikb(role))
    return ST_MENU

# ─── Confirm + Save helpers ───────────────────────────────────────────────────
async def _show_confirm(q, ctx):
    tx_type = ctx.user_data.get("tx_type","expense")
    amount  = ctx.user_data.get("amount",0)
    cat     = ctx.user_data.get("category","boshqa")
    note    = ctx.user_data.get("note","")
    label   = "💰 Kirim" if tx_type=="income" else "💸 Chiqim"
    text = (f"✅ *Tasdiqlang:*\n\n{label}\n"
            f"💵 Summa: *{fmt(amount)}*\n"
            f"📂 Kategoriya: *{cat}*\n"
            f"📅 {date.today().strftime('%d.%m.%Y')}")
    if note: text += f"\n📝 Izoh: _{note}_"
    await q.edit_message_text(text, parse_mode="Markdown", reply_markup=confirm_ikb())
    return ST_CONFIRM

async def _save_tx(q, ctx, uid, user, role):
    full_name = f"{user.first_name or ''} {user.last_name or ''}".strip() or user.username or str(uid)
    try:
        await api("post","/transactions",json={
            "type":     ctx.user_data["tx_type"],
            "amount":   ctx.user_data["amount"],
            "category": ctx.user_data["category"],
            "note":     ctx.user_data.get("note",""),
            "date":     date.today().isoformat(),
            "added_by_id":   uid,
            "added_by_name": full_name,
        })
        label = "💰 Kirim" if ctx.user_data["tx_type"]=="income" else "💸 Chiqim"
        await q.edit_message_text(
            f"✅ *Saqlandi!*\n\n{label}: *{fmt(ctx.user_data['amount'])}*\n"
            f"📂 {ctx.user_data['category']}",
            parse_mode="Markdown", reply_markup=main_menu_ikb(role))
    except Exception as e:
        log.error(e); await q.edit_message_text("❌ Saqlashda xatolik.", reply_markup=main_menu_ikb(role))
    ctx.user_data.clear(); ctx.user_data["role"]=role
    return ST_MENU

# ─── Voice message handler ───────────────────────────────────────────────────
UNCLEAR_MSGS = [
    "Hmm, bu gapni tushunmadim 🤔 Qaytadan yozing yoki ovozli xabar yuboring.",
    "Aniq tushunmadim. Iltimos, boshqacha tushuntiring yoki qayta yuboring.",
    "Bu yerda nimani nazarda tutdingiz? Biroz aniqroq yozsangiz yordam beraman.",
    "Kechirasiz, bu so'zni anglamadim. Qayta urinib ko'ring!",
]
import random

# ─── O'zbek raqam so'zlari lug'ati (noto'g'ri translit ham qabul qilinadi) ────
UZ_NUMBERS = {
    # birliklar
    "bir": 1, "ikki": 2, "uch": 3, "to'rt": 4, "tort": 4, "tört": 4,
    "besh": 5, "olti": 6, "yetti": 7, "sakkiz": 8, "to'qqiz": 9, "toqqiz": 9,
    # o'nliklar
    "o'n": 10, "on": 10, "yigirma": 20, "o'ttiz": 30, "ottiz": 30,
    "qirq": 40, "kirk": 40, "ellik": 50, "elim": 50, "elli": 50,
    "oltmish": 60, "etmish": 70, "sakson": 80, "saxon": 80,
    "to'qson": 90, "toqson": 90,
    # yuzlar
    "yuz": 100, "yüz": 100,
    # ko'paytiruvchilar
    "ming": 1000, "min": 1000, "mln": 1_000_000, "million": 1_000_000,
    "milliard": 1_000_000_000,
}

def parse_uz_number_words(text: str):
    """
    O'zbek raqam so'zlarini raqamga aylantiradi.
    "ikki yuz ellik ming" → 250000
    "Saxon Min" → 80000  (noto'g'ri translit ham ishlaydi)
    "Elimin" → 50000  (ellik ming)
    """
    # Compound patterns — whisper birlashtirgan so'zlar
    COMPOUNDS = {
        "elimin":    50_000,  "eliMin":   50_000,
        "yuzming":   100_000, "yuzmin":   100_000,
        "mingso":    1_000,   "saksonmin":80_000,
        "ottizming": 30_000,  "qirqming": 40_000,
        "ellikning": 50_000,
    }

    text_l = text.lower().replace("'","")
    # Compound tekshirish
    for comp, val in COMPOUNDS.items():
        if comp in text_l:
            # Oldida raqam bor?
            m = re.search(r"(\d+)\s*" + comp[:4], text_l)
            if m:
                return int(m.group(1)) * val
            return val

    words = re.sub(r"[^a-zA-Z0-9'Ѐ-ӿ ]", " ", text_l).split()
    total = 0; current = 0

    for word in words:
        try:
            n = float(word.replace(",","."))
            current += n; continue
        except: pass

        val = UZ_NUMBERS.get(word)
        if val is None:
            # Fuzzy match
            for key, v in UZ_NUMBERS.items():
                if len(key) >= 3 and len(word) >= 3:
                    common = sum(1 for a,b in zip(key,word) if a==b)
                    if common >= min(len(key),len(word)) - 1:
                        val = v; break
        if val is None: continue

        if val >= 1000:
            if current == 0: current = 1
            total += current * val
            current = 0
        elif val == 100:
            if current == 0: current = 1
            current *= 100
        else:
            current += val

    total += current
    return total if total > 0 else None

def _sync_transcribe(file_path: str) -> str:
    """
    Vosk (offline O'zbek modeli) → eng ishonchli yechim.
    Fallback: Google Speech → faster-whisper
    """
    import os as _os

    # ── 1. VOSK — offline, O'zbek uchun maxsus model ──────────────────────────
    try:
        import vosk, wave, json
        from pydub import AudioSegment

        MODEL_PATH = _os.path.join(
            _os.path.dirname(_os.path.abspath(__file__)),
            "vosk-model-uz"
        )
        if _os.path.exists(MODEL_PATH):
            # OGG → WAV (16kHz mono — Vosk talab qiladi)
            audio = AudioSegment.from_ogg(file_path)
            audio = audio.set_frame_rate(16000).set_channels(1)
            import tempfile
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as wf:
                wav_path = wf.name
            audio.export(wav_path, format="wav")

            model = vosk.Model(MODEL_PATH)
            rec   = vosk.KaldiRecognizer(model, 16000)
            with wave.open(wav_path, "rb") as wf:
                while True:
                    data = wf.readframes(4000)
                    if not data: break
                    rec.AcceptWaveform(data)
            result = json.loads(rec.FinalResult())
            text   = result.get("text", "").strip()
            try: _os.unlink(wav_path)
            except: pass
            if text:
                log.info(f"Vosk result: {text!r}")
                return text
        else:
            log.info(f"Vosk model yo'q: {MODEL_PATH}")
    except ImportError:
        log.info("vosk o'rnatilmagan")
    except Exception as e:
        log.warning(f"Vosk xatolik: {e}")

    # ── 2. Google Speech Recognition — internet kerak ──────────────────────────
    try:
        import speech_recognition as sr
        from pydub import AudioSegment
        import tempfile

        audio = AudioSegment.from_ogg(file_path)
        audio = audio.set_frame_rate(16000).set_channels(1)
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as wf:
            wav_path = wf.name
        audio.export(wav_path, format="wav")

        recognizer = sr.Recognizer()
        with sr.AudioFile(wav_path) as source:
            audio_data = recognizer.record(source)
        try: _os.unlink(wav_path)
        except: pass

        for lang in ("uz-UZ", "ru-RU", "en-US"):
            try:
                text = recognizer.recognize_google(audio_data, language=lang)
                if text:
                    log.info(f"Google ({lang}): {text!r}")
                    return text
            except: pass
    except ImportError:
        log.info("speech_recognition o'rnatilmagan")
    except Exception as e:
        log.warning(f"Google SR xatolik: {e}")

    # ── 3. faster-whisper — oxirgi imkoniyat ───────────────────────────────────
    try:
        from faster_whisper import WhisperModel
        model = WhisperModel("small", device="cpu", compute_type="int8")
        segments, info = model.transcribe(file_path)
        text = " ".join(s.text for s in segments).strip()
        log.info(f"Whisper ({info.language}): {text!r}")
        return text
    except ImportError:
        pass
    except Exception as e:
        log.warning(f"Whisper xatolik: {e}")

    return ""


async def transcribe_voice_file(file_path: str) -> str:
    """Run blocking transcription in thread pool — doesn't block event loop"""
    import asyncio, functools
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, functools.partial(_sync_transcribe, file_path))

INCOME_WORDS = [
    "tushdi","tushum","kirim","olindi","keldi","topildi","received",
    "daromad","sotuv","oplata","оплата","пришло","получили","income","доход","приход"
]
EXPENSE_WORDS = [
    "chiqdi","sarflandi","xarajat","to'ladik","haqdorim","ketdi","berdik",
    "sotib","xarid","ijara","oylik","expense","потратили","заплатили","расход","затрат"
]

async def detect_intent_and_process(update_or_msg, ctx, text: str, role: str, uid: int, user):
    """Matnni tahlil qilib kirim/chiqim/hisobotga yo'naltiradi"""
    text_l = text.lower()

    # Hisobot so'rovi
    report_words = ["hisobot","report","qancha","necha","jami","balans",
                    "bugun","hafta","oy","yil","ko'rsat","chiqar","статистика","отчет"]
    if any(w in text_l for w in report_words):
        period = "today"
        if any(w in text_l for w in ["hafta","week","недел"]): period = "week"
        elif any(w in text_l for w in ["oy","month","месяц"]): period = "month"
        elif any(w in text_l for w in ["yil","year","год"]): period = "year"
        try:
            rep = await api("get", f"/report?period={period}")
            msg = fmt_report(rep, period)
        except:
            msg = "❌ Hisobot olishda xatolik."
        if hasattr(update_or_msg, "reply_text"):
            await update_or_msg.reply_text(msg, parse_mode="Markdown", reply_markup=back_ikb(role))
        return ST_MENU

    # Summa bor → kirim yoki chiqim
    amount = extract_amount(text)
    if amount:
        # Har safar yangi amount — eskisini tozalaymiz
        ctx.user_data["amount"] = amount
        ctx.user_data.pop("category", None)
        ctx.user_data.pop("note", None)

        # 1. Matndan tur aniqlaymiz (eng yuqori ustuvorlik)
        if any(w in text_l for w in INCOME_WORDS):
            tx_type = "income"
            ctx.user_data["tx_type"] = tx_type
        elif any(w in text_l for w in EXPENSE_WORDS):
            tx_type = "expense"
            ctx.user_data["tx_type"] = tx_type
        # 2. Kontekstda tur allaqachon belgilangan bo'lsa — ishlatamiz
        elif ctx.user_data.get("tx_type"):
            tx_type = ctx.user_data["tx_type"]
        # 3. Aniq emas — foydalanuvchidan so'raymiz
        else:
            tx_type = None

        if tx_type:
            ctx.user_data["tx_type"] = tx_type
            label = "💰 Kirim" if tx_type=="income" else "💸 Chiqim"
            if hasattr(update_or_msg, "reply_text"):
                await update_or_msg.reply_text(
                    f"{label}: *{fmt(amount)}*\n\n📂 Kategoriyani tanlang:",
                    parse_mode="Markdown", reply_markup=await cat_ikb(tx_type))
            return ST_CATEGORY
        else:
            # So'raymiz
            if hasattr(update_or_msg, "reply_text"):
                await update_or_msg.reply_text(
                    f"*{fmt(amount)}* — kirim yoki chiqim?",
                    parse_mode="Markdown",
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton(f"💰 Kirim ({fmt(amount)})", callback_data="add_income"),
                         InlineKeyboardButton(f"💸 Chiqim ({fmt(amount)})", callback_data="add_expense")],
                        [InlineKeyboardButton("❌ Bekor", callback_data="cancel")],
                    ]))
            return ST_CATEGORY

    # Tushunarsiz
    return None

# ─── Voice state: waiting for typed text after voice ─────────────────────────
VOICE_WAITING_TEXT = "voice_waiting_text"

async def handle_voice(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    role = await guard(update)
    if not role: return ConversationHandler.END
    if not can_add_tx(role):
        await update.message.reply_text("❌ Sizda kirim/chiqim qo\'shish huquqi yo\'q.")
        return ST_MENU

    uid  = update.effective_user.id
    user = update.effective_user

    msg = await update.message.reply_text("🎙 Ovoz qabul qilindi, tahlil qilinmoqda...")

    # Transcription sinash
    transcribed = ""
    try:
        voice = update.message.voice
        tg_file = await ctx.bot.get_file(voice.file_id)
        import tempfile, os as _os
        with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as f:
            tmp_path = f.name
        await tg_file.download_to_drive(tmp_path)
        transcribed = await transcribe_voice_file(tmp_path)
        try: _os.unlink(tmp_path)
        except: pass
    except Exception as e:
        log.warning(f"Voice error: {e}")

    # Transcription muvaffaqiyatli
    if transcribed:
        await msg.edit_text(f"🎙 Eshitildi: _{transcribed}_", parse_mode="Markdown")
        result = await detect_intent_and_process(update.message, ctx, transcribed, role, uid, user)
        if result is not None:
            return result

    # Transcription ishlamadi yoki tushunilmadi — kirim/chiqim tugmalar ko'rsat
    await msg.edit_text(
        "🎙 Ovoz qabul qilindi!\n\n"
        "Kirim yoki chiqim?",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("💰 Kirim", callback_data="add_income"),
             InlineKeyboardButton("💸 Chiqim", callback_data="add_expense")],
            [InlineKeyboardButton("❌ Bekor", callback_data="cancel")],
        ]))
    return ST_MENU

async def voice_text_fallback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Voice yuborilgandan keyin foydalanuvchi matn yozsa"""
    if not ctx.user_data.get(VOICE_WAITING_TEXT):
        return None  # bu handler uchun emas
    ctx.user_data.pop(VOICE_WAITING_TEXT, None)
    role = await guard(update)
    if not role: return ConversationHandler.END
    uid  = update.effective_user.id
    text = update.message.text.strip()
    result = await detect_intent_and_process(update.message, ctx, text, role, uid, update.effective_user)
    if result is None:
        await update.message.reply_text(
            "🤔 Tushunmadim. Boshqacha yozing:\n"
            "• `500 ming so'm tushdi` — kirim\n"
            "• `Ijara 2 mln to'ladik` — chiqim",
            parse_mode="Markdown",
            reply_markup=main_menu_ikb(role))
        return ST_MENU
    return result

# ─── Text input handlers ──────────────────────────────────────────────────────
async def amount_input(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    role = await guard(update)
    if not role: return ConversationHandler.END
    uid  = update.effective_user.id
    text = update.message.text.strip()

    # Matndan summa va tur birga kelishi mumkin: "chiqim 20000" / "20 тысяч income"
    amount = extract_amount(text)

    # Tur so'zini tekshiramiz — ctx.user_data dagi turni override qilish mumkin
    text_l = text.lower()
    if any(w in text_l for w in INCOME_WORDS):
        ctx.user_data["tx_type"] = "income"
    elif any(w in text_l for w in EXPENSE_WORDS):
        ctx.user_data["tx_type"] = "expense"

    if not amount:
        # Matnda summa yo'q — lekin tur so'zi bo'lishi mumkin
        # Misol: faqat "kirim" deb yozsa — summa so'raymiz
        if any(w in text_l for w in INCOME_W+EXPENSE_W):
            await update.message.reply_text(
                "💵 *Summani yozing:*\n\nMisol: `500000` | `1.5mln` | `200k`",
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Bekor",callback_data="cancel")]]))
            return ST_AMOUNT
        await update.message.reply_text(
            "❓ Summani tushunmadim.\n\nMisol: `500000` | `1.5mln` | `200k`",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Bekor",callback_data="cancel")]]))
        return ST_AMOUNT

    ctx.user_data["amount"] = amount
    tx_type = ctx.user_data.get("tx_type")

    # Tur hali aniq emas — so'raymiz
    if not tx_type:
        await update.message.reply_text(
            f"*{fmt(amount)}* — kirim yoki chiqim?",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton(f"💰 Kirim ({fmt(amount)})",  callback_data="add_income"),
                 InlineKeyboardButton(f"💸 Chiqim ({fmt(amount)})", callback_data="add_expense")],
                [InlineKeyboardButton("❌ Bekor", callback_data="cancel")],
            ]))
        return ST_CATEGORY

    label = "💰 Kirim" if tx_type=="income" else "💸 Chiqim"
    await update.message.reply_text(
        f"{label}: *{fmt(amount)}*\n\n📂 Kategoriyani tanlang:",
        parse_mode="Markdown", reply_markup=await cat_ikb(tx_type))
    return ST_CATEGORY

async def custom_cat_input(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    role = await guard(update)
    if not role: return ConversationHandler.END
    cat = update.message.text.strip().lower()
    if not cat or len(cat)>50:
        await update.message.reply_text("❓ Noto'g'ri nom."); return ST_CUSTOM_CAT
    tx_type = ctx.user_data.get("tx_type","both")
    try:
        await api("post","/categories",json={"name":cat,"type":tx_type,"color":"#6366f1"})
        saved = f"✅ *'{cat}'* saqlandi!\n\n"
    except: saved=""
    ctx.user_data["category"] = cat
    await update.message.reply_text(
        f"{saved}📝 *Izoh yozing* (ixtiyoriy):",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⏭ O'tkazish",callback_data="skip_note")]]))
    return ST_NOTE

async def note_input(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    role = await guard(update)
    if not role: return ConversationHandler.END
    note = update.message.text.strip()
    ctx.user_data["note"] = "" if note.lower() in ("yo'q","yoq","-","no","skip") else note
    tx_type = ctx.user_data.get("tx_type","expense")
    amount  = ctx.user_data.get("amount",0)
    cat     = ctx.user_data.get("category","boshqa")
    label   = "💰 Kirim" if tx_type=="income" else "💸 Chiqim"
    text = (f"✅ *Tasdiqlang:*\n\n{label}\n"
            f"💵 Summa: *{fmt(amount)}*\n"
            f"📂 Kategoriya: *{cat}*\n"
            f"📅 {date.today().strftime('%d.%m.%Y')}")
    if ctx.user_data["note"]: text += f"\n📝 Izoh: _{ctx.user_data['note']}_"
    await update.message.reply_text(text, parse_mode="Markdown", reply_markup=confirm_ikb())
    return ST_CONFIRM

async def del_date_text(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    role = await guard(update)
    if not role: return ConversationHandler.END
    if not can_manage(role):
        await update.message.reply_text("❌ Ruxsat yo'q."); return ST_MENU
    txt = update.message.text.strip()
    try: datetime.strptime(txt, "%Y-%m-%d")
    except:
        await update.message.reply_text("❓ Format: `YYYY-MM-DD`", parse_mode="Markdown")
        return ST_DEL_DATE_INPUT
    # Show as inline — reuse _show_date_txs via fake callback
    txs = await api("get", f"/transactions/by-date/{txt}")
    if not txs:
        await update.message.reply_text(f"📭 *{txt}* da tranzaksiya yo'q.",
            parse_mode="Markdown", reply_markup=back_ikb(role))
        return ST_MENU
    income_txs  = [t for t in txs if t["type"]=="income"]
    expense_txs = [t for t in txs if t["type"]=="expense"]
    lines = [f"📅 *{txt}* sanasidagi tranzaksiyalar:\n"]
    for tx in txs:
        e = "💰" if tx["type"]=="income" else "💸"
        who = f" [{tx.get('added_by_name','?')}]" if tx.get("added_by_name") else ""
        lines.append(f"{e} #{tx['id']} — *{fmt(tx['amount'])}* | {tx['category']}{who}")
    lines.append(f"\n💰 Jami kirim: *{fmt(sum(t['amount'] for t in income_txs))}*")
    lines.append(f"💸 Jami chiqim: *{fmt(sum(t['amount'] for t in expense_txs))}*")
    ids_all    = ",".join(str(t["id"]) for t in txs)
    ids_income = ",".join(str(t["id"]) for t in income_txs)
    ids_expense= ",".join(str(t["id"]) for t in expense_txs)
    rows = [[InlineKeyboardButton(f"🗑 Hammasi ({len(txs)} ta)",       callback_data=f"del_all_{ids_all}")]]
    if income_txs:
        rows.append([InlineKeyboardButton(f"💰 Faqat kirim ({len(income_txs)} ta)", callback_data=f"del_income_{ids_income}")])
    if expense_txs:
        rows.append([InlineKeyboardButton(f"💸 Faqat chiqim ({len(expense_txs)} ta)",callback_data=f"del_expense_{ids_expense}")])
    rows.append([InlineKeyboardButton("🔢 Bitta ID",  callback_data="del_by_id")])
    rows.append([InlineKeyboardButton("🏠 Bosh menyu",callback_data="main_menu")])
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown",
                                    reply_markup=InlineKeyboardMarkup(rows))
    return ST_DEL_MAIN

async def del_id_text(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    role = await guard(update)
    if not role: return ConversationHandler.END
    if not can_manage(role):
        await update.message.reply_text("❌ Ruxsat yo'q."); return ST_MENU
    raw = update.message.text.strip()
    ids = [int(x) for x in re.findall(r"\d+", raw)]
    if not ids:
        await update.message.reply_text("❓ ID topilmadi. Misol: `42` yoki `42 55 78`",
            parse_mode="Markdown"); return ST_DEL_PICK_ID
    try:
        result = await api("post","/transactions/bulk-delete", json=ids)
        deleted = result.get("deleted",0)
        await update.message.reply_text(
            f"✅ *{deleted}* ta o'chirildi: {ids}",
            parse_mode="Markdown", reply_markup=back_ikb(role))
    except Exception as e:
        log.error(e); await update.message.reply_text("❌ Xatolik.", reply_markup=back_ikb(role))
    return ST_MENU

async def edit_cat_text(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    role = await guard(update)
    if not role: return ConversationHandler.END
    if not can_manage(role):
        await update.message.reply_text("❌ Ruxsat yo'q."); return ST_MENU
    new_name = update.message.text.strip().lower()
    if not new_name or len(new_name)>50:
        await update.message.reply_text("❓ Noto'g'ri nom."); return ST_EDIT_CAT_NAME
    old = ctx.user_data.get("editing_cat")
    if old:
        try:
            await api("put",f"/categories/{old}",json={"name":new_name,"color":"#6366f1"})
            await update.message.reply_text(f"✅ '{old}' → '{new_name}'", reply_markup=back_ikb(role))
        except: await update.message.reply_text("❌ Xatolik.", reply_markup=back_ikb(role))
    else:
        ctx.user_data["new_cat_name"] = new_name
        await update.message.reply_text(
            f"📂 *'{new_name}'* — qaysi tur?",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("💰 Kirim",   callback_data="newcat_type_income"),
                 InlineKeyboardButton("💸 Chiqim",  callback_data="newcat_type_expense")],
                [InlineKeyboardButton("🔄 Ikkalasi",callback_data="newcat_type_both")],
            ]))
        return ST_EDIT_CAT_NAME
    ctx.user_data.clear(); ctx.user_data["role"]=role
    return ST_MENU

async def add_admin_text(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Super admin yangi foydalanuvchi ID si kiritadi, keyin rol tanlaydi"""
    role = await guard(update)
    if not role or not is_super(role): return ConversationHandler.END
    raw = update.message.text.strip()
    if not raw.isdigit():
        await update.message.reply_text("❓ Faqat raqam (Telegram ID) yuboring."); return ST_ADD_ADMIN_ROLE
    uid2 = int(raw)
    ctx.user_data["new_user_id"] = uid2
    await update.message.reply_text(
        f"👤 `{uid2}` uchun rol tanlang:",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("1️⃣ Kirim/Chiqim qo'shish",  callback_data=f"rp|{uid2}|tx_only")],
            [InlineKeyboardButton("2️⃣ Faqat hisobot ko'rish",  callback_data=f"rp|{uid2}|report_only")],
            [InlineKeyboardButton("3️⃣ Hamma huquq (to'liq)",   callback_data=f"rp|{uid2}|full")],
            [InlineKeyboardButton("❌ Bekor",                   callback_data="super_users")],
        ]))
    return ST_ADD_ADMIN_ROLE

# ─── Import file ──────────────────────────────────────────────────────────────
async def import_file(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    role = await guard(update)
    if not role: return ConversationHandler.END
    if not can_manage(role):
        await update.message.reply_text("❌ Ruxsat yo'q."); return ST_MENU
    doc = update.message.document
    if not doc or not doc.file_name.lower().endswith(".csv"):
        await update.message.reply_text("❌ Faqat .csv fayl yuboring."); return ST_IMPORT_FILE
    f = await ctx.bot.get_file(doc.file_id)
    buf = io.BytesIO(); await f.download_to_memory(buf)
    data = buf.getvalue()
    ctx.user_data["import_file_data"] = data
    ctx.user_data["import_file_name"] = doc.file_name
    try: rc = len(list(csv.DictReader(io.StringIO(data.decode("utf-8-sig")))))
    except: rc="?"
    try:
        prev = await api("get","/import/preview?period=month")
        existing = prev.get("count",0)
        if existing > 0:
            await update.message.reply_text(
                f"📥 *{rc}* ta tranzaksiya bor\n\n"
                f"⚠️ Bu oyda *{existing}* ta mavjud. Qanday qo'shamiz?",
                parse_mode="Markdown", reply_markup=import_conflict_ikb())
            return ST_IMPORT_CONFIRM
        else:
            async with httpx.AsyncClient() as c:
                r = await c.post(f"{API_URL}/import?mode=append",
                                 files={"file":(doc.file_name,io.BytesIO(data),"text/csv")},timeout=30)
                r.raise_for_status(); res=r.json()
            await update.message.reply_text(
                f"✅ *{res['inserted']}* ta qo'shildi!",
                parse_mode="Markdown", reply_markup=back_ikb(role))
            ctx.user_data.clear(); ctx.user_data["role"]=role; return ST_MENU
    except Exception as e:
        log.error(e); await update.message.reply_text("❌ Xatolik.", reply_markup=back_ikb(role))
    return ST_MENU

# ─── Reply keyboard text ──────────────────────────────────────────────────────

async def category_text_handler(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """ST_CATEGORY holatida user matn yozsa — kirim/chiqim aniqlaydi"""
    role = await guard(update)
    if not role: return ConversationHandler.END

    text = update.message.text.strip().lower()
    uid  = update.effective_user.id

    INCOME_WORDS  = ["kirim","income","kirdi","tushdi","keldi","да","прибыль","доход","приход"]
    EXPENSE_WORDS = ["chiqim","expense","xarajat","chiqdi","ketdi","расход","затрата","расход"]

    stored_amount = ctx.user_data.get("amount")

    # Agar summa saqlanmagan — yana summa so'rash kerak
    if not stored_amount:
        if any(w in text for w in INCOME_WORDS):
            ctx.user_data["tx_type"] = "income"
        elif any(w in text for w in EXPENSE_WORDS):
            ctx.user_data["tx_type"] = "expense"
        await update.message.reply_text(
            "💵 *Summani yozing:*\n\nMisol: `500000` | `1.5mln` | `200k`",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Bekor", callback_data="cancel")]]))
        return ST_AMOUNT

    # Summa bor — faqat tur kerak
    if any(w in text for w in INCOME_WORDS):
        tx_type = "income"
    elif any(w in text for w in EXPENSE_WORDS):
        tx_type = "expense"
    else:
        # Tushunmadik — qayta so'raymiz
        label = f"*{fmt(stored_amount)}*"
        await update.message.reply_text(
            f"💰 {label} — bu kirimmi yoki chiqim?\n\n"
            "«kirim» yoki «chiqim» deb yozing, yoki tugmani bosing:",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton(f"💰 Kirim", callback_data="add_income"),
                 InlineKeyboardButton(f"💸 Chiqim", callback_data="add_expense")],
                [InlineKeyboardButton("❌ Bekor", callback_data="cancel")],
            ]))
        return ST_CATEGORY

    ctx.user_data["tx_type"] = tx_type
    label = "💰 Kirim" if tx_type == "income" else "💸 Chiqim"
    await update.message.reply_text(
        f"{label}: *{fmt(stored_amount)}*\n\n📂 Kategoriyani tanlang:",
        parse_mode="Markdown",
        reply_markup=await cat_ikb(tx_type))
    return ST_CATEGORY

async def reply_kb_handler(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    role = await guard(update)
    if not role: return ConversationHandler.END
    ctx.user_data["role"] = role
    txt = update.message.text
    uid = update.effective_user.id
    if txt == "🏠 Bosh menyu":
        ctx.user_data.clear(); ctx.user_data["role"]=role
        await update.message.reply_text("Amalni tanlang:", reply_markup=main_menu_ikb(role))
        return ST_MENU
    if txt == "👤 Profil":
        await show_profile(update, ctx); return ST_MENU
    # Try smart intent detection for any other text
    if can_add_tx(role):
        result = await detect_intent_and_process(update.message, ctx, txt, role, uid, update.effective_user)
        if result is not None: return result
    if txt == "⚙️ Admin panel":
        if not can_manage(role) and not is_super(role):
            await update.message.reply_text("❌ Ruxsat yo'q."); return ST_MENU
        user = update.effective_user
        full = f"{user.first_name or ''} {user.last_name or ''}".strip()
        role_label = {"super_admin":"👑 Super Admin","full":"3️⃣ To'liq","report_only":"2️⃣ Hisobot","tx_only":"1️⃣ Kirim/Chiqim"}.get(role,"?")
        rows = []
        if is_super(role):
            rows.append([InlineKeyboardButton("👥 Adminlar boshqaruvi", callback_data="super_users")])
        if can_manage(role):
            rows.append([InlineKeyboardButton("🗑 O'chirish",          callback_data="del_main")])
            rows.append([InlineKeyboardButton("✏️ Kategoriyalar",       callback_data="edit_cats")])
            rows.append([InlineKeyboardButton("📥 Import",              callback_data="import_start")])
        rows.append([InlineKeyboardButton("🏠 Bosh menyu",             callback_data="main_menu")])
        await update.message.reply_text(
            f"⚙️ *Admin panel*\n\n👤 {full}\n🔑 {role_label}",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(rows))
        return ST_MENU
    await update.message.reply_text(
        random.choice(UNCLEAR_MSGS) + "\n\nYoki quyidagi tugmalardan foydalaning:",
        reply_markup=main_menu_ikb(role))
    return ST_MENU


# ─── Edit TX text handlers ────────────────────────────────────────────────────
async def edit_tx_amount_input(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    role = await guard(update)
    if not role: return ConversationHandler.END
    amount = extract_amount(update.message.text.strip())
    if not amount:
        await update.message.reply_text("❓ Summani tushunmadim. Misol: `500000` yoki `1.5mln`",
            parse_mode="Markdown")
        return ST_EDIT_TX_AMOUNT
    tx = ctx.user_data.get("edit_tx", {})
    tx_id = tx.get("id")
    if not tx_id:
        await update.message.reply_text("❌ Xatolik. Qaytadan boshlang.", reply_markup=back_ikb(role))
        return ST_MENU
    try:
        await api("put", f"/transactions/{tx_id}", {**tx, "amount": amount})
        ctx.user_data["edit_tx"] = {**tx, "amount": amount}
        await update.message.reply_text(
            f"✅ Summa yangilandi: *{fmt(amount)}*",
            parse_mode="Markdown", reply_markup=back_ikb(role))
    except Exception as e:
        log.error(e); await update.message.reply_text("❌ Xatolik.", reply_markup=back_ikb(role))
    return ST_MENU

async def edit_tx_note_input(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    role = await guard(update)
    if not role: return ConversationHandler.END
    note = update.message.text.strip()
    if note.lower() in ("yo'q","yoq","-","o'chir","delete","clear","tozala"): note = ""
    tx = ctx.user_data.get("edit_tx", {})
    tx_id = ctx.user_data.get("edit_tx_id") or tx.get("id")
    if not tx_id:
        await update.message.reply_text("❌ Xatolik.", reply_markup=back_ikb(role))
        return ST_MENU
    try:
        await api("put", f"/transactions/{tx_id}", {**tx, "note": note, "amount": float(tx.get("amount",0))})
        ctx.user_data["edit_tx"] = {**tx, "note": note}
        msg = f"✅ Izoh yangilandi: _{note}_" if note else "✅ Izoh tozalandi."
        await update.message.reply_text(msg, parse_mode="Markdown", reply_markup=back_ikb(role))
    except Exception as e:
        log.error(e); await update.message.reply_text("❌ Xatolik.", reply_markup=back_ikb(role))
    return ST_MENU

# ─── /myid ────────────────────────────────────────────────────────────────────
async def myid_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    await update.message.reply_text(f"🆔 Sizning Telegram ID: `{uid}`", parse_mode="Markdown")

# ─── Main ─────────────────────────────────────────────────────────────────────
def main():
    if not BOT_TOKEN:
        log.error("BOT_TOKEN yo'q!"); return
    if not SUPER_ADMIN_ID:
        log.warning("SUPER_ADMIN_ID sozlanmagan! .env ga SUPER_ADMIN_ID=123456 qo'shing.")
    log.info(f"Super admin: {SUPER_ADMIN_ID}")

    app = Application.builder().token(BOT_TOKEN).build()

    conv = ConversationHandler(
        entry_points=[
            CommandHandler("start", start),
            MessageHandler(filters.VOICE, handle_voice),
            MessageHandler(filters.Regex("^(🏠 Bosh menyu|👤 Profil|⚙️ Admin panel)$"), reply_kb_handler),
        ],
        states={
            ST_MENU: [
                CallbackQueryHandler(btn),
                MessageHandler(filters.VOICE, handle_voice),
                MessageHandler(filters.Regex("^(🏠 Bosh menyu|👤 Profil|⚙️ Admin panel)$"), reply_kb_handler),
            ],
            ST_AMOUNT: [
                MessageHandler(filters.VOICE, handle_voice),
                MessageHandler(filters.TEXT & ~filters.COMMAND, amount_input),
                CallbackQueryHandler(btn),
            ],
            ST_CATEGORY: [
                MessageHandler(filters.VOICE, handle_voice),
                MessageHandler(filters.TEXT & ~filters.COMMAND, category_text_handler),
                CallbackQueryHandler(btn),
            ],
            ST_CUSTOM_CAT: [
                MessageHandler(filters.VOICE, handle_voice),
                MessageHandler(filters.TEXT & ~filters.COMMAND, custom_cat_input),
                CallbackQueryHandler(btn),
            ],
            ST_NOTE: [
                MessageHandler(filters.VOICE, handle_voice),
                MessageHandler(filters.TEXT & ~filters.COMMAND, note_input),
                CallbackQueryHandler(btn),
            ],
            ST_CONFIRM: [
                MessageHandler(filters.VOICE, handle_voice),
                CallbackQueryHandler(btn),
            ],
            ST_DEL_MAIN: [
                CallbackQueryHandler(btn),
                MessageHandler(filters.Regex("^(🏠 Bosh menyu|👤 Profil|⚙️ Admin panel)$"), reply_kb_handler),
            ],
            ST_DEL_DATE_INPUT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, del_date_text),
                CallbackQueryHandler(btn),
            ],
            ST_DEL_PICK_ID: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, del_id_text),
                CallbackQueryHandler(btn),
            ],
            ST_IMPORT_FILE: [
                MessageHandler(filters.Document.ALL, import_file),
                CallbackQueryHandler(btn),
            ],
            ST_IMPORT_CONFIRM: [CallbackQueryHandler(btn)],
            ST_EDIT_CAT_NAME: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, edit_cat_text),
                CallbackQueryHandler(btn),
            ],
            ST_ADD_ADMIN_ROLE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, add_admin_text),
                CallbackQueryHandler(btn),
            ],
            ST_EDIT_TX_AMOUNT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, edit_tx_amount_input),
                CallbackQueryHandler(btn),
            ],
            ST_EDIT_TX_CATEGORY: [CallbackQueryHandler(btn)],
            ST_EDIT_TX_NOTE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, edit_tx_note_input),
                CallbackQueryHandler(btn),
            ],
        },
        fallbacks=[
            CommandHandler("start", start),
            MessageHandler(filters.Regex("^(🏠 Bosh menyu|👤 Profil|⚙️ Admin panel)$"), reply_kb_handler),
            MessageHandler(filters.TEXT & ~filters.COMMAND, reply_kb_handler),
        ],
        per_message=False,
        allow_reentry=True,
    )

    app.add_handler(conv)
    app.add_handler(CommandHandler("myid", myid_cmd))

    log.info(f"Bot ishga tushdi ✅ | API_URL={API_URL} | SUPER_ADMIN={SUPER_ADMIN_ID}")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
