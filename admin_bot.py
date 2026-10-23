"""
بوت الإدارة - متجر الفضائل
Admin Bot for Sewing Shop
"""

import os
import json
from dotenv import load_dotenv
from telegram import Update
from telegram.request import HTTPXRequest
from telegram.ext import (
    Application, CommandHandler, ContextTypes,
    ConversationHandler, MessageHandler, filters
)

# تحميل المتغيرات من .env
load_dotenv()

# ═══ الحالات ═══
ASK_PHOTO, ASK_NAME, ASK_PRICE, ASK_DESC = range(4)

def load_token():
    return os.getenv("ADMIN_BOT_TOKEN")

def load_products():
    with open("products.json", "r", encoding="utf-8") as f:
        return json.load(f)

def save_products(data):
    with open("products.json", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

# ═══ التحقق من صاحبة المتجر ═══
def is_admin(user_id):
    # يمكنك وضع معرفك أو معرف صاحبة المتجر هنا
    # مؤقتاً: نسمح لأي شخص (للتجربة). لاحقاً: معرفك.
    return True 

# ═══ إضافة منتج ═══
async def add_product_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("⛔ ليس لديك صلاحية.")
        return ConversationHandler.END
    
    await update.message.reply_text("📸 أرسلي صورة المنتج:")
    return ASK_PHOTO

async def get_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # حفظ الصورة
    photo_file_id = update.message.photo[-1].file_id
    context.user_data['new_product'] = {'photo': photo_file_id}
    
    await update.message.reply_text("✍️ ما هو اسم المنتج؟")
    return ASK_NAME

async def get_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['new_product']['name'] = update.message.text
    await update.message.reply_text("💰 ما هو السعر؟ (أرقام فقط)")
    return ASK_PRICE

async def get_price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        price = int(update.message.text)
        context.user_data['new_product']['price'] = price
    except ValueError:
        await update.message.reply_text("⚠️ الرجاء إدخال رقم صحيح.")
        return ASK_PRICE
    
    await update.message.reply_text("📝 أضيفي وصفاً قصيراً للمنتج:")
    return ASK_DESC

async def get_desc(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['new_product']['desc'] = update.message.text
    product = context.user_data['new_product']
    
    # 1. حفظ في المنتجات (مؤقتاً في قسم "jalabib")
    data = load_products()
    if "jalabib" not in data:
        data["jalabib"] = []
    
    new_id = len(data["jalabib"]) + 1
    data["jalabib"].append({
        "id": new_id,
        "name": product['name'],
        "price": product['price'],
        "colors": ["أحمر"], # سنطورها لاحقاً
        "sizes": ["M"],     # سنطورها لاحقاً
        "description": product['desc']
    })
    save_products(data)
    
    # 2. النشر في القناة
    channel_id = int(os.getenv("CHANNEL_ID"))
    smart_link = f"https://t.me/sewingFadha_il_bot?start=product_{new_id}"
    
    caption = (
        f"✨ <b>{product['name']}</b>\n\n"
        f"💰 السعر: {product['price']} دج\n"
        f"📝 {product['desc']}\n\n"
        f"🛒 <a href='{smart_link}'>اطلبي الآن</a>"
    )
    
    try:
        await context.bot.send_photo(
            chat_id=channel_id,
            photo=product['photo'],
            caption=caption,
            parse_mode="HTML"
        )
        await update.message.reply_text("✅ تم إضافة المنتج ونشره في القناة بنجاح!")
    except Exception as e:
        await update.message.reply_text(f"⚠️ فشل النشر في القناة: {e}")
    
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ تم الإلغاء.")
    return ConversationHandler.END

# ═══ Main ═══
def main():
    token = load_token()
    # إعدادات الشبكة
    request = HTTPXRequest(
        connect_timeout=30.0,
        read_timeout=30.0,
        write_timeout=30.0,
        pool_timeout=30.0,
    )
    
    app = Application.builder().token(token).request(request).get_updates_request(request).build()
    
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("add", add_product_start)],
        states={
            ASK_PHOTO: [MessageHandler(filters.PHOTO, get_photo)],
            ASK_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_name)],
            ASK_PRICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_price)],
            ASK_DESC: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_desc)],
        },
        fallbacks=[CommandHandler("cancel", cancel)]
    )
    
    app.add_handler(conv_handler)
    app.add_handler(CommandHandler("cancel", cancel))
    
    print("🤖 بوت الإدارة يعمل...")
    app.run_polling()

if __name__ == "__main__":
    main()