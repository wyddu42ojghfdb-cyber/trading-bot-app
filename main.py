from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
import sqlite3

app = FastAPI(title="TRC20-USDT Trading Control System")

# 🔓 حل مشكلة الحظر وتفعيل استقبال طلبات واجهة المستخدم والمشرف من github.io
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
    # إنشاء جدول حفظ الحالات المترابط مع واجهة تطبيقك الرسومية
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS system_status (
        username TEXT PRIMARY KEY,
        balance REAL DEFAULT 0.0,
        trade_executed INTEGER DEFAULT 0,
        deposit_status TEXT DEFAULT 'none',
        pending_deposit REAL DEFAULT 0.0,
        withdraw_status TEXT DEFAULT 'none',
        pending_withdraw REAL DEFAULT 0.0,
        withdraw_wallet TEXT
    )""")
    conn.commit()
    conn.close()

init_db()

class UserRegister(BaseModel):
    username: str
    user_wallet: str
    referred_by: Optional[str] = None

class DepositRequestData(BaseModel):
    username: str
    amount: float

class WithdrawRequestData(BaseModel):
    username: str
    wallet: str
    amount: float

class AdminActionData(BaseModel):
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
        cursor.execute(
            "INSERT OR IGNORE INTO system_status (username, balance) VALUES (?, 0.0)",
            (user.username,)
        )
        conn.commit()
        return {"message": f"تم تسجيل {user.username} وربط محفظته بنجاح!"}
    except sqlite3.IntegrityError:
        raise HTTPException(status_code=400, detail="اسم المستخدم مسجل مسبقاً")
    finally:
        conn.close()

# ---- 2. الدالة المسؤولة عن جلب الحالات والتحديث التلقائي لواجهة هاتف المستخدم ----
@app.get("/user/status")
def get_user_status(username: str):
    conn = sqlite3.connect("trading_app.db")
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM system_status WHERE username = ?", (username,))
    row = cursor.fetchone()
    
    if not row:
        # إذا لم يكن مسجلاً، نقوم بإنشاء سجل فارغ له لضمان عدم توقف الواجهة
        cursor.execute("INSERT OR IGNORE INTO system_status (username) VALUES (?)", (username,))
        conn.commit()
        cursor.execute("SELECT * FROM system_status WHERE username = ?", (username,))
        row = cursor.fetchone()
        
    res = dict(row)
    res["trade_executed"] = True if res["trade_executed"] == 1 else False
    conn.close()
    return res

# ---- 3. استقبال طلبات الإيداع من واجهة المستخدم وحفظها ----
@app.post("/deposit/request")
def deposit_request(req: DepositRequestData):
    conn = sqlite3.connect("trading_app.db")
    cursor = conn.cursor()
    cursor.execute("INSERT OR IGNORE INTO system_status (username) VALUES (?)", (req.username,))
    cursor.execute(
        "UPDATE system_status SET deposit_status = 'pending', pending_deposit = ? WHERE username = ?",
        (req.amount, req.username)
    )
    conn.commit()
    conn.close()
    return {"status": "success"}

# ---- 4. استقبال طلبات السحب من واجهة المستخدم وحفظها ----
@app.post("/withdraw/request")
def withdraw_request(req: WithdrawRequestData):
    conn = sqlite3.connect("trading_app.db")
    cursor = conn.cursor()
    cursor.execute("SELECT balance FROM users WHERE username = ?", (req.username,))
    user_bal = cursor.fetchone()
    
    if not user_bal or user_bal[0] < req.amount:
        conn.close()
        raise HTTPException(status_code=400, detail="Yetersiz bakiye!")
        
    cursor.execute("INSERT OR IGNORE INTO system_status (username) VALUES (?)", (req.username,))
    cursor.execute(
        "UPDATE system_status SET withdraw_status = 'pending', pending_withdraw = ?, withdraw_wallet = ? WHERE username = ?",
        (req.amount, req.wallet, req.username)
    )
    conn.commit()
    conn.close()
    return {"status": "success"}

# ---- 5. مسارات جلب التحكم للمشرف للموافقة اليدوية والتلقائية ----
@app.post("/api/yonetici/talepler")
def get_admin_demands():
    conn = sqlite3.connect("trading_app.db")
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT username as kullanici, pending_deposit as miktar FROM system_status WHERE deposit_status='pending'")
    yatirmalar = [dict(row) for row in cursor.fetchall()]
    cursor.execute("SELECT username as kullanici, pending_withdraw as miktar, withdraw_wallet as cuzdan FROM system_status WHERE withdraw_status='pending'")
    cekmeler = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return {"yatirmalar": yatirmalar, "cekmeler": cekmeler}

@app.post("/api/yonetici/yatirma_onayla")
def approve_manual_deposit(username: str):
    conn = sqlite3.connect("trading_app.db")
    cursor = conn.cursor()
    cursor.execute("SELECT pending_deposit FROM system_status WHERE username = ?", (username,))
    amount = cursor.fetchone()
    if amount:
        cursor.execute("UPDATE users SET balance = balance + ?, is_active = 1 WHERE username = ?", (amount[0], username))
        cursor.execute("UPDATE system_status SET balance = balance + ?, deposit_status = 'approved', pending_deposit = 0 WHERE username = ?", (amount[0], username))
        conn.commit()
    conn.close()
    return {"message": "Success"}

# ---- 6. زر المشرف السحري الخاص بك لتوزيع الأرباح (15%) وعمولات الإحالة ----
@app.post("/admin/run-trade-button")
@app.post("/api/yonetici/sihirli_buton")
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
        
        # تفعيل إشعار الأرباح الحية على واجهة هاتف المستخدم فوراً
        cursor.execute("UPDATE system_status SET balance = ?, trade_executed = 1 WHERE username = ?", (new_balance, username))
        
        if referred_by:
            ref_bonus = profit * 0.20
            referral_rewards[referred_by] = referral_rewards.get(referred_by, 0.0) + ref_bonus

    cursor.executemany("UPDATE users SET balance = ? WHERE username = ?", updates)
    for referrer, bonus_amount in referral_rewards.items():
        cursor.execute("UPDATE users SET balance = balance + ? WHERE username = ?", (bonus_amount, referrer))
        cursor.execute("UPDATE system_status SET balance = balance + ? WHERE username = ?", (bonus_amount, referrer))
        
    conn.commit()
    cursor.execute("SELECT COUNT(*) FROM users")
    total_users = cursor.fetchone()[0]
    conn.close()
    return {"message": "Success", "total_users_system": total_users}
    
