import os
from supabase import create_client, Client
from dotenv import load_dotenv

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

def save_order(order_data):
    """حفظ طلب جديد"""
    response = supabase.table("orders").insert(order_data).execute()
    return response.data

def get_orders():
    """عرض الطلبات"""
    response = supabase.table("orders").select("*").order("created_at", desc=True).execute()
    return response.data