"""
بوت الإدارة - متجر الفضائل
Admin Bot for Sewing Shop
"""

import os
import json
import uuid
import requests
from dotenv import load_dotenv
from database import load_products, save_product, update_product, delete_product, compress_image, upload_image_to_supabase
from telegram import InputMediaPhoto, Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from telegram.request import HTTPXRequest
from telegram.ext import (
    Application, CommandHandler, ContextTypes,
    ConversationHandler, MessageHandler, CallbackQueryHandler,
    filters
)

load_dotenv()

# ═══ الحالات ═══
CHOOSE_CATEGORY, ASK_PHOTO, ASK_NAME, ASK_PRICE, ASK_DYNAMIC_ATTR, ASK_DESC = range(6)
PREVIEW_PRODUCT = 6  # ✅ حالة جديدة: معاينة المنتج قبل النشر
EDIT_ID, EDIT_FIELD, EDIT_VALUE = range(10, 13)
DELETE_ID, DELETE_CONFIRM = range(13, 15)
ASK_PHOTOS_ID, ASK_MORE_PHOTOS = range(20, 22)

MAX_PHOTOS = 10  # ✅ حد أقصى للصور

ATTR_QUESTIONS = {
    "colors": "🎨 ما الألوان المتاحة؟ (افصلي بينها بفاصلة)",
    "sizes": "📏 ما المقاسات المتاحة؟ (افصلي بينها بفاصلة)",
    "volume": "🧴 ما هو حجم/سعة المنتج؟ (مثال: 50ml)",
    "weight": "⚖️ ما هو وزن المنتج؟ (مثال: 1kg)",
    "details": "📝 أضيفي تفاصيل إضافية (مثال: قطن، مصنوع يدوياً)"
}

ARABIC_ATTR_NAMES = {
    "colors": "🎨 الألوان",
    "sizes": "📏 المقاسات",
    "volume": "🧴 السعة",
    "weight": "⚖️ الوزن",
    "details": "📝 التفاصيل"
}

ARABIC_CATEGORIES = {
    "jalabib": "👗 جلابيب",
    "accessories": "💍 أكسسوارات",
    "perfumes": "🧴 عطور",
    "oils": "🌿 زيوت",
    "home": "🏠 مستلزمات منزلية",
    "other": "🛍️ آخر"
}


def load_token():
    token = os.getenv("ADMIN_BOT_TOKEN")
    if token:
        return token
    if os.path.exists(".env"):
        with open(".env", "r", encoding="utf-8") as f:
            for line in f:
                if line.strip().startswith("ADMIN_BOT_TOKEN="):
                    return line.strip().split("=", 1)[1].strip().strip('"')
    raise ValueError("⚠️ ADMIN_BOT_TOKEN غير موجود في متغيرات البيئة أو .env")


def load_data():
    with open("products.json", "r", encoding="utf-8") as f:
        return json.load(f)


def save_data(data):
    with open("products.json", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def build_caption(product_name, price, attributes, description, product_id, is_preview=False):
    """بناء نص الكابشن للمنتج (يُستخدم في المعاينة والنشر)"""
    smart_link = f"https://t.me/sewingFadha_il_bot?start=product_{product_id}"
    
    attributes_text = ""
    for k, v in attributes.items():
        arabic_name = ARABIC_ATTR_NAMES.get(k, k)
        if isinstance(v, list):
            v = "، ".join([str(item).strip() for item in v])
        attributes_text += f"{arabic_name}: {v}\n"
    
    caption = (
        f"✨ <b>{product_name}</b>\n\n"
        f"💰 السعر: {price} دج\n"
        f"{attributes_text}"
        f"📝 {description}\n\n"
        f"🛒 <a href='{smart_link}'>اطلبي الآن</a>"
    )
    
    if is_preview:
        caption = "👁️ <b>معاينة المنتج:</b>\n\n" + caption
    
    return caption, smart_link

import asyncio
import httpx

async def download_and_upload_image(context, photo_id, max_retries=3):
    """دالة قوية لتحميل الصورة من تيليجرام ورفعها إلى Supabase مع محاولات متعددة"""
    for attempt in range(max_retries):
        try:
            # 1. جلب مسار الملف من تيليجرام
            file_info = await context.bot.get_file(photo_id)
            telegram_url = file_info.file_path
            
            # 2. تحميل الصورة باستخدام httpx (أكثر استقراراً من requests)
            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.get(telegram_url)
                response.raise_for_status()
                image_bytes = response.content
            
            # 3. ضغط الصورة
            compressed_bytes = compress_image(image_bytes, max_width=800, quality=85)
            
            # 4. رفع الصورة إلى Supabase
            safe_name = f"product_{uuid.uuid4().hex[:10]}.jpg"
            public_url = upload_image_to_supabase(compressed_bytes, safe_name)
            
            if public_url:
                return public_url  # نجحنا!
                
        except Exception as e:
            print(f"⚠️ محاولة {attempt + 1} فشلت للصورة {photo_id[:10]}...: {e}")
            if attempt < max_retries - 1:
                await asyncio.sleep(2)  # الانتظار ثانيتين قبل المحاولة التالية
            else:
                raise e  # فشلت كل المحاولات

import time # تأكدي من وجودها في أعلى الملف
def upload_with_retry(image_bytes, filename, max_retries=3):
    """محاولة رفع الصورة إلى Supabase مع إعادة المحاولة عند الفشل"""
    for attempt in range(max_retries):
        try:
            # استدعاء دالة الرفع الأصلية الخاصة بك
            url = upload_image_to_supabase(image_bytes, filename)
            if url:
                return url
        except Exception as e:
            print(f"⚠️ محاولة رفع {attempt + 1} فشلت: {e}")
            if attempt < max_retries - 1:
                time.sleep(2) # الانتظار ثانيتين قبل المحاولة التالية
    return None

def get_preview_keyboard():
    """أزرار المعاينة الموحدة (لتجنب التكرار)"""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ نشر في القناة", callback_data="preview_publish")],
        [InlineKeyboardButton("✏️ تعديل الاسم", callback_data="preview_edit_name"),
         InlineKeyboardButton("💰 تعديل السعر", callback_data="preview_edit_price")],
        [InlineKeyboardButton("📝 تعديل الوصف", callback_data="preview_edit_desc")],
        [InlineKeyboardButton("❌ إلغاء", callback_data="preview_cancel")]
    ])

# ═══ التحقق من صاحبة المتجر ═══
def is_admin(user_id):
    """
    ✅ إصلاح: التحقق الفعلي من صلاحيات الأدمن.
    ضعي ADMIN_ID في متغيرات البيئة (أو .env) كمعرف تيليجرام الخاص بك.
    يمكن وضع أكثر من معرف مفصولاً بفاصلة.
    """
    admin_ids_str = os.getenv("ADMIN_ID", "")
    if not admin_ids_str:
        # في حال عدم التعيين، نرفض الجميع حفاظاً على الأمان (أو نسمح في وضع التطوير)
        print("⚠️ ADMIN_ID غير معيّن! لن يُسمح لأحد باستخدام البوت.")
        return False
    admin_ids = [x.strip() for x in admin_ids_str.split(",") if x.strip()]
    return str(user_id) in admin_ids


async def deny_non_admin(update: Update):
    """إرسال رسالة رفض للمستخدم غير المصرح"""
    if update.message:
        await update.message.reply_text("⛔ ليس لديك صلاحية استخدام هذا البوت.")
    elif update.callback_query:
        await update.callback_query.answer("⛔ ليس لديك صلاحية.", show_alert=True)


async def start_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await deny_non_admin(update)
        return

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
    if not is_admin(update.effective_user.id):
        await deny_non_admin(update)
        return

    text = update.message.text

    # ✅ الإصلاح: الأزرار التي لها ConversationHandler نتركها له (بدون استدعاء مزدوج)
    if text in ("➕ إضافة منتج", "🗑️ حذف منتج", "✏️ تعديل منتج", "🖼️ إضافة صور"):
        # هذه الأزرار مُلتقطة بواسطة ConversationHandler كـ entry_points
        # لا نفعل شيئاً هنا لتجنب الاستدعاء المزدوج
        return

    if text == "📦 عرض المنتجات":
        await list_products(update, context)
    elif text == "📊 الإحصائيات":
        await stats(update, context)
    elif text == "📦 الطلبات":
        await orders_stats(update, context)
    else:
        await update.message.reply_text("⚠️ الرجاء اختيار زر من القائمة.")


# ═══ إضافة منتج ═══
async def add_product_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await deny_non_admin(update)
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

    context.user_data['new_product'] = {'category': cat_id, 'attributes': {}, 'photos': []}
    context.user_data['remaining_attrs'] = list(cat_attrs)

    await query.edit_message_text("📸 ممتاز! الآن أرسلي صورة المنتج:")
    return ASK_PHOTO


async def get_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    ✅ إصلاح: دعم الألبومات (media_group_id) مع انتظار بسيط لتجميع الصور.
    تيليجرام يرسل كل صورة في الألبوم كرسالة منفصلة بنفس media_group_id.
    """
    product = context.user_data.get('new_product')
    if not product:
        await update.message.reply_text("⚠️ حدث خطأ، أرسلي /cancel وابدئي من جديد.")
        return ConversationHandler.END

    photos = product.setdefault('photos', [])

    if not update.message.photo:
        await update.message.reply_text("⚠️ الرجاء إرسال صورة.")
        return ASK_PHOTO

    if len(photos) >= MAX_PHOTOS:
        await update.message.reply_text(f"⚠️ وصلتِ للحد الأقصى ({MAX_PHOTOS} صور). اضغطي 'تم' للمتابعة.")
        keyboard = [[InlineKeyboardButton("✅ تم، انتقل للخطوة التالية", callback_data="photos_done")]]
        await update.message.reply_text("هل تريدين المتابعة؟", reply_markup=InlineKeyboardMarkup(keyboard))
        return ASK_PHOTO

    photo_id = update.message.photo[-1].file_id
    photos.append(photo_id)

    # ✅ إذا كانت ضمن ألبوم، لا نرسل رسالة لكل صورة (لتجنب الإزعاج)
    media_group_id = getattr(update.message, "media_group_id", None)

    if media_group_id:
        # ضمن ألبوم: ننتظر انتهاء الألبوم ثم نرسل رسالة واحدة
        # نستخدم job بسيط بعد 1.5 ثانية للتحقق
        if 'album_waiting' not in context.user_data:
            context.user_data['album_waiting'] = True

            async def notify_album_done(ctx: ContextTypes.DEFAULT_TYPE):
                context.user_data.pop('album_waiting', None)
                current_photos = context.user_data.get('new_product', {}).get('photos', [])
                keyboard = [[InlineKeyboardButton("✅ تم، انتقل للخطوة التالية", callback_data="photos_done")]]
                try:
                    await ctx.bot.send_message(
                        chat_id=update.effective_chat.id,
                        text=f"📸 تم استلام {len(current_photos)} صورة.\n"
                             "أرسلي المزيد أو اضغطي 'تم' للمتابعة.",
                        reply_markup=InlineKeyboardMarkup(keyboard)
                    )
                except Exception:
                    pass

            context.job_queue.run_once(notify_album_done, when=1.5)
    else:
        keyboard = [[InlineKeyboardButton("✅ تم، انتقل للخطوة التالية", callback_data="photos_done")]]
        await update.message.reply_text(
            f"📸 تم استلام الصورة ({len(photos)}/{MAX_PHOTOS}).\n"
            "أرسلي صورة أخرى، أو اضغطي 'تم' للمتابعة.",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    return ASK_PHOTO


async def photos_done(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    photos = context.user_data.get('new_product', {}).get('photos', [])
    if not photos:
        await query.edit_message_text("⚠️ لم ترسلي أي صورة! أرسلي صورة أولاً.")
        return ASK_PHOTO

    await query.edit_message_text("✍️ ممتاز! الآن، ما هو اسم المنتج؟")
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
    if not remaining:
        await update.message.reply_text("📝 أضيفي وصفاً قصيراً للمنتج:")
        return ASK_DESC

    attr = remaining.pop(0)
    value = update.message.text

    if attr in ["colors", "sizes"]:
        value = value.replace("،", ",").replace(".", ",")
        value = [v.strip() for v in value.split(",") if v.strip()]

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
    """حفظ الوصف وعرض معاينة للمنتج (بدلاً من النشر المباشر)"""
    context.user_data['new_product']['description'] = update.message.text
    product = context.user_data['new_product']
    
    if not is_admin(update.effective_user.id):
        await deny_non_admin(update)
        return ConversationHandler.END
    
    # ═══ 1. رفع الصور إلى Supabase ═══

        # ═══ 1. رفع الصور إلى Supabase ═══
    await update.message.reply_text("⏳ جاري رفع الصور، يرجى الانتظار... (قد يستغرق دقيقة)")
    
    photo_urls = []
    failed_photos = []
    
    for idx, photo_id in enumerate(product.get('photos', []), 1):
        try:
            # استخدام الدالة القوية
            public_url = await download_and_upload_image(context, photo_id)
            photo_urls.append(public_url)
            print(f"✅ [DEBUG] تم رفع الصورة {idx} بنجاح: {public_url}")
        except Exception as e:
            print(f"❌ فشل رفع الصورة {idx} نهائياً بعد 3 محاولات: {e}")
            failed_photos.append(idx)
    
    # ═══ التحقق ═══
    if not photo_urls:
        await update.message.reply_text(
            "❌ فشل رفع جميع الصور إلى القاعدة.\n"
            "هذه المشكلة بسبب ضعف الاتصال بالإنترنت.\n"
            "يرجى المحاولة مرة أخرى لاحقاً."
        )
        return ConversationHandler.END
    
    if failed_photos:
        await update.message.reply_text(
            f"⚠️ تم رفع {len(photo_urls)} من {len(product.get('photos', []))} صورة.\n"
            f"الصور الفاشلة: {', '.join(map(str, failed_photos))}\n"
            f"💡 يمكنك المتابعة، لكن الصور الفاشلة لن تظهر في المتجر الإلكتروني."
        )

    # ═══ 3. حفظ بيانات المنتج مؤقتاً في user_data ═══
    context.user_data['preview_product'] = {
        'name': product['name'],
        'price': product['price'],
        'category': product['category'],
        'description': product['description'],
        'attributes': product.get('attributes', {}),
        'photo': photo_urls[0],
        'photos': photo_urls,
        'original_photos': product.get('photos', [])  # file_ids للنشر
    }
    
    # ═══ 4. بناء الكابشن للمعاينة ═══
    caption, _ = build_caption(
        product['name'],
        product['price'],
        product.get('attributes', {}),
        product['description'],
        product_id=0,  # مؤقتاً، سيتم تحديثه بعد النشر
        is_preview=True
    )
    
    # ═══ 5. عرض المعاينة ═══
    reply_markup = get_preview_keyboard()

    try:
        if len(photo_urls) == 1:
            await update.message.reply_photo(
                photo=photo_urls[0],
                caption=caption,
                parse_mode="HTML",
                reply_markup=reply_markup
            )
        else:
            await update.message.reply_photo(
                photo=photo_urls[0],
                caption=caption,
                parse_mode="HTML",
                reply_markup=reply_markup
            )
            if len(photo_urls) > 1:
                media_group = [InputMediaPhoto(media=url) for url in photo_urls[1:MAX_PHOTOS]]
                await update.message.reply_media_group(media=media_group)
    except Exception as e:
        await update.message.reply_text(f"⚠️ فشل عرض المعاينة: {e}")
        return ConversationHandler.END
    
    return PREVIEW_PRODUCT

async def preview_publish(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """نشر المنتج في القناة بعد الموافقة"""
    query = update.callback_query
    await query.answer()
    
    product = context.user_data.get('preview_product')
    if not product:
        await query.edit_message_caption("⚠️ انتهت صلاحية المعاينة. يرجى البدء من جديد.")
        return ConversationHandler.END
    
    # ═══ 1. حفظ المنتج في Supabase ═══
    product_data = {
        "name": product['name'],
        "price": product['price'],
        "category": product['category'],
        "description": product['description'],
        "attributes": product['attributes'],
        "photo": product['photo'],
        "photos": product['photos']
    }
    
    try:
        saved_product = save_product(product_data)
        new_id = saved_product[0]['id'] if saved_product else 0
    except Exception as e:
        await query.edit_message_caption(f"⚠️ فشل حفظ المنتج: {e}")
        return ConversationHandler.END
    
    # ═══ 2. بناء الكابشن النهائي (مع ID الحقيقي) ═══
    caption, _ = build_caption(
        product['name'],
        product['price'],
        product['attributes'],
        product['description'],
        product_id=new_id,
        is_preview=False
    )
    
    # ═══ 3. النشر في القناة ═══
    channel_id = int(os.getenv("CHANNEL_ID"))
    try:
        original_photos = product.get('original_photos', [])
        if not original_photos:
            await query.edit_message_caption("⚠️ لا توجد صور للنشر!")
            return ConversationHandler.END
        
        if len(original_photos) == 1:
            sent_message = await context.bot.send_photo(
                chat_id=channel_id,
                photo=original_photos[0],
                caption=caption,
                parse_mode="HTML"
            )
            update_product(new_id, {
                "message_id": sent_message.message_id,
                "message_ids": [sent_message.message_id]
            })
        else:
            media_group = []
            for i, photo in enumerate(original_photos[:MAX_PHOTOS]):
                if i == 0:
                    media_group.append(InputMediaPhoto(media=photo, caption=caption, parse_mode="HTML"))
                else:
                    media_group.append(InputMediaPhoto(media=photo))
            
            sent_messages = await context.bot.send_media_group(
                chat_id=channel_id,
                media=media_group
            )
            if sent_messages:
                all_ids = [m.message_id for m in sent_messages]
                update_product(new_id, {
                    "message_id": all_ids[0],
                    "message_ids": all_ids
                })
        
        await query.edit_message_caption(
            f"✅ <b>تم نشر المنتج بنجاح!</b>\n\n"
            f"🆔 ID: {new_id}\n"
            f"📦 {product['name']}",
            parse_mode="HTML"
        )
    except Exception as e:
        await query.edit_message_caption(
            f"⚠️ فشل النشر في القناة: {e}\n\n"
            f"تم حفظ المنتج في القاعدة (ID: {new_id}) لكن لم يُنشر."
        )
    
    context.user_data.pop('preview_product', None)
    return ConversationHandler.END

async def preview_edit_field(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """بدء تعديل حقل من المعاينة"""
    query = update.callback_query
    await query.answer()
    
    field = query.data.replace("preview_edit_", "")  # name / price / desc
    context.user_data['preview_editing'] = field
    
    field_names = {
        "name": "الاسم الجديد",
        "price": "السعر الجديد (أرقام فقط)",
        "desc": "الوصف الجديد"
    }
    
    await query.message.reply_text(
        f"✏️ أرسلي {field_names.get(field, 'القيمة الجديدة')}:\n"
        f"(أو أرسلي /cancel للإلغاء)",
        parse_mode="HTML"
    )

    # (اختياري) إزالة الأزرار من الرسالة القديمة لمنع الضغط عليها مجدداً
    try:
        await query.edit_message_reply_markup(reply_markup=None)
    except Exception:
        pass

    return PREVIEW_PRODUCT

async def preview_apply_edit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """تطبيق التعديل وإعادة عرض المعاينة"""
    field = context.user_data.get('preview_editing')
    product = context.user_data.get('preview_product')
    
    if not product:
        await update.message.reply_text("⚠️ انتهت صلاحية المعاينة. يرجى البدء من جديد.")
        return ConversationHandler.END
    
    if not field:
        await update.message.reply_text("⚠️ يرجى اختيار أحد أزرار التعديل أولاً (الاسم / السعر / الوصف).")
        return PREVIEW_PRODUCT  # ← نبقى في المعاينة ولا ننهيها
    
    new_value = update.message.text
    
    # التحقق من صحة السعر
    if field == "price":
        try:
            new_value = int(new_value)
        except ValueError:
            await update.message.reply_text("⚠️ السعر يجب أن يكون رقماً. حاولي مرة أخرى:")
            return PREVIEW_PRODUCT
    
    # تحديث الحقل
    if field == "name":
        product['name'] = new_value
    elif field == "price":
        product['price'] = new_value
    elif field == "desc":
        product['description'] = new_value
    
    context.user_data['preview_product'] = product
    context.user_data.pop('preview_editing', None)
    
    # إعادة عرض المعاينة
    caption, _ = build_caption(
        product['name'],
        product['price'],
        product['attributes'],
        product['description'],
        product_id=0,
        is_preview=True
    )
    
    reply_markup = get_preview_keyboard()
    
    await update.message.reply_photo(
        photo=product['photo'],
        caption=caption,
        parse_mode="HTML",
        reply_markup=get_preview_keyboard()
    )
    return PREVIEW_PRODUCT

async def preview_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """إلغاء المعاينة مع تنظيف الصور المرفوعة"""
    query = update.callback_query
    await query.answer()
    
    product = context.user_data.get('preview_product')
    
    # ═══ 1. حذف الصور من Supabase (تنظيف) ═══
    if product:
        try:
            from database import supabase
            filenames = [url.split('/')[-1] for url in product.get('photos', [])]
            if filenames:
                supabase.storage.from_("products").remove(filenames)
        except Exception as e:
            print(f"⚠️ فشل حذف الصور المؤقتة: {e}")

    # ═══ 2. مسح البيانات المؤقتة ═══
    context.user_data.pop('preview_product', None)
    context.user_data.pop('preview_editing', None)
    
    # ═══ 3. إبلاغ المستخدم ═══
    await query.edit_message_caption("❌ تم إلغاء إضافة المنتج.")
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # ✅ التحقق من وجود صور معلقة وحذفها
    product = context.user_data.get('preview_product')
    if product:
        try:
            from database import supabase
            filenames = [url.split('/')[-1] for url in product.get('photos', [])]
            if filenames:
                supabase.storage.from_("products").remove(filenames)
        except Exception as e:
            print(f"⚠️ فشل حذف الصور المؤقتة: {e}")
            
    context.user_data.clear()
    await update.message.reply_text("❌ تم الإلغاء.")
    return ConversationHandler.END

async def list_products(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await deny_non_admin(update)
        return

    try:
        products = load_products()
    except Exception as e:
        await update.message.reply_text(f"⚠️ فشل جلب المنتجات: {e}")
        return

    if not products:
        await update.message.reply_text("📭 لا توجد منتجات حالياً.")
        return

    text = "📦 <b>قائمة المنتجات الحالية:</b>\n\n"
    for p in products:
        cat_id = p.get("category", "")
        cat_name = ARABIC_CATEGORIES.get(cat_id, cat_id)
        text += f"🆔 <b>ID: {p['id']}</b> | {p['name']}\n"
        text += f"   💰 السعر: {p['price']} دج | القسم: {cat_name}\n\n"

    text += "💡 <i>للتعديل أو الحذف، استخدم الأوامر /edit أو /delete</i>"
    await update.message.reply_text(text, parse_mode="HTML")


async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await deny_non_admin(update)
        return

    products = load_products()
    if not products:
        await update.message.reply_text("📊 لا توجد منتجات في المتجر حالياً.")
        return

    text = "📊 <b>إحصائيات المتجر:</b>\n\n"
    total_products = len(products)

    cat_counts = {}
    for p in products:
        cat = p.get("category", "other")
        cat_counts[cat] = cat_counts.get(cat, 0) + 1

    for cat_id, count in cat_counts.items():
        cat_name = ARABIC_CATEGORIES.get(cat_id, cat_id)
        text += f"{cat_name}: {count} منتج\n"

    text += f"\n📦 <b>الإجمالي: {total_products} منتج</b>"
    await update.message.reply_text(text, parse_mode="HTML")


# ═══ تعديل ═══
async def edit_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await deny_non_admin(update)
        return ConversationHandler.END
    await update.message.reply_text(
        "🛠️ أرسلي <b>ID</b> المنتج الذي تريدين تعديله:\n(استخدمي /list لمعرفة الأرقام)",
        parse_mode="HTML"
    )
    return EDIT_ID


async def edit_get_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        p_id = int(update.message.text)
    except ValueError:
        await update.message.reply_text("⚠️ الرجاء إرسال رقم صحيح.")
        return EDIT_ID

    context.user_data['edit_id'] = p_id
    keyboard = [
        [InlineKeyboardButton("💰 تعديل السعر", callback_data="edit_price")],
        [InlineKeyboardButton("✍️ تعديل الاسم", callback_data="edit_name")],
        [InlineKeyboardButton("📝 تعديل الوصف", callback_data="edit_desc")],
    ]
    await update.message.reply_text("ماذا تريدين أن تعدلي؟", reply_markup=InlineKeyboardMarkup(keyboard))
    return EDIT_FIELD


async def edit_choose_field(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data['edit_field'] = query.data
    await query.edit_message_text("✍️ أرسلي القيمة الجديدة:")
    return EDIT_VALUE


async def edit_save(update: Update, context: ContextTypes.DEFAULT_TYPE):
    new_value = update.message.text
    p_id = context.user_data.get('edit_id')
    field = context.user_data.get('edit_field')

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

    try:
        updated = update_product(p_id, update_data)
        if not updated:
            await update.message.reply_text(f"⚠️ لم يتم العثور على منتج بالمعرف {p_id}.")
            return ConversationHandler.END
    except Exception as e:
        await update.message.reply_text(f"⚠️ فشل التحديث في قاعدة البيانات: {e}")
        return ConversationHandler.END

    # تحديث المنشور في القناة
    try:
        products = load_products()
        p = next((item for item in products if item["id"] == p_id), None)

        if p and p.get("message_id"):
            channel_id = int(os.getenv("CHANNEL_ID"))
            caption = f"✨ <b>{p['name']}</b>\n\n"
            caption += f"💰 السعر: {p['price']} دج\n"
            for k, v in p.get('attributes', {}).items():
                arabic_name = ARABIC_ATTR_NAMES.get(k, k)
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


# ═══ حذف ═══
async def delete_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await deny_non_admin(update)
        return ConversationHandler.END
    await list_products(update, context)
    await update.message.reply_text(
        "🗑️ أرسلي <b>ID</b> المنتج الذي تريدين حذفه (من القائمة أعلاه):\n"
        "(أو /cancel للإلغاء)",
        parse_mode="HTML"
    )
    return DELETE_ID


async def delete_get_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        p_id = int(update.message.text)
    except ValueError:
        await update.message.reply_text("⚠️ الرجاء إرسال رقم صحيح (أو /cancel).")
        return DELETE_ID

    context.user_data['delete_id'] = p_id

    products = load_products()
    product_name = None
    for p in products:
        if p["id"] == p_id:
            product_name = p["name"]
            break

    if product_name is None:
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


async def delete_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data != "confirm_delete_yes":
        await query.edit_message_text("❌ تم الإلغاء.")
        return ConversationHandler.END

    p_id = context.user_data.get('delete_id')
    if p_id is None:
        await query.edit_message_text("⚠️ حدث خطأ، يرجى إعادة المحاولة.")
        return ConversationHandler.END

    try:
        products = load_products()
        product = next((p for p in products if p["id"] == p_id), None)

        if not product:
            await query.edit_message_text(f"⚠️ لم يتم العثور على منتج بالمعرف {p_id}.")
            return ConversationHandler.END

        delete_product(p_id)
        print(f"✅ تم حذف المنتج (ID: {p_id}) من القاعدة.")

        channel_id = int(os.getenv("CHANNEL_ID"))
        if product.get("message_ids"):
            try:
                for msg_id in product["message_ids"]:
                    await context.bot.delete_message(chat_id=channel_id, message_id=msg_id)
            except Exception as e:
                print(f"⚠️ فشل حذف بعض الصور: {e}")
        elif product.get("message_id"):
            try:
                await context.bot.delete_message(chat_id=channel_id, message_id=product["message_id"])
            except Exception as e:
                print(f"⚠️ فشل حذف المنشور: {e}")

        await query.edit_message_text(f"✅ تم حذف المنتج (ID: {p_id}) والمنشور من القناة بنجاح!")
    except Exception as e:
        await query.edit_message_text(f"⚠️ حدث خطأ أثناء الحذف: {e}")

    return ConversationHandler.END


# ═══ الطلبات ═══
async def orders_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await deny_non_admin(update)
        return

    try:
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


# ═══ إضافة صور ═══
async def add_photos_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await deny_non_admin(update)
        return ConversationHandler.END
    await update.message.reply_text("🖼️ أرسلي <b>ID</b> المنتج الذي تريدين إضافة صور له:", parse_mode="HTML")
    return ASK_PHOTOS_ID


async def add_photos_get_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        p_id = int(update.message.text)
    except ValueError:
        await update.message.reply_text("⚠️ الرجاء إرسال رقم صحيح.")
        return ASK_PHOTOS_ID

    context.user_data['photo_product_id'] = p_id

    products = load_products()
    if not any(p["id"] == p_id for p in products):
        await update.message.reply_text(f"⚠️ لم يتم العثور على منتج بالمعرف {p_id}.")
        return ConversationHandler.END

    await update.message.reply_text("📸 ممتاز! أرسلي الصور الجديدة (واحدة تلو الأخرى).\nعندما تنتهين، اضغطي /done.")
    return ASK_MORE_PHOTOS


async def add_more_photos(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        p_id = context.user_data.get('photo_product_id')
        if p_id is None:
            await update.message.reply_text("⚠️ حدث خطأ، يرجى البدء من جديد.")
            return ConversationHandler.END

        # ✅ إذا أرسل المستخدم /done
        if update.message.text == "/done":
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

        if not update.message.photo:
            await update.message.reply_text("⚠️ الرجاء إرسال صورة أو /done للانتهاء.")
            return ASK_MORE_PHOTOS

        photo_id = update.message.photo[-1].file_id

        products = load_products()
        p = next((item for item in products if item["id"] == p_id), None)
        if not p:
            await update.message.reply_text("⚠️ لم يتم العثور على المنتج.")
            return ConversationHandler.END

        photos = p.get("photos") or []
        if isinstance(photos, str):
            photos = json.loads(photos)
        if not isinstance(photos, list):
            photos = []

        # ✅ الإصلاح: التحقق من الحد الأقصى
        if len(photos) >= MAX_PHOTOS:
            await update.message.reply_text(
                f"⚠️ وصلتِ للحد الأقصى ({MAX_PHOTOS} صور). اضغطي /done للانتهاء."
            )
            return ASK_MORE_PHOTOS

        photos.append(photo_id)
        update_product(p_id, {"photos": photos})

        await update.message.reply_text(f"✅ تم حفظ الصورة ({len(photos)}/{MAX_PHOTOS}). أرسلي صورة أخرى أو /done للانتهاء.")
        return ASK_MORE_PHOTOS

    except Exception as e:
        print(f"🔴 خطأ في add_more_photos: {e}")
        await update.message.reply_text(f"⚠️ حدث خطأ غير متوقع: {e}")
        return ASK_MORE_PHOTOS


async def handle_album_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if not is_admin(query.from_user.id):
        await query.answer("⛔ ليس لديك صلاحية.", show_alert=True)
        return

    data_choice = query.data.split("_")
    action = data_choice[1]
    p_id = int(data_choice[2])

    products = load_products()
    p = next((item for item in products if item["id"] == p_id), None)
    if not p:
        await query.edit_message_text(f"⚠️ لم يتم العثور على منتج بالمعرف {p_id}.")
        return

    if action == "no":
        await query.edit_message_text("✅ تم حفظ الصور في البوت، لكن المنشور القديم في القناة لم يتغير.")
        return

    channel_id = int(os.getenv("CHANNEL_ID"))

    # حذف المنشور القديم
    if p.get("message_ids"):
        try:
            for msg_id in p["message_ids"]:
                await context.bot.delete_message(chat_id=channel_id, message_id=msg_id)
        except Exception as e:
            print(f"⚠️ فشل حذف بعض الصور القديمة: {e}")
    elif p.get("message_id"):
        try:
            await context.bot.delete_message(chat_id=channel_id, message_id=p["message_id"])
        except Exception as e:
            print(f"⚠️ فشل حذف المنشور: {e}")

    caption = f"✨ <b>{p['name']}</b>\n\n"
    caption += f"💰 السعر: {p['price']} دج\n"
    for k, v in p.get('attributes', {}).items():
        arabic_name = ARABIC_ATTR_NAMES.get(k, k)
        if isinstance(v, list):
            v = "، ".join([str(item).strip() for item in v])
        caption += f"{arabic_name}: {v}\n"
    caption += f"📝 {p.get('description', '')}\n\n"
    smart_link = f"https://t.me/sewingFadha_il_bot?start=product_{p['id']}"
    caption += f"🛒 <a href='{smart_link}'>اطلبي الآن</a>"

    photos = p.get("photos") or []
    if isinstance(photos, str):
        photos = json.loads(photos)
    if not isinstance(photos, list):
        photos = []

    if not photos:
        await query.edit_message_text("⚠️ لا توجد صور لهذا المنتج!")
        return

    media_group = []
    for i, photo in enumerate(photos[:MAX_PHOTOS]):
        if i == 0:
            media_group.append(InputMediaPhoto(media=photo, caption=caption, parse_mode="HTML"))
        else:
            media_group.append(InputMediaPhoto(media=photo))

    try:
        sent_messages = await context.bot.send_media_group(chat_id=channel_id, media=media_group)
        all_ids = [m.message_id for m in sent_messages]
        update_product(p_id, {"message_id": all_ids[0], "message_ids": all_ids})
        await query.edit_message_text("✅ تم نشر ألبوم الصور الجديد في القناة!")
    except Exception as e:
        await query.edit_message_text(f"⚠️ فشل النشر: {e}")

def build_caption(product_name, price, attributes, description, product_id, is_preview=False):
    """بناء نص الكابشن للمنتج (يُستخدم في المعاينة والنشر)"""
    smart_link = f"https://t.me/sewingFadha_il_bot?start=product_{product_id}"
    
    attributes_text = ""
    for k, v in attributes.items():
        arabic_name = ARABIC_ATTR_NAMES.get(k, k)
        if isinstance(v, list):
            v = "، ".join([str(item).strip() for item in v])
        attributes_text += f"{arabic_name}: {v}\n"
    
    caption = (
        f"✨ <b>{product_name}</b>\n\n"
        f"💰 السعر: {price} دج\n"
        f"{attributes_text}"
        f"📝 {description}\n\n"
        f"🛒 <a href='{smart_link}'>اطلبي الآن</a>"
    )
    
    if is_preview:
        caption = "👁️ <b>معاينة المنتج:</b>\n\n" + caption
    
    return caption, smart_link
async def timeout_cleanup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """تنظيف الصور عند انتهاء وقت المحادثة"""
    product = context.user_data.get('preview_product')
    if product:
        try:
            from database import supabase
            filenames = [url.split('/')[-1] for url in product.get('photos', [])]
            if filenames:
                supabase.storage.from_("products").remove(filenames)
        except Exception as e:
            print(f"⚠️ فشل حذف الصور عند انتهاء المهلة: {e}")
    
    context.user_data.clear()
    await update.effective_chat.send_message("⏳ انتهت مهلة المحادثة وتم إلغاء العملية وتنظيف الصور المؤقتة.")
    return ConversationHandler.END
async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """تسجيل الأخطاء وإبلاغ المستخدم بلطف"""
    # تسجيل الخطأ في الـ Console
    print(f"⚠️ [ERROR] حدث خطأ: {context.error}")
    
    # إذا كان الخطأ هو انتهاء مهلة (TimedOut)
    import telegram
    if isinstance(context.error, telegram.error.TimedOut):
        if update and hasattr(update, 'effective_message'):
            try:
                await update.effective_message.reply_text(
                    "⚠️ حدث خطأ في الشبكة أثناء محاولة رفع الصورة.\n"
                    "قد تكون الصورة كبيرة أو الاتصال بطيئاً.\n"
                    "💡 يرجى المحاولة مرة أخرى، أو استخدام صورة أصغر حجماً."
                )
            except Exception as e:
                print(f"⚠️ فشل إرسال رسالة الخطأ للمستخدم: {e}")

# ═══ Main ═══
def main():
    token = load_token()
    request = HTTPXRequest(
        connect_timeout=60.0,
        read_timeout=60.0,
        write_timeout=60.0,
        pool_timeout=60.0,
        media_write_timeout=120.0,  # ✅ وقت إضافي لرفع الصور والوسائط

    )

    app = Application.builder().token(token).request(request).get_updates_request(request).build()
    # ✅ إضافة معالج الأخطاء العام
    app.add_error_handler(error_handler)

    # ═══ 1. الإضافة ═══
    conv_handler = ConversationHandler(
        entry_points=[
            CommandHandler("add", add_product_start),
            MessageHandler(filters.Regex("^➕ إضافة منتج$"), add_product_start)
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
            
            # ✅ الحالة الجديدة: المعاينة
            PREVIEW_PRODUCT: [
                CallbackQueryHandler(preview_publish, pattern="^preview_publish$"),
                CallbackQueryHandler(preview_edit_field, pattern="^preview_edit_"),
                CallbackQueryHandler(preview_cancel, pattern="^preview_cancel$"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, preview_apply_edit),
            ],
            # ✅ إضافة معالج انتهاء المهلة
            ConversationHandler.TIMEOUT: [
                MessageHandler(filters.ALL, timeout_cleanup)
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        conversation_timeout=1800  # ← 30 دقيقة (بدلاً من 15)
    )
    app.add_handler(conv_handler)

    # ═══ 2. التعديل ═══
    edit_handler = ConversationHandler(
        entry_points=[
            CommandHandler("edit", edit_start),
            MessageHandler(filters.Regex("^✏️ تعديل منتج$"), edit_start)
        ],
        states={
            EDIT_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, edit_get_id)],
            EDIT_FIELD: [CallbackQueryHandler(edit_choose_field, pattern="^edit_")],
            EDIT_VALUE: [MessageHandler(filters.TEXT & ~filters.COMMAND, edit_save)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        conversation_timeout=900
    )
    app.add_handler(edit_handler)

    # ═══ 3. الحذف ═══
    delete_handler = ConversationHandler(
        entry_points=[
            CommandHandler("delete", delete_start),
            MessageHandler(filters.Regex("^🗑️ حذف منتج$"), delete_start)
        ],
        states={
            DELETE_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, delete_get_id)],
            DELETE_CONFIRM: [CallbackQueryHandler(delete_confirm, pattern="^confirm_delete_")],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        conversation_timeout=900
    )
    app.add_handler(delete_handler)

    # ═══ 4. إضافة صور ═══
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
        fallbacks=[CommandHandler("cancel", cancel)],
        conversation_timeout=1800
    )
    app.add_handler(photos_handler)

    # ═══ 5. معالج اختيار الألبوم (معالج واحد فقط) ═══
    app.add_handler(CallbackQueryHandler(handle_album_choice, pattern="^album_"))

    # ═══ 6. الأوامر العادية ═══
    app.add_handler(CommandHandler("start", start_admin))
    app.add_handler(CommandHandler("list", list_products))
    app.add_handler(CommandHandler("stats", stats))
    app.add_handler(CommandHandler("cancel", cancel))
    app.add_handler(CommandHandler("orders", orders_stats))

    # ═══ 7. الأزرار الثابتة (في النهاية) ═══
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_admin_buttons))

    is_render = os.environ.get("RENDER") is not None
    webhook_url = os.environ.get("WEBHOOK_URL")

    if is_render and webhook_url:
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
        print("🤖 بوت الإدارة يعمل في وضع Polling (محلي)")
        app.run_polling()


if __name__ == "__main__":
    main()