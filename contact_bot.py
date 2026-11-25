import os
from supabase import create_client, Client
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters
from telegram.request import HTTPXRequest
from dotenv import load_dotenv

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

def load_token():
    token = os.getenv("CONTACT_BOT_TOKEN")
    if token: return token
    raise ValueError("⚠️ CONTACT_BOT_TOKEN غير موجود")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 مرحباً بك في خدمة الدعم!\n\n"
        "يمكنك كتابة استفسارك أو شكواك هنا، وسنقوم بالرد عليك في أقرب وقت."
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    message_text = update.message.text
    
    try:
        response = supabase.table("tickets").insert({
            "user_id": user.id,
            "user_name": user.first_name,
            "username": user.username or "لا يوجد",
            "message": message_text
        }).execute()
        
        ticket_id = response.data[0]['id']
        
        admin_message = (
            f"📩 <b>تذكرة دعم جديدة #{ticket_id}</b>\n\n"
            f"👤 من: {user.first_name} (@{user.username or 'لا يوجد'})\n"
            f"🆔 ID: {user.id}\n\n"
            f"💬 الرسالة:\n{message_text}\n\n"
            f"<i>للرد، قم بالرد (Reply) على هذه الرسالة.</i>"
        )
        
        admin_id = int(os.getenv("ADMIN_CHAT_ID", "-5454243830"))
        await context.bot.send_message(chat_id=admin_id, text=admin_message, parse_mode="HTML")
        await update.message.reply_text(f"✅ تم استلام رسالتك! رقم التذكرة: #{ticket_id}")
        
    except Exception as e:
        await update.message.reply_text(f"⚠️ حدث خطأ: {e}")

async def handle_admin_reply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    if not message.reply_to_message or message.reply_to_message.from_user.id != context.bot.id:
        return
    
    original_text = message.reply_to_message.text or ""
    if "تذكرة دعم جديدة #" not in original_text:
        return
    
    try:
        ticket_id = int(original_text.split("تذكرة دعم جديدة #")[1].split()[0])
        response = supabase.table("tickets").select("user_id").eq("id", ticket_id).execute()
        
        if not response.data:
            await message.reply_text(f"⚠️ التذكرة #{ticket_id} غير موجودة في قاعدة البيانات.")
            return
        
        user_id = response.data[0]['user_id']
        
        await context.bot.send_message(
            chat_id=user_id,
            text=f"📩 <b>رد من الدعم (تذكرة #{ticket_id}):</b>\n\n{message.text}",
            parse_mode="HTML"
        )
        await message.reply_text(f"✅ تم إرسال الرد إلى الزبونة (تذكرة #{ticket_id}).")
        
    except Exception as e:
        await message.reply_text(f"⚠️ حدث خطأ: {e}")

def main():
    token = load_token()
    request = HTTPXRequest(connect_timeout=30.0, read_timeout=30.0)
    
    # بناء التطبيق
    app = Application.builder().token(token).request(request).get_updates_request(request).build()
    
    # إضافة المعالجات
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND & filters.ChatType.PRIVATE, handle_message))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND & filters.ChatType.GROUPS, handle_admin_reply))
    
    # ═══ اكتشاف بيئة التشغيل ═══
    is_render = os.environ.get("RENDER") is not None
    webhook_url = os.environ.get("WEBHOOK_URL")
    
    if is_render and webhook_url:
        # ═══ وضع Webhook (على Render) ═══
        port = int(os.environ.get("PORT", 8080))
        print(f"🚀 بوت الدعم يعمل في وضع Webhook على المنفذ {port}")
        
        # ✅ run_webhook سيقوم بتشغيل الخادم تلقائياً (بدون flask)
        app.run_webhook(
            listen="0.0.0.0",
            port=port,
            url_path="contact_webhook",
            webhook_url=f"{webhook_url}/contact_webhook",
            drop_pending_updates=True
        )
    else:
        # ═══ وضع Polling (محلياً) ═══
        print("🤖 بوت الدعم يعمل في وضع Polling (محلي)")
        app.run_polling()

if __name__ == "__main__":
    main()