from database import supabase

try:
    # محاولة قراءة المنتجات
    response = supabase.table("products").select("*").execute()
    print("✅ الاتصال ناجح! عدد المنتجات:", len(response.data))
except Exception as e:
    print("❌ فشل الاتصال:", e)