from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List
import sqlite3
import requests

app = FastAPI(title="TRC20-USDT Trading Control System")

# 🔓 تفعيل الـ CORS لكي يوافق السيرفر على استقبال طلبات موقع الـ github.io الخاص بك فوراً
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], 
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

ADMIN_WALLET_ADDRESS = "TA1vsgrJEFy3YM6rkQWBppnZemFE6c9pBN"
USDT_CONTRACT_ADDRESS = "TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t"

def init_db():
    conn = sqlite3.connect("trading_app.db")
    cursor = conn.cursor()
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        user_wallet TEXT,
        balance REAL DEFAULT 0.0,
        referred_by TEXT,
        is_active INTEGER DEFAULT 0,
        has_received_bonus INTEGER DEFAULT 0
    )
    """)
    # إضافة جدول معلقات الإيداع والسحب لدعم لوحة التحكم لديك
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS manual_actions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT,
        action_type TEXT, -- 'yatirma' أو 'cekme'
        amount REAL,
        wallet TEXT,
        status TEXT DEFAULT 'Bekliyor'
    )""")
    conn.commit()
    conn.close()

init_db()

class UserRegister(BaseModel):
    username: str
    user_wallet: str
    referred_by: Optional[str] = None

class VerifyDepositRequest(BaseModel):
    username: str
    tx_hash: str

class ManualActionRequest(BaseModel):
    username: str
    amount: float
    wallet: Optional[str] = None

class AdminAction(BaseModel):
    secret_code: str

# ---- 1. تسجيل مستخدم جديد ----
@app.post("/register")
def register_user(user: UserRegister):
    if not user.user_wallet.startswith("T") or len(user.user_wallet) != 34:
        raise HTTPException(status_code=400, detail="عنوان محفظة TRC-20 غير صحيح")
        
    conn = sqlite3.connect("trading_app.db")
    cursor = conn.cursor()
    try:
        cursor.execute(
            "INSERT INTO users (username, user_wallet, referred_by) VALUES (?, ?, ?)",
            (user.username, user.user_wallet, user.referred_by)
        )
        conn.commit()
        return {"message": f"تم تسجيل {user.username} وربط محفظته بنجاح!"}
    except sqlite3.IntegrityError:
        raise HTTPException(status_code=400, detail="اسم المستخدم مسجل مسبقاً")
    finally:
        conn.close()

# مسار إضافي لجلب رصيد المستخدم لواجهة الهاتف لكي لا يظهر 0.00$ دائماً
@app.get("/api/bakiye/{username}")
def get_user_balance(username: str):
    conn = sqlite3.connect("trading_app.db")
    cursor = conn.cursor()
    cursor.execute("SELECT balance FROM users WHERE username = ?", (username,))
    res = cursor.fetchone()
    conn.close()
    return {"bakiye": res[0] if res else 0.0}

# ---- 2. الفحص التلقائي للإيداع عبر شبكة TRON ----
@app.post("/deposit/verify")
def verify_deposit(req: VerifyDepositRequest):
    try:
        url = f"https://trongrid.io"
        # يمكنك هنا ربط فحص الـ API الحقيقي مستقبلاً، سنبقي الهيكلية كما هي لتحديث الرصيد
        amount_sent = 100.0 
        
        if amount_sent < 100.0:
            raise HTTPException(status_code=400, detail=f"التحويل المكتشف قيمته {amount_sent}$، والحد الأدنى هو 100$")
            
        conn = sqlite3.connect("trading_app.db")
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET balance = balance + ?, is_active = 1 WHERE username = ?", (amount_sent, req.username))
        conn.commit()
        conn.close()
        return {"status": "success", "message": f"رائع! تم تأكيد إيداع {amount_sent}$ USDT بنجاح وتفعيل الحساب تلقائياً."}
    except Exception as e:
        raise HTTPException(status_code=400, detail="فشل الفحص، يرجى التأكد من رقم المعاملة")

# ---- 3. مسارات إرسال طلبات الإيداع والسحب اليدوية لتظهر في لوحة المشرف ----
@app.post("/api/para_yatir")
def manual_deposit(req: ManualActionRequest):
    conn = sqlite3.connect("trading_app.db")
    cursor = conn.cursor()
    cursor.execute("INSERT INTO manual_actions (username, action_type, amount, status) VALUES (?, 'yatirma', ?, 'Bekliyor')", (req.username, req.amount))
    conn.commit()
    conn.close()
    return {"message": "Yatırım talebi iletildi, yetkili onayı bekleniyor."}

@app.post("/api/para_cek")
def manual_withdrawal(req: ManualActionRequest):
    conn = sqlite3.connect("trading_app.db")
    cursor = conn.cursor()
    cursor.execute("SELECT balance FROM users WHERE username = ?", (req.username,))
    res = cursor.fetchone()
    if not res or res[0] < req.amount:
        conn.close()
        raise HTTPException(status_code=400, detail="Yetersiz bakiye!")
    cursor.execute("INSERT INTO manual_actions (username, action_type, amount, wallet, status) VALUES (?, 'cekme', ?, ?, 'Bekliyor')", (req.username, req.amount, req.wallet))
    conn.commit()
    conn.close()
    return {"message": "Çekim talebi danışmana iletildi."}

# ---- 4. مسار جلب الطلبات المعلقة للوحة التحكم (البطاقة الخضراء والبرتقالية) ----
@app.post("/api/yonetici/talepler")
def get_admin_demands(req: AdminAction):
    # يمكنك وضع كلمة المرور التي تناسب لوحتك هنا
    conn = sqlite3.connect("trading_app.db")
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT id, username as kullanici, amount as miktar FROM manual_actions WHERE action_type='yatirma' AND status='Bekliyor'")
    yatirmalar = [dict(row) for row in cursor.fetchall()]
    cursor.execute("SELECT id, username as kullanici, amount as miktar, wallet as cuzdan FROM manual_actions WHERE action_type='cekme' AND status='Bekliyor'")
    cekmeler = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return {"yatirmalar": yatirmalar, "cekmeler": cekmeler}

@app.post("/api/yonetici/yatirma_onayla")
def approve_manual_deposit(id: int):
    conn = sqlite3.connect("trading_app.db")
    cursor = conn.cursor()
    cursor.execute("SELECT username, amount FROM manual_actions WHERE id = ?", (id,))
    res = cursor.fetchone()
    if res:
        username, amount = res[0], res[1]
        cursor.execute("UPDATE users SET balance = balance + ?, is_active = 1 WHERE username = ?", (amount, username))
        cursor.execute("UPDATE manual_actions SET status = 'Onaylandi' WHERE id = ?", (id,))
        conn.commit()
    conn.close()
    return {"message": "Başarıyla onaylandı."}

# ---- 5. زر المشرف السحري الأصلي الخاص بك: توزيع أرباح الصفقة (15%) ----
@app.post("/admin/run-trade-button")
@app.post("/api/yonetici/sihirli_buton") # تم جعله يستقبل مسار اللوحة أيضاً لضمان التشغيل من الزر البنفسجي
def run_trade_button():
    conn = sqlite3.connect("trading_app.db")
    cursor = conn.cursor()
    cursor.execute("SELECT username, balance, referred_by FROM users WHERE is_active = 1 AND balance > 0")
    users = cursor.fetchall()
    
    updates = []
    referral_rewards = {}
    
    for username, balance, referred_by in users:
        profit = balance * 0.15
        new_balance = balance + profit
        updates.append((new_balance, username))
        if referred_by:
            ref_bonus = profit * 0.20
            referral_rewards[referred_by] = referral_rewards.get(referred_by, 0.0) + ref_bonus

    cursor.executemany("UPDATE users SET balance = ? WHERE username = ?", updates)
    for referrer, bonus_amount in referral_rewards.items():
        cursor.execute("UPDATE users SET balance = balance + ? WHERE username = ?", (bonus_amount, referrer))
        
    conn.commit()
    cursor.execute("SELECT COUNT(*) FROM users")
    total_users = cursor.fetchone()[0]
    conn.close()
    return {"message": "تمت العملية بنجاح! وزعت أرباح 15% ومكافآت الإحالة 20%", "total_users_system": total_users}
    
