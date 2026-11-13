import os
from supabase import create_client, Client
from dotenv import load_dotenv
import requests
from PIL import Image
from io import BytesIO

load_dotenv()

url: str = os.getenv("SUPABASE_URL")
key: str = os.getenv("SUPABASE_KEY")
supabase: Client = create_client(url, key)

def load_products():
    """تحميل المنتجات من Supabase"""
    response = supabase.table("products").select("*").execute()
    # تحويل البيانات لتشبه الهيكل القديم (لأن الألوان والمقاسات في JSONB)
    return response.data

def save_product(product_data):
    """حفظ منتج جديد"""
    # إزالة الحقول الفارغة لتجنب أخطاء Supabase
    clean_data = {k: v for k, v in product_data.items() if v is not None}
    response = supabase.table("products").insert(clean_data).execute()
    return response.data

def update_product(product_id, update_data):
    """تحديث منتج موجود"""
    response = supabase.table("products").update(update_data).eq("id", product_id).execute()
    return response.data

def delete_product(product_id):
    """حذف منتج"""
    response = supabase.table("products").delete().eq("id", product_id).execute()
    return response.data

def get_orders():
    """عرض الطلبات"""
    response = supabase.table("orders").select("*").order("created_at", desc=True).execute()
    return response.data

def save_order(order_data):
    """حفظ طلب جديد في Supabase"""
    try:
        response = supabase.table("orders").insert(order_data).execute()
        return response.data
    except Exception as e:
        print(f"⚠️ فشل حفظ الطلب في Supabase: {e}")
        return None

def upload_image_to_supabase(image_bytes, file_name, bucket="products"):
    """رفع صورة (كبايتات) إلى Supabase Storage وإرجاع رابطها العام"""
    try:
        # رفع الصورة
        supabase.storage.from_(bucket).upload(
            file_name,
            image_bytes,
            {"content-type": "image/jpeg"}
        )
        # الحصول على الرابط العام
        return supabase.storage.from_(bucket).get_public_url(file_name)
    except Exception as e:
        print(f"⚠️ فشل رفع الصورة: {e}")
        return None

def compress_image(image_bytes, max_width=800, quality=85):
    """ضغط الصورة: تصغير العرض إلى max_width (إذا كانت أكبر) وتقليل الجودة"""
    try:
        image = Image.open(BytesIO(image_bytes))
        if image.width > max_width:
            ratio = max_width / image.width
            new_size = (max_width, int(image.height * ratio))
            image = image.resize(new_size, Image.Resampling.LANCZOS)
        output = BytesIO()
        image.convert("RGB").save(output, format="JPEG", quality=quality)
        return output.getvalue()
    except Exception as e:
        print(f"⚠️ فشل ضغط الصورة: {e}")
        return image_bytes  # إرجاع الأصلية إذا فشل الضغط