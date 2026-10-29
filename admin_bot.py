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

EDIT_ID, EDIT_FIELD, EDIT_VALUE = range(10, 13) # أرقام جديدة لتجنب التعارض

DELETE_ID, DELETE_CONFIRM = range(13, 15)

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
    
async def list_products(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """عرض جميع المنتجات في بوت الإدارة"""
    data = load_data()
    products = data.get("products", [])
    
    if not products:
        await update.message.reply_text("📭 لا توجد منتجات حالياً.")
        return
    
    text = "📦 <b>قائمة المنتجات الحالية:</b>\n\n"
    for p in products:
        # جلب اسم القسم
        cat_id = p.get("category", "")
        cat_name = data["categories"].get(cat_id, {}).get("name", "غير محدد")
        
        text += f"🆔 <b>ID: {p['id']}</b> | {p['name']}\n"
        text += f"   💰 السعر: {p['price']} دج | القسم: {cat_name}\n\n"
    
    text += "💡 <i>للتعديل أو الحذف، استخدم الأوامر /edit أو /delete</i>"
    await update.message.reply_text(text, parse_mode="HTML")
async def edit_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🛠️ أرسلي <b>ID</b> المنتج الذي تريدين تعديله:\n(استخدمي /list لمعرفة الأرقام)", parse_mode="HTML")
    return EDIT_ID

async def edit_get_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        p_id = int(update.message.text)
        context.user_data['edit_id'] = p_id
        
        keyboard = [
            [InlineKeyboardButton("💰 تعديل السعر", callback_data="edit_price")],
            [InlineKeyboardButton("✍️ تعديل الاسم", callback_data="edit_name")],
            [InlineKeyboardButton("📝 تعديل الوصف", callback_data="edit_desc")],
        ]
        await update.message.reply_text("ماذا تريدين أن تعدلي؟", reply_markup=InlineKeyboardMarkup(keyboard))
        return EDIT_FIELD
    except ValueError:
        await update.message.reply_text("⚠️ الرجاء إرسال رقم صحيح.")
        return EDIT_ID

async def edit_choose_field(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data['edit_field'] = query.data # edit_price, edit_name, edit_desc
    
    await query.edit_message_text("✍️ أرسلي القيمة الجديدة:")
    return EDIT_VALUE

async def edit_save(update: Update, context: ContextTypes.DEFAULT_TYPE):
    new_value = update.message.text
    p_id = context.user_data['edit_id']
    field = context.user_data['edit_field']
    
    data = load_data()
    for p in data["products"]:
        if p["id"] == p_id:
            if field == "edit_price":
                try:
                    p["price"] = int(new_value)
                except ValueError:
                    await update.message.reply_text("⚠️ السعر يجب أن يكون رقماً.")
                    return EDIT_VALUE
            elif field == "edit_name":
                p["name"] = new_value
            elif field == "edit_desc":
                p["description"] = new_value
            break
    
    save_data(data)
    await update.message.reply_text(f"✅ تم تعديل المنتج (ID: {p_id}) بنجاح!\n\n(تذكير: المنشور في القناة لن يتحدث تلقائياً، ستحتاجين إلى إعادة نشر المنتج أو تعديله يدوياً).")
    return ConversationHandler.END

async def delete_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🗑️ أرسلي <b>ID</b> المنتج الذي تريدين حذفه:", parse_mode="HTML")
    return DELETE_ID

async def delete_get_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        p_id = int(update.message.text)
        context.user_data['delete_id'] = p_id
        
        # البحث عن المنتج لعرض اسمه في التأكيد
        data = load_data()
        product_name = "غير معروف"
        for p in data["products"]:
            if p["id"] == p_id:
                product_name = p["name"]
                break
        
        keyboard = [
            [InlineKeyboardButton("✅ نعم، احذف", callback_data="confirm_delete_yes")],
            [InlineKeyboardButton("❌ إلغاء", callback_data="confirm_delete_no")]
        ]
        await update.message.reply_text(
            f"⚠️ هل أنت متأكدة من حذف المنتج:\n<b>{product_name}</b> (ID: {p_id})؟",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return DELETE_CONFIRM
    except ValueError:
        await update.message.reply_text("⚠️ الرجاء إرسال رقم صحيح.")
        return DELETE_ID

async def delete_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.data == "confirm_delete_yes":
        p_id = context.user_data['delete_id']
        data = load_data()
        data["products"] = [p for p in data["products"] if p["id"] != p_id]
        save_data(data)
        await query.edit_message_text(f"✅ تم حذف المنتج (ID: {p_id}) بنجاح!")
    else:
        await query.edit_message_text("❌ تم الإلغاء.")
        
    return ConversationHandler.END

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """عرض إحصائيات المتجر"""
    data = load_data()
    products = data.get("products", [])
    categories = data.get("categories", {})
    
    if not products:
        await update.message.reply_text("📊 لا توجد منتجات في المتجر حالياً.")
        return
    
    text = "📊 <b>إحصائيات المتجر:</b>\n\n"
    total_products = len(products)
    
    # حساب عدد المنتجات في كل قسم
    cat_counts = {}
    for p in products:
        cat = p.get("category", "other")
        cat_counts[cat] = cat_counts.get(cat, 0) + 1
        
    for cat_id, cat_info in categories.items():
        count = cat_counts.get(cat_id, 0)
        if count > 0:
            text += f"{cat_info['name']}: {count} منتج\n"
    
    text += f"\n📦 <b>الإجمالي: {total_products} منتج</b>"
    
    await update.message.reply_text(text, parse_mode="HTML")

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
    
    edit_handler = ConversationHandler(
        entry_points=[CommandHandler("edit", edit_start)],
        states={
            EDIT_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, edit_get_id)],
            EDIT_FIELD: [CallbackQueryHandler(edit_choose_field, pattern="^edit_")],
            EDIT_VALUE: [MessageHandler(filters.TEXT & ~filters.COMMAND, edit_save)],
        },
        fallbacks=[CommandHandler("cancel", cancel)]
    )
    app.add_handler(edit_handler)

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

    delete_handler = ConversationHandler(
        entry_points=[CommandHandler("delete", delete_start)],
        states={
            DELETE_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, delete_get_id)],
            DELETE_CONFIRM: [CallbackQueryHandler(delete_confirm, pattern="^confirm_delete_")],
        },
        fallbacks=[CommandHandler("cancel", cancel)]
    )
    app.add_handler(delete_handler)
    
    app.add_handler(conv_handler)
    app.add_handler(CommandHandler("cancel", cancel))
    app.add_handler(CommandHandler("list", list_products))
    app.add_handler(CommandHandler("stats", stats))
    
    print("🤖 بوت الإدارة يعمل...")
    app.run_polling()

if __name__ == "__main__":
    main()