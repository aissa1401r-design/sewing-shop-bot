"""
بوت الإدارة - متجر الفضائل
Admin Bot for Sewing Shop
"""

import os
import json
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.request import HTTPXRequest
from telegram.ext import (
    Application, CommandHandler, ContextTypes,
    ConversationHandler, MessageHandler, CallbackQueryHandler, filters
)

load_dotenv()

# ═══ الحالات ═══ (تم حذف التكرار)
CHOOSE_CATEGORY, ASK_PHOTO, ASK_NAME, ASK_PRICE, ASK_DYNAMIC_ATTR, ASK_DESC = range(6)

ATTR_QUESTIONS = {
    "colors": "🎨 ما الألوان المتاحة؟ (افصلي بينها بفاصلة)",
    "sizes": "📏 ما المقاسات المتاحة؟ (افصلي بينها بفاصلة)",
    "volume": "🧴 ما هو حجم/سعة المنتج؟ (مثال: 50ml)",
    "weight": "⚖️ ما هو وزن المنتج؟ (مثال: 1kg)",
    "details": "📝 أضيفي تفاصيل إضافية (مثال: قطن، مصنوع يدوياً)"
}

def load_token():
    return os.getenv("ADMIN_BOT_TOKEN")

def load_data(): # ← تغير الاسم
    with open("products.json", "r", encoding="utf-8") as f:
        return json.load(f)

def save_data(data): # ← تغير الاسم
    with open("products.json", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

# ═══ التحقق من صاحبة المتجر ═══
def is_admin(user_id):
    return True 

# ═══ إضافة منتج ═══
async def add_product_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("⛔ ليس لديك صلاحية.")
        return ConversationHandler.END
    
    data = load_data()
    categories = data.get("categories", {})
    
    keyboard = []
    for cat_id, cat_info in categories.items():
        keyboard.append([InlineKeyboardButton(cat_info["name"], callback_data=f"cat_{cat_id}")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "🛍️ <b>ما هو نوع المنتج الذي تريدين إضافته؟</b>\nاختر القسم:",
        parse_mode="HTML",
        reply_markup=reply_markup
    )
    return CHOOSE_CATEGORY

async def category_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    cat_id = query.data.replace("cat_", "")
    data = load_data()
    cat_attrs = data["categories"][cat_id]["attributes"]
    
    context.user_data['new_product'] = {'category': cat_id, 'attributes': {}}
    context.user_data['remaining_attrs'] = list(cat_attrs) 
    
    await query.edit_message_text("📸 ممتاز! الآن أرسلي صورة المنتج:")
    return ASK_PHOTO

async def get_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    photo_file_id = update.message.photo[-1].file_id
    context.user_data['new_product']['photo'] = photo_file_id
    
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
    
    remaining = context.user_data.get('remaining_attrs', [])
    if remaining:
        attr = remaining[0] 
        question = ATTR_QUESTIONS.get(attr, "أدخلي القيمة:")
        await update.message.reply_text(question)
        return ASK_DYNAMIC_ATTR 
    else:
        await update.message.reply_text("📝 أضيفي وصفاً قصيراً للمنتج:")
        return ASK_DESC

async def get_dynamic_attr(update: Update, context: ContextTypes.DEFAULT_TYPE):
    remaining = context.user_data.get('remaining_attrs', [])
    attr = remaining.pop(0) 
    
    value = update.message.text
    if attr in ["colors", "sizes"]:
        if "،" in value:
            value = [v.strip() for v in value.split("،")]
        else: 
            value = [v.strip() for v in value.split(",")]
            
    context.user_data['new_product']['attributes'][attr] = value
    
    if remaining:
        next_attr = remaining[0]
        question = ATTR_QUESTIONS.get(next_attr, "أدخلي القيمة:")
        await update.message.reply_text(question)
        return ASK_DYNAMIC_ATTR 
    else:
        await update.message.reply_text("📝 أضيفي وصفاً قصيراً للمنتج:")
        return ASK_DESC

async def get_desc(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['new_product']['description'] = update.message.text
    product = context.user_data['new_product']
    
    data = load_data()
    all_ids = [p.get("id", 0) for p in data["products"]]
    new_id = max(all_ids, default=0) + 1
    product['id'] = new_id
    data["products"].append(product)
    save_data(data)
    
    channel_id = int(os.getenv("CHANNEL_ID"))
    smart_link = f"https://t.me/sewingFadha_il_bot?start=product_{new_id}"
    
        # ═══ تجهيز نص السمات للعرض (بالعربية) ═══
    ARABIC_NAMES = {
        "colors": "🎨 الألوان",
        "sizes": "📏 المقاسات",
        "volume": "🧴 السعة",
        "weight": "⚖️ الوزن",
        "details": "📝 التفاصيل"
    }
    
    attributes_text = ""
    for k, v in product['attributes'].items():
        # ترجمة اسم السمة
        arabic_name = ARABIC_NAMES.get(k, k) 
        
        # معالجة القوائم (مثل الألوان والمقاسات)
        if isinstance(v, list):
            # تنظيف العناصر من أي مسافات زائدة
            cleaned_v = [str(item).strip() for item in v]
            # دمجها بفاصلة عربية
            v = "، ".join(cleaned_v)
            
        attributes_text += f"{arabic_name}: {v}\n"

    caption = (
        f"✨ <b>{product['name']}</b>\n\n"
        f"💰 السعر: {product['price']} دج\n"
        f"{attributes_text}"
        f"📝 {product['description']}\n\n" # ← تغير desc إلى description
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
            CHOOSE_CATEGORY: [CallbackQueryHandler(category_chosen, pattern="^cat_")],
            ASK_PHOTO: [MessageHandler(filters.PHOTO, get_photo)],
            ASK_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_name)],
            ASK_PRICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_price)],
            ASK_DYNAMIC_ATTR: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_dynamic_attr)], 
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