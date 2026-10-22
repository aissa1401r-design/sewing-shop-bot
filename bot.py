"""
بوت تلجرام - متجر الخياطة
Sewing Shop Telegram Bot
"""

import json
import os
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    ContextTypes, filters, ConversationHandler, MessageHandler
)
from telegram.request import HTTPXRequest

# ═══ الروابط الذكية (Smart Links) ═══
SMART_LINKS = {
    "jalabiya_red": "الجلابية الحمراء",
    "jalabiya_blue": "الجلابية الزرقاء",
    "silik": "قماش حرير",
    "perfum": "عطر الفانيليا"
}
ASK_NAME, ASK_PHONE, ASK_ADDRESS, CONFIRM = range(4)

def load_token():
    with open(".env", "r", encoding="utf-8") as f:
        for line in f:
            if line.strip().startswith("BOT_TOKEN="):
                return line.strip().split("=", 1)[1].strip().strip('"')
    raise ValueError("Token not found")

def load_products():
    """قراءة المنتجات من ملف JSON"""
    with open("products.json", "r", encoding="utf-8") as f:
        return json.load(f)

# ═══ أوامر البوت ═══
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """الترحيب الأول"""
    # 1. التحقق من وجود كلمة سرية (رابط ذكي)
    args = context.args

    # القائمة الرئيسية
    keyboard = [
        [InlineKeyboardButton("👗 تصفح الجلابيب", callback_data="cat_jalabib")],
        [InlineKeyboardButton("🧵 تصفح الأقمشة", callback_data="cat_fabrics")],
        [InlineKeyboardButton("🛍️ المنتجات المكملة", callback_data="cat_others")],
        [InlineKeyboardButton("📞 تواصل معنا", callback_data="contact")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    if args and args[0] in SMART_LINKS:
        # ═══ الزبونة أتت من رابط ذكي ═══
        product_name = SMART_LINKS[args[0]]
        context.user_data['selected_product'] = product_name

        # نضيف زر "اطلب الآن" مخصص
        smart_keyboard = [
            [InlineKeyboardButton(f"🛒 اطلب {product_name} الان", callback_data="order_start_red")],
            [InlineKeyboardButton(f"👗 تصفح كل المنتجات", callback_data="back_home")]
        ]
        smart_markup = InlineKeyboardMarkup(smart_keyboard)

        await update.message.reply_text(
            f"أهلا بك 🌸\n"
            f"لاحظت إعجابك ب <b>{product_name}</b>\n"
            f"هل تودين طلبه الان, أم تصفح المتجر؟",
            parse_mode="HTML",
            reply_markup=smart_markup
        )

    else:
        # ═══ ترحيب عادي ═══    
        await update.message.reply_text(
            "أهلاً بك في متجر الخياطة اليدوية 🌸\n\n"
            "نحن نقدم لكم افضل الجلابيب, بأفضل الاقمشة, مع منتجات أخرى مكملة.\n"
            "اختر مايهمك:",
            reply_markup=reply_markup
        )

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالجة النقرات"""
    query = update.callback_query
    
    # ⚠️ مهم: تجاهل زر الطلب ليصل إلى ConversationHandler
    if query.data in ("order_start", "order_start_red"):
        await query.answer()  # ← تأكيد النقرة لتجنب الخطأ
        return
    
    await query.answer()

    if query.data == "contact":
        await query.edit_message_text("📞 للتواصل مع صاحبة المتجر:\n@اسم_حساب_صاحبة_المتجر")
    
    elif query.data == "cat_jalabib":
        products = load_products()["jalabib"]
        text = "👗 <b>الجلابيب المتوفرة:</b>\n\n"
        for p in products:
            text += f"🔹 <b>{p['name']}</b>\n"
            text += f"💰 السعر: {p['price']} دج\n"
            text += f"🎨 الألوان: {', '.join(p['colors'])}\n"
            text += f"📏 المقاسات: {', '.join(p['sizes'])}\n"
            text += f"<i>{p['description']}</i>\n\n"

        keyboard = [
            [InlineKeyboardButton("🛒 اطلب الان", callback_data="order_start")],
            [InlineKeyboardButton("⬅️ رجوع", callback_data="back_home")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await query.edit_message_text(text, parse_mode="HTML", reply_markup=reply_markup)
    
    elif query.data == "cat_fabrics":
        products = load_products()["fabrics"]
        text = "🧵 <b>الاقمشة المتوفرة: </b>\n\n"
        for p in products:
            text += f"🔹 <b>{p['name']}</b>\n"
            text += f"💰 السعر: {p['price']} دج\n"
            text += f"🎨 الألوان: {', '.join(p['colors'])}\n"
            text += f"<i>{p['description']}</i>\n\n"

        keyboard = [
            [InlineKeyboardButton("🛒 اطلب الآن", callback_data="order_start")],
            [InlineKeyboardButton("⬅️ رجوع", callback_data="back_home")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(text, parse_mode="HTML", reply_markup=reply_markup)

    elif query.data == "cat_others":
        products = load_products()["others"]  # ← أضفنا ()
        text = "🛍️ <b>المنتجات المكملة:</b>\n\n"
        for p in products:
            text += f"🔹 <b>{p['name']}</b>\n"
            text += f"💰 السعر: {p['price']} دج\n"
            text += f"<i>{p['description']}</i>\n\n"  # ← أضفنا </i>
        
        keyboard = [
            [InlineKeyboardButton("🛒 اطلب الان", callback_data="order_start")],
            [InlineKeyboardButton("⬅️ رجوع", callback_data="back_home")]
        ]

        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(text, parse_mode="HTML", reply_markup=reply_markup)
    
    elif query.data == "back_home":
        keyboard = [
            [InlineKeyboardButton("👗 تصفح الجلابيب", callback_data="cat_jalabib")],
            [InlineKeyboardButton("🧵 تصفح الأقمشة", callback_data="cat_fabrics")],
            [InlineKeyboardButton("🛍️ المنتجات المكملة", callback_data="cat_others")],
            [InlineKeyboardButton("📞 تواصل معنا", callback_data="contact")],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(
            "أهلاً بك في متجر الخياطة اليدوية 🌸\n\nاختر ما يهمك:",
            reply_markup=reply_markup
        )
 
# ═══ استمارة الطلب ═══
async def order_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """بدء المحادثة"""
    print("[DEBUG] دخلنا الى order_start")
    
    query = update.callback_query
    await query.answer()

    context.user_data['order'] = {}
    context.user_data['order']['product'] = context.user_data.get('selected_product', 'منتج غير محدد')
    await query.edit_message_text("📝 ممتاز! لنبدأ طلبك.\n\nما هو <b>اسمك الكامل</b>؟", parse_mode="HTML")
    return ASK_NAME

async def get_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """استلام الاسم"""
    print("دخلنا الى get_name")
    context.user_data['order']['name'] = update.message.text
    await update.message.reply_text("📞 جيد! الآن، ما هو <b>رقم هاتفك</b>؟", parse_mode="HTML")
    return ASK_PHONE

async def get_phone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """استلام الهاتف"""
    print("دخلنا الى get_phone")
    context.user_data['order']['phone'] = update.message.text
    await update.message.reply_text("📍 رائع! الآن، ما هو <b>عنوانك بالتفصيل</b> (الولاية، البلدية، الشارع)؟", parse_mode="HTML")
    return ASK_ADDRESS

async def get_address(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """استلام العنوان + عرض الملخص"""
    print("دخلنا الى get_address")
    context.user_data['order']['address'] = update.message.text

    order = context.user_data['order']
    summary = (
        f"<b>ملخص طلبك:</b>\n\n"
        f"👤 الاسم: {order['name']}\n"
        f"📞 الهاتف: {order['phone']}\n"
        f"📍 العنوان: {order['address']}\n\n"
        f"هل تؤكدين الطلب؟"
    )

    keyboard = [
        [InlineKeyboardButton("✅ نعم, تأكيد", callback_data="confirm_yes")],
        [InlineKeyboardButton("❌ إلغاء", callback_data="confirm_no")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(summary, parse_mode="HTML", reply_markup=reply_markup)
    return CONFIRM

async def confirm_order(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """تأكيد أو إلغاء"""
    print("دخلنا الى confirm_order")
    query = update.callback_query
    
    # 1. الرد على الزر فوراً (حتى لا تنتهي صلاحيته)
    await query.answer()

    if query.data == "confirm_yes":
        order = context.user_data.get('order', {})

        # 2. إرسال رسالة التأكيد للزبونة (فوراً)
        await query.edit_message_text(
            "✅ تم استلام طلبك بنجاح!\n\n"
            "سنتواصل معك قريباً إن شاء الله للتأكيد النهائي.",
            parse_mode="HTML"
        )

        # 3. تجهيز رسالة الإشعار للمجموعة
        admin_message = (
            f"🔔 <b>طلب جديد</b>\n\n"
            f"📦 <b>المنتج: </b>{order.get('product', 'غير محدد')}\n"
            f"👤 الاسم: {order.get('name')}\n"
            f"📞 الهاتف: {order.get('phone')}\n"
            f"📍 العنوان: {order.get('address')}\n"
            f"🆔 حساب الزبونة: @{query.from_user.username or 'لا يوجد'}"
        )
        
        # 4. إرسال الإشعار للمجموعة (في الخلفية)
        try:
            admin_id = int(os.getenv("ADMIN_CHAT_ID", "-5454243830"))
            await context.bot.send_message(
                chat_id=admin_id,
                text=admin_message,
                parse_mode="HTML"
            )
            print("✅ تم إرسال الإشعار للمجموعة بنجاح.")
        except Exception as e:
            print(f"⚠️ فشل إرسال الإشعار للمجموعة: {e}")
        
        return ConversationHandler.END

    else:
        await query.edit_message_text("❌ تم إلغاء الطلب. يمكنك التجول في المتجر.", parse_mode="HTML")
        return ConversationHandler.END
        
def main():
    token = load_token()

    request = HTTPXRequest(
        connect_timeout=30.0,
        read_timeout=30.0,
        write_timeout=30.0,
        pool_timeout=30.0,
    )
    app = (
        Application.builder()
        .token(token)
        .request(request)
        .get_updates_request(request)
        .build()
    )

    app.add_handler(CommandHandler("start", start))

    conv_handler = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(order_start, pattern="^order_start$"),
            CallbackQueryHandler(order_start, pattern="^order_start_red$")
        ],
        states={
            ASK_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_name)],
            ASK_PHONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_phone)],
            ASK_ADDRESS: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_address)],
            CONFIRM: [CallbackQueryHandler(confirm_order, pattern="^confirm_")],
        },
        fallbacks=[
            CommandHandler("start", start),
        ],
        conversation_timeout=300,
        per_message=False        
    )
    app.add_handler(conv_handler)

    app.add_handler(CallbackQueryHandler(button_handler))

    print("بوت المتجر يعمل.....")
    app.run_polling()

if __name__ == "__main__":
    main()