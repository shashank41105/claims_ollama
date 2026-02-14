# ClaimTrackr - AI-Powered Claims Processing (Ollama Edition)

![Version](https://img.shields.io/badge/version-2.0.0-blue)
![Python](https://img.shields.io/badge/python-3.8%2B-green)
![Ollama](https://img.shields.io/badge/Ollama-Local%20AI-purple)

## 🌟 Overview

ClaimTrackr is an advanced AI-powered insurance claim processing system that runs completely locally using Ollama. This ensures data privacy, security, and no external API costs while providing intelligent claim analysis and fraud detection.

## 🚀 Key Features

- **🤖 Local AI Processing**: Uses Ollama for complete privacy and security
- **📊 Intelligent Analysis**: Automated claim validation and fraud detection
- **⚡ Fast Processing**: Optimized for quick turnaround times
- **🎨 Modern UI**: Beautiful, responsive interface with dark mode
- **💾 Vector Search**: FAISS-powered document retrieval
- **🔒 Privacy First**: All data processed locally, never leaves your system
- **📱 Mobile Responsive**: Works seamlessly on all devices

## 📋 Prerequisites

Before you begin, ensure you have the following installed:

- **Python 3.8 or higher**
- **Ollama** (Install from [https://ollama.ai](https://ollama.ai))
- **pip** (Python package manager)

## 🛠️ Installation

### Step 1: Install Ollama

```bash
# For macOS/Linux
curl -fsSL https://ollama.ai/install.sh | sh

# For Windows
# Download from https://ollama.ai/download
```

### Step 2: Pull Required Models

```bash
# Pull the main models
ollama pull llama3.1
ollama pull llama3.2
ollama pull nomic-embed-text
```

**Note**: Initial model downloads may take some time (several GB).

### Step 3: Clone and Setup Project

```bash
# Clone or download the project
cd ClaimTrackr-Ollama

# Create virtual environment (recommended)
python -m venv venv

# Activate virtual environment
# On Windows:
venv\Scripts\activate
# On macOS/Linux:
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### Step 4: Prepare Documents

```bash
# Create documents folder
mkdir documents

# Add your insurance policy PDF files to the documents folder
# Example: member_handbook.pdf, policy_terms.pdf, etc.
```

### Step 5: Create Sample Medical Bills (Optional)

If you want to test with sample data, create these sample PDFs in a `Bills` folder:

**Sample Bill Structure:**
```
APOLLO HOSPITALS
Patient Information:
- Name: John Doe
- Date of Birth: 01/01/1990
- Address: 123 Main St, City
- Phone Number: 1234567890

Service Details:
Date of Service: 02/02/2024
Diagnosis: Fever and Cold
Details: Consultation and prescribed medication

Service charges:
Doctor's fee - 1500
Medicines - 2000
Total charge - 3500
Membership Discount - 10%
Amount payable - 3150
```

## 🚦 Running the Application

### Start Ollama Service

```bash
# In a separate terminal, start Ollama
ollama serve
```

### Start ClaimTrackr

```bash
# Activate virtual environment if not already active
# venv\Scripts\activate (Windows) or source venv/bin/activate (Mac/Linux)

# Run the application
python main_BUPA_ollama.py
```

### Access the Application

Open your browser and navigate to:
```
http://localhost:8081
```

## 📖 Usage Guide

### Submitting a Claim

1. **Fill in Patient Details**
   - Patient name (required)
   - Address
   - Treatment date

2. **Select Claim Type**
   - Choose from various medical services
   - General Practitioner, Specialist, etc.

3. **Enter Claim Information**
   - Claim reason/diagnosis
   - Medical facility name
   - Claim amount

4. **Upload Medical Bill**
   - PDF format required
   - Must contain patient name, diagnosis, and charges

5. **Submit and Wait**
   - Processing typically takes 30-60 seconds
   - AI analyzes the claim for validity
   - Checks against exclusions and policy terms

### Understanding Results

The system provides:
- ✅ **Claim Status**: Accepted or Rejected
- 📊 **Verification Summary**: Information and exclusion checks
- 📝 **Executive Summary**: Overview of the decision
- 🔍 **Detailed Analysis**: Document verification and fraud detection
- 💰 **Approved Amount**: If claim is accepted

## 🏗️ System Architecture

```
┌─────────────────┐
│   Web Browser   │
│   (Frontend)    │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  Flask Server   │
│  (Backend API)  │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│     Ollama      │
│ (Local AI LLMs) │
├─────────────────┤
│  • llama3.1     │ ◄── Complex Analysis
│  • llama3.2     │ ◄── Fast Extraction
│  • nomic-embed  │ ◄── Embeddings
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  FAISS Vector   │
│    Database     │
│ (Policy Docs)   │
└─────────────────┘
```

## 🔧 Configuration

### Model Selection

You can modify the models used in `main_BUPA_ollama.py`:

```python
MAIN_MODEL = "llama3.1"      # For complex analysis
FAST_MODEL = "llama3.2"      # For quick extractions
EMBEDDING_MODEL = "nomic-embed-text"  # For embeddings
```

### Exclusion List

Customize the exclusion list in `main_BUPA_ollama.py`:

```python
general_exclusion_list = [
    "HIV/AIDS", 
    "Parkinson's disease", 
    "Alzheimer's disease",
    # Add more exclusions as needed
]
```

## 🐛 Troubleshooting

### Ollama Connection Issues

**Problem**: "Cannot connect to Ollama"

**Solutions**:
1. Ensure Ollama is running: `ollama serve`
2. Check if models are installed: `ollama list`
3. Verify Ollama is running on port 11434: `curl http://localhost:11434/api/tags`

### Model Not Found

**Problem**: "Missing models" error

**Solution**:
```bash
ollama pull llama3.1
ollama pull llama3.2
ollama pull nomic-embed-text
```

### Slow Processing

**Problem**: Claims take too long to process

**Solutions**:
1. First time processing creates embeddings (takes longer)
2. Subsequent requests use cached embeddings (faster)
3. Consider using lighter models:
   ```python
   MAIN_MODEL = "llama3.2"  # Lighter but still capable
   ```

### PDF Reading Errors

**Problem**: Cannot read uploaded PDF

**Solutions**:
1. Ensure PDF is not password-protected
2. Verify PDF contains extractable text (not scanned images)
3. Check file size is reasonable (< 10MB recommended)

### Port Already in Use

**Problem**: Port 8081 is already in use

**Solution**: Change the port in `main_BUPA_ollama.py`:
```python
app.run(host='0.0.0.0', port=8082, debug=True)  # Use different port
```

## 📊 Performance Optimization

### Caching Embeddings

The system automatically caches FAISS embeddings in the `faiss_index` folder. To rebuild:

```bash
# Delete the cache
rm -rf faiss_index

# Restart the application
python main_BUPA_ollama.py
```

### Memory Management

For systems with limited RAM:
1. Use `llama3.2` for all operations (lighter)
2. Reduce chunk size in text splitting
3. Limit concurrent requests

## 🔐 Security & Privacy

- ✅ All data processed locally
- ✅ No external API calls
- ✅ No data leaves your system
- ✅ HIPAA-compliant architecture
- ✅ Can run completely offline

## 📝 Project Structure

```
ClaimTrackr-Ollama/
├── main_BUPA_ollama.py      # Main Flask application
├── requirements.txt          # Python dependencies
├── README.md                 # This file
├── templates/
│   └── index.html           # Enhanced UI with Tailwind CSS
├── documents/               # Insurance policy PDFs
│   ├── handbook.pdf
│   └── policy.pdf
├── faiss_index/            # Cached embeddings (auto-generated)
└── Bills/                  # Sample medical bills (optional)
```

## 🎯 Roadmap

- [ ] Multi-language support
- [ ] OCR for scanned documents
- [ ] Batch claim processing
- [ ] Advanced fraud detection
- [ ] Claims analytics dashboard
- [ ] Export to PDF reports

## 🤝 Contributing

Contributions are welcome! Please feel free to submit pull requests or open issues.

## 📄 License

This project is for educational and demonstration purposes.

## 🙏 Acknowledgments

- **Ollama** for local AI capabilities
- **LangChain** for the AI framework
- **Tailwind CSS** for the beautiful UI
- **FAISS** for vector search

## 📞 Support

For issues or questions:
1. Check the Troubleshooting section
2. Review Ollama documentation: https://ollama.ai/docs
3. Open an issue on the project repository

## 🎉 Success Indicators

When everything is working correctly, you should see:

```
==============================================================
ClaimTrackr - AI-Powered Claims Processing (Ollama Edition)
==============================================================

Ollama Status: Ollama is running and all models are available

Initializing document embeddings...
Loading existing FAISS index...

==============================================================
Starting Flask server...
Access the application at: http://localhost:8081
==============================================================
```

---

**Happy Claim Processing! 🚀**
