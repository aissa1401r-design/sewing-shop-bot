"""
بوت التواصل - متجر الفضائل
Contact Bot for Sewing Shop
"""

import os
from telegram import Update
from telegram.ext import (
    Application, CommandHandler, ContextTypes,
    ConversationHandler, MessageHandler, filters
)
from telegram.request import HTTPXRequest

# ═══ الحالات ═══
ASK_MESSAGE = range(1)

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

# ═══ استقبال الرسالة ═══
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    message_text = update.message.text
    
    # تجهيز رسالة الإشعار لمجموعة الدعم
    admin_message = (
        f"📩 <b>رسالة دعم جديدة</b>\n\n"
        f"👤 من: {user.first_name} (@{user.username or 'لا يوجد'})\n"
        f"🆔 ID: {user.id}\n\n"
        f"💬 الرسالة:\n{message_text}"
    )
    
    try:
        # إرسال إلى مجموعة الدعم (أو حساب صاحبة المتجر)
        admin_id = int(os.getenv("ADMIN_CHAT_ID", "-5454243830"))
        await context.bot.send_message(
            chat_id=admin_id,
            text=admin_message,
            parse_mode="HTML"
        )
        await update.message.reply_text("✅ تم استلام رسالتك! سنرد عليك قريباً.")
    except Exception as e:
        await update.message.reply_text(f"⚠️ حدث خطأ: {e}")

def main():
    token = load_token()
    request = HTTPXRequest(
        connect_timeout=30.0,
        read_timeout=30.0,
        write_timeout=30.0,
        pool_timeout=30.0,
    )
    app = Application.builder().token(token).request(request).get_updates_request(request).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
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