"""
بوت تلجرام - متجر الخياطة
Sewing Shop Telegram Bot
"""

import json
import os
from database import load_products as db_load_products, save_order
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto
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

ASK_NAME, ASK_PHONE, ASK_ADDRESS, CONFIRM, ASK_DYNAMIC_ATTR = range(5)

def load_token():
    # 1. حاول القراءة من متغيرات البيئة (Render)
    token = os.getenv("BOT_TOKEN")
    if token:
        return token
    
    # 2. إذا لم يوجد، اقرأ من ملف .env (محلياً)
    if os.path.exists(".env"):
        with open(".env", "r", encoding="utf-8") as f:
            for line in f:
                if line.strip().startswith("BOT_TOKEN="):
                    return line.strip().split("=", 1)[1].strip().strip('"')
    
    raise ValueError("⚠️ BOT_TOKEN غير موجود في متغيرات البيئة أو .env")

def load_products():
    """قراءة المنتجات من ملف supabase"""
    try:
        return db_load_products()
    except Exception as e:
        print(f"⚠️ فشل جلب المنتجات من Supabase: {e}")
        return []

# ═══ أوامر البوت ═══
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """الترحيب الأول"""
    args = context.args
    
    # ═══ 1. قراءة الأقسام من products.json (الملف المحلي) ═══
    categories = {}
    try:
        with open("products.json", "r", encoding="utf-8") as f:
            data = json.load(f)
            categories = data.get("categories", {})
    except FileNotFoundError:
        # إذا لم يوجد الملف، نستخدم الأقسام الثابتة
        categories = {
            "jalabib": {"name": "👗 جلابيب"},
            "accessories": {"name": "💍 أكسسوارات"},
            "perfumes": {"name": "🧴 عطور"},
            "oils": {"name": "🌿 زيوت"},
            "home": {"name": "🏠 مستلزمات منزلية"},
            "other": {"name": "🛍️ آخر"}
        }

    # بناء الأزرار
    keyboard = []
    row = []
    for cat_id, cat_info in categories.items():
        row.append(InlineKeyboardButton(cat_info["name"], callback_data=f"cat_{cat_id}"))
        if len(row) == 2:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)
    
    keyboard.append([InlineKeyboardButton("📞 تواصل معنا", callback_data="contact")])
    reply_markup = InlineKeyboardMarkup(keyboard)

    if args:
        arg = args[0]
        product_name = None
        
        SMART_LINKS = {
            "jalabiya_red": "الجلابية الحمراء",
            "jalabiya_blue": "الجلابية الزرقاء",
        }
        
        if arg in SMART_LINKS:
            product_name = SMART_LINKS[arg]
        elif arg.startswith("product_"):
            try:
                product_id = int(arg.split("_")[1])
                products = load_products()  # من Supabase
                for p in products:
                    if p.get("id") == product_id:
                        product_name = p["name"]
                        break
            except (ValueError, IndexError):
                pass
        
        if product_name:
            context.user_data['selected_product'] = product_name
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
            return

    await update.message.reply_text(
        "أهلاً بك في متجر الخياطة اليدوية 🌸\n\n"
        "نحن نقدم لكم أفضل المنتجات.\n"
        "اختر ما يهمك:",
        reply_markup=reply_markup
    )

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالجة النقرات"""
    query = update.callback_query

    ARABIC_CATEGORIES = {
        "jalabib": "👗 جلابيب",
        "accessories": "💍 أكسسوارات",
        "perfumes": "🧴 عطور",
        "oils": "🌿 زيوت",
        "home": "🏠 مستلزمات منزلية",
        "other": "🛍️ آخر"
    }

    if query.data in ("order_start", "order_start_red"):
        await query.answer()
        return
    
    await query.answer()

    if query.data == "contact":
        await query.edit_message_text("📞 للتواصل مع صاحبة المتجر:\n@اسم_حساب_صاحبة_المتجر")
    
    elif query.data.startswith("cat_") or query.data.startswith("page_"):
        if query.data.startswith("cat_"):
            cat_id = query.data.replace("cat_", "")
            page = 0
        else:
            parts = query.data.split("_")
            cat_id = parts[1]
            page = int(parts[2])

        products = load_products()  # من Supabase (قائمة)
        filtered_products = [p for p in products if p.get("category") == cat_id]
        
        ARABIC_CATEGORIES = {
            "jalabib": "👗 جلابيب",
            "accessories": "💍 أكسسوارات",
            "perfumes": "🧴 عطور",
            "oils": "🌿 زيوت",
            "home": "🏠 مستلزمات منزلية",
            "other": "🛍️ آخر"
        }
        cat_name = ARABIC_CATEGORIES.get(cat_id, cat_id)

        if not filtered_products:
            await query.edit_message_text(f"لا توجد منتجات حالياً في قسم {cat_name}.")
            return

        p = filtered_products[page]
        photo_id = p.get("photo")
        caption = f"<b>{p['name']}</b>\n\n"
        caption += f"💰 السعر: {p['price']} دج\n"
        
        ARABIC_NAMES = {"colors": "🎨 الألوان", "sizes": "📏 المقاسات", "volume": "🧴 السعة"}
        for k, v in p.get('attributes', {}).items():
            arabic_name = ARABIC_NAMES.get(k, k)
            if isinstance(v, list):
                v = "، ".join([str(item).strip() for item in v])
            caption += f"{arabic_name}: {v}\n"
        caption += f"\n<i>{p.get('description', '')}</i>"

        keyboard = [
            [InlineKeyboardButton("🛒 اطلب الآن", callback_data=f"order_dyn_{p['id']}")],
            [
                InlineKeyboardButton("⬅️ السابق", callback_data=f"page_{cat_id}_{page-1}"),
                InlineKeyboardButton(f"{page+1}/{len(filtered_products)}", callback_data="ignore"),
                InlineKeyboardButton("التالي ➡️", callback_data=f"page_{cat_id}_{page+1}")
            ],
            [InlineKeyboardButton("⬅️ رجوع للأقسام", callback_data="back_home")]
        ]
        
        if page == 0:
            keyboard[1].pop(0)
            keyboard[1].insert(0, InlineKeyboardButton(" ", callback_data="ignore"))
        if page == len(filtered_products) - 1:
            keyboard[1].pop()
            keyboard[1].append(InlineKeyboardButton(" ", callback_data="ignore"))

        reply_markup = InlineKeyboardMarkup(keyboard)

        try:
            if photo_id:
                await query.edit_message_media(
                    media=InputMediaPhoto(media=photo_id, caption=caption, parse_mode="HTML"),
                    reply_markup=reply_markup
                )
            else:
                await query.edit_message_text(caption, parse_mode="HTML", reply_markup=reply_markup)
        except Exception as e:
            print(f"⚠️ فشل تعديل الرسالة: {e}")
            try:
                await query.message.delete()
            except:
                pass
            await query.message.reply_text(caption, parse_mode="HTML", reply_markup=reply_markup)

    elif query.data == "back_home":
        # ═══ قراءة الأقسام من products.json (وليس من Supabase) ═══
        categories = {}
        try:
            with open("products.json", "r", encoding="utf-8") as f:
                data = json.load(f)
                categories = data.get("categories", {})
        except FileNotFoundError:
            categories = {
                "jalabib": {"name": "👗 جلابيب"},
                "accessories": {"name": "💍 أكسسوارات"},
                "perfumes": {"name": "🧴 عطور"},
                "oils": {"name": "🌿 زيوت"},
                "home": {"name": "🏠 مستلزمات منزلية"},
                "other": {"name": "🛍️ آخر"}
            }

        keyboard = []
        row = []
        for cat_id, cat_info in categories.items():
            row.append(InlineKeyboardButton(cat_info["name"], callback_data=f"cat_{cat_id}"))
            if len(row) == 2:
                keyboard.append(row)
                row = []
        if row:
            keyboard.append(row)
        
        keyboard.append([InlineKeyboardButton("📞 تواصل معنا", callback_data="contact")])
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            "أهلاً بك في متجر الخياطة العصرية 🌸\n\nاختر ما يهمك:",
            reply_markup=reply_markup
        )

# ═══ استمارة الطلب ═══
async def order_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """بدء المحادثة"""
    print("[DEBUG] دخلنا الى order_start")
    query = update.callback_query
    await query.answer()

    # إذا لم يكن هناك منتج مختار (طلب عادي)، نأخذه من الـ callback_data
        # 1. هل أتى من رابط ذكي أو من زر الطلب؟
    selected_product = context.user_data.get('selected_product')
    
    # إذا لم يكن هناك منتج مختار، نأخذ الـ ID من الزر ونبحث عن الاسم
    if not selected_product and query.data.startswith("order_dyn_"):
        product_id = int(query.data.replace("order_dyn_", ""))
        data = load_products()
        for p in data:
            if p.get("id") == product_id:
                selected_product = p["name"]
                break

    if not selected_product:
        selected_product = 'منتج غير محدد'
        
    context.user_data['selected_product'] = selected_product
    context.user_data['order'] = {'product': selected_product}
    
    # 2. البحث عن المنتج في الملف لمعرفة سماته (اللون، المقاس، إلخ)
    data = load_products()  # ← هذه قائمة منتجات الآن
    product_obj = None
    
    # البحث عن المنتج بالاسم في القائمة
    for p in data:
        if p.get("name") == selected_product:
            product_obj = p
            break
            
    # 3. تجهيز قائمة الأسئلة الديناميكية
    context.user_data['remaining_attrs'] = []
    if product_obj:
        attrs = product_obj.get("attributes", {})
        for k, v in attrs.items():
            # نأخذ فقط السمات التي لها خيارات متعددة (مثل الألوان والمقاسات)
            if isinstance(v, list) and v:
                context.user_data['remaining_attrs'].append({'key': k, 'options': v})
    
    # 4. هل هناك سؤال ديناميكي (لون أو مقاس)؟
    if context.user_data['remaining_attrs']:
        attr_data = context.user_data['remaining_attrs'].pop(0)
        context.user_data['current_attr_key'] = attr_data['key']
        
        # بناء أزرار الخيارات (مثل: أحمر، أزرق)
        keyboard = []
        for option in attr_data['options']:
            keyboard.append([InlineKeyboardButton(option, callback_data=f"attr_{option}")])
            
        # ترجمة اسم السمة للعرض
        ARABIC_NAMES = {"colors": "اللون", "sizes": "المقاس", "volume": "السعة"}
        display_name = ARABIC_NAMES.get(attr_data['key'], attr_data['key'])
            
        await query.edit_message_text(
            f"📝 ممتاز! لنبدأ طلبك لـ <b>{selected_product}</b>.\n\nاختر <b>{display_name}</b>:",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return ASK_DYNAMIC_ATTR
    else:
        # إذا لم تكن هناك سمات (مثل منتج ليس له لون أو مقاس)
        await query.edit_message_text("📝 ممتاز! لنبدأ طلبك.\n\nما هو <b>اسمك الكامل</b>؟", parse_mode="HTML")
        return ASK_NAME

async def get_dynamic_attr(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """استقبال اللون أو المقاس المختار"""
    query = update.callback_query
    await query.answer()
    
    # 1. استخراج القيمة المختارة
    selected_value = query.data.replace("attr_", "")
    attr_key = context.user_data.get('current_attr_key')
    
    # 2. حفظها في الطلب
    ARABIC_NAMES = {"colors": "اللون", "sizes": "المقاس", "volume": "السعة"}
    display_key = ARABIC_NAMES.get(attr_key, attr_key)
    context.user_data['order'][display_key] = selected_value
    
    # 3. هل بقي سؤال آخر؟
    if context.user_data['remaining_attrs']:
        attr_data = context.user_data['remaining_attrs'].pop(0)
        context.user_data['current_attr_key'] = attr_data['key']
        
        keyboard = []
        for option in attr_data['options']:
            keyboard.append([InlineKeyboardButton(option, callback_data=f"attr_{option}")])
            
        display_name = ARABIC_NAMES.get(attr_data['key'], attr_data['key'])
            
        await query.edit_message_text(
            f"اختر <b>{display_name}</b>:",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return ASK_DYNAMIC_ATTR
    else:
        # انتهت الأسئلة، ننتقل لسؤال الاسم
        await query.edit_message_text("📝 رائع! الآن، ما هو <b>اسمك الكامل</b>؟", parse_mode="HTML")
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
    
    # بناء الملخص ديناميكياً
    summary = f"<b>ملخص طلبك:</b>\n\n"
    summary += f"📦 المنتج: {order.get('product', 'غير محدد')}\n"
    if 'اللون' in order: summary += f"🎨 اللون: {order['اللون']}\n"
    if 'المقاس' in order: summary += f"📏 المقاس: {order['المقاس']}\n"
    if 'السعة' in order: summary += f"🧴 السعة: {order['السعة']}\n"
    summary += f"👤 الاسم: {order.get('name')}\n"
    summary += f"📞 الهاتف: {order.get('phone')}\n"
    summary += f"📍 العنوان: {order.get('address')}\n\n"
    summary += "هل تؤكدين الطلب؟"

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
        admin_message = f"🔔 <b>طلب جديد</b>\n\n"
        admin_message += f"📦 <b>المنتج: </b>{order.get('product', 'غير محدد')}\n"
        if 'اللون' in order: admin_message += f"🎨 اللون: {order['اللون']}\n"
        if 'المقاس' in order: admin_message += f"📏 المقاس: {order['المقاس']}\n"
        if 'السعة' in order: admin_message += f"🧴 السعة: {order['السعة']}\n"
        admin_message += f"👤 الاسم: {order.get('name')}\n"
        admin_message += f"📞 الهاتف: {order.get('phone')}\n"
        admin_message += f"📍 العنوان: {order.get('address')}\n"
        admin_message += f"🆔 حساب الزبونة: @{query.from_user.username or 'لا يوجد'}"
        
        # ═══ حفظ الطلب في orders.json ═══
        order_data = {
            "product": order.get('product'),
            "color": order.get('اللون', ''),
            "size": order.get('المقاس', ''),
            "volume": order.get('السعة', ''),
            "customer_name": order.get('name'),
            "customer_phone": order.get('phone'),
            "customer_address": order.get('address'),
            "customer_username": query.from_user.username or "لا يوجد",
        }
        save_order(order_data)
        # ═════════════════════════════════
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
        
# أضف هذه الدالة في bot.py (بعد دالة start)

async def go_back_home(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """العودة للقائمة الرئيسية أثناء المحادثة"""
    query = update.callback_query
    await query.answer()
    
    # ═══ قراءة الأقسام من products.json ═══
    categories = {}
    try:
        with open("products.json", "r", encoding="utf-8") as f:
            data = json.load(f)
            categories = data.get("categories", {})
    except FileNotFoundError:
        categories = {
            "jalabib": {"name": "👗 جلابيب"},
            "accessories": {"name": "💍 أكسسوارات"},
            "perfumes": {"name": "🧴 عطور"},
            "oils": {"name": "🌿 زيوت"},
            "home": {"name": "🏠 مستلزمات منزلية"},
            "other": {"name": "🛍️ آخر"}
        }

    keyboard = []
    row = []
    for cat_id, cat_info in categories.items():
        row.append(InlineKeyboardButton(cat_info["name"], callback_data=f"cat_{cat_id}"))
        if len(row) == 2:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)
    
    keyboard.append([InlineKeyboardButton("📞 تواصل معنا", callback_data="contact")])
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        "أهلاً بك في متجر الخياطة العصرية 🌸\n\nاختر ما يهمك:",
        reply_markup=reply_markup
    )
    return ConversationHandler.END

def main():
    token = load_token()
    
    # ═══ إعدادات الشبكة ═══
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

    # ═══ إضافة المعالجات (كما هي) ═══
    app.add_handler(CommandHandler("start", start))
    conv_handler = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(order_start, pattern="^order_start$"),
            CallbackQueryHandler(order_start, pattern="^order_start_red$"),
            CallbackQueryHandler(order_start, pattern="^order_dyn_.*")
        ],
        states={
            ASK_DYNAMIC_ATTR: [CallbackQueryHandler(get_dynamic_attr, pattern="^attr_.*")],
            ASK_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_name)],
            ASK_PHONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_phone)],
            ASK_ADDRESS: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_address)],
            CONFIRM: [CallbackQueryHandler(confirm_order, pattern="^confirm_")],
        },
        fallbacks=[CommandHandler("start", start)],
        conversation_timeout=300,
        per_message=False        
    )
    app.add_handler(conv_handler)
    app.add_handler(CallbackQueryHandler(button_handler))

    # ═══ اكتشاف بيئة التشغيل ═══
    # Render يوفر متغير بيئة اسمه RENDER
    is_render = os.environ.get("RENDER") is not None
    webhook_url = os.environ.get("WEBHOOK_URL")

    if is_render and webhook_url:
        # ═══ وضع Webhook (على Render) ═══
        port = int(os.environ.get("PORT", 8080))
        print(f"🚀 تشغيل البوت في وضع Webhook على المنفذ {port}")
        app.run_webhook(
            listen="0.0.0.0",
            port=port,
            url_path="webhook",
            webhook_url=f"{webhook_url}/webhook",
            drop_pending_updates=True
        )
    else:
        # ═══ وضع Polling (على جهازك المحلي) ═══
        print("🤖 تشغيل البوت في وضع Polling (محلي)")
        app.run_polling()

if __name__ == "__main__":
    main()