from fastapi import FastAPI, HTTPException, Depends
from pydantic import BaseModel
from typing import List, Optional
import sqlite3

app = FastAPI(title="Algo-Trading Control System")

# ---- إعداد قاعدة البيانات وتوليد الجداول ----
def init_db():
    conn = sqlite3.connect("trading_app.db")
    cursor = conn.cursor()
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        balance REAL DEFAULT 0.0,
        referred_by TEXT,
        is_active INTEGER DEFAULT 0,
        has_received_bonus INTEGER DEFAULT 0
    )
    """)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS transactions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT,
        type TEXT,
        amount REAL,
        status TEXT DEFAULT 'pending',
        proof_image TEXT
    )
    """)
    conn.commit()
    conn.close()

init_db()

class UserRegister(BaseModel):
    username: str
    referred_by: Optional[str] = None

class DepositRequest(BaseModel):
    username: str
    amount: float
    proof_image: str

class ProcessTransaction(BaseModel):
    transaction_id: int
    action: str

@app.post("/register")
def register_user(user: UserRegister):
    conn = sqlite3.connect("trading_app.db")
    cursor = conn.cursor()
    try:
        cursor.execute("INSERT INTO users (username, referred_by) VALUES (?, ?)", (user.username, user.referred_by))
        conn.commit()
        return {"message": f"تم تسجيل المستخدم {user.username} بنجاح!"}
    except sqlite3.IntegrityError:
        raise HTTPException(status_code=400, detail="اسم المستخدم مسجل مسبقاً")
    finally:
        conn.close()

@app.post("/deposit/request")
def request_deposit(req: DepositRequest):
    if req.amount < 100.0:
        raise HTTPException(status_code=400, detail="عذراً، الحد الأدنى للإيداع هو 100$")
    
    conn = sqlite3.connect("trading_app.db")
    cursor = conn.cursor()
    cursor.execute("INSERT INTO transactions (username, type, amount, proof_image) VALUES (?, 'deposit', ?, ?)", (req.username, req.amount, req.proof_image))
    conn.commit()
    conn.close()
    return {"message": "تم إرسال طلب الإيداع بنجاح، بانتظار موافقة المشرف"}

@app.post("/admin/process-transaction")
def process_transaction(proc: ProcessTransaction):
    conn = sqlite3.connect("trading_app.db")
    cursor = conn.cursor()
    cursor.execute("SELECT username, type, amount, status FROM transactions WHERE id = ?", (proc.transaction_id,))
    tx = cursor.fetchone()
    if not tx or tx[3] != 'pending':
        raise HTTPException(status_code=404, detail="الطلب غير موجود أو تمت معالجته مسبقاً")
    
    username, tx_type, amount, _ = tx
    
    if proc.action == "approve":
        cursor.execute("UPDATE transactions SET status = 'approved' WHERE id = ?", (proc.transaction_id,))
        if tx_type == "deposit":
            cursor.execute("UPDATE users SET balance = balance + ?, is_active = 1 WHERE username = ?", (amount, username))
            cursor.execute("SELECT referred_by FROM users WHERE username = ?", (username,))
            referrer = cursor.fetchone()[0]
            
            if referrer:
                cursor.execute("SELECT COUNT(*) FROM users WHERE referred_by = ? AND is_active = 1", (referrer,))
                active_friends = cursor.fetchone()[0]
                cursor.execute("SELECT has_received_bonus FROM users WHERE username = ?", (referrer,))
                has_bonus = cursor.fetchone()[0]
                
                if active_friends >= 40 and has_bonus == 0:
                    cursor.execute("UPDATE users SET balance = balance + 10000, has_received_bonus = 1 WHERE username = ?", (referrer,))
        conn.commit()
        conn.close()
        return {"message": "تمت الموافقة على الطلب بنجاح وتحديث الأرصدة"}
    else:
        cursor.execute("UPDATE transactions SET status = 'rejected' WHERE id = ?", (proc.transaction_id,))
        conn.commit()
        conn.close()
        return {"message": "تم رفض الطلب"}

@app.post("/admin/run-trade-button")
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
    return {"message": "تم تشغيل الصفقة وتوزيع الأرباح 15% والمكافآت 20%", "total_users": total_users}
  
