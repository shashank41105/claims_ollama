# setup_db.py - Run this first to initialize the database
# Usage: python setup_db.py

import sqlite3
import struct
import sys

try:
    import sqlite_vec
except ImportError:
    print("ERROR: sqlite-vec not installed. Run: pip install sqlite-vec")
    sys.exit(1)

try:
    from ollama import embed
except ImportError:
    print("ERROR: ollama package not installed. Run: pip install ollama")
    sys.exit(1)

DB_PATH = "claimtrackr.db"

# General exclusion list (matches original)
EXCLUSIONS = [
    {"name": "HIV/AIDS", "description": "All HIV/AIDS related treatments, medications, and consultations including AIDS-related complex conditions"},
    {"name": "Parkinson's disease", "description": "Parkinson's disease treatment and management, chronic degenerative neurological condition"},
    {"name": "Alzheimer's disease", "description": "Alzheimer's disease treatment and management, chronic degenerative neurological condition"},
    {"name": "Pregnancy", "description": "Prenatal care, delivery, postnatal care, and complications of pregnancy"},
    {"name": "Substance abuse", "description": "Alcohol abuse treatment, drug addiction rehabilitation, and related complications"},
    {"name": "Self-inflicted injuries", "description": "Injuries from suicide attempts, self-harm, and injuries sustained while committing a crime"},
    {"name": "Sexually transmitted diseases", "description": "Treatment for all STDs except when contracted through blood transfusion"},
    {"name": "Pre-existing conditions", "description": "Any condition that existed before policy inception with 24-month waiting period"},
    {"name": "Cosmetic procedures", "description": "Plastic surgery for aesthetic purposes and dental cosmetics"},
    {"name": "Experimental treatments", "description": "Treatments not approved by medical authorities, clinical trials, unproven therapies"},
]

EMBEDDING_MODEL = "nomic-embed-text"
EXPECTED_EMBEDDING_DIM = 768


def serialize_f32(vector):
    """Serialize a list of floats into a compact bytes object for sqlite-vec."""
    if len(vector) != EXPECTED_EMBEDDING_DIM:
        raise ValueError(f"Expected {EXPECTED_EMBEDDING_DIM} dimensions, got {len(vector)}")
    return struct.pack(f"{len(vector)}f", *vector)


def init_database():
    """Initialize SQLite database with vector support."""
    conn = sqlite3.connect(DB_PATH)
    conn.enable_load_extension(True)
    sqlite_vec.load(conn)
    cursor = conn.cursor()

    # ── Claims table ──────────────────────────────────────────────────
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS claims (
        id TEXT PRIMARY KEY,
        patient_name TEXT NOT NULL,
        diagnosis TEXT,
        amount REAL,
        date TEXT,
        medical_facility TEXT,
        claim_type TEXT,
        claim_reason TEXT,
        status TEXT,
        risk_level TEXT,
        risk_score INTEGER,
        file_path TEXT,
        icd10_code TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)

    # ── FIX #14: Add indexes for frequently queried columns ──────────
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_claims_patient ON claims(patient_name)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_claims_date ON claims(date)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_claims_status ON claims(status)")

    # ── Claims vector table (for duplicate detection) ─────────────────
    cursor.execute("""
    CREATE VIRTUAL TABLE IF NOT EXISTS claims_vec USING vec0(
        claim_id TEXT PRIMARY KEY,
        diagnosis_embedding float[768]
    )
    """)

    # ── Exclusions table ──────────────────────────────────────────────
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS exclusions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL UNIQUE,
        description TEXT
    )
    """)

    # ── Exclusions vector table (pre-computed embeddings) ─────────────
    cursor.execute("""
    CREATE VIRTUAL TABLE IF NOT EXISTS exclusions_vec USING vec0(
        exclusion_id INTEGER PRIMARY KEY,
        embedding float[768]
    )
    """)

    # ── Context cache table ───────────────────────────────────────────
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS context_cache (
        cache_key TEXT PRIMARY KEY,
        content TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)

    conn.commit()
    print("[OK] Database tables created.")
    return conn


def precompute_exclusion_embeddings(conn):
    """Pre-compute and store embeddings for all exclusion items."""
    cursor = conn.cursor()

    # Clear existing exclusions (idempotent re-run)
    cursor.execute("DELETE FROM exclusions")
    cursor.execute("DELETE FROM exclusions_vec")

    print(f"[..] Computing embeddings for {len(EXCLUSIONS)} exclusions...")

    for excl in EXCLUSIONS:
        text = f"{excl['name']}: {excl['description']}"

        try:
            response = embed(model=EMBEDDING_MODEL, input=text)
            vector = response["embeddings"][0]
            
            if len(vector) != EXPECTED_EMBEDDING_DIM:
                print(f" [WARN] Unexpected embedding dimension for '{excl['name']}': {len(vector)}")
                continue
                
        except Exception as e:
            print(f" [WARN] Failed to embed '{excl['name']}': {e}")
            continue

        cursor.execute(
            "INSERT INTO exclusions (name, description) VALUES (?, ?)",
            (excl["name"], excl["description"]),
        )
        excl_id = cursor.lastrowid

        cursor.execute(
            "INSERT INTO exclusions_vec (exclusion_id, embedding) VALUES (?, ?)",
            (excl_id, serialize_f32(vector)),
        )
        print(f" [OK] {excl['name']}")

    conn.commit()
    print(f"[OK] {len(EXCLUSIONS)} exclusion embeddings stored.\n")


def main():
    print("=" * 60)
    print("ClaimTrackr — Database Initialization")
    print("=" * 60)
    print()

    conn = init_database()
    precompute_exclusion_embeddings(conn)

    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM exclusions")
    count = cursor.fetchone()[0]
    print(f"[VERIFY] Exclusions in DB: {count}")

    cursor.execute("SELECT COUNT(*) FROM exclusions_vec")
    vec_count = cursor.fetchone()[0]
    print(f"[VERIFY] Exclusion vectors: {vec_count}")
    
    cursor.execute("SELECT name FROM sqlite_master WHERE type='index' AND name LIKE 'idx_%'")
    indexes = [row[0] for row in cursor.fetchall()]
    print(f"[VERIFY] Database indexes: {', '.join(indexes)}")

    conn.close()
    print()
    print("=" * 60)
    print("Database ready! Next: python optimized_app.py")
    print("=" * 60)


if __name__ == "__main__":
    main()
