"""
بوت الإدارة - متجر الفضائل
Admin Bot for Sewing Shop
"""

import os
import json
import uuid
import requests
import asyncio
import httpx
import time
from dotenv import load_dotenv
from database import load_products, save_product, update_product, delete_product, compress_image, upload_image_to_supabase, get_all_orders, update_order_status, search_products_by_name
from telegram import InputMediaPhoto, Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton, Bot
from telegram.request import HTTPXRequest
from telegram.ext import (
    Application, CommandHandler, ContextTypes,
    ConversationHandler, MessageHandler, CallbackQueryHandler,
    filters
)

load_dotenv()

# ═══ الحالات ═══
CHOOSE_CATEGORY, ASK_PHOTO, ASK_NAME, ASK_PRICE, ASK_DYNAMIC_ATTR, ASK_DESC = range(6)
PREVIEW_PRODUCT = 6
EDIT_ID, EDIT_FIELD, EDIT_VALUE = range(10, 13)
DELETE_ID, DELETE_CONFIRM = range(13, 15)
ASK_PHOTOS_ID, ASK_MORE_PHOTOS = range(20, 22)
ASK_SEARCH_QUERY = 7

MAX_PHOTOS = 10

ATTR_QUESTIONS = {
    "colors": "🎨 ما الألوان المتاحة؟ (افصلي بينها بفاصلة)",
    "sizes": "📏 ما المقاسات المتاحة؟ (افصلي بينها بفاصلة)",
    "volume": "🧴 ما هو حجم/سعة المنتج؟ (مثال: 50ml)",
    "weight": "⚖️ ما هو وزن المنتج؟ (مثال: 1kg)",
    "details": "📝 أضيفي تفاصيل إضافية (مثال: قطن، مصنوع يدوياً)"
}

ARABIC_ATTR_NAMES = {
    "colors": "🎨 الألوان", "sizes": "📏 المقاسات", "volume": "🧴 السعة",
    "weight": "⚖️ الوزن", "details": "📝 التفاصيل"
}

ARABIC_CATEGORIES = {
    "jalabib": "👗 جلابيب", "accessories": "💍 أكسسوارات",
    "perfumes": "🧴 عطور", "oils": "🌿 زيوت",
    "home": "🏠 مستلزمات منزلية", "other": "🛍️ آخر"
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


async def download_and_upload_image(context, photo_id, max_retries=3):
    for attempt in range(max_retries):
        try:
            file_info = await context.bot.get_file(photo_id)
            telegram_url = file_info.file_path
            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.get(telegram_url)
                response.raise_for_status()
                image_bytes = response.content
            compressed_bytes = compress_image(image_bytes, max_width=800, quality=85)
            safe_name = f"product_{uuid.uuid4().hex[:10]}.jpg"
            public_url = upload_image_to_supabase(compressed_bytes, safe_name)
            if public_url:
                return public_url
        except Exception as e:
            print(f"⚠️ محاولة {attempt + 1} فشلت للصورة {photo_id[:10]}...: {e}")
            if attempt < max_retries - 1:
                await asyncio.sleep(2)
            else:
                raise e


def upload_with_retry(image_bytes, filename, max_retries=3):
    for attempt in range(max_retries):
        try:
            url = upload_image_to_supabase(image_bytes, filename)
            if url: return url
        except Exception as e:
            print(f"⚠️ محاولة رفع {attempt + 1} فشلت: {e}")
            if attempt < max_retries - 1:
                time.sleep(2)
    return None


def get_preview_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ نشر في القناة", callback_data="preview_publish")],
        [InlineKeyboardButton("✏️ تعديل الاسم", callback_data="preview_edit_name"),
         InlineKeyboardButton("💰 تعديل السعر", callback_data="preview_edit_price")],
        [InlineKeyboardButton("📝 تعديل الوصف", callback_data="preview_edit_desc")],
        [InlineKeyboardButton("❌ إلغاء", callback_data="preview_cancel")]
    ])


def is_admin(user_id):
    admin_ids_str = os.getenv("ADMIN_ID", "")
    if not admin_ids_str:
        print("⚠️ ADMIN_ID غير معيّن! لن يُسمح لأحد باستخدام البوت.")
        return False
    admin_ids = [x.strip() for x in admin_ids_str.split(",") if x.strip()]
    return str(user_id) in admin_ids


async def deny_non_admin(update: Update):
    if update.message:
        await update.message.reply_text("⛔ ليس لديك صلاحية استخدام هذا البوت.")
    elif update.callback_query:
        await update.callback_query.answer("⛔ ليس لديك صلاحية.", show_alert=True)


# ═══ الأزرار الثابتة ═══
async def start_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await deny_non_admin(update)
        return
    keyboard = [
        [KeyboardButton("➕ إضافة منتج")],
        [KeyboardButton("📦 عرض المنتجات"), KeyboardButton("🔍 بحث عن منتج")],
        [KeyboardButton("📊 الإحصائيات")],
        [KeyboardButton("🗑️ حذف منتج"), KeyboardButton("✏️ تعديل منتج")],
        [KeyboardButton("🖼️ إضافة صور"), KeyboardButton("📦 الطلبات")]
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    await update.message.reply_text("أهلاً بك في لوحة تحكم المتجر 🌸\nاختر ما تريدين:", reply_markup=reply_markup)


async def handle_admin_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await deny_non_admin(update)
        return
    text = update.message.text
    if text in ("➕ إضافة منتج", "🗑️ حذف منتج", "✏️ تعديل منتج", "🖼️ إضافة صور"):
        return
    if text == "📦 عرض المنتجات": await list_products(update, context)
    elif text == "📊 الإحصائيات": await stats(update, context)
    elif text == "📦 الطلبات": await list_orders(update, context)
    else: await update.message.reply_text("⚠️ الرجاء اختيار زر من القائمة.")


# ═══ إضافة منتج ═══
async def add_product_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await deny_non_admin(update)
        return ConversationHandler.END
    data = load_data()
    categories = data.get("categories", {})
    keyboard = [[InlineKeyboardButton(cat_info["name"], callback_data=f"cat_{cat_id}")] for cat_id, cat_info in categories.items()]
    await update.message.reply_text("🛍️ <b>ما هو نوع المنتج الذي تريدين إضافته؟</b>\nاختر القسم:", parse_mode="HTML", reply_markup=InlineKeyboardMarkup(keyboard))
    return CHOOSE_CATEGORY


async def category_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    cat_id = query.data.replace("cat_", "")
    data = load_data()
    context.user_data['new_product'] = {'category': cat_id, 'attributes': {}, 'photos': []}
    context.user_data['remaining_attrs'] = list(data["categories"][cat_id]["attributes"])
    await query.edit_message_text("📸 ممتاز! الآن أرسلي صورة المنتج:")
    return ASK_PHOTO


async def get_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
        return ASK_PHOTO
    photos.append(update.message.photo[-1].file_id)
    keyboard = [[InlineKeyboardButton("✅ تم، انتقل للخطوة التالية", callback_data="photos_done")]]
    await update.message.reply_text(f"📸 تم استلام الصورة ({len(photos)}/{MAX_PHOTOS}).\nأرسلي صورة أخرى، أو اضغطي 'تم' للمتابعة.", reply_markup=InlineKeyboardMarkup(keyboard))
    return ASK_PHOTO


async def photos_done(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not context.user_data.get('new_product', {}).get('photos'):
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
        context.user_data['new_product']['price'] = int(update.message.text)
    except ValueError:
        await update.message.reply_text("⚠️ الرجاء إدخال رقم صحيح.")
        return ASK_PRICE
    remaining = context.user_data.get('remaining_attrs', [])
    if remaining:
        await update.message.reply_text(ATTR_QUESTIONS.get(remaining[0], "أدخلي القيمة:"))
        return ASK_DYNAMIC_ATTR
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
        value = [v.strip() for v in value.replace("،", ",").replace(".", ",").split(",") if v.strip()]
    context.user_data['new_product']['attributes'][attr] = value
    if remaining:
        await update.message.reply_text(ATTR_QUESTIONS.get(remaining[0], "أدخلي القيمة:"))
        return ASK_DYNAMIC_ATTR
    await update.message.reply_text("📝 أضيفي وصفاً قصيراً للمنتج:")
    return ASK_DESC


async def get_desc(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['new_product']['description'] = update.message.text
    product = context.user_data['new_product']
    if not is_admin(update.effective_user.id):
        await deny_non_admin(update)
        return ConversationHandler.END

    await update.message.reply_text("⏳ جاري رفع الصور، يرجى الانتظار...")
    photo_urls = []
    failed_photos = []
    for idx, photo_id in enumerate(product.get('photos', []), 1):
        try:
            public_url = await download_and_upload_image(context, photo_id)
            photo_urls.append(public_url)
        except Exception as e:
            print(f"❌ فشل رفع الصورة {idx}: {e}")
            failed_photos.append(idx)

    if not photo_urls:
        await update.message.reply_text("❌ فشل رفع جميع الصور. يرجى المحاولة لاحقاً.")
        return ConversationHandler.END
    if failed_photos:
        await update.message.reply_text(f"⚠️ تم رفع {len(photo_urls)} من {len(product.get('photos', []))} صورة.")

    context.user_data['preview_product'] = {
        'name': product['name'], 'price': product['price'], 'category': product['category'],
        'description': product['description'], 'attributes': product.get('attributes', {}),
        'photo': photo_urls[0], 'photos': photo_urls, 'original_photos': product.get('photos', [])
    }
    
    caption, _ = build_caption(product['name'], product['price'], product.get('attributes', {}), product['description'], product_id=0, is_preview=True)
    reply_markup = get_preview_keyboard()
    
    await update.message.reply_photo(photo=photo_urls[0], caption=caption, parse_mode="HTML", reply_markup=reply_markup)
    if len(photo_urls) > 1:
        media_group = [InputMediaPhoto(media=url) for url in photo_urls[1:MAX_PHOTOS]]
        await update.message.reply_media_group(media=media_group)
    return PREVIEW_PRODUCT


async def preview_publish(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    product = context.user_data.get('preview_product')
    if not product:
        await query.edit_message_caption("⚠️ انتهت صلاحية المعاينة.")
        return ConversationHandler.END

    product_data = {
        "name": product['name'], "price": product['price'], "category": product['category'],
        "description": product['description'], "attributes": product['attributes'],
        "photo": product['photo'], "photos": product['photos']
    }
    try:
        saved_product = save_product(product_data)
        new_id = saved_product[0]['id'] if saved_product else 0
    except Exception as e:
        await query.edit_message_caption(f"⚠️ فشل حفظ المنتج: {e}")
        return ConversationHandler.END

    caption, _ = build_caption(product['name'], product['price'], product['attributes'], product['description'], product_id=new_id, is_preview=False)
    channel_id = int(os.getenv("CHANNEL_ID"))
    try:
        original_photos = product.get('original_photos', [])
        if not original_photos: return ConversationHandler.END
        if len(original_photos) == 1:
            sent_message = await context.bot.send_photo(chat_id=channel_id, photo=original_photos[0], caption=caption, parse_mode="HTML")
            update_product(new_id, {"message_id": sent_message.message_id, "message_ids": [sent_message.message_id]})
        else:
            media_group = [InputMediaPhoto(media=photo, caption=caption if i==0 else None, parse_mode="HTML" if i==0 else None) for i, photo in enumerate(original_photos[:MAX_PHOTOS])]
            sent_messages = await context.bot.send_media_group(chat_id=channel_id, media=media_group)
            if sent_messages:
                all_ids = [m.message_id for m in sent_messages]
                update_product(new_id, {"message_id": all_ids[0], "message_ids": all_ids})
        await query.edit_message_caption(f"✅ <b>تم نشر المنتج بنجاح!</b>\n\n🆔 ID: {new_id}\n📦 {product['name']}", parse_mode="HTML")
    except Exception as e:
        await query.edit_message_caption(f"⚠️ فشل النشر: {e}\nتم الحفظ برقم {new_id}.")
    
    context.user_data.pop('preview_product', None)
    return ConversationHandler.END


async def preview_edit_field(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    field = query.data.replace("preview_edit_", "")
    context.user_data['preview_editing'] = field
    field_names = {"name": "الاسم الجديد", "price": "السعر الجديد (أرقام فقط)", "desc": "الوصف الجديد"}
    await query.message.reply_text(f"✏️ أرسلي {field_names.get(field, 'القيمة')}:\n(أو /cancel للإلغاء)")
    return PREVIEW_PRODUCT


async def preview_apply_edit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    field = context.user_data.get('preview_editing')
    product = context.user_data.get('preview_product')
    if not product:
        await update.message.reply_text("⚠️ انتهت صلاحية المعاينة.")
        return ConversationHandler.END
    if not field:
        await update.message.reply_text("⚠️ اختاري حقلاً للتعديل أولاً.")
        return PREVIEW_PRODUCT
    new_value = update.message.text
    if field == "price":
        try: new_value = int(new_value)
        except ValueError:
            await update.message.reply_text("⚠️ السعر يجب أن يكون رقماً.")
            return PREVIEW_PRODUCT
    if field == "name": product['name'] = new_value
    elif field == "price": product['price'] = new_value
    elif field == "desc": product['description'] = new_value
    
    context.user_data['preview_product'] = product
    context.user_data.pop('preview_editing', None)
    
    caption, _ = build_caption(product['name'], product['price'], product['attributes'], product['description'], product_id=0, is_preview=True)
    await update.message.reply_photo(photo=product['photo'], caption=caption, parse_mode="HTML", reply_markup=get_preview_keyboard())
    return PREVIEW_PRODUCT


async def preview_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    product = context.user_data.get('preview_product')
    if product:
        try:
            from database import supabase
            filenames = [url.split('/')[-1] for url in product.get('photos', [])]
            if filenames: supabase.storage.from_("products").remove(filenames)
        except: pass
    context.user_data.pop('preview_product', None)
    context.user_data.pop('preview_editing', None)
    await query.edit_message_caption("❌ تم إلغاء إضافة المنتج.")
    return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    product = context.user_data.get('preview_product')
    if product:
        try:
            from database import supabase
            filenames = [url.split('/')[-1] for url in product.get('photos', [])]
            if filenames: supabase.storage.from_("products").remove(filenames)
        except: pass
    context.user_data.clear()
    await update.message.reply_text("❌ تم الإلغاء.")
    return ConversationHandler.END


# ═══ عرض وإدارة المنتجات ═══
async def list_products(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await deny_non_admin(update); return
    try: products = load_products()
    except Exception as e:
        await update.message.reply_text(f"⚠️ فشل جلب المنتجات: {e}"); return
    if not products:
        await update.message.reply_text("📭 لا توجد منتجات حالياً."); return
    text = "📦 <b>قائمة المنتجات:</b>\n\n"
    for p in products:
        text += f"🆔 <b>ID: {p['id']}</b> | {p['name']}\n   💰 السعر: {p['price']} دج | القسم: {ARABIC_CATEGORIES.get(p.get('category'), p.get('category'))}\n\n"
    await update.message.reply_text(text, parse_mode="HTML")


async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await deny_non_admin(update); return
    products = load_products()
    if not products:
        await update.message.reply_text("📊 لا توجد منتجات."); return
    text = "📊 <b>إحصائيات المتجر:</b>\n\n"
    cat_counts = {}
    for p in products: cat_counts[p.get("category", "other")] = cat_counts.get(p.get("category", "other"), 0) + 1
    for cat_id, count in cat_counts.items(): text += f"{ARABIC_CATEGORIES.get(cat_id, cat_id)}: {count} منتج\n"
    text += f"\n📦 <b>الإجمالي: {len(products)} منتج</b>"
    await update.message.reply_text(text, parse_mode="HTML")


# ═══ التعديل والحذف ═══
async def edit_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await deny_non_admin(update); return ConversationHandler.END
    await update.message.reply_text("🛠️ أرسلي <b>ID</b> المنتج للتعديل:", parse_mode="HTML")
    return EDIT_ID


async def edit_get_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try: context.user_data['edit_id'] = int(update.message.text)
    except ValueError:
        await update.message.reply_text("⚠️ الرجاء إرسال رقم صحيح."); return EDIT_ID
    keyboard = [[InlineKeyboardButton("💰 تعديل السعر", callback_data="edit_price")], [InlineKeyboardButton("✍️ تعديل الاسم", callback_data="edit_name")], [InlineKeyboardButton("📝 تعديل الوصف", callback_data="edit_desc")]]
    await update.message.reply_text("ماذا تريدين أن تعدلي؟", reply_markup=InlineKeyboardMarkup(keyboard))
    return EDIT_FIELD


async def edit_choose_field(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data['edit_field'] = query.data
    await query.edit_message_text("✍️ أرسلي القيمة الجديدة:")
    return EDIT_VALUE


async def edit_save(update: Update, context: ContextTypes.DEFAULT_TYPE):
    new_value, p_id, field = update.message.text, context.user_data.get('edit_id'), context.user_data.get('edit_field')
    update_data = {}
    if field == "edit_price":
        try: update_data["price"] = int(new_value)
        except ValueError:
            await update.message.reply_text("⚠️ السعر يجب أن يكون رقماً."); return EDIT_VALUE
    elif field == "edit_name": update_data["name"] = new_value
    elif field == "edit_desc": update_data["description"] = new_value
    try:
        if not update_product(p_id, update_data):
            await update.message.reply_text(f"⚠️ لم يتم العثور على منتج {p_id}."); return ConversationHandler.END
    except Exception as e:
        await update.message.reply_text(f"⚠️ فشل التحديث: {e}"); return ConversationHandler.END
    
    try:
        products = load_products()
        p = next((item for item in products if item["id"] == p_id), None)
        if p and p.get("message_id"):
            caption, _ = build_caption(p['name'], p['price'], p.get('attributes', {}), p.get('description', ''), p['id'], False)
            await context.bot.edit_message_caption(chat_id=int(os.getenv("CHANNEL_ID")), message_id=p["message_id"], caption=caption, parse_mode="HTML")
    except Exception as e: print(f"⚠️ فشل تحديث المنشور: {e}")
    await update.message.reply_text(f"✅ تم تعديل المنتج (ID: {p_id}).")
    return ConversationHandler.END


async def delete_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await deny_non_admin(update); return ConversationHandler.END
    await list_products(update, context)
    await update.message.reply_text("🗑️ أرسلي <b>ID</b> المنتج للحذف:", parse_mode="HTML")
    return DELETE_ID


async def delete_get_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try: p_id = int(update.message.text)
    except ValueError:
        await update.message.reply_text("⚠️ الرجاء إرسال رقم صحيح."); return DELETE_ID
    context.user_data['delete_id'] = p_id
    products = load_products()
    product_name = next((p["name"] for p in products if p["id"] == p_id), None)
    if product_name is None:
        await update.message.reply_text(f"⚠️ لم يتم العثور على منتج {p_id}."); return ConversationHandler.END
    keyboard = [[InlineKeyboardButton("✅ نعم، احذف", callback_data="confirm_delete_yes")], [InlineKeyboardButton("❌ إلغاء", callback_data="confirm_delete_no")]]
    await update.message.reply_text(f"⚠️ هل أنت متأكدة من حذف <b>{product_name}</b> (ID: {p_id})؟", parse_mode="HTML", reply_markup=InlineKeyboardMarkup(keyboard))
    return DELETE_CONFIRM


async def delete_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.data != "confirm_delete_yes":
        await query.edit_message_text("❌ تم الإلغاء."); return ConversationHandler.END
    p_id = context.user_data.get('delete_id')
    try:
        products = load_products()
        product = next((p for p in products if p["id"] == p_id), None)
        if not product:
            await query.edit_message_text(f"⚠️ لم يتم العثور على منتج {p_id}."); return ConversationHandler.END
        delete_product(p_id)
        channel_id = int(os.getenv("CHANNEL_ID"))
        if product.get("message_ids"):
            try:
                for msg_id in product["message_ids"]: await context.bot.delete_message(chat_id=channel_id, message_id=msg_id)
            except: pass
        elif product.get("message_id"):
            try: await context.bot.delete_message(chat_id=channel_id, message_id=product["message_id"])
            except: pass
        await query.edit_message_text(f"✅ تم حذف المنتج (ID: {p_id}).")
    except Exception as e:
        await query.edit_message_text(f"⚠️ حدث خطأ: {e}")
    return ConversationHandler.END


# ═══ الطلبات ═══
async def list_orders(update: Update, context: ContextTypes.DEFAULT_TYPE, page=0):
    if not is_admin(update.effective_user.id):
        await deny_non_admin(update); return
    orders = get_all_orders()
    if not orders:
        await update.message.reply_text("📭 لا توجد طلبات."); return
    page = max(0, min(page, len(orders) - 1))
    order = orders[page]
    status = order.get('status', 'قيد المراجعة')
    status_emoji = "🚚" if status=="تم الشحن" else "✅" if status=="مكتمل" else "❌" if status=="ملغي" else "🕒"
    text = (f"🆔 <b>رقم الطلب:</b> <code>{order.get('order_code', 'غير متوفر')}</code>\n"
            f"🛍️ <b>المنتج:</b> {order.get('product_name') or order.get('product', 'غير معروف')}\n"
            f"👤 <b>الزبونة:</b> {order.get('customer_name') or order.get('name', 'غير معروف')}\n"
            f"📞 <b>الهاتف:</b> {order.get('customer_phone') or order.get('phone', 'غير معروف')}\n"
            f"📍 <b>العنوان:</b> {order.get('customer_address') or order.get('address', 'غير معروف')}\n"
            f"📊 <b>الحالة:</b> {status_emoji} {status}\n\n<i>الطلب {page+1} من {len(orders)}</i>")
    status_keyboard = [
        [InlineKeyboardButton("🚚 تم الشحن", callback_data=f"ord_status_تم الشحن_{order['id']}_{page}"), InlineKeyboardButton("✅ مكتمل", callback_data=f"ord_status_مكتمل_{order['id']}_{page}")],
        [InlineKeyboardButton("❌ ملغي", callback_data=f"ord_status_ملغي_{order['id']}_{page}")]
    ]
    nav_row = []
    if page > 0: nav_row.append(InlineKeyboardButton("⬅️ السابق", callback_data=f"ord_page_{page-1}"))
    if page < len(orders) - 1: nav_row.append(InlineKeyboardButton("التالي ➡️", callback_data=f"ord_page_{page+1}"))
    if nav_row: status_keyboard.append(nav_row)
    reply_markup = InlineKeyboardMarkup(status_keyboard)
    if update.callback_query: await update.callback_query.edit_message_text(text, parse_mode="HTML", reply_markup=reply_markup)
    else: await update.message.reply_text(text, parse_mode="HTML", reply_markup=reply_markup)

async def change_order_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """تغيير حالة الطلب وإشعار الزبونة"""
    query = update.callback_query
    await query.answer()
    
    if not is_admin(query.from_user.id):
        await query.answer("⛔ ليس لديك صلاحية.", show_alert=True)
        return
        
    # استخراج البيانات: ord_status_{new_status}_{order_id}_{page}
    parts = query.data.split("_")
    page = int(parts[-1])
    order_id = int(parts[-2])
    new_status = "_".join(parts[2:-2]) 
    
    # 1. جلب بيانات الطلب (قبل التحديث) لمعرفة customer_id
    from database import get_all_orders, update_order_status
    orders = get_all_orders()
    order = next((o for o in orders if o['id'] == order_id), None)
    
    if not order:
        await query.answer("⚠️ لم يتم العثور على الطلب.", show_alert=True)
        return
        
    customer_id = order.get('customer_id') # معرف الزبونة في تيليجرام
    
    # 2. تحديث الحالة في قاعدة البيانات
    updated = update_order_status(order_id, new_status)
    
    if updated:
        # 3. إعادة عرض الصفحة
        await list_orders(update, context, page=page)
        await query.answer(f"✅ تم التحديث إلى: {new_status}", show_alert=False)
        
        # 4. إرسال إشعار للزبونة (إذا كان لدينا معرفها)
        if customer_id:
            try:
                # إنشاء بوت مؤقت باستخدام توكن بوت الزبونات
                customer_token = os.getenv("CUSTOMER_BOT_TOKEN")
                if not customer_token:
                    print("⚠️ CUSTOMER_BOT_TOKEN غير موجود في .env، لن يتم إرسال إشعار.")
                    return

                customer_bot = telegram.Bot(token=customer_token)
                
                status_emoji = "🕒"
                if new_status == "تم الشحن": status_emoji = "🚚"
                elif new_status == "مكتمل": status_emoji = "✅"
                elif new_status == "ملغي": status_emoji = "❌"
                
                text = (
                    f"🔔 <b>تحديث على طلبك رقم {order.get('order_code', '')}:</b>\n\n"
                    f"📊 الحالة الجديدة: {status_emoji} <b>{new_status}</b>\n\n"
                    f"شكراً لتسوقك من متجرنا 🌸"
                )
                
                await customer_bot.send_message(chat_id=customer_id, text=text, parse_mode="HTML")
                print(f"✅ تم إرسال إشعار للزبونة {customer_id} بنجاح.")
            except Exception as e:
                print(f"⚠️ فشل إرسال إشعار للزبونة: {e}")
    else:
        await query.answer("⚠️ فشل تحديث حالة الطلب.", show_alert=True)
async def navigate_orders(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """التنقل بين صفحات الطلبات"""
    query = update.callback_query
    await query.answer() # إيقاف علامة التحميل على الزر
    
    # استخراج رقم الصفحة من callback_data
    # إذا كان الزر يرسل "ord_page_2"، سيصبح النص "2" ونحوله لرقم صحيح
    page = int(query.data.replace("ord_page_", ""))
    
    # استدعاء دالة عرض الطلبات مع تمرير رقم الصفحة الجديد
    await list_orders(update, context, page=page)

# ═══ إضافة صور ═══
async def add_photos_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await deny_non_admin(update); return ConversationHandler.END
    await update.message.reply_text("🖼️ أرسلي <b>ID</b> المنتج:", parse_mode="HTML")
    return ASK_PHOTOS_ID


async def add_photos_get_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try: p_id = int(update.message.text)
    except ValueError:
        await update.message.reply_text("⚠️ الرجاء إرسال رقم صحيح."); return ASK_PHOTOS_ID
    if not any(p["id"] == p_id for p in load_products()):
        await update.message.reply_text(f"⚠️ لم يتم العثور على منتج {p_id}."); return ConversationHandler.END
    context.user_data['photo_product_id'] = p_id
    await update.message.reply_text("📸 أرسلي الصور الجديدة. /done للإنهاء.")
    return ASK_MORE_PHOTOS


async def add_more_photos(update: Update, context: ContextTypes.DEFAULT_TYPE):
    p_id = context.user_data.get('photo_product_id')
    if not p_id: return ConversationHandler.END
    if update.message.text == "/done":
        keyboard = [[InlineKeyboardButton("✅ نعم، انشر ألبوماً", callback_data=f"album_yes_{p_id}")], [InlineKeyboardButton("❌ لا", callback_data=f"album_no_{p_id}")]]
        await update.message.reply_text("⚠️ نشر ألبوم جديد سيحذف المنشور القديم. متابعة؟", reply_markup=InlineKeyboardMarkup(keyboard))
        return ConversationHandler.END
    if not update.message.photo:
        await update.message.reply_text("⚠️ أرسلي صورة أو /done."); return ASK_MORE_PHOTOS
    photos = next((p.get("photos", []) for p in load_products() if p["id"] == p_id), [])
    if len(photos) >= MAX_PHOTOS:
        await update.message.reply_text("⚠️ وصلتِ للحد الأقصى."); return ASK_MORE_PHOTOS
    photos.append(update.message.photo[-1].file_id)
    update_product(p_id, {"photos": photos})
    await update.message.reply_text(f"✅ تم حفظ الصورة ({len(photos)}/{MAX_PHOTOS}).")
    return ASK_MORE_PHOTOS


async def handle_album_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id): return
    action, p_id = query.data.split("_")[1], int(query.data.split("_")[2])
    p = next((item for item in load_products() if item["id"] == p_id), None)
    if not p: return
    if action == "no":
        await query.edit_message_text("✅ تم حفظ الصور."); return
    channel_id = int(os.getenv("CHANNEL_ID"))
    if p.get("message_ids"):
        try:
            for msg_id in p["message_ids"]: await context.bot.delete_message(chat_id=channel_id, message_id=msg_id)
        except: pass
    elif p.get("message_id"):
        try: await context.bot.delete_message(chat_id=channel_id, message_id=p["message_id"])
        except: pass
    caption, _ = build_caption(p['name'], p['price'], p.get('attributes', {}), p.get('description', ''), p['id'], False)
    photos = p.get("photos", [])
    if not photos: return
    media_group = [InputMediaPhoto(media=photo, caption=caption if i==0 else None, parse_mode="HTML" if i==0 else None) for i, photo in enumerate(photos[:MAX_PHOTOS])]
    sent_messages = await context.bot.send_media_group(chat_id=channel_id, media=media_group)
    all_ids = [m.message_id for m in sent_messages]
    update_product(p_id, {"message_id": all_ids[0], "message_ids": all_ids})
    await query.edit_message_text("✅ تم نشر الألبوم.")


# ═══ البحث ═══
async def search_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await deny_non_admin(update); return ConversationHandler.END
    await update.message.reply_text("🔍 أرسلي اسم المنتج للبحث:")
    return ASK_SEARCH_QUERY


async def search_execute(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query_text = update.message.text.strip()
    if len(query_text) < 2:
        await update.message.reply_text("⚠️ أدخلي حرفين على الأقل."); return ASK_SEARCH_QUERY
    results = search_products_by_name(query_text)
    if not results:
        await update.message.reply_text(f"📭 لا توجد منتجات تطابق '{query_text}'."); return ASK_SEARCH_QUERY
    await update.message.reply_text(f"🔍 تم العثور على {len(results)} منتج.")
    for p in results:
        keyboard = [[InlineKeyboardButton("✏️ تعديل", callback_data=f"quick_edit_{p['id']}"), InlineKeyboardButton("🗑️ حذف", callback_data=f"quick_delete_{p['id']}")]]
        caption = f"🆔 <b>ID: {p['id']}</b> | {p['name']}\n💰 السعر: {p['price']} دج"
        if p.get('photo'): await update.message.reply_photo(photo=p['photo'], caption=caption, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(keyboard))
        else: await update.message.reply_text(caption, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(keyboard))
    return ASK_SEARCH_QUERY


async def handle_quick_actions(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    p_id = int(query.data.split("_")[-1])
    if "quick_edit" in query.data:
        context.user_data['edit_id'] = p_id
        keyboard = [[InlineKeyboardButton("💰 السعر", callback_data="edit_price")], [InlineKeyboardButton("✍️ الاسم", callback_data="edit_name")], [InlineKeyboardButton("📝 الوصف", callback_data="edit_desc")]]
        await query.message.reply_text(f"🛠️ تعديل المنتج (ID: {p_id}):", reply_markup=InlineKeyboardMarkup(keyboard))
        return ConversationHandler.END
    elif "quick_delete" in query.data:
        context.user_data['delete_id'] = p_id
        name = next((p["name"] for p in load_products() if p["id"] == p_id), "غير معروف")
        keyboard = [[InlineKeyboardButton("✅ نعم", callback_data="confirm_delete_yes")], [InlineKeyboardButton("❌ إلغاء", callback_data="confirm_delete_no")]]
        await query.message.reply_text(f"⚠️ حذف <b>{name}</b> (ID: {p_id})؟", parse_mode="HTML", reply_markup=InlineKeyboardMarkup(keyboard))
        return ConversationHandler.END


# ═══ المعالجات الخاصة ═══
async def timeout_cleanup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    product = context.user_data.get('preview_product')
    if product:
        try:
            from database import supabase
            filenames = [url.split('/')[-1] for url in product.get('photos', [])]
            if filenames: supabase.storage.from_("products").remove(filenames)
        except: pass
    context.user_data.clear()
    await update.effective_chat.send_message("⏳ انتهت المهلة.")
    return ConversationHandler.END


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    print(f"⚠️ [ERROR]: {context.error}")
    import telegram
    if isinstance(context.error, telegram.error.TimedOut) and update and hasattr(update, 'effective_message'):
        try: await update.effective_message.reply_text("⚠️ خطأ في الشبكة، حاولي مجدداً.")
        except: pass


# ═══ Main ═══
def main():
    token = load_token()
    request = HTTPXRequest(connect_timeout=60.0, read_timeout=60.0, write_timeout=60.0, pool_timeout=60.0, media_write_timeout=120.0)
    app = Application.builder().token(token).request(request).get_updates_request(request).build()
    app.add_error_handler(error_handler)

    # 1. الإضافة
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("add", add_product_start), MessageHandler(filters.Regex("^➕ إضافة منتج$"), add_product_start)],
        states={
            CHOOSE_CATEGORY: [CallbackQueryHandler(category_chosen, pattern="^cat_")],
            ASK_PHOTO: [MessageHandler(filters.PHOTO, get_photo), CallbackQueryHandler(photos_done, pattern="^photos_done$")],
            ASK_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_name)],
            ASK_PRICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_price)],
            ASK_DYNAMIC_ATTR: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_dynamic_attr)],
            ASK_DESC: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_desc)],
            PREVIEW_PRODUCT: [CallbackQueryHandler(preview_publish, pattern="^preview_publish$"), CallbackQueryHandler(preview_edit_field, pattern="^preview_edit_"), CallbackQueryHandler(preview_cancel, pattern="^preview_cancel$"), MessageHandler(filters.TEXT & ~filters.COMMAND, preview_apply_edit)],
            ConversationHandler.TIMEOUT: [MessageHandler(filters.ALL, timeout_cleanup)],
        },
        fallbacks=[CommandHandler("cancel", cancel)], conversation_timeout=1800, per_message=False 
    )
    app.add_handler(conv_handler)

    # 2. التعديل
    app.add_handler(ConversationHandler(
        entry_points=[CommandHandler("edit", edit_start), MessageHandler(filters.Regex("^✏️ تعديل منتج$"), edit_start), CallbackQueryHandler(edit_choose_field, pattern="^edit_")],
        states={EDIT_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, edit_get_id)], EDIT_FIELD: [CallbackQueryHandler(edit_choose_field, pattern="^edit_")], EDIT_VALUE: [MessageHandler(filters.TEXT & ~filters.COMMAND, edit_save)]},
        fallbacks=[CommandHandler("cancel", cancel)], conversation_timeout=900, per_message=False 
    ))

    # 3. الحذف
    app.add_handler(ConversationHandler(
        entry_points=[CommandHandler("delete", delete_start), MessageHandler(filters.Regex("^🗑️ حذف منتج$"), delete_start), CallbackQueryHandler(delete_confirm, pattern="^confirm_delete_")],
        states={DELETE_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, delete_get_id)], DELETE_CONFIRM: [CallbackQueryHandler(delete_confirm, pattern="^confirm_delete_")]},
        fallbacks=[CommandHandler("cancel", cancel)], conversation_timeout=900, per_message=False 
    ))

    # 4. إضافة صور
    app.add_handler(ConversationHandler(
        entry_points=[CommandHandler("add_photos", add_photos_start), MessageHandler(filters.Regex("^🖼️ إضافة صور$"), add_photos_start)],
        states={ASK_PHOTOS_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_photos_get_id)], ASK_MORE_PHOTOS: [MessageHandler(filters.PHOTO, add_more_photos), CommandHandler("done", add_more_photos)]},
        fallbacks=[CommandHandler("cancel", cancel)], conversation_timeout=1800, per_message=False 
    ))

    # 5. البحث
    app.add_handler(ConversationHandler(
        entry_points=[CommandHandler("search", search_start), MessageHandler(filters.Regex("^🔍 بحث عن منتج$"), search_start)],
        states={ASK_SEARCH_QUERY: [MessageHandler(filters.TEXT & ~filters.COMMAND, search_execute), CallbackQueryHandler(handle_quick_actions, pattern="^quick_")]},
        fallbacks=[CommandHandler("cancel", cancel)], conversation_timeout=600, per_message=False
    ))

    # معالجات الطلبات
    app.add_handler(CallbackQueryHandler(handle_album_choice, pattern="^album_"))
    app.add_handler(CallbackQueryHandler(change_order_status, pattern="^ord_status_"))
    app.add_handler(CallbackQueryHandler(navigate_orders, pattern="^ord_page_"))

    # الأوامر العادية
    app.add_handler(CommandHandler("start", start_admin))
    app.add_handler(CommandHandler("list", list_products))
    app.add_handler(CommandHandler("stats", stats))
    app.add_handler(CommandHandler("cancel", cancel))
    app.add_handler(CommandHandler("orders", list_orders))
    
    # الأزرار الثابتة
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_admin_buttons))

    is_render = os.environ.get("RENDER") is not None
    webhook_url = os.environ.get("WEBHOOK_URL")
    if is_render and webhook_url:
        port = int(os.environ.get("PORT", 8080))
        print(f"🚀 بوت الإدارة يعمل في وضع Webhook على المنفذ {port}")
        app.run_webhook(listen="0.0.0.0", port=port, url_path="admin_webhook", webhook_url=f"{webhook_url}/admin_webhook", drop_pending_updates=True)
    else:
        print("🤖 بوت الإدارة يعمل في وضع Polling (محلي)")
        app.run_polling()

if __name__ == "__main__":
    main()