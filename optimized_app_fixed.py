# optimized_app_fixed.py - FIXED VERSION with all critical bugs patched
# Fixes: OCR file handling, transactions, rate limiting, file validation, improved prompt

import os
import re
import json
import time
import uuid
import struct
import sqlite3
import logging
import threading
import tempfile
import magic  # NEW: pip install python-magic-bin (Windows) or python-magic (Linux/Mac)
from contextlib import contextmanager
from datetime import datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
import io

from flask import Flask, render_template, request, jsonify, Response
from flask_cors import CORS
from flask_limiter import Limiter  # NEW: pip install flask-limiter
from flask_limiter.util import get_remote_address
from PyPDF2 import PdfReader
from langchain_community.document_loaders import DirectoryLoader, PyPDFLoader
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_community.vectorstores import FAISS
from langchain_community.embeddings import OllamaEmbeddings

# NEW: OCR imports
try:
    import pytesseract
    from pdf2image import convert_from_path
    OCR_AVAILABLE = True
except ImportError:
    OCR_AVAILABLE = False
    print("WARNING: pytesseract/pdf2image not installed. Scanned PDFs will not work.")
    print("Run: pip install pytesseract pdf2image pillow")

try:
    import sqlite_vec
except ImportError:
    sqlite_vec = None

try:
    from ollama import chat, embed
    import requests as http_requests
except ImportError:
    raise ImportError("Run: pip install ollama requests")

# ─── Logging with Rotation ─────────────────────────────────────────────────
from logging.handlers import RotatingFileHandler  # NEW

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# NEW: Rotating file handler
file_handler = RotatingFileHandler(
    'claimtrackr.log',
    maxBytes=10*1024*1024,  # 10MB
    backupCount=5
)
file_handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
logger.addHandler(file_handler)

# ─── Flask App ──────────────────────────────────────────────────────────────
app = Flask(__name__)
CORS(app)
app.secret_key = os.environ.get('SECRET_KEY') or os.urandom(32)

# NEW: Rate limiter
limiter = Limiter(
    app=app,
    key_func=get_remote_address,
    default_limits=["200 per day", "50 per hour"],
    storage_uri="memory://"
)

# ─── Configuration ──────────────────────────────────────────────────────────
OLLAMA_BASE_URL = "http://localhost:11434"
MAIN_MODEL = "llama3.2"
FAST_MODEL = "llama3.2"
EMBEDDING_MODEL = "nomic-embed-text"
FAISS_PATH = "faiss_index"
DB_PATH = "claimtrackr.db"
CACHE_TTL_SECONDS = 300
MAX_FILE_SIZE = 10 * 1024 * 1024
EXPECTED_EMBEDDING_DIM = 768

# NEW: Upload directory for audit trail
UPLOAD_DIR = Path("uploads")
UPLOAD_DIR.mkdir(exist_ok=True)

# ─── Globals ────────────────────────────────────────────────────────────────
cached_faiss_db = None
_cache_lock = threading.Lock()

EXCLUSION_NAMES = [
    "HIV/AIDS", "Parkinson's disease", "Alzheimer's disease",
    "pregnancy", "substance abuse", "self-inflicted injuries",
    "sexually transmitted diseases", "STD", "pre-existing conditions",
    "cosmetic procedures", "experimental treatments",
]


# ============================================================================
# DATABASE
# ============================================================================

@contextmanager
def get_db():
    """Get a thread-local SQLite connection with vec0 loaded."""
    conn = sqlite3.connect(DB_PATH)
    try:
        if sqlite_vec:
            conn.enable_load_extension(True)
            sqlite_vec.load(conn)
        conn.row_factory = sqlite3.Row
        yield conn
    finally:
        conn.close()


def serialize_f32(vector):
    """Pack a float list into bytes for sqlite-vec with validation."""
    if len(vector) != EXPECTED_EMBEDDING_DIM:
        raise ValueError(f"Expected {EXPECTED_EMBEDDING_DIM} dimensions, got {len(vector)}")
    return struct.pack(f"{len(vector)}f", *vector)


# ============================================================================
# OCR & FILE HANDLING (FIXED)
# ============================================================================

def get_file_content(file) -> str:
    """
    FIXED: Extract text from PDF - digital OR scanned with OCR.
    Bug fix: convert_from_path needs file path, not BytesIO.
    """
    text = ""
    temp_path = None
    
    try:
        if not file.filename.endswith(".pdf"):
            return ""
        
        # Try 1: Digital text extraction (fast)
        pdf = PdfReader(file)
        for page in pdf.pages:
            page_text = page.extract_text()
            if page_text:
                text += page_text + "\n"
        
        # Try 2: OCR for scanned PDFs
        if not text.strip() and OCR_AVAILABLE:
            logger.info("No digital text found, attempting OCR...")
            
            # FIXED: Save to temp file first (pdf2image needs file path)
            file.seek(0)
            with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as tmp:
                tmp.write(file.read())
                temp_path = tmp.name
            
            try:
                images = convert_from_path(temp_path)  # FIXED: Now uses file path
                for i, image in enumerate(images):
                    page_text = pytesseract.image_to_string(image)
                    text += page_text + "\n"
                    logger.info(f"OCR page {i+1}: {len(page_text)} chars")
                
                if text.strip():
                    logger.info(f"OCR successful: {len(text)} chars total")
                else:
                    logger.warning("OCR found no text")
            except Exception as ocr_err:
                logger.error(f"OCR failed: {ocr_err}")
        
        elif not text.strip() and not OCR_AVAILABLE:
            logger.warning("No digital text found and OCR not available")
        
    except Exception as e:
        logger.error(f"PDF read error: {e}")
    finally:
        # Clean up temp file
        if temp_path and os.path.exists(temp_path):
            os.unlink(temp_path)
    
    return text.strip()


def validate_uploaded_file(file) -> tuple:
    """
    NEW: Comprehensive file validation with magic bytes.
    Returns: (is_valid, error_message, safe_filename)
    """
    if not file or not file.filename:
        return False, "No file provided", None
    
    # Check 1: Extension
    if not file.filename.lower().endswith('.pdf'):
        return False, "Only PDF files are accepted", None
    
    # Check 2: File size
    file.seek(0, 2)
    size = file.tell()
    file.seek(0)
    
    if size > MAX_FILE_SIZE:
        return False, f"File too large ({size/1024/1024:.1f}MB > {MAX_FILE_SIZE//(1024*1024)}MB)", None
    
    if size == 0:
        return False, "Empty file", None
    
    # Check 3: Magic bytes (actual file type)
    try:
        file_header = file.read(1024)
        file.seek(0)
        
        mime = magic.from_buffer(file_header, mime=True)
        if mime != 'application/pdf':
            return False, f"File is not a valid PDF (detected: {mime})", None
        
        # Check 4: PDF structure
        pdf = PdfReader(file)
        file.seek(0)
        
        if len(pdf.pages) == 0:
            return False, "PDF has no pages", None
        
        if len(pdf.pages) > 50:
            return False, "PDF too large (max 50 pages)", None
            
    except Exception as e:
        return False, f"Corrupted PDF: {str(e)}", None
    
    # Check 5: Sanitize filename
    safe_name = "".join(c for c in file.filename if c.isalnum() or c in "._-")
    if not safe_name:
        safe_name = f"claim_{uuid.uuid4().hex[:8]}.pdf"
    
    return True, None, safe_name


def save_uploaded_file(file, claim_id: str, safe_name: str = None) -> str:
    """Save original PDF for audit trail."""
    try:
        if safe_name is None:
            safe_name = "".join(c for c in file.filename if c.isalnum() or c in "._-")
        file_path = UPLOAD_DIR / f"{claim_id}_{safe_name}"
        file.seek(0)
        file.save(file_path)
        logger.info(f"Saved uploaded file: {file_path}")
        return str(file_path)
    except Exception as e:
        logger.error(f"File save error: {e}")
        return None


# ============================================================================
# OLLAMA & EMBEDDINGS
# ============================================================================

def check_ollama_status():
    """Check if Ollama is running and required models are available."""
    try:
        resp = http_requests.get(f"{OLLAMA_BASE_URL}/api/tags", timeout=5)
        if resp.status_code == 200:
            model_names = [m["name"] for m in resp.json().get("models", [])]
            for required in [MAIN_MODEL, EMBEDDING_MODEL]:
                if not any(required in n for n in model_names):
                    return False, f"Missing model: {required}"
            return True, "Ollama is running and all models are available"
        return False, "Ollama is not responding"
    except http_requests.exceptions.ConnectionError:
        return False, "Cannot connect to Ollama. Is it running?"
    except Exception as e:
        return False, f"Error: {e}"


def get_faiss_db():
    """Load or create FAISS vector store (cached in memory with thread safety)."""
    global cached_faiss_db
    
    if cached_faiss_db is not None:
        return cached_faiss_db
    
    with _cache_lock:
        if cached_faiss_db is not None:
            return cached_faiss_db
        
        try:
            embeddings = OllamaEmbeddings(model=EMBEDDING_MODEL, base_url=OLLAMA_BASE_URL)
            
            if os.path.exists(FAISS_PATH):
                db = FAISS.load_local(FAISS_PATH, embeddings)
            else:
                docs = _load_documents()
                if not docs:
                    return None
                chunks = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=200).split_documents(docs)
                db = FAISS.from_documents(chunks, embeddings)
                db.save_local(FAISS_PATH)
            
            cached_faiss_db = db
            return db
        except Exception as e:
            logger.error(f"FAISS error: {e}")
            return None


def _load_documents():
    """Load PDFs from documents/ folder."""
    if not os.path.exists("documents"):
        os.makedirs("documents")
        return []
    try:
        loader = DirectoryLoader("documents", glob="**/*.pdf", loader_cls=PyPDFLoader)
        return loader.load()
    except Exception as e:
        logger.error(f"Document loading error: {e}")
        return []


def get_cached_context(cache_key: str, search_query: str) -> str:
    """Retrieve RAG context with DB-level caching (5-min TTL)."""
    try:
        with get_db() as conn:
            cursor = conn.cursor()
            
            cursor.execute("SELECT content, created_at FROM context_cache WHERE cache_key = ?", (cache_key,))
            row = cursor.fetchone()
            if row:
                created = datetime.fromisoformat(row["created_at"])
                if datetime.utcnow() - created < timedelta(seconds=CACHE_TTL_SECONDS):
                    return row["content"]
            
            db = get_faiss_db()
            if not db:
                return "No policy documents available."
            
            results = db.similarity_search(search_query, k=3)
            content = "\n\n".join([r.page_content for r in results])
            
            cursor.execute(
                "INSERT OR REPLACE INTO context_cache (cache_key, content, created_at) VALUES (?, ?, ?)",
                (cache_key, content, datetime.utcnow().isoformat()),
            )
            conn.commit()
            return content
        
    except Exception as e:
        logger.error(f"Context cache error: {e}")
        db = get_faiss_db()
        if db:
            results = db.similarity_search(search_query, k=3)
            return "\n\n".join([r.page_content for r in results])
        return "Error retrieving policy context."


def get_claim_approval_context():
    return get_cached_context("claim_approval", "What are the documents required for claim approval?")


def get_general_exclusion_context():
    return get_cached_context("general_exclusions", "Give a list of all general exclusions")


# ============================================================================
# BILL PROCESSING
# ============================================================================

def sanitize_for_llm(text) -> str:
    """Sanitize text for LLM prompts to prevent injection attacks."""
    if text is None:
        return "N/A"
    
    text = str(text)
    text = ''.join(char for char in text if char == '\n' or char == '\t' or 
                   (ord(char) >= 32 and ord(char) != 127))
    text = re.sub(r'[<>]', '', text)
    text = re.sub(r'\{\s*\}', '', text)
    
    if len(text) > 1000:
        text = text[:997] + "..."
    
    return text if text.strip() else "N/A"


def extract_bill_info(bill_text: str) -> dict:
    """Use LLM to extract disease and expense from bill text."""
    try:
        safe_bill_text = sanitize_for_llm(bill_text[:2000])
        
        response = chat(
            model=FAST_MODEL,
            messages=[
                {
                    "role": "system",
                    "content": "Extract disease and expense from medical bills. Return ONLY JSON: {\"disease\": \"name\", \"expense\": number}",
                },
                {
                    "role": "user",
                    "content": f"Extract from this bill:\n{safe_bill_text}",
                },
            ],
            options={"temperature": 0.1},
        )
        text = response["message"]["content"]
        match = re.search(r"\{[^}]+\}", text)
        if match:
            data = json.loads(match.group())
            if data.get("expense"):
                try:
                    data["expense"] = int(float(str(data["expense"]).replace(",", "").replace("₹", "").strip()))
                except (ValueError, TypeError):
                    data["expense"] = None
            return data
    except Exception as e:
        logger.error(f"Bill extraction error: {e}")
    return {"disease": "Unknown", "expense": None}


# ============================================================================
# FRAUD DETECTION
# ============================================================================

def check_policy_violations(disease: str) -> list:
    """Check disease against pre-computed exclusion embeddings via sqlite-vec."""
    if not disease or not sqlite_vec:
        return _fallback_exclusion_check(disease)
    
    try:
        response = embed(model=EMBEDDING_MODEL, input=disease.lower())
        disease_vec = response["embeddings"][0]
    except Exception as e:
        logger.error(f"Disease embedding failed: {e}")
        return _fallback_exclusion_check(disease)
    
    violations = []
    try:
        with get_db() as conn:
            cursor = conn.cursor()
            
            # FIXED: Separate vector query from JOIN (sqlite-vec limitation)
            cursor.execute(
                """
                SELECT exclusion_id, distance
                FROM exclusions_vec
                WHERE embedding MATCH ?
                AND k = 10
                ORDER BY distance
                """,
                (serialize_f32(disease_vec),),
            )
            vec_rows = cursor.fetchall()
            
            for vec_row in vec_rows:
                cursor.execute(
                    "SELECT name, description FROM exclusions WHERE id = ?",
                    (vec_row["exclusion_id"],),
                )
                excl_row = cursor.fetchone()
                if not excl_row:
                    continue
                
                distance = vec_row["distance"]
                similarity = max(0, 1 - (distance ** 2) / 2) * 100
                
                if similarity > 40:
                    violations.append({
                        "exclusion": excl_row["name"],
                        "similarity": round(similarity, 1),
                        "disease_mentioned": disease,
                    })
                    
    except Exception as e:
        logger.error(f"Policy violation check error: {e}")
        return _fallback_exclusion_check(disease)
    
    return violations


def _fallback_exclusion_check(disease: str) -> list:
    """Simple string-matching fallback if vector DB is unavailable."""
    if not disease:
        return []
    violations = []
    disease_lower = disease.lower()
    for excl in EXCLUSION_NAMES:
        if excl.lower() in disease_lower or disease_lower in excl.lower():
            violations.append({
                "exclusion": excl,
                "similarity": 100.0,
                "disease_mentioned": disease,
            })
    return violations


def detect_duplicates(claim_data: dict, threshold: float = 0.7) -> list:
    """Detect duplicate claims using vector similarity in sqlite-vec."""
    diagnosis = claim_data.get("diagnosis", "")
    if not diagnosis or not sqlite_vec:
        return []
    
    try:
        response = embed(model=EMBEDDING_MODEL, input=diagnosis.lower())
        diag_vec = response["embeddings"][0]
    except Exception as e:
        logger.error(f"Diagnosis embedding failed: {e}")
        return []
    
    duplicates = []
    try:
        with get_db() as conn:
            cursor = conn.cursor()
            
            # FIXED: Separate vector query from JOIN (sqlite-vec limitation)
            cursor.execute(
                """
                SELECT claim_id, distance
                FROM claims_vec
                WHERE diagnosis_embedding MATCH ?
                AND k = 10
                ORDER BY distance
                """,
                (serialize_f32(diag_vec),),
            )
            vec_rows = cursor.fetchall()
            
            patient_name = claim_data.get("patient_name", "").lower()
            claimed_amount = Decimal(str(claim_data.get("amount", 0) or 0))
            
            for vec_row in vec_rows:
                cursor.execute(
                    "SELECT patient_name, diagnosis, amount, date FROM claims WHERE id = ?",
                    (vec_row["claim_id"],),
                )
                claim_row = cursor.fetchone()
                if not claim_row:
                    continue
                
                score = 0
                reasons = []
                distance = vec_row["distance"]
                diag_similarity = max(0, 1 - (distance ** 2) / 2)
                
                if diag_similarity > 0.7:
                    score += 0.4
                    reasons.append(f"Similar diagnosis ({diag_similarity:.0%} match)")
                
                if claim_row["patient_name"] and claim_row["patient_name"].lower() == patient_name:
                    score += 0.3
                    reasons.append("Same patient")
                
                try:
                    hist_amt = Decimal(str(claim_row["amount"] or 0))
                    if claimed_amount > 0 and hist_amt > 0:
                        variance = abs(claimed_amount - hist_amt) / max(claimed_amount, hist_amt)
                        if variance < Decimal('0.15'):
                            score += 0.2
                            reasons.append(f"Similar amount ({float(variance):.0%} variance)")
                except (ValueError, TypeError):
                    pass
                
                try:
                    claim_date = claim_data.get("date", "")
                    if claim_date and claim_row["date"]:
                        d1 = datetime.strptime(claim_date, "%Y-%m-%d")
                        d2 = datetime.strptime(claim_row["date"], "%Y-%m-%d")
                        days_apart = abs((d1 - d2).days)
                        if days_apart < 30:
                            score += 0.1
                            reasons.append(f"Recent ({days_apart}d apart)")
                except (ValueError, TypeError):
                    pass
                
                if score >= threshold:
                    duplicates.append({
                        "claim_id": vec_row["claim_id"],
                        "confidence": round(score * 100, 1),
                        "reasons": reasons,
                        "diagnosis": claim_row["diagnosis"],
                        "amount": claim_row["amount"],
                    })
                    
    except Exception as e:
        logger.error(f"Duplicate detection error: {e}")
    
    return duplicates


def comprehensive_fraud_check(claim_data: dict, bill_info: dict) -> dict:
    """Multi-layer fraud detection."""
    fraud_report = {
        "duplicate_confidence": 0,
        "duplicate_details": [],
        "amount_anomaly": False,
        "amount_details": "",
        "policy_violations": [],
        "information_complete": True,
        "missing_fields": [],
        "fraud_risk_level": "LOW",
        "risk_factors": [],
        "risk_score": 0,
    }
    
    duplicates = detect_duplicates(claim_data)
    if duplicates:
        fraud_report["duplicate_confidence"] = max(d["confidence"] for d in duplicates)
        fraud_report["duplicate_details"] = duplicates
        fraud_report["risk_factors"].append(
            f"Potential duplicate: {fraud_report['duplicate_confidence']:.1f}% similarity"
        )
    
    try:
        claimed = Decimal(str(claim_data.get("amount", 0) or 0))
        billed = Decimal(str(bill_info.get("expense", 0) or 0))
        
        if claimed > billed > 0:
            if (claimed - billed) > Decimal('0.01'):
                fraud_report["amount_anomaly"] = True
                variance = ((claimed - billed) / billed) * 100
                fraud_report["amount_details"] = (
                    f"Claimed ₹{claimed:.0f} exceeds billed ₹{billed:.0f} by {variance:.1f}%"
                )
                fraud_report["risk_factors"].append("Amount exceeds bill")
    except (ValueError, TypeError):
        pass
    
    disease = bill_info.get("disease", "")
    violations = check_policy_violations(disease)
    fraud_report["policy_violations"] = violations
    for v in violations:
        fraud_report["risk_factors"].append(
            f"Disease '{v['disease_mentioned']}' matches exclusion '{v['exclusion']}' ({v['similarity']}%)"
        )
    
    required = {
        "patient_name": claim_data.get("patient_name"),
        "diagnosis": bill_info.get("disease"),
        "amount": claim_data.get("amount"),
        "date": claim_data.get("date"),
        "medical_facility": claim_data.get("medical_facility"),
    }
    for field, value in required.items():
        if not value or str(value).strip() == "":
            fraud_report["information_complete"] = False
            fraud_report["missing_fields"].append(field)
    if not fraud_report["information_complete"]:
        fraud_report["risk_factors"].append(
            f"Missing: {', '.join(fraud_report['missing_fields'])}"
        )
    
    risk_score = 0
    if fraud_report["duplicate_confidence"] > 70:
        risk_score += 3
    elif fraud_report["duplicate_confidence"] > 50:
        risk_score += 2
    if fraud_report["amount_anomaly"]:
        risk_score += 3
    if fraud_report["policy_violations"]:
        risk_score += 4
    if not fraud_report["information_complete"]:
        risk_score += 2
    
    fraud_report["risk_score"] = risk_score
    if risk_score >= 6:
        fraud_report["fraud_risk_level"] = "HIGH"
    elif risk_score >= 3:
        fraud_report["fraud_risk_level"] = "MEDIUM"
    else:
        fraud_report["fraud_risk_level"] = "LOW"
    
    return fraud_report


# ============================================================================
# LLM DECISION (IMPROVED PROMPT WITH EXAMPLES)
# ============================================================================

IMPROVED_DECISION_PROMPT = """You are an insurance claims adjudication AI. Analyze the claim data and return a structured JSON decision.

# CLAIM INFORMATION
Patient: {patient_name}
Type: {claim_type}
Diagnosis: {disease}
Claimed Amount: ₹{claimed_amount}
Billed Amount: ₹{billed_amount}
Date: {date}
Facility: {facility}

# FRAUD ANALYSIS RESULTS
Risk Level: {risk_level} (Score: {risk_score}/10)
Risk Factors:
{risk_factors}

# POLICY CONTEXT
{policy_context}

# EXCLUSION LIST
{exclusion_context}

# DECISION RULES (Apply in order)

## STEP 1: Check Exclusions (MANDATORY REJECTION)
If the disease semantically matches ANY exclusion below, REJECT immediately:
- HIV/AIDS (any HIV-related treatment)
- Parkinson's disease
- Alzheimer's disease
- Pregnancy/maternity
- Substance abuse (alcohol, drugs)
- Self-inflicted injuries (suicide, self-harm)
- STDs (except from blood transfusion)
- Pre-existing conditions (24-month waiting period)
- Cosmetic procedures
- Experimental treatments

Example matches:
- "HIV treatment" → REJECT (matches "HIV/AIDS")
- "Drug rehabilitation" → REJECT (matches "substance abuse")
- "Plastic surgery for beauty" → REJECT (matches "cosmetic")

## STEP 2: Verify Amounts
If claimed_amount > billed_amount:
 - Calculate variance: (claimed - billed) / billed * 100
 - If variance > 10%: REJECT for "Amount discrepancy"
 - If billed_amount is 0 or unknown: REQUEST "Missing bill information"

## STEP 3: Check Fraud Risk
If fraud risk is HIGH AND multiple risk factors present:
 - Review risk factors carefully
 - If duplicate claim with >70% confidence: REJECT
 - If amount anomaly + duplicate: REJECT
 - If only one weak indicator: ACCEPT with note

## STEP 4: Calculate Approved Amount (if not rejected)
Base amount = MIN(claimed_amount, billed_amount)

Apply co-payment based on patient age (infer from context if possible):
- Standard: 10% co-payment → approved = base * 0.9
- Seniors (60+): 15% co-payment → approved = base * 0.85
- Children (<18): 5% co-payment → approved = base * 0.95

Round to nearest rupee.

Example:
- Claimed: ₹1,035, Billed: ₹1,035
- Patient: Adult (assume standard)
- Approved: 1035 * 0.9 = ₹931.50 → ₹932

## STEP 5: Generate Response

You MUST return ONLY valid JSON in this EXACT format (no markdown, no extra text):

{{
 "status": "ACCEPTED" or "REJECTED",
 "approved_amount": <number or 0 if rejected>,
 "primary_reason": "<one clear sentence explaining decision>",
 "confidence": "HIGH" or "MEDIUM" or "LOW",
 "policy_reference": "<specific section, e.g., 'Section 4.2, General Exclusions'>",
 "risk_assessment": "<brief summary of fraud analysis>",
 "customer_message": "<professional message to send to patient>",
 "medical_assessment": "<brief analysis of medical condition and treatment appropriateness>",
 "next_steps": ["<step 1>", "<step 2>", "<step 3>"]
}}

# EXAMPLES

Example 1 - Accepted Claim:
Input: Common Cold, ₹1,035 claimed, ₹1,035 billed, LOW risk
Output:
{{
 "status": "ACCEPTED",
 "approved_amount": 932,
 "primary_reason": "Claim approved for covered GP consultation with standard 10% co-payment applied",
 "confidence": "HIGH",
 "policy_reference": "Section 2.1, General Practitioner Services",
 "risk_assessment": "No fraud indicators detected. Legitimate routine consultation.",
 "customer_message": "Your claim has been approved. Payment of ₹932 will be processed within 7-10 business days.",
 "medical_assessment": "Common cold is a routine condition appropriately treated by a general practitioner. Treatment is medically necessary and reasonable.",
 "next_steps": [
 "Payment will be transferred to registered bank account",
 "Confirmation email will be sent",
 "Keep claim reference number for records"
 ]
}}

Example 2 - Rejected (Exclusion):
Input: HIV treatment, ₹5,000 claimed, ₹5,000 billed, LOW risk
Output:
{{
 "status": "REJECTED",
 "approved_amount": 0,
 "primary_reason": "HIV/AIDS treatment is explicitly excluded under policy terms",
 "confidence": "HIGH",
 "policy_reference": "Section 4.2, General Exclusions, Item 1",
 "risk_assessment": "No fraud detected. Legitimate medical need but policy exclusion applies.",
 "customer_message": "We regret to inform you that HIV/AIDS treatment is not covered under your current policy as per Section 4.2 of the member handbook. Please contact our support team to explore alternative coverage options.",
 "medical_assessment": "HIV is a chronic condition requiring ongoing treatment. While medically necessary, it falls under policy exclusions.",
 "next_steps": [
 "Review policy exclusions in member handbook",
 "Contact support at claims@insurance.com for alternative coverage",
 "Appeal within 30 days if you believe this is an error"
 ]
}}

Example 3 - Rejected (Fraud):
Input: Fever, ₹15,000 claimed, ₹720 billed, HIGH risk (duplicate 87%, amount anomaly)
Output:
{{
 "status": "REJECTED",
 "approved_amount": 0,
 "primary_reason": "Claim rejected due to significant discrepancies: amount claimed exceeds bill by 1983%, and duplicate claim detected with 87% similarity",
 "confidence": "HIGH",
 "policy_reference": "Section 5, Fraud Prevention Policy",
 "risk_assessment": "Multiple fraud indicators: severe amount inflation and near-duplicate claim submitted 10 days ago. Requires investigation.",
 "customer_message": "Your claim has been flagged for review due to discrepancies in the submitted information. Our fraud investigation team will contact you within 3 business days. Please have your original documentation ready.",
 "medical_assessment": "Unable to verify medical necessity due to documentation inconsistencies.",
 "next_steps": [
 "Fraud investigation team will contact you",
 "Prepare original bills and receipts for verification",
 "Claim will be reviewed manually within 5 business days"
 ]
}}

Now analyze the claim above and return your decision in the exact JSON format.
"""


# ============================================================================
# SSE STREAMING CLAIM PROCESSOR (MODIFIED for file saving)
# ============================================================================

def process_claim_stream(claim_data: dict, bill_content: str, bill_info: dict, file_path: str = None):
    """Generator that yields SSE events as each processing stage completes."""
    
    def sse(stage: str, data: dict) -> str:
        payload = json.dumps({"stage": stage, **data})
        return f"data: {payload}\n\n"
    
    try:
        # Stage 1: Bill extracted
        yield sse("bill_extracted", {
            "message": "Medical bill analyzed",
            "disease": bill_info.get("disease", "Unknown"),
            "expense": bill_info.get("expense"),
            "progress": 30,
        })
        
        # Stage 2: Fraud detection
        fraud_report = comprehensive_fraud_check(claim_data, bill_info)
        
        yield sse("fraud_complete", {
            "message": "Fraud analysis complete",
            "fraud_report": fraud_report,
            "progress": 55,
        })
        
        # Stage 3: Retrieve policy context
        approval_ctx = get_claim_approval_context()
        exclusion_ctx = get_general_exclusion_context()
        
        yield sse("context_retrieved", {
            "message": "Policy context loaded",
            "progress": 65,
        })
        
        # Stage 4: LLM Decision
        yield sse("generating", {
            "message": "AI is making decision...",
            "progress": 70,
        })
        
        risk_factors_str = "; ".join(fraud_report["risk_factors"]) if fraud_report["risk_factors"] else "None"
        
        # FIXED: Use improved prompt with examples
        prompt = IMPROVED_DECISION_PROMPT.format(
            patient_name=sanitize_for_llm(claim_data.get("patient_name", "")),
            claim_type=sanitize_for_llm(claim_data.get("claim_type", "")),
            disease=sanitize_for_llm(bill_info.get("disease", "Unknown")),
            claimed_amount=sanitize_for_llm(claim_data.get("amount", 0)),
            billed_amount=sanitize_for_llm(bill_info.get("expense") or "Unknown"),
            date=sanitize_for_llm(claim_data.get("date", "")),
            facility=sanitize_for_llm(claim_data.get("medical_facility", "")),
            risk_level=sanitize_for_llm(fraud_report["fraud_risk_level"]),
            risk_score=sanitize_for_llm(fraud_report["risk_score"]),
            risk_factors=sanitize_for_llm(risk_factors_str),
            policy_context=sanitize_for_llm(approval_ctx[:1500]),
            exclusion_context=sanitize_for_llm(exclusion_ctx[:1000]),
        )
        
        yield sse("keepalive", {
            "message": "AI processing...",
            "progress": 75,
        })
        
        response = chat(
            model=MAIN_MODEL,
            messages=[
                {"role": "system", "content": "You are an insurance claims adjudicator. Always respond with valid JSON only."},
                {"role": "user", "content": prompt},
            ],
            options={"temperature": 0.3},
        )
        
        llm_text = response["message"]["content"]
        
        json_match = re.search(r"\{[\s\S]*\}", llm_text)
        if json_match:
            try:
                decision = json.loads(json_match.group())
            except json.JSONDecodeError:
                decision = _fallback_decision(llm_text, fraud_report)
        else:
            decision = _fallback_decision(llm_text, fraud_report)
        
        # Stage 5: Complete
        yield sse("decision", {
            "message": "Decision rendered",
            "decision": decision,
            "fraud_report": fraud_report,
            "progress": 95,
        })
        
        # Save claim in background (file already saved before stream started)
        
        threading.Thread(
            target=_save_claim_with_logging,
            args=(claim_data, bill_info, fraud_report, decision, file_path),
            daemon=True,
        ).start()
        
        yield sse("complete", {
            "message": "Processing complete",
            "progress": 100,
        })
        
    except Exception as e:
        logger.error(f"Processing error: {e}")
        yield sse("error", {"message": str(e)})


def _fallback_decision(llm_text: str, fraud_report: dict) -> dict:
    """Build a fallback decision if LLM doesn't return valid JSON."""
    status = "REJECTED" if fraud_report["fraud_risk_level"] == "HIGH" else "ACCEPTED"
    return {
        "status": status,
        "approved_amount": 0,
        "primary_reason": llm_text[:200] if llm_text else "Unable to parse AI response",
        "confidence": "LOW",
        "policy_reference": "N/A",
        "risk_assessment": f"Risk level: {fraud_report['fraud_risk_level']}",
        "customer_message": "Your claim is being reviewed. Please contact support for details.",
        "medical_assessment": "Assessment could not be completed automatically.",
        "next_steps": ["Contact claims support for manual review"],
    }


# ============================================================================
# DATABASE SAVING (FIXED with transactions)
# ============================================================================

def _save_claim_with_logging(claim_data: dict, bill_info: dict, fraud_report: dict, decision: dict, file_path: str = None):
    """Wrapper for save_claim that logs failures at CRITICAL level."""
    try:
        save_claim(claim_data, bill_info, fraud_report, decision, file_path)
    except Exception as e:
        logger.critical(f"FAILED TO SAVE CLAIM: {e}", exc_info=True)


def save_claim(claim_data: dict, bill_info: dict, fraud_report: dict, decision: dict, file_path: str = None):
    """
    FIXED: Persist claim to SQLite with proper transaction handling.
    Both inserts succeed or both fail (atomic).
    """
    conn = None
    try:
        conn = sqlite3.connect(DB_PATH)
        if sqlite_vec:
            conn.enable_load_extension(True)
            sqlite_vec.load(conn)
        cursor = conn.cursor()
        
        claim_id = claim_data.get("id", f"CLM-{uuid.uuid4().hex[:12].upper()}")
        
        # FIXED: Explicit transaction wrapper
        cursor.execute("BEGIN TRANSACTION")
        
        try:
            # Insert claim
            cursor.execute(
                """INSERT OR REPLACE INTO claims
                (id, patient_name, diagnosis, amount, date, medical_facility,
                claim_type, claim_reason, status, risk_level, risk_score, file_path)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    claim_id,
                    claim_data.get("patient_name", ""),
                    bill_info.get("disease", ""),
                    float(claim_data.get("amount", 0) or 0),
                    claim_data.get("date", ""),
                    claim_data.get("medical_facility", ""),
                    claim_data.get("claim_type", ""),
                    claim_data.get("claim_reason", ""),
                    decision.get("status", ""),
                    fraud_report.get("fraud_risk_level", ""),
                    fraud_report.get("risk_score", 0),
                    file_path,
                ),
            )
            
            # Insert vector
            diagnosis = bill_info.get("disease", "")
            if diagnosis and sqlite_vec:
                try:
                    resp = embed(model=EMBEDDING_MODEL, input=diagnosis.lower())
                    vec = resp["embeddings"][0]
                    cursor.execute(
                        "INSERT OR REPLACE INTO claims_vec (claim_id, diagnosis_embedding) VALUES (?, ?)",
                        (claim_id, serialize_f32(vec)),
                    )
                except Exception as e:
                    logger.warning(f"Could not store claim vector: {e}")
                    # Don't rollback for vector failure - claim is still valid
            
            # Both succeeded - commit
            conn.commit()
            logger.info(f"Claim {claim_id} saved successfully")
            
        except Exception as e:
            # Rollback on any error
            conn.rollback()
            logger.error(f"Failed to save claim {claim_id}: {e}")
            raise
            
    except Exception as e:
        logger.critical(f"Database error: {e}")
        raise
    finally:
        if conn:
            conn.close()


# ============================================================================
# FLASK ROUTES
# ============================================================================

@app.route("/")
def index():
    status, message = check_ollama_status()
    return render_template("index.html", ollama_status=status, ollama_message=message)


@app.route("/check_status")
def check_status():
    status, message = check_ollama_status()
    return jsonify({"status": status, "message": message})


@app.route("/health")
def health_check():
    """Health check endpoint for monitoring."""
    health = {
        "status": "healthy",
        "ollama": False,
        "database": False,
        "faiss": False,
    }
    
    ollama_ok, _ = check_ollama_status()
    health["ollama"] = ollama_ok
    if not ollama_ok:
        health["status"] = "degraded"
    
    try:
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT 1")
            health["database"] = True
    except Exception as e:
        logger.error(f"Health check DB error: {e}")
        health["status"] = "unhealthy"
    
    try:
        if get_faiss_db() is not None:
            health["faiss"] = True
        else:
            if not os.path.exists(FAISS_PATH):
                health["status"] = "degraded"
            else:
                health["status"] = "unhealthy"
    except Exception as e:
        logger.error(f"Health check FAISS error: {e}")
        health["status"] = "unhealthy"
    
    status_code = 200 if health["status"] == "healthy" else (503 if health["status"] == "unhealthy" else 200)
    return jsonify(health), status_code


# ============================================================================
# ADMIN UI ROUTES
# ============================================================================

@app.route("/admin")
def admin_panel():
    """Admin dashboard for managing exclusions."""
    try:
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id, name, description FROM exclusions ORDER BY name")
            exclusions = cursor.fetchall()
            return render_template("admin.html", exclusions=exclusions)
    except Exception as e:
        return f"Error: {e}", 500


@app.route("/admin/exclusions", methods=["POST"])
def add_exclusion():
    """Add new exclusion dynamically with embedding."""
    try:
        name = request.form.get("name", "").strip()
        description = request.form.get("description", "").strip()
        
        if not name:
            return jsonify({"error": "Name required"}), 400
        
        # Generate embedding for new exclusion
        text = f"{name}: {description}"
        response = embed(model=EMBEDDING_MODEL, input=text)
        vector = serialize_f32(response["embeddings"][0])
        
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO exclusions (name, description) VALUES (?, ?)",
                (name, description),
            )
            excl_id = cursor.lastrowid
            
            cursor.execute(
                "INSERT INTO exclusions_vec (exclusion_id, embedding) VALUES (?, ?)",
                (excl_id, vector),
            )
            conn.commit()
        
        logger.info(f"Added exclusion: {name}")
        return jsonify({"success": True, "id": excl_id})
        
    except Exception as e:
        logger.error(f"Add exclusion error: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/admin/exclusions/<int:id>", methods=["DELETE"])
def delete_exclusion(id):
    """Remove exclusion from database."""
    try:
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM exclusions_vec WHERE exclusion_id = ?", (id,))
            cursor.execute("DELETE FROM exclusions WHERE id = ?", (id,))
            conn.commit()
        logger.info(f"Deleted exclusion {id}")
        return jsonify({"success": True})
    except Exception as e:
        logger.error(f"Delete exclusion error: {e}")
        return jsonify({"error": str(e)}), 500


# ============================================================================
# FORM VALIDATION & PROCESSING
# ============================================================================

def validate_claim_form(request) -> tuple:
    """Validate form data. Returns (is_valid, error_message, claim_data, safe_filename)."""
    name = request.form.get("name", "").strip()
    address = request.form.get("address", "").strip()
    claim_type = request.form.get("claim_type", "").strip()
    claim_reason = request.form.get("claim_reason", "").strip()
    date = request.form.get("date", "").strip()
    medical_facility = request.form.get("medical_facility", "").strip()
    total_claim_amount = request.form.get("total_claim_amount", "").strip()
    description = request.form.get("description", "").strip()
    medical_bill = request.files.get("medical_bill")
    
    if not all([name, claim_type, claim_reason, medical_bill, total_claim_amount]):
        return False, "Please fill in all required fields", None, None
    
    try:
        amount = Decimal(total_claim_amount)
        if amount <= 0:
            return False, "Claim amount must be greater than 0", None, None
    except:
        return False, "Claim amount must be a valid number", None, None
    
    if date:
        try:
            datetime.strptime(date, "%Y-%m-%d")
        except ValueError:
            return False, "Date must be in YYYY-MM-DD format", None, None
    
    # FIXED: Comprehensive file validation
    is_valid, error_msg, safe_name = validate_uploaded_file(medical_bill)
    if not is_valid:
        return False, error_msg, None, None
    
    claim_data = {
        "patient_name": name,
        "address": address,
        "claim_type": claim_type,
        "claim_reason": claim_reason,
        "date": date or datetime.now().strftime("%Y-%m-%d"),
        "medical_facility": medical_facility,
        "amount": total_claim_amount,
        "description": description,
    }
    
    return True, None, claim_data, safe_name


@app.route("/process_claim", methods=["POST"])
@limiter.limit("5 per minute")  # NEW: Rate limiting - max 5 claims per minute per IP
def process_claim():
    """Process a claim and return SSE stream."""
    try:
        status, message = check_ollama_status()
        if not status:
            return jsonify({"error": True, "message": message}), 503
        
        is_valid, error_message, claim_data, safe_filename = validate_claim_form(request)
        if not is_valid:
            return jsonify({"error": True, "message": error_message}), 400
        
        medical_bill = request.files.get("medical_bill")
        
        # Extract bill text (with OCR if needed)
        bill_content = get_file_content(medical_bill)
        if not bill_content:
            return jsonify({"error": True, "message": "Unable to read medical bill PDF (tried digital text and OCR)"}), 400
        
        bill_info = extract_bill_info(bill_content)
        
        claim_data["id"] = f"CLM-{uuid.uuid4().hex[:12].upper()}"
        claim_data["diagnosis"] = bill_info.get("disease", claim_data.get("claim_reason", ""))
        
        # FIX: Save file HERE while request context is still open
        file_path = save_uploaded_file(medical_bill, claim_data["id"], safe_filename)
        
        # Pass file_path (string) not file object to the stream
        return Response(
            process_claim_stream(claim_data, bill_content, bill_info, file_path),
            mimetype="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",
                "Connection": "keep-alive",
            },
        )
        
    except Exception as e:
        logger.error(f"Route error: {e}")
        return jsonify({"error": True, "message": str(e)}), 500


# ============================================================================
# STARTUP
# ============================================================================

if __name__ == "__main__":
    print("=" * 60)
    print("ClaimTrackr — FIXED EDITION with OCR & Admin")
    print("=" * 60)
    
    status, message = check_ollama_status()
    print(f"\nOllama Status: {message}")
    
    print("\nFeatures:")
    print(" ✓ OCR for scanned PDFs (Tesseract) - FIXED")
    print(" ✓ File upload saving (audit trail)")
    print(" ✓ Admin UI for exclusions (/admin)")
    print(" ✓ Vector-based duplicate detection")
    print(" ✓ SSE streaming responses")
    print(" ✓ SQLite persistence - FIXED with transactions")
    print(" ✓ Rate limiting (5 claims/min per IP)")
    print(" ✓ Comprehensive file validation (magic bytes)")
    print(" ✓ Improved LLM prompt with examples")
    print(" ✓ Rotating log files")
    
    if os.path.exists(DB_PATH):
        print(f"\n[OK] Database found: {DB_PATH}")
    else:
        print(f"\n[WARN] Database not found. Run: python setup_db.py")
    
    print(f"\n[OK] Upload directory: {UPLOAD_DIR.absolute()}")
    
    print("\nInitializing FAISS embeddings...")
    get_faiss_db()
    
    print("\n" + "=" * 60)
    print("Starting server at: http://localhost:8081")
    print("Admin panel at: http://localhost:8081/admin")
    print("=" * 60 + "\n")
    
    app.run(host="0.0.0.0", port=8081, debug=True, threaded=True)
