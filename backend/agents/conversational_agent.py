"""
agents/conversational_agent.py
================================
Architecture: 3 small, focused LLM calls instead of 1 overloaded prompt.

Step 1 - CLASSIFIER: Is this ORDER or TRIAGE? Extract primary complaint.
Step 2A - TRIAGE RESPONDER: If triage, what to say next? (Uses full history)
Step 2B - ORDER EXTRACTOR: If order, extract medicine + qty as structured JSON.

This prevents semantic drift because:
- The classifier only classifies - it doesn't recommend medicines
- The triage responder only has pain-relevant medicines in its catalogue
- The order extractor only extracts - it doesn't make clinical decisions
- primary_complaint is set once and carried forward, never re-derived
"""

import sys
import json
import random
import re
from pathlib import Path
from difflib import SequenceMatcher

_BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

from agents.state import AgentState
from core.database import supabase
from core.config import settings
from observability.langfuse_client import log_agent_step

from langchain_groq import ChatGroq
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage

llm = ChatGroq(
    model="llama-3.3-70b-versatile",
    api_key=settings.GROQ_API_KEY,
    temperature=0.1,
)

llm_creative = ChatGroq(
    model="llama-3.3-70b-versatile",
    api_key=settings.GROQ_API_KEY,
    temperature=0.4,
)

CLASSIFIER_SYSTEM = """Classify this pharmacy conversation turn. Reply ONLY with valid JSON:
{
  "intent": "ORDER" | "TRIAGE" | "CONFIRM_ORDER" | "EMERGENCY" | "CONVERSATION" | "REJECT_SUGGESTION" | "PRICE_QUERY" | "GENERAL_INFO" | "PRODUCT_QUERY" | "SUPPLY_QUERY",
  "primary_complaint": "<the main medical complaint e.g. headache, fever, cough - set to null if user explicitly says to ignore/remove it>",
  "stomach_sensitive": <true if patient mentioned stomach issues, ulcers, or stomach sensitivity, else false>,
  "medicine_mentioned": "<specific brand/medicine name if user mentioned one precisely, else null>",
  "quantity": <integer if explicitly mentioned e.g. "2 boxes", else 1. Do NOT multiply by days — just extract the raw number mentioned>,
  "user_is_confirming": <true if user is saying yes/sure/ok/order it/let's do it to a previous suggestion>,
  "user_wants_all": <true if user says "both", "all", "everything", "1 and 2" to select multiple products>,
  "symptoms_to_ignore": ["list of symptoms user explicitly says to ignore"]
}

Intent rules:
- GENERAL_INFO: user is asking a general medical/health INFORMATION question — not ordering anything.
  Examples: "what pain relievers are safe for headaches?", "which antibiotic is best for throat infection?",
  "is ibuprofen safe during pregnancy?", "what medicine should I take for fever?",
  "are there any side effects of paracetamol?", "what is the difference between ibuprofen and paracetamol?",
  "can I take aspirin with blood pressure medication?", "what are safe medicines for diabetics?",
  "which is better for cold - paracetamol or ibuprofen?", "what should I take for body pain?",
  "is Mucosolvan safe for diabetics?", "is X safe for me?", "can a diabetic take Y?",
  "is there a sugar-free version of X?", "is X safe with my condition?",
  "I need something for cough but I am diabetic, is Mucosolvan safe?"
  KEY SIGNALS: question words (what, which, is X safe, can I take, are there, is there a) + symptom/condition/health context, NO clear purchase intent.
  CRITICAL: If message contains "is X safe", "is X safe for me", "is there a sugar-free", "can a diabetic take",
  "is it safe with my condition", or asks about suitability/alternatives for a health condition
  → ALWAYS classify as GENERAL_INFO even if a specific medicine name is mentioned.
  The presence of a medicine name alone does NOT make it an ORDER — the user must show clear purchase intent.
  NEVER classify as GENERAL_INFO if user says "order", "get me", "give me" a medicine with no safety question.

- PRODUCT_QUERY: user is asking about details of a specific product — either in context OR explicitly named in this message.
  Examples: "how much package size i get in this", "what is the dosage", "is it sugar free", "how many tablets in a pack",
  "how much quantity i get in cetaphil", "what is the package size of ibuprofen", "how many ml in this bottle",
  "what does it contain", "is cetaphil good for dry skin", "how big is the pack",
  "do I need a prescription for Ramipril?", "is Ramipril prescription only?",
  "does Wysolone require a prescription?", "is ibuprofen OTC or prescription?",
  "do I need a doctor's note for X?", "can I buy X without prescription?",
  "is X available over the counter?", "is X a prescription medicine?",
  "how long will a pack of 20 last?", "how many days will this last me?",
  "is it safe with contact lenses?", "can I use this with contacts?"
  KEY SIGNALS: "prescription", "prescription only", "OTC", "over the counter", "doctor's note",
  "need a script", "need a prescription" combined with a specific medicine name
  → ALWAYS classify as PRODUCT_QUERY when user asks if a named medicine requires prescription.
  NEVER route these to GENERAL_INFO.
  "what are the ingredients", "is it suitable for kids", "what does it contain", "tell me more about it",
  "how should I take this", "what is this used for", "any side effects of this".
  KEY SIGNAL: "this", "it", "that", "the one you recommended" — referring to a product already in context.
  ALWAYS classify as PRODUCT_QUERY when user asks "how much" + "in this/it" (package size question).

- SUPPLY_QUERY: user is asking when their current medicine supply will run out, or how long it will last.
  Examples: "when will my Wysolone run out?", "I started on March 5th taking 1 pill a day, when does it run out?",
  "how many days does my supply last?", "I have 30 tablets and take 2 a day, how long will it last?",
  "when should I reorder?", "I want to reorder my Wysolone, I've been taking one pill a day since March 5th".
  KEY SIGNALS: mentions of start date, pill frequency, "run out", "supply", "last me", "how long",
  "when should I reorder", "I've been taking X per day".
  IMPORTANT: Classify as SUPPLY_QUERY even if user also mentions wanting to reorder — answer the
  supply calculation FIRST, then offer to place the order.
  Also extract: medicine_mentioned if a specific product is named.

- PRICE_QUERY: user is asking about the price of a specific product.
  Examples: "how much is X?", "what's the price of Y?", "how much does Z cost?", "price for A", "cost of B"

- EMERGENCY: user describes an acute life-threatening or urgent medical situation.
  Examples: "I can't breathe", "chest pain", "heart attack", "severe allergic reaction",
  "choking", "passed out", "seizure", "stroke", "overdose", "I'm dying", "suicidal".
  ALWAYS classify as EMERGENCY — never ORDER or TRIAGE. Even if PENDING SUGGESTION exists.

- ORDER: user wants a SPECIFIC NAMED medicine (e.g. "give me Paracetamol 500mg", "I want NORSAN Omega-3 Vegan")
  Examples: "i want those pink vitamins Vitasprint", "get me B12 please", "need NORSAN omega-3",
  "I need to order Cromo-ratiopharm Augentropfen", "I want to buy Mucosolvan",
  "I need to order X for N days", "get me ibuprofen for a week"
  CRITICAL RULE 0 — HIGHEST PRIORITY: If user says "I need to order", "I want to order",
  "can I order", "I want to buy", "please order", "get me", "give me" + a specific named medicine,
  classify as ORDER regardless of any additional product/safety questions in the same message.
  The safety/supply/contact-lens question is SECONDARY — answer it inline, do NOT route to GENERAL_INFO.

- TRIAGE: user describes symptoms, health goals, or product ATTRIBUTES/PROPERTIES rather than a specific name.
  Examples: "something for a cold", "vegan omega-3", "painkiller without ibuprofen",
  "omega-3 that isn't from fish", "something for brain health", "algae-based supplement"

- CONFIRM_ORDER: user is confirming a recommendation the assistant just made (yes/sure/ok/order it/go ahead/do it/yep/please)
  IMPORTANT: Also classify as CONFIRM_ORDER when user says "both", "all", "everything", "1 and 2" to select multiple products.

- CONVERSATION: user is making casual conversational response (greetings/thanks/apologies/farewells/short acknowledgements)

- REJECT_SUGGESTION: user explicitly rejects a suggestion ("no ignore headache just get the B12")

CRITICAL RULES:
0. HIGHEST PRIORITY — Explicit order intent + specific named medicine ALWAYS = ORDER, regardless of
   any additional questions in the message (supply duration, contact lens safety, side effects etc.).
   Key signals: "I need to order", "I want to order", "can I order", "I want to buy",
   "please order", "get me", "give me" + a specific named medicine.
   Answer the secondary question inline within the ORDER response. NEVER route to GENERAL_INFO.
1. If user describes WHAT THEY WANT by properties (vegan, algae-based, fish-free, brain health, non-drowsy)
   rather than a specific brand name -> intent = TRIAGE, medicine_mentioned = null.
2. Only set medicine_mentioned when user says an EXACT product name like "NORSAN Omega-3 Vegan".
3. Short messages (1-3 words) like 'ok', 'thanks', 'cool', 'sure', 'alright', 'got it', 'nice'
   ALWAYS = CONVERSATION, not ORDER or CONFIRM_ORDER.
4. Pure numbers like "1", "2", "3" or "1." "2." "3." = CONVERSATION (handled separately as product selection).
5. If PENDING SUGGESTION exists and user confirms -> intent = CONFIRM_ORDER, medicine_mentioned = suggestion name.
6. If user says "both", "all", "everything", or "1 and 2" -> set user_wants_all = true and intent = CONFIRM_ORDER.

Output ONLY the JSON. No markdown."""

TRIAGE_SYSTEM = """You are an expert clinical pharmacy assistant. Your recommendations must be medically precise.

PRIMARY COMPLAINT: {pcomplaint}
PATIENT CONTEXT: {tcontext}
RELEVANT MEDICINES FOR THIS COMPLAINT:
{catalogue}

CONTRAINDICATION RULES:
- Stomach ulcer/gastric issues -> NO ibuprofen, aspirin, diclofenac (NSAIDs cause GI bleeding)
- Blood thinners/Warfarin -> NO aspirin, ibuprofen (increase bleeding risk)
- Heart failure/cardiac condition -> NO ibuprofen, naproxen (cause fluid retention)
- Kidney disease -> NO ibuprofen, naproxen (nephrotoxic)
- Asthma -> NO aspirin, ibuprofen (can trigger bronchospasm)
- Pregnancy -> NO ibuprofen, aspirin (teratogenic in 3rd trimester)
- Hypertension/Lisinopril/Amlodipine -> NO ibuprofen, naproxen (raises BP, interferes with medication)
- Liver disease -> NO high-dose paracetamol

Safe alternatives: Paracetamol is almost always safe for pain/fever with any of above conditions.
For cold/respiratory symptoms -> prefer Sinupret, Umckaloabo over generic painkillers.

MULTI-SYMPTOM NUANCE RULE:
If the patient reports multiple symptoms and the recommended medicine covers MOST but not ALL:
- Recommend the best medicine for the primary/majority of symptoms
- Acknowledge the uncovered symptom with a safe non-medicine suggestion (gargle, lozenges, steam)
- Keep the additional note to ONE sentence maximum

SUPPLEMENT / NUTRITION RULES:
- Vegan / plant-based / algae-based Omega-3 -> recommend NORSAN Omega-3 Vegan (algae oil, not fish)
- Fish-based Omega-3 or unspecified -> NORSAN Omega-3 Total or NORSAN Omega-3 Kapseln
- Brain health + Omega-3 -> NORSAN Omega-3 Vegan covers both
- Always acknowledge the specific attribute the user asked for (vegan, algae, fish-free)

RESPONSE FORMAT (JSON only):
{{
  "reply": "<your clinical response ending with: Want me to proceed with the order?>",
  "ready_to_order": <true if recommending a specific medicine>,
  "recommended_medicine": "<exact medicine name from catalogue if ready_to_order=true, else null>",
  "confidence": <0.0 to 1.0>
}}

Output ONLY the JSON. No markdown."""

# ── OTC info for Indian pharmacy context ─────────────────────────────────────
GENERAL_INFO_EXAMPLES = {
    "headache":   "• Paracetamol (Crocin, Dolo, Calpol) — mild pain & fever\n• Ibuprofen (Brufen, Combiflam) — pain & inflammation",
    "migraine":   "• Paracetamol (Crocin, Dolo) — first-line for migraine\n• Ibuprofen (Brufen) — if paracetamol insufficient\n⚕️ Consult a neurologist for frequent migraines",
    "fever":      "• Paracetamol (Crocin, Dolo 650, Calpol) — most commonly used\n• Ibuprofen (Brufen) — if fever is high & no stomach issues",
    "cold":       "• Paracetamol (Crocin, Dolo) — for fever & body ache\n• Cetirizine (Cetcip, Okacet) — for runny nose & sneezing\n• Steam inhalation + warm fluids — for congestion relief",
    "cough":      "• Benadryl / Honitus / Alex — common OTC cough syrups\n• Mucolytic (Mucinex, Ambrodil) — for chesty cough with phlegm\n⚕️ Consult a doctor if cough persists beyond 1 week",
    "body pain":  "• Paracetamol (Crocin, Dolo) — for general body ache\n• Ibuprofen (Brufen, Combiflam) — for muscle pain & inflammation\n• Diclofenac gel (Voveran) — topical option for localised pain",
    "throat":     "• Strepsils / Cofsils lozenges — soothing relief\n• Warm salt water gargle — reduces inflammation\n• Paracetamol (Crocin) — for throat pain & fever\n⚕️ See a doctor if severe or lasts more than 3 days",
    "stomach":    "• ORS (Electral, Enerzal) — for hydration & diarrhoea\n• Gelusil / Digene / Eno — for acidity & gas\n• Domperidone (Domstal) — for nausea\n⚕️ Consult a doctor for severe or persistent stomach pain",
    "allergy":    "• Cetirizine (Cetcip, Zyrtec, Alerid) — non-drowsy antihistamine\n• Loratadine (Clarityn) — once-a-day allergy relief\n• Fexofenadine (Allegra 120) — for allergic rhinitis",
    "pain":       "• Paracetamol (Crocin, Dolo) — for general pain & fever\n• Ibuprofen (Brufen, Combiflam) — for inflammatory pain\n• Diclofenac (Voveran, Voltaren) — for joint or muscle pain",
    "sleep":      "• Melatonin (Sleepwell, Dozile) — for mild sleep issues\n⚕️ Consult a doctor for chronic insomnia — prescription sleep aids are controlled in India",
    "anxiety":    "⚕️ Anxiety is very treatable — please consult a qualified doctor or psychiatrist for proper care.",
    "diabetes":   "⚕️ Diabetes medications require a prescription. Please consult your doctor for ongoing management.",
    "blood pressure": "⚕️ Blood pressure medicines require a prescription. Please consult your doctor.",
    "skin":       "• Calamine lotion — for rashes & itching\n• Betadine — for minor wound cleaning\n• Cetaphil / Aveeno / Lacto Calamine — for dry or sensitive skin\n⚕️ Consult a dermatologist for persistent skin conditions",
}

COMPLAINT_KEYWORD_MAP = {
    "headache": ["paracetamol", "nurofen", "ibuprofen", "migra"],
    "migraine": ["paracetamol", "nurofen", "ibuprofen"],
    "fever": ["paracetamol", "nurofen", "ibuprofen"],
    "pain": ["paracetamol", "nurofen", "ibuprofen", "diclo"],
    "muscle pain": ["diclo", "ibuprofen", "nurofen"],
    "cold": ["sinupret", "umckaloabo", "mucosolvan", "nurofen", "paracetamol"],
    "flu": ["sinupret", "umckaloabo", "nurofen", "paracetamol"],
    "cough": ["mucosolvan", "umckaloabo", "sinupret"],
    "sore throat": ["umckaloabo", "sinupret"],
    "sinus": ["sinupret"],
    "congestion": ["sinupret"],
    "runny nose": ["sinupret", "umckaloabo"],
    "stomach": ["iberogast", "omni-biotic", "kijimea", "multilac", "probio", "v-biotics"],
    "heartburn": ["iberogast"],
    "nausea": ["iberogast", "omni-biotic"],
    "diarrhea": ["loperamid", "kijimea", "omni-biotic", "multilac"],
    "ibs": ["kijimea", "omni-biotic", "multilac", "v-biotics"],
    "constipation": ["dulcolax"],
    "bloating": ["iberogast", "omni-biotic", "kijimea"],
    "gut": ["omni-biotic", "kijimea", "multilac", "probio", "v-biotics"],
    "bladder": ["aqualibra", "cystinol", "granu fink"],
    "urinary": ["aqualibra", "cystinol", "granu fink"],
    "uti": ["aqualibra", "cystinol"],
    "eye": ["vividrin", "cromo", "augentropfen", "livocab", "hyaluron", "redcare aug"],
    "eye pain": ["vividrin", "cromo", "augentropfen", "hyaluron"],
    "dry eyes": ["hyaluron", "augentropfen"],
    "eye allergy": ["vividrin", "cromo", "livocab"],
    "itchy eyes": ["vividrin", "cromo", "livocab", "cetirizin"],
    "allergy": ["cetirizin", "vividrin", "livocab", "cromo"],
    "hay fever": ["cetirizin", "vividrin", "livocab"],
    "skin": ["eucerin", "bepanthen", "panthenol", "aveeno", "cetaphil", "fenihydrocort", "redcare wund", "osa"],
    "eczema": ["eucerin", "aveeno", "fenihydrocort", "bepanthen"],
    "dry skin": ["eucerin", "aveeno", "cetaphil", "urearepair"],
    "wound": ["bepanthen", "panthenol", "osa", "redcare wund"],
    "rash": ["fenihydrocort", "bepanthen", "eucerin"],
    "hair loss": ["minoxidil"],
    "scalp": ["frida", "minoxidil"],
    "itchy skin": ["aveeno", "eucerin", "fenihydrocort", "cetaphil", "bepanthen"],
    "sensitive skin": ["aveeno", "cetaphil", "eucerin"],
    "sleep": ["calmvalera"],
    "anxiety": ["calmvalera"],
    "stress": ["calmvalera", "vitasprint", "magnesium"],
    "vitamin": ["vitasprint", "centrum", "vitamin b", "vigantolvit", "magnesium", "b12", "norsan", "multivitamin"],
    "tired": ["vitasprint", "centrum", "b12", "norsan", "magnesium"],
    "energy": ["vitasprint", "centrum", "b12"],
    "omega": ["norsan"],
    "omega-3": ["norsan"],
    "omega 3": ["norsan"],
    "fish oil": ["norsan omega-3 total", "norsan omega-3 kapseln", "norsan"],
    "vegan": ["norsan omega-3 vegan", "norsan", "multivitamin"],
    "algae": ["norsan omega-3 vegan", "norsan"],
    "plant-based": ["norsan omega-3 vegan", "norsan"],
    "brain": ["norsan", "vitasprint", "centrum", "b12"],
    "brain health": ["norsan", "vitasprint", "b12"],
    "heart health": ["norsan", "magnesium verla"],
    "magnesium": ["magnesium verla"],
    "vitamin d": ["vigantolvit"],
    "vitamin b": ["vitasprint", "vitamin b-komplex", "b12"],
    "supplement": ["norsan", "vitasprint", "centrum", "magnesium", "multivitamin"],
    "probiotic": ["omni-biotic", "multilac", "probio", "v-biotics", "kijimea"],
    "prostate": ["prostata", "granu fink", "saw palmeto"],
    "hormones": ["femiloges"],
    "feminine": ["colpofix", "natural intimate", "femiloges"],
    "blood pressure": ["ramipril"],
    "heart": ["ramipril", "magnesium"],
}

CHRONIC_MEDICINE_CONDITIONS = {
    "thyroxin": "thyroid", "levothyroxin": "thyroid", "t4": "thyroid", "thyroid": "thyroid",
    "metformin": "diabetes", "insulin": "diabetes", "glibenclamid": "diabetes",
    "glimepirid": "diabetes", "sitagliptin": "diabetes", "empagliflozin": "diabetes",
    "dapagliflozin": "diabetes", "liraglutid": "diabetes",
    "ramipril": "high blood pressure", "lisinopril": "high blood pressure",
    "amlodipin": "high blood pressure", "enalapril": "high blood pressure",
    "losartan": "high blood pressure", "valsartan": "high blood pressure",
    "candesartan": "high blood pressure", "bisoprolol": "heart condition",
    "metoprolol": "heart condition", "atorvastatin": "cholesterol",
    "simvastatin": "cholesterol", "rosuvastatin": "cholesterol", "aspirin": "heart health",
    "salbutamol": "asthma", "formoterol": "asthma", "budesonid": "asthma",
    "montelukast": "asthma", "inhaler": "asthma",
    "sertralin": "anxiety/depression", "escitalopram": "anxiety/depression",
    "fluoxetine": "anxiety/depression", "citalopram": "anxiety/depression",
    "duloxetine": "anxiety/depression",
}

PAINKILLER_KEYWORDS = [
    "paracetamol", "nurofen", "ibuprofen", "diclofenac", "aspirin",
    "naproxen", "diclo", "voltaren", "alg", "schmerz"
]

DELIVERY_KEYWORDS = [
    "delivery", "deliver", "arrive", "shipping", "ship", "estimated",
    "arrive within", "arrive by", "delivery time", "delivery estimate",
    "will be prepared", "ready for pickup", "pickup", "estimated delivery",
]

ACKNOWLEDGMENT_WORDS = {
    "ok", "okay", "ok thanks", "thanks", "thank you", "cool",
    "alright", "got it", "sure", "nice", "great", "perfect",
}

NEGATIVE_RESPONSE_KEYWORDS = [
    "i want nothing", "want nothing", "nothing", "none", "don't want anything",
    "not interested", "no thanks", "not needed", "skip", "i'll pass", "i'm good",
    "i'm fine", "nothing for now", "don't need anything", "no order",
    "don't want to order", "not ordering anything", "not ordering",
    "nah", "nope", "not now", "maybe later", "another time",
]

DIRECT_ORDER_KEYWORDS = [
    "order", "get", "buy", "want", "need", "give", "send", "ship",
    "purchase", "pick up", "pickup", "collect",
]

QUANTITY_KEYWORDS = [
    "box", "boxes", "pack", "packs", "bottle", "bottles", "strip", "strips",
    "tablet", "tablets", "capsule", "capsules", "blister", "blisters",
    "sachet", "sachets", "tube", "tubes", "packet", "packets",
]

NON_PRESCRIPTION_SUPPLEMENTS = [
    "omega-3", "omega 3", "norsan", "fish oil", "algae oil", "dha", "epa",
    "vitamin", "vitasprint", "centrum", "multivitamin", "b-complex", "b12",
    "vitamin d", "vitamin c", "vitamin b", "magnesium", "zinc", "iron",
    "probiotic", "omni-biotic", "multilac", "kijimea", "probio", "v-biotics",
    "supplement", "nutrition", "herbal", "natural", "plant-based", "vegan",
    "algae-based", "fish-free",
]

SKIP_WORDS = {
    "a", "an", "the", "of", "for", "and", "my", "me", "i", "get", "need", "want", "give",
    "some", "can", "please", "mg", "ml", "st", "g", "tablet", "tablets", "capsule",
    "capsules", "lotion", "cream", "gel", "spray", "pack", "packs", "box", "boxes",
}

ACTIVE_INGREDIENTS = [
    "paracetamol", "acetaminophen", "ibuprofen", "nurofen", "aspirin",
    "diclofenac", "voltaren", "naproxen", "loperamid", "imodium",
    "ramipril", "lisinopril", "amlodipine", "metformin", "atorvastatin",
    "omeprazole", "pantoprazole", "esomeprazole", "simvastatin",
    "cetirizin", "loratadin", "diphenhydramin", "melatonin",
    "sinupret", "umckaloabo", "mucosolvan", "ambroxol",
    "ibergast", "gaviscon", "motilium", "buscopan",
    "vitasprint", "centrum", "multivitamin", "magnesium",
    "norsan", "omega", "b12", "vitamind", "vitaminb",
]


# ── Pure helpers ──────────────────────────────────────────────────────────────

def _get_chronic_condition_from_medicine(medicine_name: str) -> str:
    if not medicine_name:
        return ""
    name_lower = medicine_name.lower()
    for keyword, condition in CHRONIC_MEDICINE_CONDITIONS.items():
        if keyword in name_lower:
            return condition
    return ""


def _should_clear_complaint(medicine_name: str) -> bool:
    return bool(_get_chronic_condition_from_medicine(medicine_name))


def _extract_json(text: str) -> str:
    text = text.strip()
    if not text:
        return text
    if text.startswith("\n"):
        text = text[1:].strip()
    bt = chr(96) * 3
    for marker in [bt + "json", bt]:
        if text.startswith(marker):
            text = text[len(marker):].strip()
        if text.endswith(marker):
            text = text[:-len(marker)].strip()
    return text.strip()


def _fetch_products() -> list[dict]:
    try:
        resp = supabase.table("products").select(
            "id,name,price,prescription_required,description,package_size"
        ).execute()
        return resp.data or []
    except Exception as e:
        print(f"⚠️ Error fetching products from Supabase: {e}")
        return []


def _filter_for_complaint(
    products: list[dict], complaint: str, stomach_sensitive: bool
) -> list[dict]:
    complaint_lower = (complaint or "").lower()
    keywords = []
    for key, kws in COMPLAINT_KEYWORD_MAP.items():
        if key in complaint_lower or complaint_lower in key:
            keywords.extend(kws)
    if not keywords:
        return products
    filtered = [p for p in products if any(kw in p["name"].lower() for kw in keywords)]
    if stomach_sensitive and any(
        c in complaint_lower for c in ["headache", "migraine", "pain", "fever"]
    ):
        filtered = [
            p for p in filtered
            if not any(x in p["name"].lower() for x in ["ibuprofen", "aspirin", "diclofenac"])
        ] or filtered
    return filtered if len(filtered) >= 3 else products


def _catalogue_str(products: list[dict]) -> str:
    lines = []
    for p in products:
        line = f"- {p['name']} (EUR{p['price']})"
        if p.get("package_size"):
            line += f" - {p['package_size']}"
        if p.get("prescription_required"):
            line += " [Rx REQUIRED]"
        if p.get("description"):
            line += f" - {p['description']}"
        lines.append(line)
    return "\n".join(lines)


def _format_price_response(product: dict) -> str:
    name  = product.get("name", "Unknown product")
    price = product.get("price", 0)
    pkg   = product.get("package_size")
    rx    = product.get("prescription_required", False)
    resp  = f"**{name}**\n💰 Price: EUR{price:.2f}"
    if pkg:
        resp += f"\n📦 Package size: {pkg}"
    if rx:
        resp += "\n⚠️ Prescription required"
    return resp


def _build_history(history: list[dict]) -> list:
    msgs = []
    for turn in history:
        content = (turn.get("content") or "").strip()
        if not content:
            continue
        msgs.append(
            HumanMessage(content=content) if turn.get("role") == "user"
            else AIMessage(content=content)
        )
    return msgs


def _build_triage_context(history: list[dict], user_message: str) -> str:
    all_user_msgs = [
        t.get("content", "") for t in history if t.get("role") == "user"
    ] + [user_message]
    return " | ".join(all_user_msgs)


def _sim(a: str, b: str) -> float:
    if not a or not b:
        return 0.0
    a, b = a.lower(), b.lower()
    if a == b:
        return 1.0
    if a in b or b in a:
        return 0.8
    return SequenceMatcher(None, a, b).ratio()


def _is_duplicate_response(
    new_response: str, last_response: str, threshold: float = 0.9
) -> bool:
    if not new_response or not last_response:
        return False
    new_norm  = " ".join(new_response.lower().split())
    last_norm = " ".join(last_response.lower().split())
    if new_norm == last_norm:
        return True
    return SequenceMatcher(None, new_norm, last_norm).ratio() >= threshold


def _is_direct_order(user_message: str, medicine_mentioned: str = None) -> bool:
    msg_lower         = user_message.lower()
    has_quantity      = any(qty in msg_lower for qty in QUANTITY_KEYWORDS)
    has_order_intent  = any(kw in msg_lower for kw in DIRECT_ORDER_KEYWORDS)
    has_numeric_qty   = bool(re.search(r'\d+\s*(box|pack|bottle|strip|capsule|tablet)', msg_lower))

    if medicine_mentioned and (has_quantity or has_numeric_qty or has_order_intent):
        return True

    for supplement in NON_PRESCRIPTION_SUPPLEMENTS:
        if supplement in msg_lower and (has_order_intent or has_quantity or has_numeric_qty):
            return True

    direct_patterns = [
        r'\bi want\b', r"\bi'd like\b", r'\bget me\b', r'\bbuy\b',
        r'\bneed\b.*\bnow\b', r'\border\b.*\bnow\b',
        r'\bsend me\b', r'\bship\b',
    ]
    return any(re.search(p, msg_lower) for p in direct_patterns)


def _is_non_prescription_supplement(medicine_name: str) -> bool:
    if not medicine_name:
        return False
    name_lower = medicine_name.lower()
    return any(supp in name_lower for supp in NON_PRESCRIPTION_SUPPLEMENTS)


def _contains_delivery_info(text: str) -> bool:
    if not text:
        return False
    return any(kw in text.lower() for kw in DELIVERY_KEYWORDS)


def _format_refill_notification(state: AgentState) -> str:
    if not state.get("refill_alert") or not state.get("refill_medicine"):
        return ""
    from datetime import datetime
    try:
        due_date  = datetime.strptime(state["refill_due_date"], "%Y-%m-%d")
        days_until = (due_date - datetime.now()).days
        if days_until < 0:
            days_text = f"overdue by {abs(days_until)} days"
        elif days_until == 0:
            days_text = "due today"
        else:
            days_text = f"due in {days_until} days"
    except Exception:
        days_text = ""
    return (
        f"\n\n🔔 **Refill Reminder:** Your **{state['refill_medicine']}** is {days_text}. "
        f"Would you like me to prepare a refill order for you?"
    )


def _is_user_acknowledging(user_message: str) -> bool:
    if not user_message:
        return False
    msg_lower = user_message.lower().strip()
    return msg_lower in ACKNOWLEDGMENT_WORDS or any(ack in msg_lower for ack in ACKNOWLEDGMENT_WORDS)


def _is_negative_response(user_message: str) -> bool:
    if not user_message:
        return False
    msg_lower = user_message.lower().strip()
    if msg_lower in ["nothing", "none", "nope", "nah", "no", "skip", "pass"]:
        return True
    return any(kw in msg_lower for kw in NEGATIVE_RESPONSE_KEYWORDS)


def _normalize_medicine_name(name: str) -> str:
    name = name.lower()
    name = re.sub(r'(\d)\s*(mg|g|ml|%)', r'\1\2', name)
    name = re.sub(r'[\s\-.]+', '', name)
    return name


def _extract_active_ingredient(medicine_name: str) -> str:
    name = medicine_name.lower()
    for ingredient in ACTIVE_INGREDIENTS:
        if ingredient in name:
            return ingredient
    return name.split()[0] if name.split() else name


def _matches_active_ingredient(query: str, product_name: str) -> bool:
    qi = _extract_active_ingredient(query)
    pi = _extract_active_ingredient(product_name)
    return qi == pi or qi in pi or pi in qi


def _parse_multiple_medicines(medicine_string: str) -> list[str]:
    if not medicine_string:
        return []
    cleaned = medicine_string.strip()
    separators = [
        r',\s*and\s+', r',\s*', r'\s+and\s+', r'\s+\+\s+', r'&\s*',
    ]
    for sep_pattern in separators:
        parts = re.split(sep_pattern, cleaned, flags=re.IGNORECASE)
        if len(parts) > 1:
            medicines = [p.strip() for p in parts if p.strip() and len(p.strip()) > 1]
            if medicines:
                return medicines
    for conj in ['and', 'und', '+', '&']:
        parts = re.split(rf'\s+{re.escape(conj)}\s+', cleaned, flags=re.IGNORECASE)
        if len(parts) > 1:
            medicines = [p.strip() for p in parts if p.strip() and len(p.strip()) > 1]
            if medicines:
                return medicines
    medicine_pairs = [
        ['paracetamol', 'mucosolvan'], ['paracetamol', 'ibuprofen'],
        ['nurofen', 'mucosolvan'], ['aspirin', 'paracetamol'],
        ['sinupret', 'mucosolvan'], ['cetirizin', 'mucosolvan'],
    ]
    cl = cleaned.lower()
    for pair in medicine_pairs:
        if all(m in cl for m in pair):
            return pair
    return [cleaned]


def _find_matches(query: str, products: list[dict], threshold: float = 0.72) -> list[dict]:
    if not query:
        return []
    q            = query.lower().strip()
    q_normalized = _normalize_medicine_name(q)
    q_words      = [w for w in q.split() if len(w) > 2 and w not in SKIP_WORDS]

    exact = [p for p in products if p["name"].lower().strip() == q]
    if exact:
        return exact

    exact_norm = [p for p in products if _normalize_medicine_name(p["name"]) == q_normalized]
    if exact_norm:
        return exact_norm

    if q_words:
        wm = [p for p in products if all(w in p["name"].lower() for w in q_words)]
        if wm:
            filtered = [p for p in wm if _matches_active_ingredient(q, p["name"])]
            return filtered if filtered else []

    if q_words:
        scored = []
        for p in products:
            pw     = p["name"].lower().split()
            scores = [max(_sim(qw, w) for w in pw) for qw in q_words]
            if min(scores) >= threshold:
                scored.append((sum(scores) / len(scores), p))
        if scored:
            scored.sort(key=lambda x: x[0], reverse=True)
            filtered = [(s, p) for s, p in scored if _matches_active_ingredient(q, p["name"])]
            if filtered:
                top = filtered[0][0]
                return [p for s, p in filtered if s >= top - 0.10]
            return []

    return [p for p in products if q in p["name"].lower() and _matches_active_ingredient(q, p["name"])]


def _match_prescription_medicine(
    user_requested: str,
    prescription_medicines: list[str],
    products: list[dict],
) -> dict | None:
    if not prescription_medicines or not user_requested:
        return None
    user_lower = user_requested.lower().strip()

    for rx_med in prescription_medicines:
        rx_lower = rx_med.lower().strip()
        if rx_lower == user_lower:
            m = _find_matches(rx_med, products)
            if m:
                return m[0]

    for rx_med in prescription_medicines:
        rx_lower = rx_med.lower().strip()
        if rx_lower in user_lower or user_lower in rx_lower:
            m = _find_matches(rx_med, products)
            if m:
                return m[0]

    user_ingredient = _extract_active_ingredient(user_requested)
    for rx_med in prescription_medicines:
        rx_ingredient = _extract_active_ingredient(rx_med)
        if user_ingredient and rx_ingredient:
            if (user_ingredient == rx_ingredient
                    or user_ingredient in rx_ingredient
                    or rx_ingredient in user_ingredient):
                m = _find_matches(rx_med, products)
                if m:
                    return m[0]

    for rx_med in prescription_medicines:
        if _sim(user_lower, rx_med.lower().strip()) >= 0.75:
            m = _find_matches(rx_med, products)
            if m:
                return m[0]

    return None


def _is_selection_response(user_message: str) -> tuple[bool, int]:
    """
    Detect that user is selecting a numbered product option.
    Handles:
      - Bare number: "3"
      - Number + dot/paren: "3." / "3)"
      - Number + product name: "3. NORSAN Omega-3 Total" / "3 norsan total"
      - Ordinals: "third", "3rd"
      - Prefixed: "option 3", "#3", "number 3"
    """
    msg = user_message.strip().lower()
    msg_clean = msg.rstrip(".")

    if msg_clean.isdigit():
        num = int(msg_clean)
        if 1 <= num <= 10:
            return True, num - 1

    m = re.match(r'^(\d+)[.)]\s*', msg)
    if m:
        num = int(m.group(1))
        if 1 <= num <= 10:
            return True, num - 1

    m = re.match(r'^(?:option|number|#)\s*(\d+)', msg)
    if m:
        num = int(m.group(1))
        if 1 <= num <= 10:
            return True, num - 1

    ordinals = {
        "first": 0, "second": 1, "third": 2, "fourth": 3, "fifth": 4,
        "sixth": 5, "seventh": 6, "eighth": 7, "ninth": 8, "tenth": 9,
        "1st": 0, "2nd": 1, "3rd": 2, "4th": 3, "5th": 4,
        "6th": 5, "7th": 6, "8th": 7, "9th": 8, "10th": 9,
    }
    if msg_clean in ordinals:
        return True, ordinals[msg_clean]
    for word, idx in ordinals.items():
        if msg_clean.startswith(word):
            return True, idx

    return False, -1


def _is_multi_selection(user_message: str) -> tuple[bool, list[int]]:
    msg = user_message.strip().lower()
    multi_keywords = [
        "both", "all", "everything", "every item", "all items", "all of them",
        "i want both", "get both", "order both", "want both", "take both",
        "give me both", "i need both", "need both", "please both",
    ]
    if any(kw in msg for kw in multi_keywords):
        return True, []
    m = re.findall(r'(\d+)\s*(?:and|&)\s*(\d+)', msg)
    if m:
        return True, [int(x) - 1 for tup in m for x in tup]
    if re.match(r'^[\d\s,]+$', msg.replace(" ", "")):
        numbers = re.findall(r'\d+', msg)
        indices = [int(x) - 1 for x in numbers]
        if indices:
            return True, indices
    return False, []


def _extract_quantity_from_message(user_message: str) -> int:
    msg = user_message.lower()
    m   = re.search(
        r'(\d+)\s*(?:packets?|packs?|st(?:ück)?|tablets?|capsules?|boxes?|for each|of each)?',
        msg,
    )
    if m:
        qty = int(m.group(1))
        if 0 < qty <= 100:
            return qty
    return 1


def _parse_freq_from_string(s: str) -> int:
    """Parse a frequency integer from a dosage string like 'Three times daily', 'BD', '1-0-1'."""
    s = s.lower().strip()
    if "as needed" in s or "prn" in s or "bei bedarf" in s:
        return 1
    if "four" in s or "4 times" in s or "qid" in s or "1-1-1-1" in s:
        return 4
    if "three" in s or "3 times" in s or "tds" in s or "tid" in s or "1-1-1" in s:
        return 3
    if "twice" in s or "2 times" in s or "bd" in s or "1-0-1" in s or "two times" in s:
        return 2
    if "once" in s or "1 time" in s or "od" in s or "daily" in s:
        return 1
    m = re.search(r'(\d)-(\d)-(\d)', s)
    if m:
        total = int(m.group(1)) + int(m.group(2)) + int(m.group(3))
        if total > 0:
            return total
    m = re.search(r'(\d+)\s*times', s)
    if m:
        return int(m.group(1))
    m = re.search(r'every\s*(\d+)\s*hours?', s)
    if m:
        hours = int(m.group(1))
        if hours > 0:
            return max(1, round(24 / hours))
    return 1


# ── Default dosage frequencies based on medicine type/category ─────────────────
MEDICINE_TYPE_DEFAULT_DOSAGE = {
    "eye": 3, "augentropfen": 3, "vividrin": 3, "cromo": 3, "livocab": 3, "hyaluron": 3,
    "redcare": 3, "optrex": 3, "blephaclear": 3, "artelac": 3, "hylo": 3,
    "nasal": 2, "nose": 2, "spray": 2, "nasenspray": 2, "rinus": 2, "otriven": 2,
    "saline": 2, "mucosolvan nasal": 3,
    "ear": 2, "ot": 2, "ear drops": 2, "otriv": 2,
    "cough": 3, "syrup": 3, "mucosolvan": 3, "ambroxol": 3, "honitus": 3,
    "benadryl": 3, "alex cough": 3, "sinupret": 3, "umckaloabo": 3,
    "pain": 3, "ibuprofen": 3, "nurofen": 3, "paracetamol": 3, "dolo": 3,
    "crocin": 3, "diclofenac": 2, "voltaren": 2, "aspirin": 3,
    "allergy": 1, "cetirizin": 1, "cetcip": 1, "zyrtec": 1, "alerid": 1,
    "loratadin": 1, "clarityn": 1, "fexofenadin": 1, "allegra": 1,
    "vitamin": 1, "b12": 1, "b-complex": 1, "multivitamin": 1, "norsan": 1,
    "omega": 1, "magnesium": 1, "vitasprint": 1, "centrum": 1,
    "probiotic": 1, "omni-biotic": 1, "multilac": 1, "kijimea": 1,
    "probio": 1, "v-biotics": 1,
    "skin": 2, "cream": 2, "gel": 2, "lotion": 2, "eczema": 2,
    "bepanthen": 2, "panthenol": 2, "eucerin": 2, "aveeno": 2,
    "cetaphil": 2, "fenihydrocort": 2,
}


def _get_default_dosage_for_medicine(medicine_name: str) -> int:
    if not medicine_name:
        return 1
    medicine_lower = medicine_name.lower()
    for key, freq in MEDICINE_TYPE_DEFAULT_DOSAGE.items():
        if key in medicine_lower:
            return freq
    words = medicine_lower.split()
    for word in words:
        if len(word) > 3 and word in MEDICINE_TYPE_DEFAULT_DOSAGE:
            return MEDICINE_TYPE_DEFAULT_DOSAGE[word]
    for key, freq in MEDICINE_TYPE_DEFAULT_DOSAGE.items():
        if medicine_lower in key:
            return freq
    return 1


def _extract_duration_based_quantity(
    user_message: str,
    patient_id:   str = None,
    medicine_name: str = None,
) -> tuple[int, str, bool]:
    """
    Detect duration-based ordering: "for 2 days", "for a week", "for 3 days twice a day".
    Returns (quantity, dosage_frequency_string, duration_was_detected).

    Logic:
      1. Parse duration from message
      2. Parse explicit frequency from message (e.g. "twice a day")
      3. If no explicit frequency, look up patient's known dosage_frequency from order_history
      4. If still not found, use medicine-type default frequency
      5. quantity = duration_days x daily_frequency
    """
    msg = user_message.lower()

    # ── 1. Parse duration ─────────────────────────────────────────────────────
    duration_days = None
    duration_patterns = [
        (r'for\s+(\d+)\s*(day|days|week|weeks|month|months)', True),
        (r'(\d+)\s*(day|days|week|weeks|month|months)\s+(?:supply|course|treatment)', True),
        (r'(\d+)[- ](day|days)(?:\s+course|\s+supply|\s+treatment)?', True),
    ]
    unit_map = {"day": 1, "days": 1, "week": 7, "weeks": 7, "month": 30, "months": 30}

    for pattern, _ in duration_patterns:
        m = re.search(pattern, msg)
        if m:
            n, unit = int(m.group(1)), m.group(2)
            duration_days = n * unit_map.get(unit, 1)
            break

    if not duration_days:
        m = re.search(r'for\s+a\s+(day|week|month)', msg)
        if m:
            duration_days = {"day": 1, "week": 7, "month": 30}[m.group(1)]

    if not duration_days:
        return 1, "", False

    # ── 2. Parse explicit frequency from message ──────────────────────────────
    freq = None
    dosage_str = ""

    freq_patterns = [
        (r'(\d+)\s*times?\s*(?:a|per)\s*day',                              lambda x: int(x.group(1))),
        (r'(\d+)\s*times?\s*daily',                                         lambda x: int(x.group(1))),
        (r'(\d+)x\s*(?:daily|a\s*day)',                                     lambda x: int(x.group(1))),
        (r'twice\s*(?:a\s*)?day|twice\s*daily',                            lambda x: 2),
        (r'three\s*times?\s*(?:a\s*)?day|thrice\s*daily',                  lambda x: 3),
        (r'four\s*times?\s*(?:a\s*)?day',                                  lambda x: 4),
        (r'every\s*(\d+)\s*hours?',                                        lambda x: max(1, round(24 / int(x.group(1))))),
        (r'(\d+)\s*(?:tablet|capsule|pill|drop)s?\s*(?:a|per|each)\s*day', lambda x: int(x.group(1))),
        (r'once\s*(?:a\s*)?day|once\s*daily',                              lambda x: 1),
    ]
    for pat, extractor in freq_patterns:
        match = re.search(pat, msg)
        if match:
            freq = extractor(match)
            break

    # ── 3. Look up known dosage from order_history ────────────────────────────
    if freq is None and patient_id and medicine_name:
        try:
            from core.database import supabase as _sb
            hist = (
                _sb.table("order_history")
                .select("dosage_frequency")
                .eq("patient_id", patient_id.upper())
                .ilike("medicine_name", f"%{medicine_name.split()[0]}%")
                .order("purchase_date", desc=True)
                .limit(1)
                .execute()
            )
            if hist.data:
                stored = hist.data[0].get("dosage_frequency") or ""
                if stored:
                    freq = _parse_freq_from_string(stored)
                    dosage_str = stored
        except Exception:
            pass

    # ── 4. Fallback to medicine-type default ──────────────────────────────────
    if freq is None and medicine_name:
        freq = _get_default_dosage_for_medicine(medicine_name)
        if not dosage_str:
            dosage_str = {1: "Once daily", 2: "Twice daily",
                          3: "Three times daily", 4: "Four times daily"}.get(freq, f"{freq} times daily")

    # ── 5. Also check original message for medicine type keywords ─────────────
    if freq is None:
        freq = _get_default_dosage_for_medicine(user_message.lower())
        if freq > 1 and not dosage_str:
            dosage_str = {1: "Once daily", 2: "Twice daily",
                          3: "Three times daily", 4: "Four times daily"}.get(freq, f"{freq} times daily")

    if freq is None:
        freq = 1

    if not dosage_str:
        dosage_str = {1: "Once daily", 2: "Twice daily",
                      3: "Three times daily", 4: "Four times daily"}.get(freq, f"{freq} times daily")

    qty = max(1, min(duration_days * freq, 200))
    return qty, dosage_str, True


def _extract_per_medicine_quantities(user_message: str, medicines: list) -> dict:
    msg    = user_message.lower()
    result = {}

    for med in medicines:
        anchor    = med.lower().split()[0]
        anchor_re = re.escape(anchor)

        m = re.search(
            rf'(\d+)\s*(?:pack|packs|packet|packets|box|boxes|bottle|bottles|'
            rf'strip|strips|tablet|tablets|capsule|capsules)?\s*(?:of\s+)?({anchor_re})',
            msg,
        )
        if m:
            qty = int(m.group(1))
            if 0 < qty <= 100:
                result[med] = qty
                continue

        m2 = re.search(rf'{anchor_re}[^\d]*(\d+)', msg)
        if m2:
            qty = int(m2.group(1))
            if 0 < qty <= 100:
                result[med] = qty
                continue

    global_qty = _extract_quantity_from_message(user_message)
    for med in medicines:
        if med not in result:
            result[med] = global_qty

    return result


# ── Safety notes for specific medicine + condition combinations ─────────────
MEDICINE_CONDITION_SAFETY = {
    ("mucosolvan", "diabet"):   "Mucosolvan (ambroxol) syrup formulations often contain sugar — diabetics should choose the **sugar-free tablet or capsule form** (Mucosolvan 30mg tablets are sugar-free). Always check the label.",
    ("mucosolvan", "sugar"):    "Mucosolvan syrup contains sugar. The **tablet form (30mg)** is sugar-free and suitable for diabetics.",
    ("ibuprofen",  "diabet"):   "Ibuprofen is generally safe short-term for diabetics, but it can affect kidney function and interact with some diabetes medications. Use the lowest effective dose and consult your doctor if unsure.",
    ("aspirin",    "diabet"):   "Low-dose aspirin is often prescribed for diabetics with heart risk. High-dose aspirin can affect blood sugar. Consult your doctor before use.",
    ("paracetamol","diabet"):   "Paracetamol (acetaminophen) is the **safest OTC painkiller/fever reducer for diabetics** — it does not affect blood sugar at standard doses.",
    ("cetirizin",  "diabet"):   "Cetirizine antihistamines are generally safe for diabetics. Prefer sugar-free formulations if available.",
    ("ibuprofen",  "kidney"):   "Ibuprofen is NOT recommended for people with kidney disease — it reduces blood flow to the kidneys. Paracetamol is a safer alternative.",
    ("ibuprofen",  "heart"):    "Ibuprofen is not recommended for people with heart conditions — it can cause fluid retention and raise blood pressure. Ask your doctor.",
    ("ibuprofen",  "asthma"):   "Ibuprofen can trigger bronchospasm in aspirin-sensitive asthmatics. Use paracetamol instead and consult your doctor.",
    ("ibuprofen",  "pregnan"):  "Ibuprofen is NOT safe in the 3rd trimester of pregnancy. Paracetamol is the recommended alternative.",
    ("ibuprofen",  "stomach"):  "Ibuprofen can irritate the stomach lining and worsen ulcers. Paracetamol is a safer choice for people with stomach issues.",
}


def _build_general_info_response(
    complaint_label: str,
    complaint_lower: str,
    user_message:    str = "",
) -> str:
    user_lower = user_message.lower() if user_message else complaint_lower

    for (medicine_kw, condition_kw), safety_note in MEDICINE_CONDITION_SAFETY.items():
        if medicine_kw in user_lower and condition_kw in user_lower:
            return (
                f"Great question! Here's what you should know:\n\n"
                f"💊 **{medicine_kw.capitalize()} + {condition_kw}:** {safety_note}\n\n"
                f"⚠️ I'm a pharmacy ordering assistant, not a doctor — this is general "
                f"information only. Please consult your doctor or pharmacist before starting "
                f"any new medicine, especially with an existing condition.\n\n"
                f"📋 If your doctor has already prescribed something, you can upload your "
                f"prescription here and I'll arrange delivery.\n\n"
                f"Would you like to order a specific medicine, or do you have more questions? 😊"
            )

    otc_examples = ""
    for kw, examples in GENERAL_INFO_EXAMPLES.items():
        if kw in complaint_lower:
            otc_examples = examples
            break

    if otc_examples:
        examples_block = (
            "\n\n💊 Common OTC options for " + complaint_label + ":\n"
            + otc_examples + "\n"
        )
    else:
        examples_block = ""

    return (
        "Hi! I'm a pharmacy ordering assistant — I'm not a doctor and cannot give "
        "medical advice or recommend specific medicines for " + complaint_label + ".\n\n"
        + complaint_label.capitalize()
        + " can have different causes, so the safest step is always to consult a qualified "
        "doctor or visit a clinic — especially if symptoms are severe, frequent, or come "
        "with other signs."
        + examples_block + "\n"
        "⚠️ Always read the label for dosage and warnings. Some medicines are not suitable "
        "for people with stomach, kidney, liver, or heart conditions, or during pregnancy.\n\n"
        "📋 If you already have a doctor's prescription, feel free to upload it here — "
        "I can verify the medicines and arrange delivery.\n\n"
        "How else can I help you today? 😊"
    )


def _build_inline_qa(user_message: str, product_details: dict) -> str:
    """
    Detect and answer secondary product/safety questions embedded in an order message.
    e.g. "I need to order Cromo Augentropfen. How long will 20 units last? Safe with contacts?"
    Returns a formatted answer block, or "" if no inline questions detected.
    """
    msg = user_message.lower()
    answers = []

    # ── Supply duration: "how long will a pack of 20 last?" ──────────────────
    has_duration_q = (
        ("how long" in msg and "last" in msg)
        or "how long will" in msg
        or "how many days will" in msg
        or "how many days does" in msg
    )
    if has_duration_q:
        pm = re.search(r'pack\s+of\s+(\d+)|(\d+)\s*(?:units?|doses?|single|drops?|ml)', msg)
        pack_units = int(pm.group(1) or pm.group(2)) if pm else None

        # Also try to get pack size from product details
        if not pack_units and product_details:
            pkg = product_details.get("package_size", "") or ""
            pm2 = re.search(r'(\d+)', pkg)
            if pm2:
                pack_units = int(pm2.group(1))

        if pack_units:
            freq_il  = 1
            drops_il = 1
            eyes_il  = 1
            drop_m = re.search(r'(\d+)\s*drop', msg)
            if drop_m:
                drops_il = int(drop_m.group(1))
            if "each eye" in msg or "both eyes" in msg:
                eyes_il = 2
            freq_m = re.search(r'(\d+)\s*times?\s*(?:a\s*)?day', msg)
            if freq_m:
                freq_il = int(freq_m.group(1))
            elif "four times" in msg:
                freq_il = 4
            elif "three times" in msg:
                freq_il = 3
            elif "twice" in msg:
                freq_il = 2
            daily = drops_il * eyes_il * freq_il
            if daily > 0:
                days_lasts = pack_units // daily
                answers.append(
                    f"📦 **Supply duration:** A pack of {pack_units} units "
                    f"({drops_il} drop × {eyes_il} eye(s) × {freq_il}×/day = {daily}/day) "
                    f"→ lasts approximately **{days_lasts} day(s)**."
                )
        else:
            answers.append(
                "📦 **Supply duration:** Please let me know the pack size (number of units) "
                "and your daily usage so I can calculate exactly how long it will last."
            )

    # ── Contact lens safety ───────────────────────────────────────────────────
    if "contact lens" in msg or "contact lense" in msg or "contacts" in msg:
        answers.append(
            "👁️ **Contact lenses:** Single-dose preservative-free eye drops are generally "
            "compatible with contact lenses. As a precaution, remove your lenses before "
            "applying drops and wait at least 15 minutes before reinserting. "
            "Always check the product leaflet to confirm the drops are preservative-free."
        )

    if not answers:
        return ""

    return "\n\n".join(answers) + "\n\n---\n\n"


def _calculate_supply_runout(user_message: str) -> str:
    from datetime import datetime, timedelta

    msg = user_message.lower()

    freq = 1
    freq_patterns = [
        r'(\d+)\s*(?:pill|tablet|capsule|tab|cap)s?\s*(?:a|per)\s*day',
        r'(?:taking|take|takes)\s+(\d+)\s*(?:pill|tablet|capsule|tab|cap)',
        r'(\d+)\s*(?:pill|tablet|capsule|tab|cap)s?\s*daily',
        r'(\d+)x\s*(?:daily|a\s*day)',
    ]
    for pat in freq_patterns:
        m = re.search(pat, msg)
        if m:
            try:
                freq = int(m.group(1))
            except (IndexError, ValueError):
                freq = 1
            break
    if "one pill a day" in msg or "one tablet a day" in msg or "one capsule a day" in msg:
        freq = 1

    supply_count = None
    supply_patterns = [
        r'(?:have|got|bought|purchased)\s+(\d+)\s*(?:pill|tablet|capsule|tab|cap)',
        r'(\d+)\s*(?:pill|tablet|capsule|tab|cap)s?\s*(?:left|remaining|in\s*stock)',
        r'supply\s+of\s+(\d+)',
        r'(\d+)\s*(?:day|days)\s+supply',
        r'(\d+)\s*(?:strip|pack|box)',
    ]
    for pat in supply_patterns:
        m = re.search(pat, msg)
        if m:
            supply_count = int(m.group(1))
            break

    start_date = None
    current_year = datetime.now().year

    month_names = {
        "january": 1, "february": 2, "march": 3, "april": 4,
        "may": 5, "june": 6, "july": 7, "august": 8,
        "september": 9, "october": 10, "november": 11, "december": 12,
        "jan": 1, "feb": 2, "mar": 3, "apr": 4, "jun": 6,
        "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
    }
    date_patterns = [
        r'(january|february|march|april|may|june|july|august|september|october|november|december|'
        r'jan|feb|mar|apr|jun|jul|aug|sep|oct|nov|dec)\s+(\d{1,2})(?:st|nd|rd|th)?',
        r'(\d{1,2})(?:st|nd|rd|th)?\s+(january|february|march|april|may|june|july|august|'
        r'september|october|november|december|jan|feb|mar|apr|jun|jul|aug|sep|oct|nov|dec)',
    ]
    for pat in date_patterns:
        m = re.search(pat, msg)
        if m:
            try:
                g1, g2 = m.group(1), m.group(2)
                if g1.isdigit():
                    day, month_str = int(g1), g2
                else:
                    month_str, day = g1, int(g2)
                month_num = month_names.get(month_str.lower())
                if month_num:
                    start_date = datetime(current_year, month_num, day)
                    if (start_date - datetime.now()).days > 30:
                        start_date = datetime(current_year - 1, month_num, day)
                break
            except Exception:
                pass

    if not start_date:
        m = re.search(r'(\d+)\s*(day|week|month)s?\s*ago', msg)
        if m:
            n, unit = int(m.group(1)), m.group(2)
            delta = {"day": 1, "week": 7, "month": 30}.get(unit, 1)
            from datetime import timedelta
            start_date = datetime.now() - timedelta(days=n * delta)

    if start_date and supply_count:
        days_left_from_start = supply_count // freq
        from datetime import timedelta
        runout_date = start_date + timedelta(days=days_left_from_start)
        days_from_now = (runout_date - datetime.now()).days
        if days_from_now < 0:
            timing = f"**already ran out** {abs(days_from_now)} days ago (on {runout_date.strftime('%B %d')})"
        elif days_from_now == 0:
            timing = "**running out today**"
        elif days_from_now <= 3:
            timing = f"running out **very soon — in {days_from_now} day(s)** (on {runout_date.strftime('%B %d')})"
        else:
            timing = f"running out on **{runout_date.strftime('%B %d')}** ({days_from_now} days from now)"
        return (
            f"Starting from {start_date.strftime('%B %d')} with {supply_count} tablets "
            f"at {freq}/day, your supply is {timing}."
        )

    elif start_date and not supply_count:
        from datetime import timedelta
        days_elapsed = (datetime.now() - start_date).days
        tablets_used = days_elapsed * freq
        assumed_qty  = 10
        assumed_note = "assuming a standard 10-tablet pack"
        tablets_left = max(0, assumed_qty - tablets_used)
        if tablets_left <= 0:
            runout_str = f"already run out (you've used {tablets_used} of {assumed_qty} tablets)"
            reorder_urgency = "You should reorder immediately."
        else:
            runout_date  = datetime.now() + timedelta(days=tablets_left // freq)
            days_to_run  = tablets_left // freq
            runout_str   = (
                f"running out in **{days_to_run} {'day' if days_to_run == 1 else 'days'}** "
                f"(around **{runout_date.strftime('%B %d')}**)"
            )
            if days_to_run <= 3:
                reorder_urgency = "⚠️ You should reorder very soon!"
            elif days_to_run <= 7:
                reorder_urgency = "You should reorder this week."
            else:
                reorder_urgency = ""
        return (
            f"You started on {start_date.strftime('%B %d')} taking {freq}/day — "
            f"that's {days_elapsed} {'day' if days_elapsed == 1 else 'days'} elapsed. "
            f"Based on a standard pack ({assumed_qty} tablets, {assumed_note}), "
            f"your supply is {runout_str}. {reorder_urgency}"
        )

    elif supply_count and not start_date:
        from datetime import timedelta
        days_remaining = supply_count // freq
        runout_date = datetime.now() + timedelta(days=days_remaining)
        return (
            f"With {supply_count} tablets at {freq}/day, your supply will last "
            f"**{days_remaining} more days**, running out around "
            f"**{runout_date.strftime('%B %d')}**."
        )

    return ""


# ── Main agent ────────────────────────────────────────────────────────────────

def conversational_agent(state: AgentState) -> AgentState:
    user_message         = state.get("user_message", "")
    conversation_history = state.get("conversation_history") or []
    products             = _fetch_products()

    # ── PRE-STEP: Resolve numeric/ordinal/name product selection ─────────────
    pending_options = state.get("pending_product_options") or []
    if pending_options:
        is_multi, indices = _is_multi_selection(user_message)
        if is_multi:
            if not indices:
                indices = list(range(len(pending_options)))

            if all(0 <= i < len(pending_options) for i in indices):
                selected_products = [pending_options[i] for i in indices]
                extracted_qty     = _extract_quantity_from_message(user_message)
                if extracted_qty > 1:
                    state["extracted_quantity"] = extracted_qty

                if len(selected_products) == 1:
                    sp = selected_products[0]
                    state["product_id"]              = sp["id"]
                    state["product_name"]            = sp["name"]
                    state["prescription_required"]   = sp.get("prescription_required", False)
                    state["extracted_medicine"]      = [sp["name"]]
                    state["extracted_quantity"]      = state.get("extracted_quantity") or 1
                    state["user_requested_medicine"] = sp["name"]
                else:
                    state["product_id"]              = None
                    state["product_name"]            = ", ".join(p["name"] for p in selected_products)
                    state["prescription_required"]   = any(
                        p.get("prescription_required", False) for p in selected_products
                    )
                    state["extracted_medicine"]      = [p["name"] for p in selected_products]
                    state["extracted_quantity"]      = state.get("extracted_quantity") or 1
                    state["user_requested_medicine"] = ", ".join(p["name"] for p in selected_products)

                state["clarification_needed"]    = False
                state["pending_product_options"] = None
                state["order_status"]            = "approved"
                log_agent_step(state=state, agent="ConversationalAgent",
                               action="MULTI_PRODUCT_SELECTION_RESOLVED",
                               details={"products": [p["name"] for p in selected_products],
                                        "selection": indices})
                return state
            else:
                reply = (
                    f"Sorry, that's not a valid selection. "
                    f"Please select valid number(s) between 1 and {len(pending_options)}."
                )
                state["clarification_needed"]   = True
                state["clarification_question"] = reply
                state["order_status"]           = "needs_clarification"
                state["final_response"]         = reply
                return state

        is_selection, selected_index = _is_selection_response(user_message)
        if is_selection:
            if 0 <= selected_index < len(pending_options):
                sp = pending_options[selected_index]
                state["product_id"]              = sp["id"]
                state["product_name"]            = sp["name"]
                state["prescription_required"]   = sp.get("prescription_required", False)
                state["extracted_medicine"]      = [sp["name"]]
                state["extracted_quantity"]      = state.get("extracted_quantity") or 1
                state["user_requested_medicine"] = sp["name"]
                state["clarification_needed"]    = False
                state["pending_product_options"] = None
                log_agent_step(state=state, agent="ConversationalAgent",
                               action="PRODUCT_SELECTION_RESOLVED",
                               details={"product": sp["name"], "selection": selected_index + 1})
                return state
            else:
                reply = (
                    f"Sorry, that's not a valid option. "
                    f"Please select a number between 1 and {len(pending_options)}."
                )
                state["clarification_needed"]   = True
                state["clarification_question"] = reply
                state["order_status"]           = "needs_clarification"
                state["final_response"]         = reply
                return state

        # Name-based selection
        msg_lower_sel = user_message.strip().lower()
        name_match_idx = None
        for idx, opt in enumerate(pending_options):
            opt_lower  = opt.get("name", "").lower()
            user_words = [w for w in re.split(r"[\s\-.,]+", msg_lower_sel) if len(w) > 2]
            if any(w in opt_lower for w in user_words):
                name_match_idx = idx
                break

        if name_match_idx is not None:
            sp = pending_options[name_match_idx]
            state["product_id"]              = sp["id"]
            state["product_name"]            = sp["name"]
            state["prescription_required"]   = sp.get("prescription_required", False)
            state["extracted_medicine"]      = [sp["name"]]
            state["extracted_quantity"]      = state.get("extracted_quantity") or 1
            state["user_requested_medicine"] = sp["name"]
            state["clarification_needed"]    = False
            state["pending_product_options"] = None
            log_agent_step(state=state, agent="ConversationalAgent",
                           action="PRODUCT_SELECTION_RESOLVED_BY_NAME",
                           details={"product": sp["name"], "user_said": user_message})
            return state

    existing_complaint = state.get("primary_complaint") or ""
    existing_stomach   = state.get("stomach_sensitive") or False

    log_agent_step(state=state, agent="ConversationalAgent", action="START",
                   details={"user_message": user_message,
                            "existing_complaint": existing_complaint,
                            "history_turns": len(conversation_history)})

    existing_suggestion = (state.get("triage_suggestion") or "").strip()
    last_assistant      = next(
        (t.get("content", "") for t in reversed(conversation_history)
         if t.get("role") == "assistant"),
        "",
    )
    if "Order approved" in last_assistant or "will be prepared for you" in last_assistant:
        existing_suggestion = ""
        state["triage_suggestion"]       = None
        state["extracted_medicine"]      = None
        state["product_id"]              = None
        state["product_name"]            = None
        state["pending_product_options"] = None

    suggestion_hint = (
        f"\nPENDING SUGGESTION: The assistant previously suggested '{existing_suggestion}' "
        f"and asked if the user wants to order it."
        if existing_suggestion else ""
    )

    # ── STEP 1: Classify intent ───────────────────────────────────────────────
    try:
        cls_resp = llm.invoke([
            SystemMessage(content=CLASSIFIER_SYSTEM),
            HumanMessage(content=(
                f"Conversation history summary: "
                f"{_build_triage_context(conversation_history, '')}"
                f"{suggestion_hint}\n\nLatest message: \"{user_message}\""
            )),
        ])
        raw_cls = _extract_json(cls_resp.content.strip())
        cls     = json.loads(raw_cls)
    except Exception as e:
        log_agent_step(state=state, agent="ConversationalAgent", action="CLASSIFIER_ERROR",
                       details={"error": str(e)})
        cls = {"intent": "TRIAGE", "primary_complaint": existing_complaint,
               "stomach_sensitive": False, "user_is_confirming": False}

    intent             = cls.get("intent", "TRIAGE")
    new_complaint      = cls.get("primary_complaint") or existing_complaint
    stomach_flag       = cls.get("stomach_sensitive", False) or existing_stomach
    medicine_mentioned = (cls.get("medicine_mentioned") or "").strip()
    order_qty          = cls.get("quantity") or 1
    is_confirming      = cls.get("user_is_confirming", False)

    # ── CRITICAL RULE 0: Explicit order intent + named medicine = ORDER always ─
    # Override mis-classification (e.g. GENERAL_INFO) when user clearly says
    # "I need to order X", "I want to buy X" even if message also contains
    # product/safety questions. Those are answered inline.
    EXPLICIT_ORDER_PHRASES = [
        "i need to order", "i want to order", "can i order", "i'd like to order",
        "i want to buy", "please order", "i need to buy",
    ]
    msg_lower_rule0 = user_message.lower()
    if (
        intent in ("GENERAL_INFO", "TRIAGE", "PRODUCT_QUERY")
        and medicine_mentioned
        and any(phrase in msg_lower_rule0 for phrase in EXPLICIT_ORDER_PHRASES)
    ):
        intent = "ORDER"
        log_agent_step(state=state, agent="ConversationalAgent",
                       action="INTENT_OVERRIDE_EXPLICIT_ORDER",
                       details={"original_intent": cls.get("intent"), "medicine": medicine_mentioned})

    # ── Duration-based quantity override ─────────────────────────────────────
    extracted_med_for_duration = medicine_mentioned
    if not extracted_med_for_duration:
        msg_for_med = user_message.lower()
        for dur_pat in [r'for\s+\d+\s*day', r'for\s+a\s+day', r'for\s+\d+\s*week', r'for\s+\d+\s*month']:
            msg_for_med = re.sub(dur_pat, '', msg_for_med)
        for kw in ['order', 'get', 'buy', 'need', 'want', 'please', 'i ', 'my']:
            msg_for_med = msg_for_med.replace(kw, '')
        extracted_med_for_duration = msg_for_med.strip().strip('.,!?')

    _duration_qty, _duration_dosage, _duration_detected = _extract_duration_based_quantity(
        user_message,
        patient_id=state.get("patient_id"),
        medicine_name=extracted_med_for_duration or None,
    )
    if _duration_detected:
        order_qty = _duration_qty
        if _duration_dosage and not state.get("extracted_dosage"):
            state["extracted_dosage"] = _duration_dosage

    # ── Pack-size number guard ────────────────────────────────────────────────
    # If the user says "a pack of 20 units" or "how long will 20 units last",
    # the classifier may extract quantity=20 thinking it's an order quantity.
    # Detect this pattern and reset order_qty to 1 (they want 1 pack, not 20).
    _msg_lower_qty = user_message.lower()
    _pack_size_patterns = [
        r'pack\s+of\s+(\d+)\s*(?:units?|doses?|ml|drops?|single)',
        r'(\d+)\s*(?:units?|doses?|single\s*dose)\s+(?:last|will\s+last|how\s+long)',
        r'how\s+long\s+(?:will\s+)?(?:a\s+)?pack\s+of\s+(\d+)',
        r'(\d+)\s*(?:unit|dose)\s+pack',
    ]
    for _pat in _pack_size_patterns:
        _pm = re.search(_pat, _msg_lower_qty)
        if _pm:
            _pack_num = int(_pm.group(1))
            if order_qty == _pack_num:
                # The quantity the classifier extracted IS the pack size number —
                # user is describing pack contents, not ordering that many units.
                order_qty = 1
                log_agent_step(state=state, agent="ConversationalAgent",
                               action="PACK_SIZE_QTY_RESET",
                               details={"pack_size_in_msg": _pack_num, "reset_to": 1})
            break

    # ── COMPLAINT SWITCH DETECTION ───────────────────────────────────────────
    ABANDON_PHRASES = [
        "forget about", "forget it", "ignore that", "never mind", "don't worry about",
        "skip that", "cancel that", "leave it", "drop it", "nope i want", "no i want",
        "no i need", "instead order", "just order", "just get me",
    ]
    msg_lower_check = user_message.lower()
    user_is_switching = (
        any(phrase in msg_lower_check for phrase in ABANDON_PHRASES)
        and medicine_mentioned
        and medicine_mentioned.lower() not in (existing_complaint or "").lower()
    )
    if user_is_switching:
        new_complaint = None
        state["primary_complaint"]  = None
        state["triage_suggestion"]  = None
        state["extracted_medicine"] = None
        state["product_id"]         = None
        state["product_name"]       = None
        intent = "ORDER"
        log_agent_step(state=state, agent="ConversationalAgent",
                       action="COMPLAINT_SWITCH_DETECTED",
                       details={"abandoned": existing_complaint, "new_product": medicine_mentioned})

    BODY_PART_HINTS = ["for my skin", "for my hair", "for my eyes", "for my stomach",
                       "for my back", "for my knee", "for my face", "for my hands"]
    if any(hint in msg_lower_check for hint in BODY_PART_HINTS) and medicine_mentioned:
        new_complaint = None
        state["primary_complaint"] = None
        state["triage_suggestion"] = None
        intent = "ORDER"
        log_agent_step(state=state, agent="ConversationalAgent",
                       action="BODY_PART_SWITCH_DETECTED",
                       details={"new_product": medicine_mentioned})

    # ── NEGATIVE RESPONSE OVERRIDE ───────────────────────────────────────────
    if _is_negative_response(user_message):
        intent = "CONVERSATION"
        log_agent_step(state=state, agent="ConversationalAgent",
                       action="NEGATIVE_RESPONSE_DETECTED",
                       details={"user_message": user_message})

    # ── EMERGENCY FAST PATH ───────────────────────────────────────────────────
    EMERGENCY_PHRASES = [
        "can't breathe", "cannot breathe", "chest pain", "heart attack",
        "choking", "anaphylaxis", "allergic reaction", "passed out", "fainted",
        "seizure", "stroke", "severe bleeding", "overdose", "i'm dying",
        "suicidal", "want to die", "kill myself", "can't move", "unconscious",
        "difficulty breathing", "breathing difficulty", "not breathing",
        "throat closing", "swelling throat",
    ]
    is_emergency = intent == "EMERGENCY" or any(
        phrase in user_message.lower() for phrase in EMERGENCY_PHRASES
    )
    if is_emergency:
        state["triage_suggestion"]       = None
        state["extracted_medicine"]      = None
        state["product_id"]              = None
        state["pending_product_options"] = None
        emergency_response = (
            "This sounds like a medical emergency. Please call emergency services (112 / 911) "
            "or have someone take you to the nearest emergency room immediately.\n\n"
            "While waiting for help:\n"
            "- Stay calm and sit upright\n"
            "- Use your inhaler or EpiPen if available\n"
            "- Loosen any tight clothing around your neck or chest\n"
            "- Do not eat or drink anything\n"
            "- Keep someone with you\n\n"
            "Please seek emergency care now. I can help with pharmacy orders once you are safe."
        )
        state["clarification_needed"]   = True
        state["clarification_question"] = emergency_response
        state["order_status"]           = "needs_clarification"
        state["final_response"]         = emergency_response
        log_agent_step(state=state, agent="ConversationalAgent", action="EMERGENCY_DETECTED",
                       details={"message": user_message[:100]})
        return state

    # ── GENERAL INFO HANDLING ─────────────────────────────────────────────────
    if intent == "GENERAL_INFO":
        complaint_lower = (new_complaint or user_message).lower()
        complaint_label = new_complaint or "your condition"
        response        = _build_general_info_response(complaint_label, complaint_lower, user_message)
        state["clarification_needed"]   = True
        state["clarification_question"] = response
        state["order_status"]           = "needs_clarification"
        state["final_response"]         = response
        state["primary_complaint"]      = new_complaint or existing_complaint
        log_agent_step(state=state, agent="ConversationalAgent",
                       action="GENERAL_INFO_RESPONSE",
                       details={"complaint": complaint_label})
        return state

    # ── CONVERSATION HANDLING ─────────────────────────────────────────────────
    if intent == "CONVERSATION":
        user_msg_lower    = user_message.lower().strip()
        conv_suggestion   = (state.get("triage_suggestion") or "").strip()
        delivery_provided = state.get("delivery_info_provided", False)

        if _is_negative_response(user_message):
            response = "No problem! If you need anything in the future, just let me know. Take care!"
            state["clarification_needed"]   = True
            state["clarification_question"] = response
            state["order_status"]           = "needs_clarification"
            state["final_response"]         = response
            log_agent_step(state=state, agent="ConversationalAgent",
                           action="NEGATIVE_RESPONSE_HANDLED",
                           details={"user_message": user_message})
            return state

        if delivery_provided and _is_user_acknowledging(user_message):
            response = "You're welcome! Is there anything else I can help you with?"
            state["clarification_needed"]   = True
            state["clarification_question"] = response
            state["order_status"]           = "needs_clarification"
            state["final_response"]         = response
            state["delivery_info_provided"] = False
            log_agent_step(state=state, agent="ConversationalAgent",
                           action="DELIVERY_ACK_RESPONSE",
                           details={"user_message": user_message})
            return state

        order_prompt = (
            "Would you like to proceed with ordering " + conv_suggestion + "?"
            if conv_suggestion else "Is there anything else I can help you with?"
        )

        conversation_responses = {
            "hi":               "Hello! How can I help you with your pharmacy needs today?",
            "hello":            "Hello! How can I help you with your pharmacy needs today?",
            "hey":              "Hey there! How can I help you with your pharmacy needs today?",
            "good morning":     "Good morning! How can I help you with your pharmacy needs today?",
            "good afternoon":   "Good afternoon! How can I help you with your pharmacy needs today?",
            "good evening":     "Good evening! How can I help you with your pharmacy needs today?",
            "thank you":        "You're welcome! Is there anything else I can help you with?",
            "thanks":           "You're welcome! Is there anything else I can help you with?",
            "thank you so much":"You're very welcome! Is there anything else I can help you with?",
            "many thanks":      "You're very welcome! Is there anything else I can help you with?",
            "thx":              "You're welcome! Is there anything else I can help you with?",
            "ok thanks":        "Great! Is there anything else I can help you with?",
            "sorry":            "No problem at all! Is there anything else I can help you with?",
            "sorry about that": "No worries! Is there anything else I can help you with?",
            "my apologies":     "No worries at all! Is there anything else I can help you with?",
            "ok":               "Sure! " + order_prompt,
            "okay":             "Great! " + order_prompt,
            "alright":          "Alright! Is there anything else I can help you with?",
            "got it":           "Got it! Is there anything else I can help you with?",
            "i see":            "Great! Is there anything else I can help you with?",
            "understood":       "Understood! Is there anything else I can help you with?",
            "sure":             "Sure! " + order_prompt,
            "no problem":       "Great! Is there anything else I can help you with?",
            "bye":              "Goodbye! Take care and feel free to come back anytime!",
            "goodbye":          "Goodbye! Take care and feel free to come back anytime!",
            "see you":          "See you later! Take care!",
            "talk to you later":"Talk to you later! Take care!",
            "have a nice day":  "Thank you, have a nice day too!",
            "have a great day": "Thank you, have a great day too!",
            "how are you":      "I'm doing well, thank you for asking! How can I help you today?",
            "what's up":        "Not much, just here to help with your pharmacy needs! What can I assist you with?",
            "nice":             "Glad you think so! Is there anything I can help you with?",
            "cool":             "Cool! What can I help you with today?",
            "great":            "Great! What can I help you with today?",
            "awesome":          "Awesome! What can I help you with today?",
        }

        response = None
        for key, resp in conversation_responses.items():
            if key in user_msg_lower:
                response = resp
                break
        if not response:
            response = "I understand! Is there anything I can help you with regarding your pharmacy needs?"

        state["clarification_needed"]   = True
        state["clarification_question"] = response
        state["final_response"]         = response
        log_agent_step(state=state, agent="ConversationalAgent", action="CONVERSATION_RESPONSE",
                       details={"user_message": user_message, "response": response[:50]})
        return state

    # ── PRODUCT QUERY HANDLING ───────────────────────────────────────────────
    if intent == "PRODUCT_QUERY":
        msg_lower_pq         = user_message.lower()
        explicit_name_in_msg = None
        if medicine_mentioned:
            ctx_name_lower = (state.get("product_name") or "").lower()
            if medicine_mentioned.lower() not in ctx_name_lower:
                explicit_name_in_msg = medicine_mentioned

        ctx_product_name = (
            explicit_name_in_msg
            or state.get("product_name")
            or state.get("triage_suggestion")
            or state.get("user_requested_medicine")
        )
        ctx_product_id = None if explicit_name_in_msg else state.get("product_id")

        product_details = None
        if ctx_product_id:
            try:
                resp = supabase.table("products").select("*").eq("id", ctx_product_id).single().execute()
                product_details = resp.data
            except Exception:
                pass
        elif ctx_product_name:
            matches = _find_matches(ctx_product_name, products)
            if matches:
                try:
                    resp = supabase.table("products").select("*").eq("id", matches[0]["id"]).single().execute()
                    product_details = resp.data
                except Exception:
                    product_details = matches[0]

        if product_details:
            name         = product_details.get("name", ctx_product_name or "this product")
            price        = product_details.get("price", "N/A")
            stock        = product_details.get("stock_quantity", "N/A")
            description  = product_details.get("description") or ""
            package_size = product_details.get("package_size") or product_details.get("pack_size") or ""
            dosage       = product_details.get("dosage") or product_details.get("dosage_form") or ""
            category     = product_details.get("category") or ""
            ingredients  = product_details.get("ingredients") or product_details.get("composition") or ""
            rx_required  = product_details.get("prescription_required", False)

            msg_lower_rx   = user_message.lower()
            is_rx_question = any(kw in msg_lower_rx for kw in [
                "prescription", "prescri", "otc", "over the counter",
                "doctor", "script", "without prescription", "need a note",
            ])

            if is_rx_question:
                if rx_required:
                    reply = (
                        f"Yes, **{name}** is a **prescription-only medicine** in most regions. "
                        "You will need a valid doctor's prescription to purchase it.\n\n"
                        "📋 You can upload your prescription here — I'll verify it and arrange delivery right away.\n\n"
                        "Would you like to go ahead and place an order once you have your prescription ready?"
                    )
                else:
                    pkg_line = f"\n📦 Package: {package_size}" if package_size else ""
                    reply = (
                        f"No, **{name}** does **not** require a prescription — it is available over the counter (OTC).\n\n"
                        f"💊 Price: €{price} · In stock: {stock} units{pkg_line}\n\n"
                        "Would you like to order it now?"
                    )
            else:
                lines = [f"Here's what I know about {name}:"]
                if package_size:
                    lines.append(f"  Package size: {package_size}")
                if dosage:
                    lines.append(f"  Dosage form: {dosage}")
                if category:
                    lines.append(f"  Category: {category}")
                if description:
                    lines.append(f"  About: {description[:200]}")
                if ingredients:
                    lines.append(f"  Ingredients: {ingredients[:150]}")
                lines.append(f"  Price: €{price}")
                lines.append(f"  Prescription required: {'Yes' if rx_required else 'No'}")
                lines.append(f"  In stock: {stock} units available")
                lines.append(
                    "\nWould you like to go ahead and place this order, "
                    "or do you have any other questions?"
                )
                reply = "\n".join(lines)
        elif ctx_product_name:
            reply = (
                f"I have {ctx_product_name} ready for your order, but I don't have "
                f"detailed product information available in our system right now. "
                f"Would you like to proceed with the order?"
            )
        else:
            reply = (
                "I'm not sure which product you're referring to. "
                "Could you mention the product name so I can help you?"
            )

        state["order_status"]         = state.get("order_status") or "needs_clarification"
        state["clarification_needed"] = False
        state["final_response"]       = reply
        log_agent_step(state=state, agent="ConversationalAgent", action="PRODUCT_QUERY_RESPONSE",
                       details={"product": ctx_product_name, "has_details": product_details is not None})
        return state

    # ── SUPPLY QUERY HANDLING ────────────────────────────────────────────────
    if intent == "SUPPLY_QUERY":
        calc_answer = _calculate_supply_runout(user_message)

        medicine_for_order = medicine_mentioned or existing_suggestion or ""
        order_offer = ""
        if medicine_for_order:
            order_offer = (
                f"\n\nWould you like me to go ahead and place a reorder for "
                f"**{medicine_for_order}** now?"
            )
            state["triage_suggestion"]       = medicine_for_order
            state["user_requested_medicine"] = medicine_for_order

        if calc_answer:
            reply = f"📅 {calc_answer}{order_offer}"
        else:
            reply = (
                "I'd be happy to help calculate when your supply runs out! "
                "Could you tell me:\n"
                "  1. How many tablets/capsules you started with\n"
                "  2. How many you take per day\n"
                "  3. When you started (or how many days ago)\n\n"
                + (f"Once I have that, I can also arrange a reorder of **{medicine_for_order}** for you." if medicine_for_order else "")
            )

        state["order_status"]           = "needs_clarification"
        state["clarification_needed"]   = True
        state["clarification_question"] = reply
        state["final_response"]         = reply
        log_agent_step(state=state, agent="ConversationalAgent",
                       action="SUPPLY_QUERY_RESPONSE",
                       details={"medicine": medicine_for_order, "calc": calc_answer[:80] if calc_answer else "unparsed"})
        return state

    # ── PRICE QUERY HANDLING ─────────────────────────────────────────────────
    if intent == "PRICE_QUERY":
        query_for_price = medicine_mentioned or user_message
        matches         = _find_matches(query_for_price, products)

        if len(matches) == 1:
            reply = _format_price_response(matches[0])
            state["clarification_needed"] = False
            state["order_status"]         = "approved"
            state["final_response"]       = reply
            log_agent_step(state=state, agent="ConversationalAgent", action="PRICE_QUERY_SINGLE",
                           details={"product": matches[0]["name"], "price": matches[0]["price"]})
        elif len(matches) > 1:
            options = "\n".join(
                f"  {i+1}. {p['name']} - EUR{p['price']}" for i, p in enumerate(matches)
            )
            reply = (
                f"I found multiple options for '{query_for_price}':\n{options}\n"
                f"Which one would you like to know more about?"
            )
            state["clarification_needed"]   = True
            state["clarification_question"] = reply
            state["order_status"]           = "needs_clarification"
            state["final_response"]         = reply
            log_agent_step(state=state, agent="ConversationalAgent", action="PRICE_QUERY_MULTIPLE",
                           details={"query": query_for_price, "options_count": len(matches)})
        else:
            reply = (
                f"I couldn't find any products matching '{query_for_price}' "
                f"in our catalogue. Could you check the name?"
            )
            state["clarification_needed"]   = True
            state["clarification_question"] = reply
            state["order_status"]           = "needs_clarification"
            state["final_response"]         = reply
            log_agent_step(state=state, agent="ConversationalAgent", action="PRICE_QUERY_NOT_FOUND",
                           details={"query": query_for_price})
        return state

    # ── Capture raw drug name before substitution ─────────────────────────────
    if medicine_mentioned:
        state["user_requested_medicine"] = medicine_mentioned
    elif not state.get("user_requested_medicine"):
        for kw in ["ibuprofen", "aspirin", "paracetamol", "nurofen", "diclofenac",
                   "voltaren", "naproxen", "codeine", "tramadol"]:
            if kw in user_message.lower():
                state["user_requested_medicine"] = kw
                break

    if new_complaint:
        state["primary_complaint"] = new_complaint
    if stomach_flag:
        state["stomach_sensitive"] = True

    triage_context          = _build_triage_context(conversation_history, user_message)
    state["triage_context"] = triage_context

    log_agent_step(state=state, agent="ConversationalAgent", action="CLASSIFIED",
                   details={"intent": intent, "complaint": new_complaint,
                            "stomach_sensitive": stomach_flag, "confirming": is_confirming,
                            "triage_suggestion": state.get("triage_suggestion")})

    # ── DIRECT ORDER DETECTION ────────────────────────────────────────────────
    is_direct_order = _is_direct_order(user_message, medicine_mentioned)
    is_supplement   = _is_non_prescription_supplement(medicine_mentioned) if medicine_mentioned else False

    if is_direct_order or (is_supplement and intent == "ORDER"):
        state["triage_complete"] = True
        if intent == "TRIAGE":
            intent = "ORDER"
        log_agent_step(state=state, agent="ConversationalAgent", action="DIRECT_ORDER_DETECTED",
                       details={"is_direct_order": is_direct_order, "is_supplement": is_supplement,
                                "medicine_mentioned": medicine_mentioned})

    # ── STEP 2A: TRIAGE ───────────────────────────────────────────────────────
    if intent == "REJECT_SUGGESTION" and medicine_mentioned:
        direct_matches = _find_matches(medicine_mentioned, products)
        if direct_matches:
            is_direct_order = True
            intent = "ORDER"
            log_agent_step(state=state, agent="ConversationalAgent",
                           action="REJECT_SUGGESTION_DIRECT_ORDER",
                           details={"product": medicine_mentioned})

    if not is_direct_order and (
        intent in ("TRIAGE", "REJECT_SUGGESTION")
        or (intent == "ORDER" and not medicine_mentioned and not state.get("triage_suggestion"))
    ):
        if medicine_mentioned:
            direct_matches = _find_matches(medicine_mentioned, products)
            if len(direct_matches) == 1:
                matched = direct_matches[0]
                state["user_requested_medicine"] = medicine_mentioned
                state["product_id"]              = matched["id"]
                state["product_name"]            = matched["name"]
                state["prescription_required"]   = matched.get("prescription_required", False)
                state["extracted_medicine"]      = [matched["name"]]
                state["extracted_quantity"]      = int(order_qty)
                state["clarification_needed"]    = False
                state["triage_suggestion"]       = matched["name"]
                log_agent_step(state=state, agent="ConversationalAgent",
                               action="NAMED_PRODUCT_DIRECT_MATCH",
                               details={"product": matched["name"], "query": medicine_mentioned})
                complaint      = new_complaint or "general condition"
                filtered_prods = _filter_for_complaint(products, complaint, stomach_flag)
                if not any(p["id"] == matched["id"] for p in filtered_prods):
                    filtered_prods = [matched] + filtered_prods
                catalogue = _catalogue_str(filtered_prods)
            elif len(direct_matches) > 1:
                options = "\n".join(f"  {i+1}. {p['name']}" for i, p in enumerate(direct_matches))
                reply   = f"I found a few options matching '{medicine_mentioned}':\n{options}\nWhich would you like?"
                state["pending_product_options"] = direct_matches
                state["clarification_needed"]    = True
                state["clarification_question"]  = reply
                state["order_status"]            = "needs_clarification"
                state["final_response"]          = reply
                state["last_agent_response"]     = reply
                notif = _format_refill_notification(state)
                if notif:
                    state["final_response"]      += notif
                    state["last_agent_response"] += notif
                return state
            else:
                complaint      = new_complaint or "general condition"
                filtered_prods = _filter_for_complaint(products, complaint, stomach_flag)
                catalogue      = _catalogue_str(filtered_prods)
        else:
            complaint      = new_complaint or "general discomfort"
            filtered_prods = _filter_for_complaint(products, complaint, stomach_flag)
            catalogue      = _catalogue_str(filtered_prods)

        history_msgs     = _build_history(conversation_history)
        already_resolved = state.get("product_name") and state.get("product_id")
        resolved_hint    = (
            f"\n\nNOTE: The patient explicitly requested '{medicine_mentioned}' and it IS "
            f"in our catalogue as '{state.get('product_name')}'. Confirm this exact product — "
            f"do NOT suggest an alternative. Set ready_to_order=true, "
            f"recommended_medicine='{state.get('product_name')}'."
        ) if already_resolved and medicine_mentioned else ""

        raw_tri = None
        try:
            tri_resp = llm_creative.invoke([
                SystemMessage(content=TRIAGE_SYSTEM.format(
                    pcomplaint=complaint,
                    tcontext=triage_context,
                    catalogue=catalogue,
                ) + resolved_hint),
                *history_msgs,
                HumanMessage(content=user_message),
            ])
            raw_tri       = _extract_json(tri_resp.content.strip())
            triage_result = json.loads(raw_tri)
        except Exception as e:
            log_agent_step(state=state, agent="ConversationalAgent", action="TRIAGE_ERROR",
                           details={"error": str(e), "raw": raw_tri or ""})
            state["clarification_needed"]   = True
            state["clarification_question"] = "Could you tell me a bit more about your symptoms?"
            state["order_status"]           = "needs_clarification"
            state["final_response"]         = state["clarification_question"]
            return state

        reply           = (triage_result.get("reply") or "").strip()
        ready_to_order  = triage_result.get("ready_to_order", False)
        recommended_med = (triage_result.get("recommended_medicine") or "").strip()
        confidence      = float(triage_result.get("confidence") or 0.0)

        log_agent_step(state=state, agent="ConversationalAgent", action="TRIAGE_RESULT",
                       details={"ready": ready_to_order, "medicine": recommended_med,
                                "confidence": confidence, "reply": reply[:100]})

        if ready_to_order and recommended_med and confidence >= 0.80:
            matches = _find_matches(recommended_med, products)
            if len(matches) == 1:
                state["triage_suggestion"] = matches[0]["name"]
            elif len(matches) > 1:
                options = "\n".join(f"  {i+1}. {p['name']}" for i, p in enumerate(matches))
                reply   = f"I'd suggest one of these:\n{options}\nWhich would you prefer?"
                state["pending_product_options"] = matches
                state["clarification_needed"]    = True
                state["clarification_question"]  = reply
                state["order_status"]            = "needs_clarification"
                state["final_response"]          = reply
                state["last_agent_response"]     = reply
                return state

        last_response = state.get("last_agent_response", "")
        if _is_duplicate_response(reply, last_response):
            reply = random.choice([
                "I understand. Is there anything else I can help you with regarding your order?",
                "Got it! Feel free to ask if you need any other assistance.",
                "Understood! Let me know if there's anything else you need.",
                "Sure thing! Is there anything else I can assist you with?",
            ])

        if _contains_delivery_info(reply):
            state["delivery_info_provided"] = True

        state["clarification_needed"]   = True
        state["clarification_question"] = reply
        state["order_status"]           = "needs_clarification"
        state["final_response"]         = reply
        state["last_agent_response"]    = reply
        return state

    # ── STEP 2B: DIRECT ORDER / CONFIRM_ORDER ─────────────────────────────────
    triage_suggestion = (state.get("triage_suggestion") or "").strip()

    if intent == "CONFIRM_ORDER" and not triage_suggestion and not medicine_mentioned:
        reply = (
            "I'd be happy to help you confirm an order, but I need to know what you'd like "
            "to order. Could you please specify the medicine or product name?"
        )
        state["clarification_needed"]   = True
        state["clarification_question"] = reply
        state["order_status"]           = "needs_clarification"
        state["final_response"]         = reply
        return state

    query = medicine_mentioned or triage_suggestion or user_message
    state["user_requested_medicine"] = medicine_mentioned or triage_suggestion or query

    # ── MULTI-MEDICINE PARSING ────────────────────────────────────────────────
    extracted_medicines = _parse_multiple_medicines(query)

    if len(extracted_medicines) > 1:
        all_matches       = {}
        missing_medicines = []

        for med in extracted_medicines:
            med_matches = _find_matches(med, products)
            if med_matches:
                all_matches[med] = med_matches
            else:
                missing_medicines.append(med)

        state["extracted_medicine"] = extracted_medicines
        per_qty = _extract_per_medicine_quantities(user_message, extracted_medicines)

        auto_resolved = []
        for med in extracted_medicines:
            if med in all_matches and all_matches[med]:
                auto_resolved.append((all_matches[med][0], per_qty.get(med, 1)))

        missing_medicines_final = [
            med for med in extracted_medicines
            if med not in all_matches or not all_matches[med]
        ]

        if len(auto_resolved) == 1 and not missing_medicines_final:
            matched, qty = auto_resolved[0]
            state["product_id"]              = matched["id"]
            state["product_name"]            = matched["name"]
            state["prescription_required"]   = matched.get("prescription_required", False)
            state["extracted_quantity"]      = qty
            state["clarification_needed"]    = False
            state["pending_product_options"] = None
            state["order_status"]            = "approved"
            log_agent_step(state=state, agent="ConversationalAgent",
                           action="MULTI_ORDER_RESOLVED_SINGLE",
                           details={"product": matched["name"], "qty": qty})
            return state

        if len(auto_resolved) >= 2 and not missing_medicines_final:
            products_list = [p for p, _ in auto_resolved]
            qtys_list     = [q for _, q in auto_resolved]

            total_amount = 0.0
            line_items   = []
            try:
                from core.database import supabase as _sb
                for prod, qty in auto_resolved:
                    pr = _sb.table("products").select("price").eq("id", prod["id"]).single().execute()
                    price = float(pr.data.get("price", 0)) if pr.data else 0.0
                    line_total = round(price * qty, 2)
                    total_amount += line_total
                    line_items.append(f"  • {prod['name']} × {qty} — €{line_total:.2f}")
            except Exception:
                for prod, qty in auto_resolved:
                    line_items.append(f"  • {prod['name']} × {qty}")

            summary_lines = "\n".join(line_items)
            total_str     = f"\n\n💰 Total: €{total_amount:.2f}" if total_amount > 0 else ""
            final_resp    = (
                f"Here's your order summary:\n{summary_lines}{total_str}\n\n"
                f"Ready to confirm? Tap Place Order below."
            )

            state["selected_products"]       = products_list
            state["multi_medicine_order"]    = True
            state["multi_quantities"]        = qtys_list
            state["product_id"]              = None
            state["product_name"]            = ", ".join(p["name"] for p in products_list)
            state["prescription_required"]   = any(
                p.get("prescription_required", False) for p in products_list
            )
            state["extracted_quantity"]      = qtys_list[0]
            state["unit_price"]              = None
            state["total_price"]             = round(total_amount, 2) if total_amount else None
            state["clarification_needed"]    = False
            state["pending_product_options"] = None
            state["order_status"]            = "approved"
            state["final_response"]          = final_resp
            state["last_agent_response"]     = final_resp
            log_agent_step(state=state, agent="ConversationalAgent",
                           action="MULTI_ORDER_AUTO_RESOLVED",
                           details={"medicines": extracted_medicines,
                                    "products":  [p["name"] for p in products_list],
                                    "quantities": qtys_list})
            return state

        reply_parts  = []
        all_options  = []
        global_index = 1
        for med in extracted_medicines:
            if med in all_matches:
                matches = all_matches[med]
                if len(matches) == 1:
                    all_options.append(matches[0])
                    reply_parts.append(f"{global_index}. {matches[0]['name']} (qty: {per_qty.get(med, 1)})")
                    global_index += 1
                else:
                    reply_parts.append(f"\nOptions for {med}:")
                    for m in matches:
                        all_options.append(m)
                        reply_parts.append(f"  {global_index}. {m['name']}")
                        global_index += 1
            else:
                reply_parts.append(f"\n⚠️ Could not find '{med}' in our catalogue")

        reply = "I found options for your items:\n" + "\n".join(reply_parts)
        reply += "\n\nWhich number would you like to order?"
        state["pending_product_options"] = all_options
        state["clarification_needed"]    = True
        state["clarification_question"]  = reply
        state["order_status"]            = "needs_clarification"
        state["final_response"]          = reply
        state["last_agent_response"]     = reply
        log_agent_step(state=state, agent="ConversationalAgent", action="MULTI_ORDER_OPTIONS",
                       details={"medicines": extracted_medicines, "options_count": len(all_options)})
        return state

    # ── PRESCRIPTION MEDICINE MATCH ───────────────────────────────────────────
    prescription_uploaded  = state.get("prescription_uploaded", False)
    prescription_medicines = state.get("prescription_medicines") or []
    user_requested         = state.get("user_requested_medicine") or query

    rx_matched_product = None
    if prescription_uploaded and prescription_medicines:
        rx_matched_product = _match_prescription_medicine(
            user_requested, prescription_medicines, products
        )
        if rx_matched_product:
            log_agent_step(state=state, agent="ConversationalAgent",
                           action="PRESCRIPTION_MATCH_FOUND",
                           details={"user_requested": user_requested,
                                    "matched_product": rx_matched_product["name"],
                                    "prescription_medicines": prescription_medicines})

    # ── SINGLE MEDICINE MATCH ─────────────────────────────────────────────────
    matches = _find_matches(query, products)

    # ── Fetch product details for inline Q&A (supply duration, contact lens etc.) ──
    matched_product_details = None
    if rx_matched_product:
        matched_product_details = rx_matched_product
    elif len(matches) == 1:
        matched_product_details = matches[0]

    if rx_matched_product:
        matched = rx_matched_product
        state["product_id"]              = matched["id"]
        state["product_name"]            = matched["name"]
        state["prescription_required"]   = matched.get("prescription_required", False)
        state["extracted_medicine"]      = [matched["name"]]
        state["extracted_quantity"]      = int(order_qty)
        state["clarification_needed"]    = False
        state["pending_product_options"] = None
        state["prescription_uploaded"]   = True

        # Inject inline Q&A answers if user asked secondary questions alongside the order
        inline_prefix = _build_inline_qa(user_message, matched_product_details)
        if inline_prefix:
            state["inline_qa"] = inline_prefix

        log_agent_step(state=state, agent="ConversationalAgent",
                       action="ORDER_RESOLVED_FROM_PRESCRIPTION",
                       details={"product": matched["name"], "qty": order_qty,
                                "prescription_verified": True})
        return state

    elif len(matches) == 1:
        matched = matches[0]
        state["product_id"]              = matched["id"]
        state["product_name"]            = matched["name"]
        state["prescription_required"]   = matched.get("prescription_required", False)
        state["extracted_medicine"]      = [matched["name"]]
        state["extracted_quantity"]      = int(order_qty)
        state["clarification_needed"]    = False
        state["pending_product_options"] = None

        # Inject inline Q&A answers if user asked secondary questions alongside the order
        inline_prefix = _build_inline_qa(user_message, matched_product_details)
        if inline_prefix:
            state["inline_qa"] = inline_prefix

        log_agent_step(state=state, agent="ConversationalAgent", action="ORDER_RESOLVED",
                       details={"product": matched["name"], "qty": order_qty})
        return state

    if len(matches) > 1:
        options = "\n".join(f"  {i+1}. {p['name']}" for i, p in enumerate(matches))
        reply   = f"I found a few options — which one?\n{options}"
        state["pending_product_options"] = matches
    else:
        reply = f"I couldn't find \"{query}\" in our catalogue. Could you check the name?"
        state["pending_product_options"] = None

    if _contains_delivery_info(reply):
        state["delivery_info_provided"] = True

    last_response = state.get("last_agent_response", "")
    if _is_duplicate_response(reply, last_response):
        reply = random.choice([
            "I understand. Is there anything else I can help you with regarding your order?",
            "Got it! Feel free to ask if you need any other assistance.",
            "Understood! Let me know if there's anything else you need.",
            "Sure thing! Is there anything else I can assist you with?",
        ])

    state["clarification_needed"]   = True
    state["clarification_question"] = reply
    state["order_status"]           = "needs_clarification"
    state["final_response"]         = reply
    state["last_agent_response"]    = reply
    return state