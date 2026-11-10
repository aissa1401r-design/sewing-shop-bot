"""
بوت التواصل - متجر الفضائل (نظام تذاكر)
Contact Bot with Ticket System
"""

import os
import json
from datetime import datetime
from telegram import Update
from telegram.ext import (
    Application, CommandHandler, ContextTypes,
    MessageHandler, filters
)
from telegram.request import HTTPXRequest
from dotenv import load_dotenv

load_dotenv()

# ═══ ملف التذاكر ═══
TICKETS_FILE = "tickets.json"

def load_tickets():
    try:
        with open(TICKETS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return {}

def save_tickets(tickets):
    with open(TICKETS_FILE, "w", encoding="utf-8") as f:
        json.dump(tickets, f, ensure_ascii=False, indent=2)

def load_token():
    token = os.getenv("CONTACT_BOT_TOKEN")
    if token:
        return token
    if os.path.exists(".env"):
        with open(".env", "r", encoding="utf-8") as f:
            for line in f:
                if line.strip().startswith("CONTACT_BOT_TOKEN="):
                    return line.strip().split("=", 1)[1].strip().strip('"')
    raise ValueError("⚠️ CONTACT_BOT_TOKEN غير موجود")

# ═══ الترحيب ═══
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 مرحباً بك في خدمة الدعم!\n\n"
        "يمكنك كتابة استفسارك أو شكواك هنا، وسنقوم بالرد عليك في أقرب وقت."
    )

# ═══ استقبال رسالة من الزبونة ═══
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    message_text = update.message.text
    
    # 1. إنشاء رقم تذكرة فريد
    tickets = load_tickets()
    ticket_id = str(len(tickets) + 1)
    
    # 2. حفظ التذكرة (user_id -> ticket_id)
    tickets[ticket_id] = {
        "user_id": user.id,
        "user_name": user.first_name,
        "username": user.username or "لا يوجد",
        "messages": [message_text],
        "date": str(datetime.now())
    }
    save_tickets(tickets)
    
    # 3. تجهيز رسالة الإشعار لمجموعة الدعم
    admin_message = (
        f"📩 <b>تذكرة دعم جديدة #{ticket_id}</b>\n\n"
        f"👤 من: {user.first_name} (@{user.username or 'لا يوجد'})\n"
        f"🆔 ID: {user.id}\n\n"
        f"💬 الرسالة:\n{message_text}\n\n"
        f"<i>للرد، قم بالرد (Reply) على هذه الرسالة.</i>"
    )
    
    try:
        admin_id = int(os.getenv("ADMIN_CHAT_ID", "-5454243830"))
        await context.bot.send_message(
            chat_id=admin_id,
            text=admin_message,
            parse_mode="HTML"
        )
        await update.message.reply_text(f"✅ تم استلام رسالتك! رقم التذكرة: #{ticket_id}")
    except Exception as e:
        await update.message.reply_text(f"⚠️ حدث خطأ: {e}")

# ═══ استقبال رد صاحبة المتجر (في المجموعة) ═══
async def handle_admin_reply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """عندما ترد صاحبة المتجر على رسالة البوت في المجموعة"""
    message = update.message
    
    # 1. التأكد من أن الرسالة هي "رد" (Reply) على رسالة البوت
    if not message.reply_to_message:
        return  # ليست رداً، نتجاهلها
    
    # 2. التأكد من أن الرسالة الأصلية هي من البوت
    if message.reply_to_message.from_user.id != context.bot.id:
        return  # ليست رداً على رسالة البوت، نتجاهلها
    
    # 3. استخراج رقم التذكرة من الرسالة الأصلية
    original_text = message.reply_to_message.text or ""
    if "تذكرة دعم جديدة #" not in original_text:
        return  # ليست تذكرة دعم، نتجاهلها
    
    try:
        # استخراج رقم التذكرة (مثلاً من "#123")
        ticket_id = original_text.split("تذكرة دعم جديدة #")[1].split()[0]
        
        # 4. جلب التذكرة من الملف
        tickets = load_tickets()
        if ticket_id not in tickets:
            await message.reply_text(f"⚠️ التذكرة #{ticket_id} غير موجودة.")
            return
        
        user_id = tickets[ticket_id]["user_id"]
        
        # 5. إرسال الرد إلى الزبونة عبر البوت
        await context.bot.send_message(
            chat_id=user_id,
            text=f"📩 <b>رد من الدعم (تذكرة #{ticket_id}):</b>\n\n{message.text}",
            parse_mode="HTML"
        )
        
        # 6. إضافة الرد إلى سجل التذكرة
        tickets[ticket_id]["messages"].append(f"[الدعم]: {message.text}")
        save_tickets(tickets)
        
        await message.reply_text(f"✅ تم إرسال الرد إلى الزبونة (تذكرة #{ticket_id}).")
        
    except Exception as e:
        await message.reply_text(f"⚠️ حدث خطأ: {e}")

# ═══ Main ═══
def main():
    token = load_token()
    request = HTTPXRequest(
        connect_timeout=30.0,
        read_timeout=30.0,
        write_timeout=30.0,
        pool_timeout=30.0,
    )
    app = Application.builder().token(token).request(request).get_updates_request(request).build()
    
    # أوامر البوت
    app.add_handler(CommandHandler("start", start))
    
    # رسائل الزبونات (الخاصة)
    app.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND & filters.ChatType.PRIVATE,
        handle_message
    ))
    
    # ردود صاحبة المتجر (في المجموعة)
    app.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND & filters.ChatType.GROUPS,
        handle_admin_reply
    ))
    
    is_render = os.environ.get("RENDER") is not None
    webhook_url = os.environ.get("WEBHOOK_URL")
    
    if is_render and webhook_url:
        port = int(os.environ.get("PORT", 8080))
        print(f"🚀 بوت الدعم يعمل في وضع Webhook على المنفذ {port}")
        app.run_webhook(
            listen="0.0.0.0",
            port=port,
            url_path="contact_webhook",
            webhook_url=f"{webhook_url}/contact_webhook",
            drop_pending_updates=True
        )
    else:
        print("🤖 بوت الدعم يعمل في وضع Polling (محلي)")
        app.run_polling()

if __name__ == "__main__":
    main()