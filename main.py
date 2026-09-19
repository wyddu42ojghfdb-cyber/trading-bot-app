from fastapi.responses import HTMLResponse
import os

# مسار لعرض واجهة المستخدم (تطبيق الهاتف) عند فتح رابط السيرفر المباشر
@app.get("/", response_class=HTMLResponse)
def read_index():
    if os.path.exists("index.html"):
        with open("index.html", "r", encoding="utf-8") as f:
            return f.read()
    return "<h1>Smart Trading Bot - Server is Live</h1>"

# مسار لعرض لوحة تحكم المشرف (الأزرار والبطاقات الملونة)
@app.get("/admin_panel", response_class=HTMLResponse)
def read_admin():
    if os.path.exists("admin.html"):
        with open("admin.html", "r", encoding="utf-8") as f:
            return f.read()
    elif os.path.exists("yönetici.html"):
        with open("yönetici.html", "r", encoding="utf-8") as f:
            return f.read()
    return "<h1>Yönetici Paneli Bulunamadı (admin.html eksik)</h1>"
    
