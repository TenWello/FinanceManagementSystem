from fastapi import FastAPI, HTTPException, Query, UploadFile, File, Header, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, FileResponse, JSONResponse
from pydantic import BaseModel
from typing import Optional, List
from datetime import date, datetime, timedelta
from pathlib import Path
from dotenv import load_dotenv
import sqlite3, os, io, csv, hmac, hashlib, base64, json, time as _time

load_dotenv(Path(__file__).parent.parent / ".env")

app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

DB_PATH        = os.getenv("DB_PATH", "/data/finance.db")
SUPER_ADMIN_ID = int(os.getenv("SUPER_ADMIN_ID", "0"))
JWT_SECRET     = os.getenv("JWT_SECRET", "secret-key-32-chars-minimum-here")
SUPER_WEB_PASS = os.getenv("SUPER_WEB_PASSWORD", "admin123")

print(f"DB: {DB_PATH}, SUPER_ADMIN: {SUPER_ADMIN_ID}")

def get_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True) if os.path.dirname(DB_PATH) else None
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            type TEXT NOT NULL,
            amount REAL NOT NULL,
            category TEXT DEFAULT 'boshqa',
            note TEXT DEFAULT '',
            date TEXT NOT NULL,
            created_at TEXT DEFAULT (datetime('now')),
            added_by_id INTEGER DEFAULT 0,
            added_by_name TEXT DEFAULT ''
        );
        CREATE TABLE IF NOT EXISTS categories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            type TEXT NOT NULL,
            color TEXT DEFAULT '#6366f1'
        );
        CREATE TABLE IF NOT EXISTS allowed_users (
            user_id INTEGER PRIMARY KEY,
            username TEXT DEFAULT '',
            full_name TEXT DEFAULT '',
            role TEXT DEFAULT 'user',
            web_password_hash TEXT DEFAULT '',
            added_at TEXT DEFAULT (datetime('now'))
        );
        INSERT OR IGNORE INTO categories (name,type,color) VALUES
            ('sotuv','income','#10b981'),('xizmat','income','#06b6d4'),
            ('investitsiya','income','#8b5cf6'),('boshqa kirim','income','#64748b'),
            ('maosh','expense','#f59e0b'),('ijara','expense','#ef4444'),
            ('transport','expense','#f97316'),('kommunal','expense','#ec4899'),
            ('oziq-ovqat','expense','#84cc16'),('reklama','expense','#a78bfa'),
            ('logistika','expense','#38bdf8'),('boshqa','both','#94a3b8');
    """)
    # migrate
    cols = [r[1] for r in conn.execute("PRAGMA table_info(transactions)").fetchall()]
    if "added_by_id"   not in cols: conn.execute("ALTER TABLE transactions ADD COLUMN added_by_id INTEGER DEFAULT 0")
    if "added_by_name" not in cols: conn.execute("ALTER TABLE transactions ADD COLUMN added_by_name TEXT DEFAULT ''")
    ucols = [r[1] for r in conn.execute("PRAGMA table_info(allowed_users)").fetchall()]
    if "role"              not in ucols: conn.execute("ALTER TABLE allowed_users ADD COLUMN role TEXT DEFAULT 'user'")
    if "full_name"         not in ucols: conn.execute("ALTER TABLE allowed_users ADD COLUMN full_name TEXT DEFAULT ''")
    if "web_password_hash" not in ucols: conn.execute("ALTER TABLE allowed_users ADD COLUMN web_password_hash TEXT DEFAULT ''")
    conn.commit(); conn.close()

init_db()

# ── Auth ──────────────────────────────────────────────────────────────────────
def _hash(p): return hashlib.sha256(p.encode()).hexdigest()

def _make_token(uid, role, name):
    p = {"uid": uid, "role": role, "name": name, "exp": int(_time.time()) + 7*24*3600}
    d = base64.urlsafe_b64encode(json.dumps(p).encode()).decode().rstrip("=")
    s = hmac.new(JWT_SECRET.encode(), d.encode(), hashlib.sha256).hexdigest()
    return f"{d}.{s}"

def _decode_token(token):
    try:
        d, s = token.rsplit(".", 1)
        if not hmac.compare_digest(s, hmac.new(JWT_SECRET.encode(), d.encode(), hashlib.sha256).hexdigest()):
            raise ValueError("bad sig")
        pad = "=" * (-len(d) % 4)
        p = json.loads(base64.urlsafe_b64decode(d + pad))
        if p["exp"] < _time.time(): raise ValueError("expired")
        return p
    except Exception as e:
        raise HTTPException(401, str(e))

def require_token(authorization: str = Header(None)):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "Token kerak")
    return _decode_token(authorization[7:])

# ── Models ────────────────────────────────────────────────────────────────────
class TxIn(BaseModel):
    type: str; amount: float; category: str="boshqa"; note: str=""; date: str=""
    added_by_id: int=0; added_by_name: str=""

class CatIn(BaseModel):
    name: str; type: str; color: str="#6366f1"

class CatUpd(BaseModel):
    name: str; color: str="#6366f1"

class UserIn(BaseModel):
    user_id: int; username: str=""; full_name: str=""; role: str="user"

class LoginReq(BaseModel):
    username: str; password: str

class SetPassReq(BaseModel):
    user_id: int; password: str

class NameUpd(BaseModel):
    username: str=""; full_name: str=""

# ── Dashboard ─────────────────────────────────────────────────────────────────
@app.get("/")
async def root():
    d = Path(__file__).parent / "dashboard.html"
    if d.exists(): return FileResponse(str(d))
    return {"msg": "Finance Manager API"}

# ── Auth endpoints ────────────────────────────────────────────────────────────
@app.post("/auth/login")
def login(r: LoginReq):
    if r.username.strip() in ("superadmin", str(SUPER_ADMIN_ID)):
        if r.password != SUPER_WEB_PASS: raise HTTPException(401, "Parol noto'g'ri")
        return {"token": _make_token(SUPER_ADMIN_ID, "super_admin", "Super Admin"),
                "role": "super_admin", "name": "Super Admin", "user_id": SUPER_ADMIN_ID}
    try: uid = int(r.username.strip())
    except: raise HTTPException(401, "Topilmadi")
    conn = get_db()
    u = conn.execute("SELECT * FROM allowed_users WHERE user_id=?", (uid,)).fetchone()
    conn.close()
    if not u: raise HTTPException(401, "Topilmadi")
    if not u["web_password_hash"]: raise HTTPException(401, "Parol belgilanmagan")
    if u["web_password_hash"] != _hash(r.password): raise HTTPException(401, "Parol noto'g'ri")
    name = (u["full_name"] or u["username"] or str(uid)).strip()
    return {"token": _make_token(uid, u["role"], name), "role": u["role"], "name": name, "user_id": uid}

@app.get("/auth/me")
def get_me(authorization: str = Header(None)):
    return require_token(authorization)

@app.post("/auth/set-password")
def set_password(r: SetPassReq, authorization: str = Header(None)):
    p = require_token(authorization)
    if p.get("role") != "super_admin": raise HTTPException(403, "Faqat super admin")
    conn = get_db()
    conn.execute("UPDATE allowed_users SET web_password_hash=? WHERE user_id=?", (_hash(r.password), r.user_id))
    conn.commit(); conn.close(); return {"ok": True}

# ── Users ─────────────────────────────────────────────────────────────────────
@app.get("/users")
def list_users():
    conn=get_db(); r=conn.execute("SELECT * FROM allowed_users ORDER BY added_at DESC").fetchall(); conn.close()
    return [dict(x) for x in r]

@app.post("/users")
def add_user(u: UserIn):
    conn=get_db()
    conn.execute("INSERT OR REPLACE INTO allowed_users (user_id,username,full_name,role) VALUES (?,?,?,?)",
                 (u.user_id,u.username,u.full_name,u.role))
    conn.commit(); conn.close(); return {"ok":True}

@app.delete("/users/{uid}")
def del_user(uid: int):
    conn=get_db(); conn.execute("DELETE FROM allowed_users WHERE user_id=?",(uid,))
    conn.commit(); conn.close(); return {"ok":True}

@app.get("/users/{uid}/check")
def check_user(uid: int):
    conn=get_db(); r=conn.execute("SELECT * FROM allowed_users WHERE user_id=?",(uid,)).fetchone(); conn.close()
    if r: return {"allowed":True,"role":r["role"],"open_mode":False}
    return {"allowed":False,"role":None,"open_mode":False}

@app.patch("/users/{uid}/name")
def upd_name(uid: int, u: NameUpd):
    conn=get_db(); conn.execute("UPDATE allowed_users SET username=?,full_name=? WHERE user_id=?",(u.username,u.full_name,uid))
    conn.commit(); conn.close(); return {"ok":True}

# ── Transactions ──────────────────────────────────────────────────────────────
@app.get("/transactions")
def list_tx(limit:int=Query(50,ge=1,le=1000), offset:int=0,
            type:Optional[str]=None, category:Optional[str]=None,
            date_from:Optional[str]=None, date_to:Optional[str]=None,
            search:Optional[str]=None, added_by_id:Optional[int]=None):
    conn=get_db(); q="SELECT * FROM transactions WHERE 1=1"; p=[]
    if type:        q+=" AND type=?"; p.append(type)
    if category:    q+=" AND category=?"; p.append(category)
    if date_from:   q+=" AND date>=?"; p.append(date_from)
    if date_to:     q+=" AND date<=?"; p.append(date_to)
    if search:      q+=" AND (note LIKE ? OR category LIKE ?)"; p+=[f"%{search}%"]*2
    if added_by_id: q+=" AND added_by_id=?"; p.append(added_by_id)
    q+=" ORDER BY date DESC,created_at DESC LIMIT ? OFFSET ?"; p+=[limit,offset]
    rows=conn.execute(q,p).fetchall(); conn.close()
    return [dict(r) for r in rows]

@app.post("/transactions")
def create_tx(tx: TxIn):
    conn=get_db()
    cur=conn.execute("INSERT INTO transactions (type,amount,category,note,date,added_by_id,added_by_name) VALUES (?,?,?,?,?,?,?)",
        (tx.type,tx.amount,tx.category,tx.note,tx.date or date.today().isoformat(),tx.added_by_id,tx.added_by_name))
    conn.commit(); r=conn.execute("SELECT * FROM transactions WHERE id=?",(cur.lastrowid,)).fetchone(); conn.close()
    return dict(r)

@app.put("/transactions/{tid}")
def update_tx(tid: int, tx: TxIn):
    conn=get_db(); ex=conn.execute("SELECT * FROM transactions WHERE id=?",(tid,)).fetchone()
    if not ex: raise HTTPException(404,"not found")
    conn.execute("UPDATE transactions SET type=?,amount=?,category=?,note=?,date=? WHERE id=?",
                 (tx.type,tx.amount,tx.category,tx.note,tx.date or ex["date"],tid))
    conn.commit(); r=conn.execute("SELECT * FROM transactions WHERE id=?",(tid,)).fetchone(); conn.close()
    return dict(r)

@app.delete("/transactions/{tid}")
def delete_tx(tid: int):
    conn=get_db(); conn.execute("DELETE FROM transactions WHERE id=?",(tid,))
    conn.commit(); conn.close(); return {"ok":True}

@app.get("/transactions/by-date/{d}")
def get_by_date(d: str):
    conn=get_db(); rows=conn.execute("SELECT * FROM transactions WHERE date=? ORDER BY created_at",(d,)).fetchall()
    conn.close(); return [dict(r) for r in rows]

@app.post("/transactions/bulk-delete")
def bulk_delete(ids: List[int]):
    if not ids: return {"ok":True,"deleted":0}
    conn=get_db(); cur=conn.execute(f"DELETE FROM transactions WHERE id IN ({','.join('?'*len(ids))})",ids)
    conn.commit(); conn.close(); return {"ok":True,"deleted":cur.rowcount}

@app.get("/transactions/dates")
def get_dates():
    conn=get_db()
    rows=conn.execute("SELECT date,COUNT(*) as total,SUM(CASE WHEN type='income' THEN amount ELSE 0 END) as income_sum,SUM(CASE WHEN type='expense' THEN amount ELSE 0 END) as expense_sum FROM transactions GROUP BY date ORDER BY date DESC LIMIT 60").fetchall()
    conn.close(); return [dict(r) for r in rows]

# ── Report ────────────────────────────────────────────────────────────────────
def date_range(period):
    t=date.today()
    if period=="today":  return t.isoformat(),t.isoformat()
    if period=="week":   s=t-timedelta(days=t.weekday()); return s.isoformat(),t.isoformat()
    if period=="month":  return t.replace(day=1).isoformat(),t.isoformat()
    if period=="year":   return t.replace(month=1,day=1).isoformat(),t.isoformat()
    return t.replace(day=1).isoformat(),t.isoformat()

def prev_range(period):
    t=date.today()
    if period=="month":
        f=t.replace(day=1); lp=f-timedelta(days=1); return lp.replace(day=1).isoformat(),lp.isoformat()
    if period=="week":
        s=t-timedelta(days=t.weekday()); ep=s-timedelta(days=1); return (ep-timedelta(days=6)).isoformat(),ep.isoformat()
    return date_range(period)

@app.get("/report")
def get_report(period:str="month"):
    conn=get_db(); df,dt=date_range(period); pdf,pdt=prev_range(period)
    try:
        def tot(a,b):
            i=conn.execute("SELECT COALESCE(SUM(amount),0) FROM transactions WHERE type='income' AND date>=? AND date<=?",(a,b)).fetchone()[0]
            e=conn.execute("SELECT COALESCE(SUM(amount),0) FROM transactions WHERE type='expense' AND date>=? AND date<=?",(a,b)).fetchone()[0]
            return i,e
        inc,exp=tot(df,dt); pi,pe=tot(pdf,pdt)
        def cats(tp,total):
            rows=conn.execute("SELECT category as name,SUM(amount) as amount FROM transactions WHERE type=? AND date>=? AND date<=? GROUP BY category ORDER BY amount DESC",(tp,df,dt)).fetchall()
            return [{"name":r["name"],"amount":r["amount"],"pct":round(r["amount"]/total*100,1) if total else 0} for r in rows]
        ic=cats("income",inc); ec=cats("expense",exp)
        daily=conn.execute("SELECT date,type,SUM(amount) as amount FROM transactions WHERE date>=? AND date<=? GROUP BY date,type ORDER BY date",(df,dt)).fetchall()
    finally: conn.close()
    return {"period":period,"date_from":df,"date_to":dt,"income":inc,"expense":exp,"net":inc-exp,
            "prev_income":pi,"prev_expense":pe,"prev_net":pi-pe,
            "income_categories":ic,"expense_categories":ec,
            "top_categories":ic[:5],"top_expense_categories":ec[:5],"daily":[dict(r) for r in daily]}

@app.get("/analytics")
def get_analytics():
    conn=get_db()
    m=conn.execute("SELECT strftime('%Y-%m',date) as month,SUM(CASE WHEN type='income' THEN amount ELSE 0 END) as income,SUM(CASE WHEN type='expense' THEN amount ELSE 0 END) as expense FROM transactions WHERE date>=date('now','-6 months') GROUP BY month ORDER BY month").fetchall()
    ci=conn.execute("SELECT category,SUM(amount) as total FROM transactions WHERE type='income' GROUP BY category ORDER BY total DESC").fetchall()
    ce=conn.execute("SELECT category,SUM(amount) as total FROM transactions WHERE type='expense' GROUP BY category ORDER BY total DESC").fetchall()
    tot=conn.execute("SELECT COUNT(*) FROM transactions").fetchone()[0]
    conn.close()
    return {"monthly":[dict(r) for r in m],"category_income":[dict(r) for r in ci],"category_expense":[dict(r) for r in ce],"total_transactions":tot}

@app.get("/admin/stats")
def admin_stats():
    conn=get_db()
    rows=conn.execute("SELECT added_by_id,added_by_name,COUNT(*) as tx_count,SUM(CASE WHEN type='income' THEN amount ELSE 0 END) as income,SUM(CASE WHEN type='expense' THEN amount ELSE 0 END) as expense,MAX(date) as last_date FROM transactions WHERE added_by_id!=0 GROUP BY added_by_id ORDER BY tx_count DESC").fetchall()
    conn.close(); return [dict(r) for r in rows]

# ── Export/Import ─────────────────────────────────────────────────────────────
@app.get("/export")
def export(period:str="month"):
    conn=get_db(); df,dt=date_range(period)
    rows=conn.execute("SELECT id,type,amount,category,note,date,added_by_name,created_at FROM transactions WHERE date>=? AND date<=? ORDER BY date DESC",(df,dt)).fetchall()
    conn.close()
    out=io.StringIO(); w=csv.writer(out)
    w.writerow(["ID","Tur","Summa (so'm)","Kategoriya","Izoh","Sana","Kim qo'shdi","Vaqt"])
    for r in rows:
        w.writerow([r["id"],"Kirim" if r["type"]=="income" else "Chiqim",r["amount"],r["category"],r["note"],r["date"],r["added_by_name"],r["created_at"]])
    out.seek(0)
    return StreamingResponse(io.BytesIO(out.getvalue().encode("utf-8-sig")),media_type="text/csv",
                             headers={"Content-Disposition":f"attachment; filename=finance_{period}.csv"})

@app.post("/import")
async def import_tx(file:UploadFile=File(...), mode:str="append"):
    content=await file.read()
    try: text=content.decode("utf-8-sig")
    except: text=content.decode("utf-8")
    rows=list(csv.DictReader(io.StringIO(text)))
    conn=get_db()
    if mode=="replace": conn.execute("DELETE FROM transactions")
    ins=0
    for row in rows:
        try:
            tp="income" if row.get("Tur","").strip() in ("Kirim","income") else "expense"
            amt=float(str(row.get("Summa (so'm)",row.get("amount","0"))).replace(" ","").replace(",","."))
            conn.execute("INSERT INTO transactions (type,amount,category,note,date,added_by_name) VALUES (?,?,?,?,?,?)",
                         (tp,amt,row.get("Kategoriya","boshqa").strip(),row.get("Izoh","").strip(),
                          row.get("Sana",date.today().isoformat()).strip(),row.get("Kim qo'shdi","import").strip()))
            ins+=1
        except: pass
    conn.commit(); conn.close(); return {"ok":True,"inserted":ins,"mode":mode}

@app.get("/import/preview")
def import_preview(period:str="month"):
    conn=get_db(); df,dt=date_range(period)
    c=conn.execute("SELECT COUNT(*) FROM transactions WHERE date>=? AND date<=?",(df,dt)).fetchone()[0]
    conn.close(); return {"count":c,"date_from":df,"date_to":dt}

# ── Categories ────────────────────────────────────────────────────────────────
@app.get("/categories")
def list_cats():
    conn=get_db(); rows=conn.execute("SELECT * FROM categories ORDER BY type,name").fetchall(); conn.close()
    return [dict(r) for r in rows]

@app.post("/categories")
def add_cat(c: CatIn):
    conn=get_db()
    try:
        conn.execute("INSERT INTO categories (name,type,color) VALUES (?,?,?)",(c.name.lower().strip(),c.type,c.color))
        conn.commit()
    except sqlite3.IntegrityError: raise HTTPException(409,"already exists")
    finally: conn.close()
    return {"ok":True}

@app.put("/categories/{name}")
def upd_cat(name:str, u:CatUpd):
    conn=get_db()
    conn.execute("UPDATE categories SET name=?,color=? WHERE name=?",(u.name.lower().strip(),u.color,name))
    conn.execute("UPDATE transactions SET category=? WHERE category=?",(u.name.lower().strip(),name))
    conn.commit(); conn.close(); return {"ok":True}

@app.delete("/categories/{name}")
def del_cat(name:str):
    conn=get_db(); conn.execute("DELETE FROM categories WHERE name=?",(name,))
    conn.commit(); conn.close(); return {"ok":True}

@app.get("/health")
def health(): return {"status":"ok","time":datetime.now().isoformat()}

@app.get("/setup")
def setup():
    init_db()
    conn=get_db(); c=conn.execute("SELECT COUNT(*) FROM categories").fetchone()[0]; conn.close()
    return {"ok":True,"categories":c,"db":DB_PATH}
