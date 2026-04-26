from fastapi import FastAPI, HTTPException, Query, UploadFile, File, Header, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, FileResponse, HTMLResponse
from pydantic import BaseModel
from typing import Optional, List
from datetime import date, datetime, timedelta
import sqlite3, os, io, csv, hmac, hashlib, base64, json, time as _time, pathlib
from pathlib import Path
from dotenv import load_dotenv

# .env faylini yuklash — finance-bot/.env
_env_path = Path(__file__).parent.parent / ".env"
load_dotenv(_env_path)

app = FastAPI(title="Finance Manager API")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# ─── SPA Middleware — brauzer so'rovlarini dashboard ga yo'naltirish ──────────
# Faqat API yo'llari (bot ishlatadigan)
_API_PREFIXES = (
    "/auth/", "/transactions", "/report", "/analytics", "/categories",
    "/users", "/export", "/import", "/health", "/admin",
)

@app.middleware("http")
async def spa_middleware(request: Request, call_next):
    """
    Browser GET so'rovi → dashboard.html (login page ichida)
    Bot/JS API so'rovi → oddiy JSON javob
    """
    if request.method == "GET":
        accept = request.headers.get("accept", "")
        path   = request.url.path
        # Browser har doim "text/html" qabul qiladi
        is_browser = "text/html" in accept
        # Auth endpoint — har doim JSON
        is_auth = path.startswith("/auth/") or path == "/health"
        if is_browser and not is_auth:
            # Browser orqali har qanday URL → dashboard.html ko'rsatamiz
            # Dashboard JS o'zi /auth/me orqali tekshiradi, login ko'rsatadi
            _dash = pathlib.Path(__file__).parent / "dashboard.html"
            if _dash.exists():
                return FileResponse(_dash)
    return await call_next(request)

DB_PATH         = os.getenv("DB_PATH", "finance.db")
SUPER_ADMIN_ID  = int(os.getenv("SUPER_ADMIN_ID", "0"))
JWT_SECRET      = os.getenv("JWT_SECRET", "change-me-please-32chars-minimum!")
SUPER_WEB_PASS  = os.getenv("SUPER_WEB_PASSWORD", "superadmin123")

print(f"[Config] SUPER_ADMIN_ID={SUPER_ADMIN_ID}, .env loaded from {_env_path}")

# ─── DB ───────────────────────────────────────────────────────────────────────
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS transactions (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            type          TEXT NOT NULL CHECK(type IN ('income','expense')),
            amount        REAL NOT NULL,
            category      TEXT NOT NULL DEFAULT 'boshqa',
            note          TEXT DEFAULT '',
            date          TEXT NOT NULL,
            created_at    TEXT DEFAULT (datetime('now')),
            added_by_id   INTEGER DEFAULT 0,
            added_by_name TEXT DEFAULT ''
        );
        CREATE TABLE IF NOT EXISTS categories (
            id    INTEGER PRIMARY KEY AUTOINCREMENT,
            name  TEXT UNIQUE NOT NULL,
            type  TEXT NOT NULL CHECK(type IN ('income','expense','both')),
            color TEXT DEFAULT '#6366f1'
        );
        CREATE TABLE IF NOT EXISTS allowed_users (
            user_id           INTEGER PRIMARY KEY,
            username          TEXT DEFAULT '',
            full_name         TEXT DEFAULT '',
            role              TEXT DEFAULT 'user',
            web_password_hash TEXT DEFAULT '',
            added_at          TEXT DEFAULT (datetime('now'))
        );
        INSERT OR IGNORE INTO categories (name,type,color) VALUES
            ('sotuv','income','#10b981'),('xizmat','income','#06b6d4'),
            ('investitsiya','income','#8b5cf6'),('boshqa kirim','income','#64748b'),
            ('maosh','expense','#f59e0b'),('ijara','expense','#ef4444'),
            ('transport','expense','#f97316'),('kommunal','expense','#ec4899'),
            ('oziq-ovqat','expense','#84cc16'),('reklama','expense','#a78bfa'),
            ('logistika','expense','#38bdf8'),('boshqa','both','#94a3b8');
    """)
    conn.commit(); conn.close()

def migrate_db():
    conn = get_db()
    cols = [r[1] for r in conn.execute("PRAGMA table_info(transactions)").fetchall()]
    if "added_by_id"   not in cols: conn.execute("ALTER TABLE transactions ADD COLUMN added_by_id INTEGER DEFAULT 0")
    if "added_by_name" not in cols: conn.execute("ALTER TABLE transactions ADD COLUMN added_by_name TEXT DEFAULT ''")
    ucols = [r[1] for r in conn.execute("PRAGMA table_info(allowed_users)").fetchall()]
    if "role"              not in ucols: conn.execute("ALTER TABLE allowed_users ADD COLUMN role TEXT DEFAULT 'user'")
    if "full_name"         not in ucols: conn.execute("ALTER TABLE allowed_users ADD COLUMN full_name TEXT DEFAULT ''")
    if "web_password_hash" not in ucols: conn.execute("ALTER TABLE allowed_users ADD COLUMN web_password_hash TEXT DEFAULT ''")
    conn.commit(); conn.close()

init_db(); migrate_db()

# ─── Auth helpers ─────────────────────────────────────────────────────────────
def _hash(p: str) -> str:
    return hashlib.sha256(p.encode()).hexdigest()

def _make_token(uid: int, role: str, name: str) -> str:
    payload = {"uid": uid, "role": role, "name": name, "exp": int(_time.time()) + 7*24*3600}
    data = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")
    sig  = hmac.new(JWT_SECRET.encode(), data.encode(), hashlib.sha256).hexdigest()
    return f"{data}.{sig}"

def _decode_token(token: str) -> dict:
    try:
        data, sig = token.rsplit(".", 1)
        expected  = hmac.new(JWT_SECRET.encode(), data.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(sig, expected): raise ValueError("bad sig")
        pad     = "=" * (-len(data) % 4)
        payload = json.loads(base64.urlsafe_b64decode(data + pad))
        if payload["exp"] < _time.time(): raise ValueError("expired")
        return payload
    except Exception as e:
        raise HTTPException(401, f"Token yaroqsiz: {e}")

def require_token(authorization: str = Header(None)) -> dict:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "Token kerak")
    return _decode_token(authorization[7:])

def require_super(authorization: str = Header(None)) -> dict:
    payload = require_token(authorization)
    if payload.get("role") != "super_admin":
        raise HTTPException(403, "Faqat super admin")
    return payload

# ─── Models ───────────────────────────────────────────────────────────────────
class TransactionIn(BaseModel):
    type: str; amount: float; category: str="boshqa"; note: str=""; date: str=""
    added_by_id: int=0; added_by_name: str=""

class CategoryIn(BaseModel):
    name: str; type: str; color: str="#6366f1"

class CategoryUpdate(BaseModel):
    name: str; color: str="#6366f1"

class UserIn(BaseModel):
    user_id: int; username: str=""; full_name: str=""; role: str="user"

class NameUpdate(BaseModel):
    username: str=""; full_name: str=""

class LoginRequest(BaseModel):
    username: str; password: str

class SetPasswordRequest(BaseModel):
    user_id: int; password: str

# ─── AUTH ─────────────────────────────────────────────────────────────────────
@app.post("/auth/login")
def login(req: LoginRequest):
    # Super admin
    if req.username.strip() in ("superadmin", str(SUPER_ADMIN_ID)):
        if req.password != SUPER_WEB_PASS:
            raise HTTPException(401, "Parol noto'g'ri")
        token = _make_token(SUPER_ADMIN_ID, "super_admin", "Super Admin")
        return {"token": token, "role": "super_admin", "name": "Super Admin", "user_id": SUPER_ADMIN_ID}
    try:
        uid = int(req.username.strip())
    except:
        raise HTTPException(401, "Foydalanuvchi topilmadi")
    conn = get_db()
    user = conn.execute("SELECT * FROM allowed_users WHERE user_id=?", (uid,)).fetchone()
    conn.close()
    if not user: raise HTTPException(401, "Foydalanuvchi topilmadi")
    stored = user["web_password_hash"] or ""
    if not stored: raise HTTPException(401, "Web parol belgilanmagan. Admin bilan bog'laning.")
    if stored != _hash(req.password): raise HTTPException(401, "Parol noto'g'ri")
    name  = (user["full_name"] or user["username"] or str(uid)).strip()
    token = _make_token(uid, user["role"], name)
    return {"token": token, "role": user["role"], "name": name, "user_id": uid}

@app.get("/auth/me")
def get_me(authorization: str = Header(None)):
    return require_token(authorization)

@app.post("/auth/set-password")
def set_web_password(req: SetPasswordRequest, authorization: str = Header(None)):
    require_super(authorization)
    conn = get_db()
    conn.execute("UPDATE allowed_users SET web_password_hash=? WHERE user_id=?",
                 (_hash(req.password), req.user_id))
    conn.commit(); conn.close()
    return {"ok": True}

# ─── Users ────────────────────────────────────────────────────────────────────
@app.get("/users")
def list_users():
    conn=get_db(); rows=conn.execute("SELECT * FROM allowed_users ORDER BY role DESC,added_at").fetchall()
    conn.close(); return [dict(r) for r in rows]

@app.post("/users")
def add_user(u: UserIn):
    conn=get_db()
    conn.execute("INSERT OR REPLACE INTO allowed_users (user_id,username,full_name,role) VALUES (?,?,?,?)",
                 (u.user_id,u.username,u.full_name,u.role))
    conn.commit(); conn.close(); return {"ok":True}

@app.delete("/users/{user_id}")
def remove_user(user_id: int):
    conn=get_db(); conn.execute("DELETE FROM allowed_users WHERE user_id=?",(user_id,))
    conn.commit(); conn.close(); return {"ok":True}

@app.get("/users/{user_id}/check")
def check_user(user_id: int):
    conn=get_db()
    row=conn.execute("SELECT * FROM allowed_users WHERE user_id=?",(user_id,)).fetchone()
    conn.close()
    if row: return {"allowed":True,"open_mode":False,"role":row["role"]}
    return {"allowed":False,"open_mode":False,"role":None}

@app.patch("/users/{user_id}/name")
def update_user_name(user_id: int, upd: NameUpdate):
    conn=get_db()
    conn.execute("UPDATE allowed_users SET username=?,full_name=? WHERE user_id=?",(upd.username,upd.full_name,user_id))
    conn.commit(); conn.close(); return {"ok":True}

# ─── Transactions ─────────────────────────────────────────────────────────────
@app.get("/transactions")
def list_transactions(
    limit:int=Query(50,ge=1,le=1000), offset:int=0,
    type:Optional[str]=None, category:Optional[str]=None,
    date_from:Optional[str]=None, date_to:Optional[str]=None,
    search:Optional[str]=None, added_by_id:Optional[int]=None,
):
    conn=get_db(); q="SELECT * FROM transactions WHERE 1=1"; p=[]
    if type:        q+=" AND type=?";                        p.append(type)
    if category:    q+=" AND category=?";                    p.append(category)
    if date_from:   q+=" AND date>=?";                       p.append(date_from)
    if date_to:     q+=" AND date<=?";                       p.append(date_to)
    if search:      q+=" AND (note LIKE ? OR category LIKE ?)"; p+=[f"%{search}%"]*2
    if added_by_id: q+=" AND added_by_id=?";                 p.append(added_by_id)
    q+=" ORDER BY date DESC,created_at DESC LIMIT ? OFFSET ?"; p+=[limit,offset]
    rows=conn.execute(q,p).fetchall(); conn.close()
    return [dict(r) for r in rows]

@app.post("/transactions")
def create_transaction(tx: TransactionIn):
    if tx.type not in ("income","expense"): raise HTTPException(400,"bad type")
    if tx.amount<=0: raise HTTPException(400,"bad amount")
    conn=get_db()
    cur=conn.execute("INSERT INTO transactions (type,amount,category,note,date,added_by_id,added_by_name) VALUES (?,?,?,?,?,?,?)",
        (tx.type,tx.amount,tx.category,tx.note,tx.date or date.today().isoformat(),tx.added_by_id,tx.added_by_name))
    conn.commit()
    row=conn.execute("SELECT * FROM transactions WHERE id=?",(cur.lastrowid,)).fetchone()
    conn.close(); return dict(row)

@app.put("/transactions/{tx_id}")
def update_transaction(tx_id:int, tx:TransactionIn):
    conn=get_db()
    ex=conn.execute("SELECT * FROM transactions WHERE id=?",(tx_id,)).fetchone()
    if not ex: raise HTTPException(404,"not found")
    conn.execute("UPDATE transactions SET type=?,amount=?,category=?,note=?,date=? WHERE id=?",
                 (tx.type,tx.amount,tx.category,tx.note,tx.date or ex["date"],tx_id))
    conn.commit()
    row=conn.execute("SELECT * FROM transactions WHERE id=?",(tx_id,)).fetchone()
    conn.close(); return dict(row)

@app.delete("/transactions/{tx_id}")
def delete_transaction(tx_id:int):
    conn=get_db()
    if not conn.execute("SELECT 1 FROM transactions WHERE id=?",(tx_id,)).fetchone():
        raise HTTPException(404,"not found")
    conn.execute("DELETE FROM transactions WHERE id=?",(tx_id,))
    conn.commit(); conn.close(); return {"ok":True}

@app.get("/transactions/by-date/{target_date}")
def get_by_date(target_date:str):
    conn=get_db()
    rows=conn.execute("SELECT * FROM transactions WHERE date=? ORDER BY created_at",(target_date,)).fetchall()
    conn.close(); return [dict(r) for r in rows]

@app.post("/transactions/bulk-delete")
def delete_by_ids(ids: List[int]):
    if not ids: return {"ok":True,"deleted":0}
    conn=get_db()
    cur=conn.execute(f"DELETE FROM transactions WHERE id IN ({','.join('?'*len(ids))})",ids)
    conn.commit(); deleted=cur.rowcount; conn.close()
    return {"ok":True,"deleted":deleted}

@app.get("/transactions/dates")
def get_transaction_dates():
    conn=get_db()
    rows=conn.execute("""SELECT date,COUNT(*) as total,
               SUM(CASE WHEN type='income' THEN amount ELSE 0 END) as income_sum,
               SUM(CASE WHEN type='expense' THEN amount ELSE 0 END) as expense_sum
        FROM transactions GROUP BY date ORDER BY date DESC LIMIT 60""").fetchall()
    conn.close(); return [dict(r) for r in rows]

# ─── Report ───────────────────────────────────────────────────────────────────
def get_date_range(period):
    today=date.today()
    if period=="today": return today.isoformat(),today.isoformat()
    if period=="week":  s=today-timedelta(days=today.weekday()); return s.isoformat(),today.isoformat()
    if period=="month": return today.replace(day=1).isoformat(),today.isoformat()
    if period=="year":  return today.replace(month=1,day=1).isoformat(),today.isoformat()
    return today.replace(day=1).isoformat(),today.isoformat()

def get_prev_range(period):
    today=date.today()
    if period=="month":
        f=today.replace(day=1); lp=f-timedelta(days=1)
        return lp.replace(day=1).isoformat(),lp.isoformat()
    if period=="week":
        s=today-timedelta(days=today.weekday()); ep=s-timedelta(days=1)
        return (ep-timedelta(days=6)).isoformat(),ep.isoformat()
    return get_date_range(period)

@app.get("/report")
def get_report(period:str="month"):
    conn=get_db(); df,dt=get_date_range(period); pdf,pdt=get_prev_range(period)
    try:
        def totals(a,b):
            i=conn.execute("SELECT COALESCE(SUM(amount),0) FROM transactions WHERE type='income' AND date>=? AND date<=?",(a,b)).fetchone()[0]
            e=conn.execute("SELECT COALESCE(SUM(amount),0) FROM transactions WHERE type='expense' AND date>=? AND date<=?",(a,b)).fetchone()[0]
            return i,e
        income,expense=totals(df,dt); pi,pe=totals(pdf,pdt)
        def cats(tx_type,total):
            rows=conn.execute("SELECT category as name,SUM(amount) as amount FROM transactions WHERE type=? AND date>=? AND date<=? GROUP BY category ORDER BY amount DESC",(tx_type,df,dt)).fetchall()
            return [{"name":r["name"],"amount":r["amount"],"pct":round(r["amount"]/total*100,1) if total else 0} for r in rows]
        inc_cats=cats("income",income); exp_cats=cats("expense",expense)
        daily=conn.execute("SELECT date,type,SUM(amount) as amount FROM transactions WHERE date>=? AND date<=? GROUP BY date,type ORDER BY date",(df,dt)).fetchall()
        daily_list=[dict(r) for r in daily]
    finally: conn.close()
    return {"period":period,"date_from":df,"date_to":dt,"income":income,"expense":expense,"net":income-expense,
            "prev_income":pi,"prev_expense":pe,"prev_net":pi-pe,
            "income_categories":inc_cats,"expense_categories":exp_cats,
            "top_categories":inc_cats[:5],"top_expense_categories":exp_cats[:5],"daily":daily_list}

@app.get("/analytics")
def get_analytics():
    conn=get_db()
    monthly=conn.execute("SELECT strftime('%Y-%m',date) as month,SUM(CASE WHEN type='income' THEN amount ELSE 0 END) as income,SUM(CASE WHEN type='expense' THEN amount ELSE 0 END) as expense FROM transactions WHERE date>=date('now','-6 months') GROUP BY month ORDER BY month").fetchall()
    ci=conn.execute("SELECT category,SUM(amount) as total FROM transactions WHERE type='income' GROUP BY category ORDER BY total DESC").fetchall()
    ce=conn.execute("SELECT category,SUM(amount) as total FROM transactions WHERE type='expense' GROUP BY category ORDER BY total DESC").fetchall()
    total=conn.execute("SELECT COUNT(*) FROM transactions").fetchone()[0]
    conn.close()
    return {"monthly":[dict(r) for r in monthly],"category_income":[dict(r) for r in ci],"category_expense":[dict(r) for r in ce],"total_transactions":total}

@app.get("/admin/stats")
def admin_stats():
    conn=get_db()
    rows=conn.execute("SELECT added_by_id,added_by_name,COUNT(*) as tx_count,SUM(CASE WHEN type='income' THEN amount ELSE 0 END) as income,SUM(CASE WHEN type='expense' THEN amount ELSE 0 END) as expense,MAX(date) as last_date FROM transactions WHERE added_by_id!=0 GROUP BY added_by_id ORDER BY tx_count DESC").fetchall()
    conn.close(); return [dict(r) for r in rows]

# ─── Export/Import ────────────────────────────────────────────────────────────
@app.get("/export")
def export_transactions(period:str="month"):
    conn=get_db(); df,dt=get_date_range(period)
    rows=conn.execute("SELECT id,type,amount,category,note,date,added_by_name,created_at FROM transactions WHERE date>=? AND date<=? ORDER BY date DESC",(df,dt)).fetchall()
    conn.close()
    out=io.StringIO(); w=csv.writer(out)
    w.writerow(["ID","Tur","Summa (so'm)","Kategoriya","Izoh","Sana","Kim qo'shdi","Vaqt"])
    for r in rows:
        w.writerow([r["id"],"Kirim" if r["type"]=="income" else "Chiqim",r["amount"],r["category"],r["note"],r["date"],r["added_by_name"],r["created_at"]])
    out.seek(0)
    fname=f"finance_{period}_{df}_to_{dt}.csv"
    return StreamingResponse(io.BytesIO(out.getvalue().encode("utf-8-sig")),media_type="text/csv",
                             headers={"Content-Disposition":f"attachment; filename={fname}"})

@app.post("/import")
async def import_transactions(file:UploadFile=File(...), mode:str="append"):
    content=await file.read()
    try: text=content.decode("utf-8-sig")
    except: text=content.decode("utf-8")
    reader=csv.DictReader(io.StringIO(text)); rows=list(reader)
    conn=get_db()
    if mode=="replace": conn.execute("DELETE FROM transactions")
    inserted=0; errors=[]
    for i,row in enumerate(rows,1):
        try:
            tx_type="income" if row.get("Tur","").strip() in ("Kirim","income") else "expense"
            amt=float(str(row.get("Summa (so'm)",row.get("amount","0"))).replace(" ","").replace(",","."))
            cat=row.get("Kategoriya",row.get("category","boshqa")).strip() or "boshqa"
            note=row.get("Izoh",row.get("note","")).strip()
            dt=row.get("Sana",row.get("date",date.today().isoformat())).strip() or date.today().isoformat()
            by_name=row.get("Kim qo'shdi","import").strip()
            conn.execute("INSERT INTO transactions (type,amount,category,note,date,added_by_name) VALUES (?,?,?,?,?,?)",(tx_type,amt,cat,note,dt,by_name))
            inserted+=1
        except Exception as e: errors.append(f"Qator {i}: {e}")
    conn.commit(); conn.close()
    return {"ok":True,"inserted":inserted,"errors":errors[:5],"mode":mode}

@app.get("/import/preview")
def preview_import(period:str="month"):
    conn=get_db(); df,dt=get_date_range(period)
    count=conn.execute("SELECT COUNT(*) FROM transactions WHERE date>=? AND date<=?",(df,dt)).fetchone()[0]
    income=conn.execute("SELECT COALESCE(SUM(amount),0) FROM transactions WHERE type='income' AND date>=? AND date<=?",(df,dt)).fetchone()[0]
    expense=conn.execute("SELECT COALESCE(SUM(amount),0) FROM transactions WHERE type='expense' AND date>=? AND date<=?",(df,dt)).fetchone()[0]
    conn.close(); return {"period":period,"date_from":df,"date_to":dt,"count":count,"income":income,"expense":expense}

# ─── Categories ───────────────────────────────────────────────────────────────
@app.get("/categories")
def list_categories():
    conn=get_db(); rows=conn.execute("SELECT * FROM categories ORDER BY type,name").fetchall()
    conn.close(); return [dict(r) for r in rows]

@app.post("/categories")
def create_category(cat:CategoryIn):
    conn=get_db()
    try:
        conn.execute("INSERT INTO categories (name,type,color) VALUES (?,?,?)",(cat.name.lower().strip(),cat.type,cat.color))
        conn.commit()
    except sqlite3.IntegrityError: raise HTTPException(409,"already exists")
    finally: conn.close()
    return {"ok":True}

@app.put("/categories/{cat_name}")
def update_category(cat_name:str, upd:CategoryUpdate):
    conn=get_db()
    new_name=upd.name.lower().strip()
    conn.execute("UPDATE categories SET name=?,color=? WHERE name=?",(new_name,upd.color,cat_name))
    conn.execute("UPDATE transactions SET category=? WHERE category=?",(new_name,cat_name))
    conn.commit(); conn.close(); return {"ok":True}

@app.delete("/categories/{cat_name}")
def delete_category(cat_name:str):
    conn=get_db(); conn.execute("DELETE FROM categories WHERE name=?",(cat_name,))
    conn.commit(); conn.close(); return {"ok":True}

@app.get("/health")
def health(): return {"status":"ok","time":datetime.now().isoformat()}

# ─── Dashboard ────────────────────────────────────────────────────────────────
# Middleware orqali barcha brauzer so'rovlari dashboard.html ga yo'naltiriladi.
# Qo'shimcha route kerak emas — middleware boshqaradi.
