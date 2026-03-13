"""
core/database.py
================
Supabase client singleton — import `supabase` anywhere.
Uses the service key so agents bypass RLS.
"""

from supabase import create_client, Client
from core.config import settings

# Create Supabase client 
supabase: Client = create_client(
    settings.SUPABASE_URL,
    settings.SUPABASE_SERVICE_KEY,
)


def test_connection() -> bool:
    """Test if Supabase connection works."""
    try:
        response = supabase.table("products").select("id").limit(1).execute()
        return True
    except Exception as e:
        print(f"⚠️ Supabase connection test failed: {e}")
        return False
