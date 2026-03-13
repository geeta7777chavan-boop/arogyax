"""
Script to update user email in Supabase.
Run: python backend/scripts/update_user_email.py
"""

import os
from pathlib import Path
from dotenv import load_dotenv
from supabase import create_client

# Setup paths
THIS_FILE = Path(__file__).resolve()
PROJECT_ROOT = THIS_FILE.parent.parent.parent
load_dotenv(PROJECT_ROOT / ".env")

SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_KEY = os.environ["SUPABASE_SERVICE_KEY"]

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# Update PAT001 with email
patient_id = "PAT001"
email = "geeta7777chavan@gmail.com"

result = supabase.table("users").update({
    "email": email
}).eq("patient_id", patient_id).execute()

if result.data:
    print(f"✅ Updated {patient_id} with email: {email}")
else:
    print(f"⚠️ User {patient_id} not found or no changes made")
    
# Verify
user = supabase.table("users").select("*").eq("patient_id", patient_id).execute()
print(f"User data: {user.data}")

