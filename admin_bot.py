"""
بوت الإدارة - متجر الفضائل
Admin Bot for Sewing Shop
"""

import os
import json
import uuid
import requests
import requests
from dotenv import load_dotenv
from database import load_products, save_product, update_product, delete_product, compress_image, upload_image_to_supabase
from telegram import InputMediaPhoto, Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
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

# حالات إضافة صور للمنتج
ASK_PHOTOS_ID, ASK_MORE_PHOTOS = range(20, 22)

ATTR_QUESTIONS = {
    "colors": "🎨 ما الألوان المتاحة؟ (افصلي بينها بفاصلة)",
    "sizes": "📏 ما المقاسات المتاحة؟ (افصلي بينها بفاصلة)",
    "volume": "🧴 ما هو حجم/سعة المنتج؟ (مثال: 50ml)",
    "weight": "⚖️ ما هو وزن المنتج؟ (مثال: 1kg)",
    "details": "📝 أضيفي تفاصيل إضافية (مثال: قطن، مصنوع يدوياً)"
}

def load_token():
    # 1. حاول القراءة من متغيرات البيئة (Render)
    token = os.getenv("ADMIN_BOT_TOKEN")
    if token:
        return token
    
    # 2. إذا لم يوجد، اقرأ من ملف .env (محلياً)
    if os.path.exists(".env"):
        with open(".env", "r", encoding="utf-8") as f:
            for line in f:
                if line.strip().startswith("ADMIN_BOT_TOKEN="):
                    return line.strip().split("=", 1)[1].strip().strip('"')
    
    raise ValueError("⚠️ ADMIN_BOT_TOKEN غير موجود في متغيرات البيئة أو .env")

def load_data(): # ← تغير الاسم
    with open("products.json", "r", encoding="utf-8") as f:
        return json.load(f)

def save_data(data): # ← تغير الاسم
    with open("products.json", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

# ═══ التحقق من صاحبة المتجر ═══
def is_admin(user_id):
    return True 

async def start_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """القائمة الرئيسية للإدارة (أزرار ثابتة)"""
    keyboard = [
        [KeyboardButton("➕ إضافة منتج")],
        [KeyboardButton("📦 عرض المنتجات"), KeyboardButton("📊 الإحصائيات")],
        [KeyboardButton("🗑️ حذف منتج"), KeyboardButton("✏️ تعديل منتج")],
        [KeyboardButton("🖼️ إضافة صور"), KeyboardButton("📦 الطلبات")]
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    
    await update.message.reply_text(
        "أهلاً بك في لوحة تحكم المتجر 🌸\nاختر ما تريدين:",
        reply_markup=reply_markup
    )

async def handle_admin_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """توجيه النصوص القادمة من الأزرار إلى الأوامر المناسبة"""
    text = update.message.text
    
    if text == "➕ إضافة منتج":
        # لا تستدعي add_product_start هنا، لأن ConversationHandler سيلتقطها من MessageHandler
        pass 
        
    elif text == "📦 عرض المنتجات":
        await list_products(update, context)
        
    elif text == "📊 الإحصائيات":
        await stats(update, context)
        
    elif text == "📦 الطلبات":
        await orders_stats(update, context)
        
    elif text == "🗑️ حذف منتج":
        # لا تستدعي delete_start هنا، ConversationHandler سيلتقطها
        pass
        
    elif text == "✏️ تعديل منتج":
        # لا تستدعي edit_start هنا، ConversationHandler سيلتقطها
        pass
    
    elif text == "🖼️ إضافة صور":
        await add_photos_start(update, context)

    else:
        await update.message.reply_text("⚠️ الرجاء اختيار زر من القائمة.")
        
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
    """استقبال الصور (صورة واحدة أو ألبوم)"""
    # حفظ الصور في قائمة
    if 'photos' not in context.user_data['new_product']:
        context.user_data['new_product']['photos'] = []
    
    # إذا كانت رسالة عادية (صورة واحدة)
    if update.message.photo:
        photo_id = update.message.photo[-1].file_id
        context.user_data['new_product']['photos'].append(photo_id)
        
        # نطلب من المستخدم إرسال المزيد أو الضغط على "تم"
        keyboard = [[InlineKeyboardButton("✅ تم، انتقل للخطوة التالية", callback_data="photos_done")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            f"📸 تم استلام الصورة ({len(context.user_data['new_product']['photos'])}/10).\n"
            "أرسلي صورة أخرى، أو اضغطي 'تم' للمتابعة.",
            reply_markup=reply_markup
        )
        return ASK_PHOTO # البقاء في نفس الحالة لاستقبال المزيد

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
    
    # ═══ هذا الجزء هو الحل ═══
    # إذا كانت السمة هي "الألوان" أو "المقاسات"، نحولها إلى قائمة
    if attr in ["colors", "sizes"]:
        # استبدال الفاصلة العربية والنقطة بفاصلة إنجليزية لتوحيد الفاصل
        value = value.replace("،", ",").replace(".", ",")
        # تقسيم النص بناءً على الفاصلة
        value = [v.strip() for v in value.split(",") if v.strip()]
    # ═══════════════════════
    
    context.user_data['new_product']['attributes'][attr] = value
    # ..
    if remaining:
        next_attr = remaining[0]
        question = ATTR_QUESTIONS.get(next_attr, "أدخلي القيمة:")
        await update.message.reply_text(question)
        return ASK_DYNAMIC_ATTR 
    else:
        await update.message.reply_text("📝 أضيفي وصفاً قصيراً للمنتج:")
        return ASK_DESC
async def get_desc(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """حفظ المنتج في Supabase والنشر في القناة"""
    context.user_data['new_product']['description'] = update.message.text
    product = context.user_data['new_product']
    
    # ═══ 1. رفع الصور إلى Supabase Storage (مع الضغط) ═══    
    photo_urls = []
    bot_token = load_token()  # ← أضف هذا السطر (كان مفقوداً)
        
    photo_urls = []
    bot_token = load_token()
    
    for photo_id in product.get('photos', []):
        try:
            # 1. جلب رابط الصورة من تيليجرام (فقط file_path، بدون إضافات)
            file_info = await context.bot.get_file(photo_id)
            telegram_url = file_info.file_path  # ← هذا الرابط كامل جاهز
            print(f"🔍 [DEBUG] رابط الصورة: {telegram_url}")
            
            # 2. تحميل الصورة
            response = requests.get(telegram_url)
            print(f"🔍 [DEBUG] حالة الطلب: {response.status_code}")
            image_bytes = response.content
            
            # 3. ضغط الصورة
            compressed_bytes = compress_image(image_bytes, max_width=800, quality=85)
            
            # 4. رفع الصورة إلى Supabase (باسم فريد وآمن)
            safe_name = f"product_{uuid.uuid4().hex[:10]}.jpg"  # ← اسم آمن
            public_url = upload_image_to_supabase(compressed_bytes, safe_name)
            
            if public_url:
                photo_urls.append(public_url)
                print(f"✅ [DEBUG] تم رفع الصورة: {public_url}")
            
        except Exception as e:
            print(f"⚠️ فشل رفع الصورة {photo_id}: {e}")
    
    # ═══ 2. تجهيز البيانات للحفظ في Supabase (بالروابط الجديدة) ═══
    product_data = {
        "name": product['name'],
        "price": product['price'],
        "category": product['category'],
        "description": product['description'],
        "attributes": product.get('attributes', {}),
        "photo": photo_urls[0] if photo_urls else product.get('photo'),
        "photos": photo_urls if photo_urls else ([product.get('photo')] if product.get('photo') else [])
    }
    
    # ═══ 3. حفظ المنتج في قاعدة البيانات ═══
    saved_product = save_product(product_data)
    new_id = saved_product[0]['id'] if saved_product else 0
    
    # ═══ 4. تجهيز النص للقناة ═══
    channel_id = int(os.getenv("CHANNEL_ID"))
    smart_link = f"https://t.me/sewingFadha_il_bot?start=product_{new_id}"
    
    ARABIC_NAMES = {
        "colors": "🎨 الألوان",
        "sizes": "📏 المقاسات",
        "volume": "🧴 السعة",
        "weight": "⚖️ الوزن",
        "details": "📝 التفاصيل"
    }
    
    attributes_text = ""
    for k, v in product['attributes'].items():
        arabic_name = ARABIC_NAMES.get(k, k)
        if isinstance(v, list):
            cleaned_v = [str(item).strip() for item in v]
            v = "، ".join(cleaned_v)
        attributes_text += f"{arabic_name}: {v}\n"

    caption = (
        f"✨ <b>{product['name']}</b>\n\n"
        f"💰 السعر: {product['price']} دج\n"
        f"{attributes_text}"
        f"📝 {product['description']}\n\n"
        f"🛒 <a href='{smart_link}'>اطلبي الآن</a>"
    )
    
    # ═══ 5. النشر في القناة (باستخدام file_id الأصلي - أمان) ═══
    try:
        # نستخدم file_id الأصلي في القناة (لضمان بقائها حتى لو تعطلت Supabase)
        original_photos = product.get('photos', [])
        if not original_photos:
            await update.message.reply_text("⚠️ لا توجد صور لهذا المنتج!")
            return ConversationHandler.END
            
        if len(original_photos) == 1:
            sent_message = await context.bot.send_photo(
                chat_id=channel_id,
                photo=original_photos[0],  # ← file_id الأصلي
                caption=caption,
                parse_mode="HTML"
            )
            update_product(new_id, {"message_id": sent_message.message_id})
        else:
            media_group = []
            for i, photo in enumerate(original_photos[:10]):
                if i == 0:
                    media_group.append(InputMediaPhoto(media=photo, caption=caption, parse_mode="HTML"))
                else:
                    media_group.append(InputMediaPhoto(media=photo))
            
            sent_messages = await context.bot.send_media_group(
                chat_id=channel_id,
                media=media_group
            )
            if sent_messages:
                update_product(new_id, {"message_id": sent_messages[0].message_id})
        
        await update.message.reply_text("✅ تم إضافة المنتج ونشره في القناة بنجاح!")
    except Exception as e:
        await update.message.reply_text(f"⚠️ فشل النشر في القناة: {e}")

    return ConversationHandler.END
async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ تم الإلغاء.")
    return ConversationHandler.END
    
async def list_products(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """عرض جميع المنتجات من Supabase"""
    try:
        products = load_products()  # ← تقرأ من Supabase
    except Exception as e:
        await update.message.reply_text(f"⚠️ فشل جلب المنتجات: {e}")
        return
    
    if not products:
        await update.message.reply_text("📭 لا توجد منتجات حالياً.")
        return
    
    text = "📦 <b>قائمة المنتجات الحالية:</b>\n\n"
    ARABIC_NAMES = {
        "jalabib": "👗 جلابيب",
        "accessories": "💍 أكسسوارات",
        "perfumes": "🧴 عطور",
        "oils": "🌿 زيوت",
        "home": "🏠 مستلزمات منزلية",
        "other": "🛍️ آخر"
    }
    
    for p in products:
        # جلب اسم القسم
        cat_id = p.get("category", "")
        cat_name = ARABIC_NAMES.get(cat_id, cat_id)
        
        text += f"🆔 <b>ID: {p['id']}</b> | {p['name']}\n"
        text += f"   💰 السعر: {p['price']} دج | القسم: {cat_name}\n\n"
    
    text += "💡 <i>للتعديل أو الحذف، استخدم الأوامر /edit أو /delete</i>"
    await update.message.reply_text(text, parse_mode="HTML")

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """عرض إحصائيات المتجر من Supabase"""
    products = load_products()  # ← من Supabase
    
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
        
    # عرض الأقسام (نحتاج جلب الأقسام من ملف JSON أو تعريفها يدوياً)
    # مؤقتاً، سنعرض الأقسام التي لديها منتجات فقط
    ARABIC_CATEGORIES = {
        "jalabib": "👗 جلابيب",
        "accessories": "💍 أكسسوارات",
        "perfumes": "🧴 عطور",
        "oils": "🌿 زيوت",
        "home": "🏠 مستلزمات منزلية",
        "other": "🛍️ آخر"
    }
    
    for cat_id, count in cat_counts.items():
        cat_name = ARABIC_CATEGORIES.get(cat_id, cat_id)
        text += f"{cat_name}: {count} منتج\n"
    
    text += f"\n📦 <b>الإجمالي: {total_products} منتج</b>"
    
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
    p_id = context.user_data.get('edit_id')
    field = context.user_data.get('edit_field')
    
    # 1. تجهيز البيانات للتحديث
    update_data = {}
    if field == "edit_price":
        try:
            update_data["price"] = int(new_value)
        except ValueError:
            await update.message.reply_text("⚠️ السعر يجب أن يكون رقماً.")
            return EDIT_VALUE
    elif field == "edit_name":
        update_data["name"] = new_value
    elif field == "edit_desc":
        update_data["description"] = new_value

    # 2. تحديث المنتج في Supabase
    try:
        updated = update_product(p_id, update_data)
        if not updated:
            await update.message.reply_text(f"⚠️ لم يتم العثور على منتج بالمعرف {p_id}.")
            return ConversationHandler.END
    except Exception as e:
        await update.message.reply_text(f"⚠️ فشل التحديث في قاعدة البيانات: {e}")
        return ConversationHandler.END

    # 3. تحديث المنشور في القناة (إذا كان له message_id)
    try:
        # جلب بيانات المنتج المحدثة من Supabase
        products = load_products()
        p = next((item for item in products if item["id"] == p_id), None)
        
        if p and p.get("message_id"):
            channel_id = int(os.getenv("CHANNEL_ID"))
            
            # بناء الكابشن الجديد
            caption = f"✨ <b>{p['name']}</b>\n\n"
            caption += f"💰 السعر: {p['price']} دج\n"
            
            ARABIC_NAMES = {"colors": "🎨 الألوان", "sizes": "📏 المقاسات", "volume": "🧴 السعة"}
            for k, v in p.get('attributes', {}).items():
                arabic_name = ARABIC_NAMES.get(k, k)
                if isinstance(v, list):
                    v = "، ".join([str(item).strip() for item in v])
                caption += f"{arabic_name}: {v}\n"
            caption += f"📝 {p.get('description', '')}\n\n"
            
            smart_link = f"https://t.me/sewingFadha_il_bot?start=product_{p['id']}"
            caption += f"🛒 <a href='{smart_link}'>اطلبي الآن</a>"
            
            await context.bot.edit_message_caption(
                chat_id=channel_id,
                message_id=p["message_id"],
                caption=caption,
                parse_mode="HTML"
            )
    except Exception as e:
        print(f"⚠️ فشل تحديث المنشور في القناة: {e}")

    await update.message.reply_text(f"✅ تم تعديل المنتج (ID: {p_id}) وتحديث المنشور في القناة!")
    return ConversationHandler.END

async def delete_get_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        p_id = int(update.message.text)
        context.user_data['delete_id'] = p_id
        
        # البحث عن المنتج في Supabase
        products = load_products()
        product_name = "غير معروف"
        found = False
        for p in products:
            if p["id"] == p_id:
                product_name = p["name"]
                found = True
                break
        
        if not found:
            await update.message.reply_text(f"⚠️ لم يتم العثور على منتج بالمعرف {p_id}.")
            return ConversationHandler.END

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

async def orders_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """عرض إحصائيات الطلبات من Supabase"""
    try:
        # جلب الطلبات من Supabase (نحتاج لاستيراد get_orders)
        from database import get_orders
        orders = get_orders()
    except Exception as e:
        await update.message.reply_text(f"⚠️ فشل جلب الطلبات: {e}")
        return
        
    if not orders:
        await update.message.reply_text("📊 لا توجد طلبات حتى الآن.")
        return
        
    total = len(orders)
    product_counts = {}
    for o in orders:
        p_name = o.get("product", "غير محدد")
        product_counts[p_name] = product_counts.get(p_name, 0) + 1
        
    text = f"📊 <b>إحصائيات الطلبات:</b>\n\n"
    text += f"📦 إجمالي الطلبات: {total}\n\n"
    text += "<b>المنتجات الأكثر طلباً:</b>\n"
    
    sorted_products = sorted(product_counts.items(), key=lambda x: x[1], reverse=True)
    for p_name, count in sorted_products[:5]:
        text += f"🔹 {p_name}: {count} طلب\n"
        
    await update.message.reply_text(text, parse_mode="HTML")

async def add_photos_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🖼️ أرسلي <b>ID</b> المنتج الذي تريدين إضافة صور له:", parse_mode="HTML")
    return ASK_PHOTOS_ID

async def add_photos_get_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        p_id = int(update.message.text)
        context.user_data['photo_product_id'] = p_id
        
        # التحقق من وجود المنتج في Supabase
        products = load_products()
        found = any(p["id"] == p_id for p in products)
        
        if not found:
            await update.message.reply_text(f"⚠️ لم يتم العثور على منتج بالمعرف {p_id}.")
            return ConversationHandler.END
            
        await update.message.reply_text("📸 ممتاز! أرسلي الصور الجديدة (واحدة تلو الأخرى).\nعندما تنتهين، اضغطي /done.")
        return ASK_MORE_PHOTOS
    except ValueError:
        await update.message.reply_text("⚠️ الرجاء إرسال رقم صحيح.")
        return ASK_PHOTOS_ID

async def add_more_photos(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        p_id = context.user_data.get('photo_product_id')
        
        # إذا أرسل المستخدم /done
        if update.message.text == "/done":
            context.user_data['photo_update_id'] = p_id
            keyboard = [
                [InlineKeyboardButton("✅ نعم، انشر ألبوماً جديداً", callback_data=f"album_yes_{p_id}")],
                [InlineKeyboardButton("❌ لا، احتفظ بالمنشور القديم", callback_data=f"album_no_{p_id}")]
            ]
            await update.message.reply_text(
                "⚠️ <b>تنبيه:</b> إذا اخترتِ نشر ألبوم جديد، سيتم حذف المنشور الحالي في القناة ونشره في مكان آخر.\n\n"
                "هل تريدين المتابعة؟",
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            return ConversationHandler.END
        
        # إذا أرسل صورة
        if update.message.photo:
            photo_id = update.message.photo[-1].file_id
            
            products = load_products()
            p = next((item for item in products if item["id"] == p_id), None)
            
            if not p:
                await update.message.reply_text("⚠️ لم يتم العثور على المنتج.")
                return ConversationHandler.END
                
            # جلب الصور الحالية
            photos = p.get("photos") or []
            if isinstance(photos, str):
                import json
                photos = json.loads(photos)
            if not isinstance(photos, list):
                photos = []
                
            photos.append(photo_id)
            
            # تحديث المنتج في Supabase
            update_product(p_id, {"photos": photos})
            
            await update.message.reply_text(f"✅ تم حفظ الصورة. أرسلي صورة أخرى أو /done للانتهاء.")
            return ASK_MORE_PHOTOS
            
        await update.message.reply_text("⚠️ الرجاء إرسال صورة أو /done للانتهاء.")
        return ASK_MORE_PHOTOS
        
    except Exception as e:
        print(f"🔴 خطأ في add_more_photos: {e}")
        await update.message.reply_text(f"⚠️ حدث خطأ غير متوقع: {e}")
        return ASK_MORE_PHOTOS

async def handle_album_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالجة اختيار نشر الألبوم أو الاحتفاظ بالمنشور القديم"""
    query = update.callback_query
    await query.answer()
    
    data_choice = query.data.split("_")
    action = data_choice[1] # yes أو no
    p_id = int(data_choice[2])
    
    # ═══ جلب المنتج من Supabase ═══
    products = load_products()
    p = next((item for item in products if item["id"] == p_id), None)
    
    if not p:
        await query.edit_message_text(f"⚠️ لم يتم العثور على منتج بالمعرف {p_id}.")
        return
    
    if action == "no":
        await query.edit_message_text("✅ تم حفظ الصور في البوت، لكن المنشور القديم في القناة لم يتغير.")
        return
    
    # إذا اختار "نعم" (نشر ألبوم جديد)
    channel_id = int(os.getenv("CHANNEL_ID"))
    
    # 1. حذف المنشور القديم
    if p.get("message_id"):
        try:
            await context.bot.delete_message(chat_id=channel_id, message_id=p["message_id"])
        except Exception as e:
            print(f"⚠️ فشل حذف المنشور: {e}")
    
    # 2. بناء الكابشن
    caption = f"✨ <b>{p['name']}</b>\n\n"
    caption += f"💰 السعر: {p['price']} دج\n"
    ARABIC_NAMES = {"colors": "🎨 الألوان", "sizes": "📏 المقاسات", "volume": "🧴 السعة"}
    for k, v in p.get('attributes', {}).items():
        arabic_name = ARABIC_NAMES.get(k, k)
        if isinstance(v, list):
            v = "، ".join([str(item).strip() for item in v])
        caption += f"{arabic_name}: {v}\n"
    caption += f"📝 {p.get('description', '')}\n\n"
    smart_link = f"https://t.me/sewingFadha_il_bot?start=product_{p['id']}"
    caption += f"🛒 <a href='{smart_link}'>اطلبي الآن</a>"
    
    # 3. جلب الصور من Supabase
    photos = p.get("photos") or []
    if isinstance(photos, str):
        import json
        photos = json.loads(photos)
    if not isinstance(photos, list):
        photos = []
    
    print(f"🔍 [DEBUG] photos = {photos}, type = {type(photos)}")
    
    if not photos:
        await query.edit_message_text("⚠️ لا توجد صور لهذا المنتج!")
        return
    
    # 4. إرسال الألبوم
    media_group = []
    for i, photo in enumerate(photos):
        if i == 0:
            media_group.append(InputMediaPhoto(media=photo, caption=caption, parse_mode="HTML"))
        else:
            media_group.append(InputMediaPhoto(media=photo))
    
    try:
        sent_messages = await context.bot.send_media_group(chat_id=channel_id, media=media_group)
        # تحديث message_id في Supabase
        update_product(p_id, {"message_id": sent_messages[0].message_id})
        await query.edit_message_text("✅ تم نشر ألبوم الصور الجديد في القناة!")
    except Exception as e:
        await query.edit_message_text(f"⚠️ فشل النشر: {e}")

async def photos_done(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """عند الانتهاء من إرسال الصور، ننتقل لسؤال الاسم"""
    query = update.callback_query
    await query.answer()
    
    # التأكد من أن لدينا صوراً
    if 'photos' not in context.user_data['new_product'] or not context.user_data['new_product']['photos']:
        await query.edit_message_text("⚠️ لم ترسلي أي صورة! أرسلي صورة أولاً.")
        return ASK_PHOTO
    
    # الانتقال لسؤال اسم المنتج
    await query.edit_message_text("✍️ ممتاز! الآن، ما هو اسم المنتج؟")
    return ASK_NAME

async def delete_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.data == "confirm_delete_yes":
        p_id = context.user_data['delete_id']
        try:
            # الحذف من Supabase
            delete_product(p_id)
            await query.edit_message_text(f"✅ تم حذف المنتج (ID: {p_id}) بنجاح!")
        except Exception as e:
            await query.edit_message_text(f"⚠️ فشل الحذف: {e}")
    else:
        await query.edit_message_text("❌ تم الإلغاء.")
        
    return ConversationHandler.END

async def delete_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """بدء عملية حذف منتج"""
    await update.message.reply_text("🗑️ أرسلي <b>ID</b> المنتج الذي تريدين حذفه:", parse_mode="HTML")
    return DELETE_ID

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
    
    # ═══ 1. محادثات الإدارة (يجب أن تكون أولاً) ═══
    
    # 1.1 الإضافة
    conv_handler = ConversationHandler(
        entry_points=[
            CommandHandler("add", add_product_start),
            MessageHandler(filters.Regex("^➕ إضافة منتج$"), add_product_start) # ← أضف هذا
        ],
        states={
            CHOOSE_CATEGORY: [CallbackQueryHandler(category_chosen, pattern="^cat_")],
            ASK_PHOTO: [
                MessageHandler(filters.PHOTO, get_photo),
                CallbackQueryHandler(photos_done, pattern="^photos_done$")
            ],
            ASK_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_name)],
            ASK_PRICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_price)],
            ASK_DYNAMIC_ATTR: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_dynamic_attr)], 
            ASK_DESC: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_desc)],
        },
        fallbacks=[CommandHandler("cancel", cancel)]
    )
    app.add_handler(conv_handler)

    # 1.2 التعديل
    edit_handler = ConversationHandler(
        entry_points=[
            CommandHandler("edit", edit_start),
            MessageHandler(filters.Regex("^✏️ تعديل منتج$"), edit_start) # ← أضف هذا
      
        ],
        states={
            EDIT_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, edit_get_id)],
            EDIT_FIELD: [CallbackQueryHandler(edit_choose_field, pattern="^edit_")],
            EDIT_VALUE: [MessageHandler(filters.TEXT & ~filters.COMMAND, edit_save)],
        },
        fallbacks=[CommandHandler("cancel", cancel)]
    )
    app.add_handler(edit_handler)

    # 1.3 الحذف
    delete_handler = ConversationHandler(
        entry_points=[
            CommandHandler("delete", delete_start),
            MessageHandler(filters.Regex("^🗑️ حذف منتج$"), delete_start) # ← أضف هذا

        ],
        states={
            DELETE_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, delete_get_id)],
            DELETE_CONFIRM: [CallbackQueryHandler(delete_confirm, pattern="^confirm_delete_")],
        },
        fallbacks=[CommandHandler("cancel", cancel)]
    )
    app.add_handler(delete_handler)

        # 1.4 إضافة صور
    photos_handler = ConversationHandler(
        entry_points=[
            CommandHandler("add_photos", add_photos_start),
            MessageHandler(filters.Regex("^🖼️ إضافة صور$"), add_photos_start)
        ],
        states={
            ASK_PHOTOS_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_photos_get_id)],
            ASK_MORE_PHOTOS: [
                MessageHandler(filters.PHOTO, add_more_photos),
                CommandHandler("done", add_more_photos)
            ],
        },
        fallbacks=[
            CommandHandler("cancel", cancel),
            CallbackQueryHandler(handle_album_choice, pattern="^album_")  # ← أضف هذا
        ]
    )
    app.add_handler(photos_handler)

    # ═══ 2. الأوامر العادية ═══
    app.add_handler(CallbackQueryHandler(handle_album_choice, pattern="^album_"))
    app.add_handler(CommandHandler("start", start_admin))
    app.add_handler(CommandHandler("list", list_products))
    app.add_handler(CommandHandler("stats", stats))
    app.add_handler(CommandHandler("cancel", cancel))
    app.add_handler(CommandHandler("orders", orders_stats))

    # ═══ 3. معالج الأزرار الثابتة (يجب أن يكون في النهاية) ═══
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_admin_buttons))

    # ═══ اكتشاف بيئة التشغيل ═══
    is_render = os.environ.get("RENDER") is not None
    webhook_url = os.environ.get("WEBHOOK_URL")

    if is_render and webhook_url:
        # ═══ وضع Webhook (على Render) ═══
        port = int(os.environ.get("PORT", 8080))
        print(f"🚀 بوت الإدارة يعمل في وضع Webhook على المنفذ {port}")
        app.run_webhook(
            listen="0.0.0.0",
            port=port,
            url_path="admin_webhook",
            webhook_url=f"{webhook_url}/admin_webhook",
            drop_pending_updates=True
        )
    else:
        # ═══ وضع Polling (على جهازك المحلي) ═══
        print("🤖 بوت الإدارة يعمل في وضع Polling (محلي)")
        app.run_polling()

if __name__ == "__main__":
    main()