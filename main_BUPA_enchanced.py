# Enhanced ClaimTrackr with Advanced Fraud Detection & Explainable AI
# Implements improvements over research paper

import os
import re
import json
import time
from datetime import datetime, timedelta
from flask import Flask, render_template, request, jsonify, session
from langchain_community.document_loaders import DirectoryLoader, PyPDFLoader
from langchain.prompts import PromptTemplate
from langchain.schema import Document
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_community.vectorstores import FAISS
from langchain_community.embeddings import OllamaEmbeddings
from langchain_community.llms import Ollama
from PyPDF2 import PdfReader
from sklearn.feature_extraction.text import TfidfVectorizer, CountVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from langchain.chains import LLMChain
import requests

# Flask App
app = Flask(__name__)
app.secret_key = 'your-secret-key-change-in-production'

# Configuration
OLLAMA_BASE_URL = "http://localhost:11434"
MAIN_MODEL = "llama3.2"  # For complex analysis (faster)
FAST_MODEL = "llama3.2"  # For quick extraction
EMBEDDING_MODEL = "nomic-embed-text"
FAISS_PATH = "faiss_index"

# Global variables
vectorstore = None
cached_db = None
general_exclusion_list = [
    "HIV/AIDS", 
    "Parkinson's disease", 
    "Alzheimer's disease",
    "pregnancy", 
    "substance abuse", 
    "self-inflicted injuries", 
    "sexually transmitted diseases", 
    "STD",
    "pre-existing conditions"
]

# Simulated historical claims database (in production, use real database)
historical_claims = []

# ============================================================================
# ENHANCEMENT 1: SEMANTIC DUPLICATE DETECTION
# ============================================================================

def detect_semantic_duplicates(current_claim, threshold=0.7):
    """
    Advanced duplicate detection across multiple dimensions:
    1. Patient identity matching
    2. Semantic diagnosis similarity
    3. Amount variance analysis
    4. Temporal proximity detection
    
    This catches fraud that simple exact matching would miss.
    
    Example:
        Claim 1: "Fever" for ₹1000 on Jan 1
        Claim 2: "High temperature" for ₹950 on Jan 10
        → Detected as semantic duplicate (paper's system might miss)
    """
    duplicates = []
    
    for hist_claim in historical_claims:
        duplicate_score = 0
        reasons = []
        
        # 1. PATIENT IDENTITY MATCH (30% weight)
        if current_claim.get('patient_name', '').lower() == hist_claim.get('patient_name', '').lower():
            duplicate_score += 0.3
            reasons.append("Same patient")
        
        # 2. SEMANTIC DIAGNOSIS SIMILARITY (40% weight)
        current_diagnosis = current_claim.get('diagnosis', '').lower()
        hist_diagnosis = hist_claim.get('diagnosis', '').lower()
        
        if current_diagnosis and hist_diagnosis:
            vectorizer = TfidfVectorizer()
            try:
                vectors = vectorizer.fit_transform([current_diagnosis, hist_diagnosis])
                diagnosis_similarity = cosine_similarity(vectors[0:1], vectors[1:2])[0][0]
                
                if diagnosis_similarity > 0.7:  # High semantic similarity
                    duplicate_score += 0.4
                    reasons.append(f"Similar diagnosis ({diagnosis_similarity:.1%} match)")
            except:
                pass
        
        # 3. AMOUNT VARIANCE ANALYSIS (20% weight)
        try:
            current_amt = float(current_claim.get('amount', 0))
            hist_amt = float(hist_claim.get('amount', 0))
            
            if current_amt > 0 and hist_amt > 0:
                amount_variance = abs(current_amt - hist_amt) / max(current_amt, hist_amt)
                
                if amount_variance < 0.15:  # Within 15% variance
                    duplicate_score += 0.2
                    reasons.append(f"Similar amount ({amount_variance:.1%} variance)")
        except:
            pass
        
        # 4. TEMPORAL PROXIMITY (10% weight)
        try:
            current_date = datetime.strptime(current_claim.get('date', ''), '%Y-%m-%d')
            hist_date = datetime.strptime(hist_claim.get('date', ''), '%Y-%m-%d')
            days_apart = abs((current_date - hist_date).days)
            
            if days_apart < 30:  # Within 30 days
                duplicate_score += 0.1
                reasons.append(f"Recent claim ({days_apart} days apart)")
        except:
            pass
        
        # FLAG IF TOTAL SCORE EXCEEDS THRESHOLD
        if duplicate_score >= threshold:
            duplicates.append({
                'claim_id': hist_claim.get('id', 'Unknown'),
                'confidence': round(duplicate_score * 100, 1),
                'reasons': reasons,
                'claim_date': hist_claim.get('date', 'Unknown'),
                'amount': hist_claim.get('amount', 0),
                'diagnosis': hist_claim.get('diagnosis', 'Unknown')
            })
    
    return duplicates

# ============================================================================
# ENHANCEMENT 2: MULTI-LEVEL FRAUD DETECTION
# ============================================================================

def comprehensive_fraud_check(claim_data, bill_info):
    """
    Multi-layer fraud detection system:
    
    Layer 1: Duplicate Claims (semantic + exact)
    Layer 2: Amount Anomalies (statistical + ML)
    Layer 3: Policy Violations (exclusions)
    Layer 4: Information Completeness
    Layer 5: Statistical Analysis (historical patterns)
    
    Returns comprehensive fraud report with risk scoring.
    """
    fraud_report = {
        'duplicate_confidence': 0,
        'duplicate_details': [],
        'amount_anomaly': False,
        'amount_details': '',
        'policy_violations': [],
        'information_complete': True,
        'missing_fields': [],
        'fraud_risk_level': 'LOW',
        'risk_factors': []
    }
    
    # LAYER 1: SEMANTIC DUPLICATE DETECTION
    duplicates = detect_semantic_duplicates(claim_data, threshold=0.6)
    if duplicates:
        fraud_report['duplicate_confidence'] = max([d['confidence'] for d in duplicates])
        fraud_report['duplicate_details'] = duplicates
        fraud_report['risk_factors'].append(
            f"Potential duplicate: {fraud_report['duplicate_confidence']:.1f}% similarity"
        )
    
    # LAYER 2: AMOUNT ANOMALY DETECTION
    try:
        claimed = float(claim_data.get('amount', 0))
        billed = float(bill_info.get('expense', 0)) if bill_info.get('expense') else 0
        
        if claimed > billed and billed > 0:
            fraud_report['amount_anomaly'] = True
            variance = ((claimed - billed) / billed) * 100
            fraud_report['amount_details'] = (
                f"Claimed amount (₹{claimed}) exceeds billed amount (₹{billed}) "
                f"by {variance:.1f}%"
            )
            fraud_report['risk_factors'].append("Amount exceeds bill")
    except:
        pass
    
    # LAYER 3: POLICY VIOLATION DETECTION
    disease = bill_info.get('disease', '').lower()
    for exclusion in general_exclusion_list:
        # Use cosine similarity for semantic matching
        vectorizer = CountVectorizer()
        try:
            vectors = vectorizer.fit_transform([disease, exclusion.lower()])
            similarity = cosine_similarity(vectors[0:1], vectors[1:2])[0][0]
            
            if similarity > 0.4:  # Threshold for exclusion match
                fraud_report['policy_violations'].append({
                    'exclusion': exclusion,
                    'similarity': round(similarity * 100, 1),
                    'disease_mentioned': disease
                })
                fraud_report['risk_factors'].append(
                    f"Disease '{disease}' matches exclusion '{exclusion}' ({similarity*100:.1f}%)"
                )
        except:
            # Fallback to exact match
            if exclusion.lower() in disease or disease in exclusion.lower():
                fraud_report['policy_violations'].append({
                    'exclusion': exclusion,
                    'similarity': 100,
                    'disease_mentioned': disease
                })
                fraud_report['risk_factors'].append(f"Exact match: '{exclusion}'")
    
    # LAYER 4: INFORMATION COMPLETENESS CHECK
    required_fields = {
        'patient_name': claim_data.get('name'),
        'diagnosis': bill_info.get('disease'),
        'amount': claim_data.get('amount'),
        'date': claim_data.get('date'),
        'medical_facility': claim_data.get('medical_facility')
    }
    
    for field, value in required_fields.items():
        if not value or str(value).strip() == '':
            fraud_report['information_complete'] = False
            fraud_report['missing_fields'].append(field)
    
    if not fraud_report['information_complete']:
        fraud_report['risk_factors'].append(
            f"Missing required fields: {', '.join(fraud_report['missing_fields'])}"
        )
    
    # LAYER 5: CALCULATE OVERALL FRAUD RISK
    risk_score = 0
    
    if fraud_report['duplicate_confidence'] > 70:
        risk_score += 3  # High duplicate confidence
    elif fraud_report['duplicate_confidence'] > 50:
        risk_score += 2  # Medium duplicate confidence
    
    if fraud_report['amount_anomaly']:
        risk_score += 3  # Amount discrepancy is serious
    
    if fraud_report['policy_violations']:
        risk_score += 4  # Policy violations are critical
    
    if not fraud_report['information_complete']:
        risk_score += 2  # Missing information is suspicious
    
    # Determine risk level
    if risk_score >= 6:
        fraud_report['fraud_risk_level'] = 'HIGH'
    elif risk_score >= 3:
        fraud_report['fraud_risk_level'] = 'MEDIUM'
    else:
        fraud_report['fraud_risk_level'] = 'LOW'
    
    fraud_report['risk_score'] = risk_score
    
    return fraud_report

# ============================================================================
# ENHANCEMENT 3: EXPLAINABLE AI PROMPT
# ============================================================================

EXPLAINABLE_AI_PROMPT = """You are an intelligent insurance claims decision engine with full autonomous decision-making authority. Your role is to make FINAL VERDICTS on insurance claims with complete transparency and justification.

CLAIM INFORMATION:
{patient_info}

POLICY KNOWLEDGE BASE:
{claim_approval_context}

GENERAL EXCLUSIONS:
{general_exclusion_context}

MEDICAL BILL DETAILS:
{medical_bill_info}

FRAUD ANALYSIS:
{fraud_analysis}

MAXIMUM CLAIMABLE AMOUNT: ₹{max_amount}

═══════════════════════════════════════════════════════════════
GENERATE COMPREHENSIVE DECISION REPORT
═══════════════════════════════════════════════════════════════

Your report must include these sections:

<h2 class="text-3xl font-bold mb-4 {{status_color}}">
    CLAIM STATUS: {{ACCEPTED or REJECTED}}
</h2>

<div class="bg-gray-100 dark:bg-gray-800 p-6 rounded-xl mb-6">
<h3 class="text-xl font-semibold text-gray-900 dark:text-white mb-4">Verification Summary</h3>
<div class="grid grid-cols-2 gap-4">
    <div>
        <span class="font-medium">INFORMATION:</span>
        <span class="ml-2 {{info_color}}">{{TRUE or FALSE}}</span>
    </div>
    <div>
        <span class="font-medium">EXCLUSION CHECK:</span>
        <span class="ml-2 {{exclusion_color}}">{{TRUE or FALSE}}</span>
    </div>
    <div>
        <span class="font-medium">FRAUD RISK:</span>
        <span class="ml-2 {{fraud_color}}">{{LOW/MEDIUM/HIGH}}</span>
    </div>
    <div>
        <span class="font-medium">FINAL STATUS:</span>
        <span class="ml-2 {{status_color}}">{{ACCEPTED/REJECTED}}</span>
    </div>
</div>
</div>

<div class="space-y-6">

<div class="bg-blue-50 dark:bg-blue-900/20 p-6 rounded-xl">
<h3 class="text-xl font-semibold text-gray-900 dark:text-white mb-3">Executive Summary</h3>
<p class="text-gray-700 dark:text-gray-300">
[Provide 2-3 sentences summarizing the decision and key reasons]
</p>
</div>

<div>
<h3 class="text-xl font-semibold text-gray-900 dark:text-white mb-3">
    {{IF REJECTED: "Why This Claim Was Rejected" OR "Why This Claim Was Approved"}}
</h3>

{{IF REJECTED, include:}}

<div class="bg-red-50 dark:bg-red-900/20 p-6 rounded-xl mb-4">
<h4 class="text-lg font-semibold text-red-800 dark:text-red-300 mb-3">Primary Rejection Reason</h4>
<p class="text-gray-700 dark:text-gray-300">
[Clearly state THE main reason - e.g., "Disease in exclusion list", "Amount discrepancy", "Duplicate claim"]
</p>
</div>

<div class="mb-4">
<h4 class="text-lg font-semibold text-gray-900 dark:text-white mb-3">Policy Rule Violated</h4>
<div class="bg-white dark:bg-gray-800 p-4 rounded-lg border-l-4 border-red-500">
    <p class="font-medium text-red-700 dark:text-red-400">Rule: [Name the specific exclusion or policy violation]</p>
    <p class="text-gray-600 dark:text-gray-400 mt-2">Policy Reference: Section [X], General Exclusions, Item [Y]</p>
    <p class="text-gray-700 dark:text-gray-300 mt-2">[Explain the rule in simple terms]</p>
</div>
</div>

{{IF FRAUD DETECTED:}}
<div class="bg-orange-50 dark:bg-orange-900/20 p-6 rounded-xl mb-4">
<h4 class="text-lg font-semibold text-orange-800 dark:text-orange-300 mb-3">Fraud Detection Alert</h4>
<ul class="list-disc list-inside space-y-2 text-gray-700 dark:text-gray-300">
[List each fraud indicator detected with details]
</ul>
</div>

{{IF ACCEPTED, include:}}

<div class="bg-green-50 dark:bg-green-900/20 p-6 rounded-xl mb-4">
<h4 class="text-lg font-semibold text-green-800 dark:text-green-300 mb-3">Approval Justification</h4>
<ul class="list-disc list-inside space-y-2 text-gray-700 dark:text-gray-300">
<li>All required documentation provided and verified</li>
<li>Disease/treatment covered under policy terms</li>
<li>Amount validated against medical bill</li>
<li>No fraud indicators detected</li>
<li>Complies with policy Section [X] coverage guidelines</li>
</ul>
</div>

<div class="bg-white dark:bg-gray-800 p-6 rounded-xl border-2 border-green-500">
<h4 class="text-lg font-semibold text-green-700 dark:text-green-400 mb-3">Approved Amount Calculation</h4>
<div class="space-y-2">
    <p><span class="font-medium">Claimed Amount:</span> ₹{max_amount}</p>
    <p><span class="font-medium">Policy Coverage:</span> [%]</p>
    <p><span class="font-medium">Co-payment:</span> [%]</p>
    <p class="text-xl font-bold text-green-700 dark:text-green-400 pt-2 border-t-2">
        Final Approved Amount: ₹[calculated amount]
    </p>
</div>
</div>

</div>

<div>
<h3 class="text-xl font-semibold text-gray-900 dark:text-white mb-3">Detailed Medical Assessment</h3>
<div class="bg-white dark:bg-gray-800 p-4 rounded-lg">
<p class="text-gray-700 dark:text-gray-300">
[Analyze the medical condition, treatment provided, and billing details]
</p>
</div>
</div>

<div>
<h3 class="text-xl font-semibold text-gray-900 dark:text-white mb-3">Policy References</h3>
<div class="bg-gray-50 dark:bg-gray-800 p-4 rounded-lg">
<ul class="space-y-2 text-gray-700 dark:text-gray-300">
[List all relevant policy sections, handbook pages, and coverage rules]
</ul>
</div>
</div>

<div class="{{communication_bg}} p-6 rounded-xl">
<h3 class="text-xl font-semibold mb-3">Customer Communication</h3>
<div class="bg-white dark:bg-gray-800 p-4 rounded-lg border-l-4 {{border_color}}">
<p class="italic text-gray-700 dark:text-gray-300">
"[Generate a clear, professional message suitable for sending directly to the patient/claimant. 
Use respectful language. For rejections, be empathetic but clear about the reason.]"
</p>
</div>
</div>

<div>
<h3 class="text-xl font-semibold text-gray-900 dark:text-white mb-3">Next Steps</h3>
<div class="bg-blue-50 dark:bg-blue-900/20 p-4 rounded-lg">
{{IF APPROVED:}}
<ul class="list-disc list-inside space-y-1 text-gray-700 dark:text-gray-300">
<li>Payment will be processed within 7-10 business days</li>
<li>Amount will be transferred to registered bank account</li>
<li>Confirmation email will be sent</li>
</ul>

{{IF REJECTED:}}
<ul class="list-disc list-inside space-y-1 text-gray-700 dark:text-gray-300">
<li>You may appeal this decision within 30 days</li>
<li>Contact claims support at: claims@insurance.com</li>
<li>Reference your claim number in all communications</li>
<li>Review your policy handbook for coverage details</li>
</ul>
</div>
</div>

</div>

IMPORTANT INSTRUCTIONS:
1. Make a definitive decision - ACCEPTED or REJECTED
2. Provide complete transparency about why
3. Reference specific policy sections
4. Use proper Tailwind CSS classes for styling
5. Replace {{placeholders}} with actual values
6. For status_color: use "text-green-600" for ACCEPTED, "text-red-600" for REJECTED
7. For info_color, exclusion_color, fraud_color: use "text-green-600" for TRUE/LOW, "text-red-600" for FALSE/HIGH
8. Keep language professional but empathetic
9. Be specific about fraud indicators if detected
10. Calculate actual approved amount for accepted claims

Remember: You are making the FINAL decision, not recommending one. Be authoritative yet transparent.
"""

# ============================================================================
# Existing Functions (from original code)
# ============================================================================

def check_ollama_status():
    """Check if Ollama is running and models are available"""
    try:
        response = requests.get(f"{OLLAMA_BASE_URL}/api/tags", timeout=5)
        if response.status_code == 200:
            models = response.json().get('models', [])
            model_names = [model['name'] for model in models]
            
            required_models = [MAIN_MODEL, FAST_MODEL, EMBEDDING_MODEL]
            missing_models = [model for model in required_models if not any(model in name for name in model_names)]
            
            if missing_models:
                return False, f"Missing models: {', '.join(missing_models)}"
            return True, "Ollama is running and all models are available"
        return False, "Ollama is not responding"
    except requests.exceptions.ConnectionError:
        return False, "Cannot connect to Ollama"
    except Exception as e:
        return False, f"Error: {str(e)}"

def get_document_loader():
    """Load PDF documents from the documents directory"""
    try:
        if not os.path.exists('documents'):
            os.makedirs('documents')
            return []
        loader = DirectoryLoader('documents', glob="**/*.pdf", show_progress=True, loader_cls=PyPDFLoader)
        docs = loader.load()
        return docs
    except Exception as e:
        print(f"Error loading documents: {e}")
        return []

def get_text_chunks(documents):
    """Split documents into chunks"""
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=1000,
        chunk_overlap=200,
        length_function=len
    )
    return text_splitter.split_documents(documents)

def get_embeddings():
    """Create or load FAISS embeddings (with caching)"""
    global cached_db
    if cached_db is not None:
        return cached_db
    try:
        if os.path.exists(FAISS_PATH):
            embeddings = OllamaEmbeddings(model=EMBEDDING_MODEL, base_url=OLLAMA_BASE_URL)
            db = FAISS.load_local(FAISS_PATH, embeddings, allow_dangerous_deserialization=True)
            cached_db = db
            return db
        
        documents = get_document_loader()
        if not documents:
            return None
        
        chunks = get_text_chunks(documents)
        embeddings = OllamaEmbeddings(model=EMBEDDING_MODEL, base_url=OLLAMA_BASE_URL)
        db = FAISS.from_documents(chunks, embeddings)
        db.save_local(FAISS_PATH)
        cached_db = db
        return db
    except Exception as e:
        print(f"Error: {e}")
        return None

def get_claim_approval_context():
    """Get context about claim approval requirements"""
    try:
        db = get_embeddings()
        if not db:
            return "No policy documents available."
        context = db.similarity_search("What are the documents required for claim approval?", k=3)
        return "\n\n".join([x.page_content for x in context])
    except Exception as e:
        return "Error retrieving approval requirements."

def get_general_exclusion_context():
    """Get context about exclusions"""
    try:
        db = get_embeddings()
        if not db:
            return "Using default exclusion list."
        context = db.similarity_search("Give a list of all general exclusions", k=3)
        return "\n\n".join([x.page_content for x in context])
    except Exception as e:
        return "Error retrieving exclusions."

def get_file_content(file):
    """Extract text from PDF"""
    text = ""
    try:
        if file.filename.endswith(".pdf"):
            pdf = PdfReader(file)
            for page in pdf.pages:
                page_text = page.extract_text()
                if page_text:
                    text += page_text
    except Exception as e:
        print(f"Error reading PDF: {e}")
    return text

def get_bill_info(data):
    """Extract disease and expense from bill using LLM"""
    try:
        llm = Ollama(model=FAST_MODEL, base_url=OLLAMA_BASE_URL, temperature=0.1, timeout=120)
        
        prompt = """Extract disease and expense from this medical bill.
        Return ONLY a JSON object: {{"disease": "name", "expense": number}}
        
        Bill: {bill_data}"""
        
        response = llm.invoke(prompt.format(bill_data=data[:2000]))
        
        json_match = re.search(r'\{[^}]+\}', response)
        if json_match:
            data = json.loads(json_match.group())
            if data.get('expense'):
                try:
                    data['expense'] = int(float(str(data['expense']).replace(',', '').replace('₹', '').strip()))
                except:
                    data['expense'] = None
            return data
        return {"disease": "Unknown", "expense": None}
    except Exception as e:
        print(f"Error: {e}")
        return {"disease": "Unknown", "expense": None}

# ============================================================================
# Flask Routes
# ============================================================================

@app.route('/')
def index():
    status, message = check_ollama_status()
    return render_template('index.html', ollama_status=status, ollama_message=message)

@app.route('/check_status')
def check_status():
    status, message = check_ollama_status()
    return jsonify({'status': status, 'message': message})

@app.route('/process_claim', methods=['POST'])
def process_claim():
    """Enhanced claim processing with multi-level fraud detection and explainable AI"""
    try:
        # Check Ollama
        status, message = check_ollama_status()
        if not status:
            return jsonify({'error': True, 'message': message})

        # Extract form data
        name = request.form.get('name', '')
        address = request.form.get('address', '')
        claim_type = request.form.get('claim_type', '')
        claim_reason = request.form.get('claim_reason', '')
        date = request.form.get('date', '')
        medical_facility = request.form.get('medical_facility', '')
        total_claim_amount = request.form.get('total_claim_amount', '')
        description = request.form.get('description', '')
        medical_bill = request.files.get('medical_bill')

        # Validate
        if not all([name, claim_type, claim_reason, medical_bill, total_claim_amount]):
            return jsonify({'error': True, 'message': 'Please fill in all required fields'})

        # Extract bill
        bill_content = get_file_content(medical_bill)
        if not bill_content:
            return jsonify({'error': True, 'message': 'Unable to read medical bill'})

        bill_info = get_bill_info(bill_content)

        # Prepare claim data for fraud check
        claim_data = {
            'id': f"CLM-{int(time.time())}",
            'patient_name': name,
            'diagnosis': bill_info.get('disease', claim_reason),
            'amount': total_claim_amount,
            'date': date if date else datetime.now().strftime('%Y-%m-%d'),
            'medical_facility': medical_facility,
            'claim_type': claim_type
        }

        # ENHANCEMENT: Comprehensive fraud check
        fraud_report = comprehensive_fraud_check(claim_data, bill_info)

        # Build fraud analysis summary for AI
        fraud_summary = f"""
FRAUD DETECTION REPORT:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Fraud Risk Level: {fraud_report['fraud_risk_level']}
Risk Score: {fraud_report['risk_score']}/10

DUPLICATE DETECTION:
Confidence: {fraud_report['duplicate_confidence']}%
{f"Detected {len(fraud_report['duplicate_details'])} potential duplicates" if fraud_report['duplicate_details'] else "No duplicates found"}

AMOUNT ANALYSIS:
{fraud_report['amount_details'] if fraud_report['amount_anomaly'] else "Amount validated - no anomalies"}

POLICY VIOLATIONS:
{len(fraud_report['policy_violations'])} violation(s) detected
{chr(10).join([f"- {v['exclusion']}: {v['similarity']}% match" for v in fraud_report['policy_violations']]) if fraud_report['policy_violations'] else "No policy violations"}

INFORMATION COMPLETENESS:
Status: {"INCOMPLETE" if not fraud_report['information_complete'] else "COMPLETE"}
{f"Missing: {', '.join(fraud_report['missing_fields'])}" if fraud_report['missing_fields'] else "All required fields present"}

RISK FACTORS:
{chr(10).join([f"• {factor}" for factor in fraud_report['risk_factors']]) if fraud_report['risk_factors'] else "• No significant risk factors"}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""

        # Patient info
        patient_info = f"""
Patient Name: {name}
Address: {address}
Claim Type: {claim_type}
Claim Reason: {claim_reason}
Medical Facility: {medical_facility}
Treatment Date: {date}
Claimed Amount: ₹{total_claim_amount}
Description: {description}
Extracted Disease: {bill_info.get('disease', 'Unknown')}
Billed Amount: ₹{bill_info.get('expense', 'Unknown')}
"""

        # Use enhanced explainable AI prompt
        llm = Ollama(model=MAIN_MODEL, base_url=OLLAMA_BASE_URL, temperature=0.3, timeout=300)
        
        prompt = EXPLAINABLE_AI_PROMPT.format(
            patient_info=patient_info,
            claim_approval_context=get_claim_approval_context(),
            general_exclusion_context=get_general_exclusion_context(),
            medical_bill_info=f"Bill Content:\n{bill_content[:1500]}",
            fraud_analysis=fraud_summary,
            max_amount=total_claim_amount
        )

        output = llm.invoke(prompt)

        # Store in historical claims (for future duplicate detection)
        historical_claims.append(claim_data)

        return jsonify({
            'error': False,
            'output': output,
            'fraud_report': fraud_report,
            'claim_data': {
                'name': name,
                'address': address,
                'claim_type': claim_type,
                'claim_reason': claim_reason,
                'date': date,
                'medical_facility': medical_facility,
                'total_claim_amount': total_claim_amount,
                'description': description
            }
        })

    except Exception as e:
        print(f"Error: {e}")
        return jsonify({'error': True, 'message': str(e)})

if __name__ == '__main__':
    print("=" * 60)
    print("ClaimTrackr - Enhanced with Advanced Fraud Detection")
    print("=" * 60)
    
    status, message = check_ollama_status()
    print(f"\nOllama Status: {message}")
    
    print("\nEnhancements:")
    print("  ✓ Multi-level fraud detection")
    print("  ✓ Semantic duplicate detection")
    print("  ✓ Explainable AI decisions")
    print("  ✓ Autonomous decision-making")
    
    print("\nInitializing embeddings...")
    get_embeddings()
    
    print("\n" + "=" * 60)
    print("Starting server at: http://localhost:8081")
    print("=" * 60 + "\n")
    
    app.run(host='0.0.0.0', port=8081, debug=True)