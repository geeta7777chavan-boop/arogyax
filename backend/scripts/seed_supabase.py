"""
seed_supabase.py
================
Ingests products-export.csv and Consumer Order History CSV into Supabase.

Usage (run from ANY directory — paths are always resolved correctly):
    python backend/scripts/seed_supabase.py

Set these in a .env file at the project root (D:/Agent/.env):
    SUPABASE_URL=https://<project>.supabase.co
    SUPABASE_SERVICE_KEY=<your service-role key>   # NOT the anon key
"""

import os, math
import random
from pathlib import Path
from datetime import datetime, timedelta
import pandas as pd
from dotenv import load_dotenv
from supabase import create_client, Client

# ── Resolve paths relative to this script — works from any working directory ──
# Layout:  D:/Agent/backend/scripts/seed_supabase.py
#          D:/Agent/.env
#          D:/Agent/data/*.csv
THIS_FILE    = Path(__file__).resolve()
PROJECT_ROOT = THIS_FILE.parent.parent.parent   # scripts -> backend -> Agent/
DATA_DIR     = PROJECT_ROOT / "data"

# Load .env from project root
load_dotenv(PROJECT_ROOT / ".env")

SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_KEY = os.environ["SUPABASE_SERVICE_KEY"]

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)


# ── Helpers ───────────────────────────────────────────────────────────────────

PRESCRIPTION_KEYWORDS = [
    "ramipril", "minoxidil", "colpofix", "femiloge", "livocab",
    "aqualibra", "mucosolvan", "retard"
]

def infer_prescription(name: str, csv_flag: str = "No") -> bool:
    if str(csv_flag).strip().lower() == "yes":
        return True
    return any(kw in name.lower() for kw in PRESCRIPTION_KEYWORDS)

def dosage_to_days(freq: str) -> int:
    """Rough supply duration (days) for a single package."""
    mapping = {
        "once daily":        30,
        "twice daily":       15,
        "three times daily": 10,
        "as needed":         45,
    }
    return mapping.get(str(freq).strip().lower(), 30)


def find_csv(keyword: str) -> Path:
    """
    Search DATA_DIR for a CSV whose filename contains `keyword` (case-insensitive).
    Prints every CSV it finds so naming issues are immediately obvious.
    """
    if not DATA_DIR.exists():
        raise FileNotFoundError(
            f"\n❌  Data folder does not exist: {DATA_DIR}"
            f"\n    Create it and place your CSV files inside."
        )

    all_csvs = sorted(DATA_DIR.glob("*.csv"))

    print(f"\n📂  CSVs found in {DATA_DIR}:")
    if not all_csvs:
        print("      (none)")
    for f in all_csvs:
        print(f"      {f.name}")

    if not all_csvs:
        raise FileNotFoundError(
            f"\n❌  No CSV files found inside: {DATA_DIR}"
        )

    matches = [f for f in all_csvs if keyword.lower() in f.name.lower()]
    if not matches:
        raise FileNotFoundError(
            f"\n❌  Could not find a CSV with '{keyword}' in its name."
            f"\n    Files present: {[f.name for f in all_csvs]}"
            f"\n    Rename your file so its name contains '{keyword}'."
        )
    return matches[0]


# ── 1. Seed PRODUCTS ──────────────────────────────────────────────────────────

def seed_products(path: Path):
    df = pd.read_csv(path, encoding="latin-1")
    df.columns = [c.strip() for c in df.columns]

    records = []
    for _, row in df.iterrows():
        price = float(row["price"])
        records.append({
            "id":                    int(row["id"]),
            "pzn":                   int(row["pzn"]),
            "name":                  str(row["name"]).strip(),
            "price":                 0.0 if math.isnan(price) else price,
            "package_size":          str(row["package_size"]).strip(),
            "description":           str(row["description"]).strip(),
            "stock_quantity":        50,          # mock initial stock
            "prescription_required": infer_prescription(str(row["name"])),
        })

    supabase.table("products").upsert(records, on_conflict="id").execute()
    print(f"✅  Seeded {len(records)} products")


# ── 2. Seed USERS from order history ─────────────────────────────────────────

def seed_users(history_df: pd.DataFrame):
    patients = (
        history_df[["patient_ID", "patient_age", "patient_gender"]]
        .drop_duplicates("patient_ID")
        .rename(columns={
            "patient_ID":     "patient_id",
            "patient_age":    "age",
            "patient_gender": "gender",
        })
    )

    records = []
    for _, row in patients.iterrows():
        records.append({
            "patient_id": str(row["patient_id"]).strip(),
            "age":        int(row["age"]),
            "gender":     str(row["gender"]).strip().upper(),
            "role":       "customer",
        })

    supabase.table("users").upsert(records, on_conflict="patient_id").execute()
    print(f"✅  Seeded {len(records)} users")


# ── 3. Seed ORDER_HISTORY ─────────────────────────────────────────────────────

def seed_order_history(history_df: pd.DataFrame):
    resp     = supabase.table("users").select("id, patient_id").execute()
    uid_map  = {u["patient_id"]: u["id"] for u in resp.data}

    resp2    = supabase.table("products").select("id, name").execute()
    prod_map = {p["name"].strip().lower(): p["id"] for p in resp2.data}

    def find_product_id(name: str):
        key = name.strip().lower()
        if key in prod_map:
            return prod_map[key]
        for k, v in prod_map.items():
            if key in k or k in key:
                return v
        return None

    records = []
    for _, row in history_df.iterrows():
        pid   = str(row["patient_ID"]).strip()
        mname = str(row["name"]).strip()
        # Generate a random time for the order (between 8 AM and 10 PM)
        random_hour = random.randint(8, 22)
        random_minute = random.randint(0, 59)
        date_str = str(row["purchase_date"]).strip()
        # Append time to the date string
        purchase_datetime = f"{date_str}T{random_hour:02d}:{random_minute:02d}:00"
        records.append({
            "patient_id":            pid,
            "user_id":               uid_map.get(pid),
            "product_id":            find_product_id(mname),
            "medicine_name":         mname,
            "quantity":              int(row["Quantity"]),
            "total_price":           float(row["Total_Price"]),
            "dosage_frequency":      str(row["dosage_frequency"]).strip(),
            "prescription_required": infer_prescription(
                                         mname,
                                         row.get("prescription_required", "No")
                                     ),
            "purchase_date":         purchase_datetime,
        })

    supabase.table("order_history").insert(records).execute()
    print(f"✅  Seeded {len(records)} order_history rows")


# ── 4. Generate REFILL_ALERTS ─────────────────────────────────────────────────

def generate_refill_alerts(history_df: pd.DataFrame):
    resp_users = supabase.table("users").select("id, patient_id").execute()
    uid_map    = {u["patient_id"]: u["id"] for u in resp_users.data}

    resp_prods = supabase.table("products").select("id, name").execute()
    prod_map   = {p["name"].strip().lower(): p["id"] for p in resp_prods.data}

    def find_pid(name: str):
        key = name.strip().lower()
        if key in prod_map:
            return prod_map[key]
        for k, v in prod_map.items():
            if key in k or k in key:
                return v
        return None

    history_df["purchase_date"] = pd.to_datetime(history_df["purchase_date"])
    today  = datetime.today().date()
    alerts = []

    for (pat_id, med_name), grp in history_df.groupby(["patient_ID", "name"]):
        latest_date      = grp["purchase_date"].max().date()
        freq             = grp.iloc[-1]["dosage_frequency"]
        days_supply      = dosage_to_days(freq) * int(grp.iloc[-1]["Quantity"])
        predicted_refill = latest_date + timedelta(days=days_supply)

        if (predicted_refill - today).days <= 30:
            uid = uid_map.get(pat_id)
            pid = find_pid(med_name)
            if uid and pid:
                alerts.append({
                    "user_id":               uid,
                    "product_id":            pid,
                    "last_purchase":         str(latest_date),
                    "predicted_refill_date": str(predicted_refill),
                    "alert_sent":            False,
                    "status":                "pending",
                })

    if alerts:
        supabase.table("refill_alerts").insert(alerts).execute()
        print(f"✅  Generated {len(alerts)} refill alerts")
    else:
        print("ℹ️  No imminent refill alerts at this time")


# ── 5. Log seed event to DECISION_LEDGER ─────────────────────────────────────

def log_sample_decision():
    supabase.table("decision_ledger").insert({
        "agent_name":     "SeedAgent",
        "action":         "DATA_LOADED",
        "reason":         "Initial CSV data ingested into Supabase. Products, users, and order history seeded successfully.",
        "input_payload":  {"source": ["products-export.csv", "Consumer_Order_History.csv"]},
        "output_payload": {"status": "success"},
    }).execute()
    print("✅  Sample decision_ledger entry logged")


# ── Main ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print(f"\n🔍  Project root : {PROJECT_ROOT}")
    print(f"🔍  Data folder  : {DATA_DIR}")

    # Auto-detect CSVs by keyword — tolerates any filename variation
    PRODUCTS_CSV = find_csv("products")
    HISTORY_CSV  = find_csv("consumer")

    print(f"\n🚀  Starting Supabase data seed...")
    print(f"    Products CSV : {PRODUCTS_CSV.name}")
    print(f"    History CSV  : {HISTORY_CSV.name}\n")

    seed_products(PRODUCTS_CSV)

    # History CSV has a 4-row header block before the real column names
    history_df = pd.read_csv(HISTORY_CSV, encoding="latin-1", skiprows=4)
    history_df.columns = [c.strip() for c in history_df.columns]
    history_df = history_df.dropna(subset=["patient_ID"])

    seed_users(history_df)
    seed_order_history(history_df)
    generate_refill_alerts(history_df)
    log_sample_decision()

    print("\n🎉  Seeding complete! Open Supabase Table Editor to verify.\n")