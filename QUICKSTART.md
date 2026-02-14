# 🚀 ClaimTrackr Quick Start Guide

## ⚡ Super Quick Setup (5 Minutes)

### Prerequisites
- Python 3.8+ installed
- Ollama installed (https://ollama.ai)

### Step-by-Step Setup

#### 1️⃣ Install Ollama Models
```bash
ollama pull llama3.1
ollama pull llama3.2
ollama pull nomic-embed-text
```
*This takes 5-10 minutes for first-time downloads*

#### 2️⃣ Start Ollama Service
```bash
# Open a new terminal and run:
ollama serve
```
*Keep this terminal open*

#### 3️⃣ Setup Python Environment
```bash
# In your project directory:

# Create virtual environment
python -m venv venv

# Activate it:
# Windows:
venv\Scripts\activate
# Mac/Linux:
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

#### 4️⃣ Add Sample Documents
```bash
# Create documents folder
mkdir documents

# Convert sample_policy.txt to PDF and place in documents folder
# Or use your own insurance policy PDFs
```

#### 5️⃣ Run the Application
```bash
python main_BUPA_ollama.py
```

#### 6️⃣ Open Browser
Navigate to: **http://localhost:8081**

---

## 🎯 Testing the System

### Use Sample Medical Bills

Create a test PDF with this content:

```
APOLLO HOSPITALS
Patient Information:
- Name: John Doe
- Date of Birth: 01/01/1990
- Address: 123 Main Street
- Phone Number: 9876543210

Service Details:
Date of Service: 02/02/2024
Diagnosis: Common Cold and Fever
Details: Prescribed medication as per prescription

Service charges:
Doctor's fee - 1500
Medicines - 2000
Total charge - 3500
Membership Discount - 10%
Amount payable - 3150
```

### Fill the Form
1. **Patient Name**: John Doe
2. **Claim Type**: General Practitioner
3. **Claim Reason**: Cold and Fever
4. **Address**: 123 Main Street
5. **Date**: 02/02/2024
6. **Medical Facility**: Apollo Hospital
7. **Claim Amount**: 3150
8. **Upload**: Your test PDF
9. **Description**: Routine consultation for cold

### Expected Result
- Processing time: 30-60 seconds
- Status: **ACCEPTED** (if disease not in exclusion list)
- Approved amount shown in report

---

## 🔧 Common Issues & Quick Fixes

### Issue: "Cannot connect to Ollama"
**Fix**: Make sure Ollama is running
```bash
ollama serve
```

### Issue: "Missing models"
**Fix**: Pull the required models
```bash
ollama pull llama3.1
ollama pull llama3.2
ollama pull nomic-embed-text
```

### Issue: "No policy documents found"
**Fix**: Add PDF files to the `documents` folder

### Issue: Port 8081 already in use
**Fix**: Change port in `main_BUPA_ollama.py` (line at bottom)
```python
app.run(host='0.0.0.0', port=8082, debug=True)  # Changed to 8082
```

---

## 💡 Pro Tips

### 1. First Run Takes Longer
- System creates embeddings on first run
- Subsequent runs are much faster

### 2. Keep Ollama Running
- Always keep `ollama serve` running in background
- On Windows, you can run it as a service

### 3. Sample Documents
- Add multiple policy documents for better coverage
- System automatically indexes all PDFs in `documents` folder

### 4. Dark Mode
- Click the moon icon in top-right corner
- Preference is saved automatically

### 5. Viewing Detailed Logs
Run with debug output:
```bash
python main_BUPA_ollama.py --debug
```

---

## 📊 Understanding the Results

### ✅ Accepted Claim
- Green status indicator
- Approved amount displayed
- All verification criteria passed

### ❌ Rejected Claim
- Red status indicator
- Clear rejection reason
- Reference to policy sections

### Verification Checks
1. **INFORMATION**: All required documents provided?
2. **EXCLUSION**: Disease in exclusion list?
3. **AMOUNT**: Claimed amount ≤ billed amount?

---

## 🎨 UI Features

### Modern Interface
- **Dark Mode**: Toggle in top-right
- **Responsive**: Works on mobile and desktop
- **Real-time Status**: Shows Ollama connectivity

### Loading Indicators
- Progress messages during processing
- Estimated time remaining
- Can't be closed during processing

### Result Modal
- Detailed claim analysis
- Print-friendly format
- Easy to share

---

## 🔄 Updating the System

### Update Models
```bash
ollama pull llama3.1
ollama pull llama3.2
```

### Update Dependencies
```bash
pip install --upgrade -r requirements.txt
```

### Clear Cache
```bash
# Delete embeddings cache
rm -rf faiss_index

# Restart application
python main_BUPA_ollama.py
```

---

## 📞 Getting Help

### Check Status
Visit: http://localhost:8081/check_status

### View Logs
Application logs appear in terminal

### Test Ollama
```bash
curl http://localhost:11434/api/tags
```

### Verify Models
```bash
ollama list
```

---

## ✨ What Makes This Special?

✅ **100% Private**: All processing happens locally  
✅ **No API Costs**: Free to run as much as you want  
✅ **Fast**: Optimized for quick responses  
✅ **Secure**: HIPAA-compliant architecture  
✅ **Offline**: Works without internet  
✅ **Modern UI**: Beautiful, easy to use  

---

**You're all set! Start processing claims with AI! 🎉**

For detailed documentation, see: [README.md](README.md)
