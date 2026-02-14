# 🔧 ClaimTrackr Troubleshooting Guide

## Table of Contents
1. [Installation Issues](#installation-issues)
2. [Ollama Problems](#ollama-problems)
3. [Model Issues](#model-issues)
4. [Application Errors](#application-errors)
5. [Performance Problems](#performance-problems)
6. [UI/Frontend Issues](#uifrontend-issues)
7. [Document Processing](#document-processing)
8. [Network Issues](#network-issues)

---

## Installation Issues

### Python Version Error
**Problem**: "Python 3.8 or higher required"

**Solutions**:
1. Check your Python version:
   ```bash
   python --version
   # or
   python3 --version
   ```
2. Install Python 3.8+:
   - **Windows**: Download from [python.org](https://www.python.org/downloads/)
   - **Mac**: `brew install python@3.11`
   - **Linux**: `sudo apt-get install python3.11`

### Pip Install Failures
**Problem**: Dependencies fail to install

**Solutions**:
1. Upgrade pip first:
   ```bash
   python -m pip install --upgrade pip
   ```
2. Install build tools:
   - **Windows**: Install Visual C++ Build Tools
   - **Mac**: `xcode-select --install`
   - **Linux**: `sudo apt-get install build-essential`

3. Install dependencies one by one:
   ```bash
   pip install flask
   pip install langchain
   pip install PyPDF2
   # etc.
   ```

### Virtual Environment Issues
**Problem**: Cannot activate virtual environment

**Solutions**:

**Windows PowerShell**:
```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
venv\Scripts\Activate.ps1
```

**Windows CMD**:
```cmd
venv\Scripts\activate.bat
```

**Mac/Linux**:
```bash
source venv/bin/activate
```

---

## Ollama Problems

### Cannot Connect to Ollama
**Problem**: "Cannot connect to Ollama" error

**Diagnostic Steps**:
```bash
# Check if Ollama is installed
ollama --version

# Check if Ollama service is running
curl http://localhost:11434/api/tags

# Check Ollama process
# Windows:
tasklist | findstr ollama
# Mac/Linux:
ps aux | grep ollama
```

**Solutions**:

1. **Start Ollama service**:
   ```bash
   # In a new terminal:
   ollama serve
   ```

2. **Check port availability**:
   ```bash
   # Windows:
   netstat -ano | findstr :11434
   # Mac/Linux:
   lsof -i :11434
   ```

3. **Kill existing Ollama process**:
   ```bash
   # Windows:
   taskkill /F /IM ollama.exe
   # Mac/Linux:
   pkill ollama
   ```

4. **Reinstall Ollama**:
   - **Mac/Linux**:
     ```bash
     curl -fsSL https://ollama.ai/install.sh | sh
     ```
   - **Windows**: Download installer from [ollama.ai](https://ollama.ai)

### Ollama Not Installed
**Problem**: "ollama: command not found"

**Solutions**:

**Mac/Linux**:
```bash
curl -fsSL https://ollama.ai/install.sh | sh
```

**Windows**:
1. Download from [https://ollama.ai/download](https://ollama.ai/download)
2. Run installer
3. Restart terminal

---

## Model Issues

### Models Not Found
**Problem**: "Missing models: llama3.1, llama3.2, nomic-embed-text"

**Solutions**:

1. **Pull all required models**:
   ```bash
   ollama pull llama3.1
   ollama pull llama3.2
   ollama pull nomic-embed-text
   ```

2. **Verify installation**:
   ```bash
   ollama list
   ```

3. **Expected output**:
   ```
   NAME                    ID              SIZE    MODIFIED
   llama3.1:latest        xxx             4.7 GB  x hours ago
   llama3.2:latest        xxx             2.0 GB  x hours ago
   nomic-embed-text:latest xxx            274 MB  x hours ago
   ```

### Model Download Fails
**Problem**: Model download interrupted or fails

**Solutions**:

1. **Check disk space**:
   ```bash
   # Need at least 10GB free
   df -h
   ```

2. **Check internet connection**:
   ```bash
   ping ollama.ai
   ```

3. **Resume download**:
   ```bash
   # Ollama automatically resumes
   ollama pull llama3.1
   ```

4. **Clear Ollama cache**:
   ```bash
   # Mac/Linux
   rm -rf ~/.ollama/models
   
   # Windows
   rmdir /s %USERPROFILE%\.ollama\models
   ```

### Model Taking Too Long
**Problem**: Model responses are very slow

**Solutions**:

1. **Use lighter model**:
   Edit `main_BUPA_ollama.py`:
   ```python
   MAIN_MODEL = "llama3.2"  # Instead of llama3.1
   ```

2. **Check system resources**:
   ```bash
   # Mac/Linux
   htop
   
   # Windows
   # Open Task Manager (Ctrl+Shift+Esc)
   ```

3. **Reduce context size**:
   In `main_BUPA_ollama.py`, reduce `max_tokens`:
   ```python
   temperature=0.3,
   max_tokens=1500  # Reduced from 2500
   ```

---

## Application Errors

### Port Already in Use
**Problem**: "Address already in use" or port 8081 error

**Solutions**:

1. **Find and kill process using port**:
   ```bash
   # Windows:
   netstat -ano | findstr :8081
   taskkill /PID <PID> /F
   
   # Mac/Linux:
   lsof -ti:8081 | xargs kill -9
   ```

2. **Change port**:
   Edit `main_BUPA_ollama.py` (last line):
   ```python
   app.run(host='0.0.0.0', port=8082, debug=True)
   ```

### Import Errors
**Problem**: "ModuleNotFoundError: No module named 'xxx'"

**Solutions**:

1. **Ensure virtual environment is activated**:
   ```bash
   # Should see (venv) in prompt
   ```

2. **Reinstall dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

3. **Install specific missing module**:
   ```bash
   pip install langchain_community
   ```

### Flask Template Not Found
**Problem**: "TemplateNotFound: index.html"

**Solutions**:

1. **Verify folder structure**:
   ```
   ClaimTrackr-Ollama/
   ├── main_BUPA_ollama.py
   └── templates/
       └── index.html
   ```

2. **Check file exists**:
   ```bash
   ls templates/index.html
   ```

3. **Verify Flask template folder setting** in `main_BUPA_ollama.py`:
   ```python
   app = Flask(__name__, template_folder='templates')
   ```

---

## Performance Problems

### Slow First Request
**Problem**: First claim takes 2-3 minutes to process

**Explanation**: Normal behavior - system is:
1. Loading models into memory
2. Creating document embeddings
3. Initializing FAISS index

**Solutions**:
- Subsequent requests will be much faster (30-60 seconds)
- Consider keeping application running
- Pre-load by making a test claim on startup

### Embeddings Taking Too Long
**Problem**: "Initializing document embeddings" hangs

**Solutions**:

1. **Check documents folder**:
   ```bash
   # Should not have too many large PDFs
   ls -lh documents/
   ```

2. **Limit document size**:
   - Keep PDFs under 10MB each
   - Maximum 10-20 documents recommended

3. **Delete and rebuild cache**:
   ```bash
   rm -rf faiss_index
   python main_BUPA_ollama.py
   ```

### High Memory Usage
**Problem**: Application using too much RAM

**Solutions**:

1. **Use smaller models**:
   ```python
   MAIN_MODEL = "llama3.2"  # ~2GB RAM
   # Instead of llama3.1 (~4.7GB RAM)
   ```

2. **Reduce chunk size**:
   ```python
   chunk_size=500,  # Reduced from 1000
   chunk_overlap=100  # Reduced from 200
   ```

3. **Limit concurrent requests**:
   Add rate limiting in Flask

---

## UI/Frontend Issues

### Page Not Loading
**Problem**: Browser shows "Cannot connect" or blank page

**Solutions**:

1. **Verify application is running**:
   - Check terminal for errors
   - Should see "Running on http://0.0.0.0:8081"

2. **Try different browser**:
   - Chrome, Firefox, Edge, Safari

3. **Clear browser cache**:
   - Ctrl+Shift+Delete (Windows/Linux)
   - Cmd+Shift+Delete (Mac)

4. **Check URL**:
   - Try `http://localhost:8081`
   - Try `http://127.0.0.1:8081`

### Dark Mode Not Working
**Problem**: Dark mode toggle doesn't work

**Solutions**:

1. **Clear localStorage**:
   - Open browser console (F12)
   - Type: `localStorage.clear()`
   - Refresh page

2. **Check JavaScript**:
   - Open console (F12)
   - Look for errors

### Loading Modal Stuck
**Problem**: Loading screen doesn't close

**Solutions**:

1. **Check browser console** for errors
2. **Refresh page** (may lose progress)
3. **Check if backend crashed** (look at terminal)
4. **Wait longer** - complex claims take time

---

## Document Processing

### PDF Not Reading
**Problem**: "Unable to read the medical bill"

**Solutions**:

1. **Check PDF format**:
   - Ensure it's a real PDF, not image
   - Try opening in Adobe Reader

2. **Check PDF protection**:
   - Remove password protection
   - Ensure PDF is not encrypted

3. **Test with sample PDF**:
   - Create simple text PDF
   - Verify it works

4. **Check file size**:
   - Keep under 10MB
   - Compress if too large

### No Text Extracted
**Problem**: PDF uploads but no text is extracted

**Solutions**:

1. **PDF might be scanned image**:
   - Use OCR tool to convert
   - Or create searchable PDF

2. **Check PDF encoding**:
   - Try exporting to new PDF
   - Use different PDF creator

### Policy Documents Not Loading
**Problem**: "No policy documents available"

**Solutions**:

1. **Verify documents folder**:
   ```bash
   ls documents/
   # Should show PDF files
   ```

2. **Check file extensions**:
   - Must be `.pdf` (lowercase)
   - Not `.PDF` or `.Pdf`

3. **Rebuild embeddings**:
   ```bash
   rm -rf faiss_index
   python main_BUPA_ollama.py
   ```

---

## Network Issues

### Cannot Access from Other Devices
**Problem**: Want to access from phone/tablet on same network

**Solutions**:

1. **Find your computer's IP**:
   ```bash
   # Windows:
   ipconfig
   # Mac/Linux:
   ifconfig
   ```

2. **Access using IP**:
   ```
   http://192.168.1.x:8081
   ```

3. **Check firewall**:
   - Allow port 8081 in firewall
   - **Windows**: Windows Defender Firewall
   - **Mac**: System Preferences > Security > Firewall

### CORS Errors
**Problem**: "CORS policy" errors in browser console

**Solutions**:

1. **Add CORS support**:
   ```bash
   pip install flask-cors
   ```

2. **Update `main_BUPA_ollama.py`**:
   ```python
   from flask_cors import CORS
   
   app = Flask(__name__)
   CORS(app)
   ```

---

## Debug Mode

### Enable Detailed Logging

Add to `main_BUPA_ollama.py`:

```python
import logging

logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('claimtrackr.log'),
        logging.StreamHandler()
    ]
)
```

### Check Logs

```bash
# View real-time logs
tail -f claimtrackr.log

# Search for errors
grep ERROR claimtrackr.log
```

---

## Getting More Help

### Collect Debug Information

When reporting issues, include:

1. **System Information**:
   ```bash
   python --version
   ollama --version
   pip list | grep langchain
   ```

2. **Error Messages**:
   - Full traceback from terminal
   - Browser console errors (F12)

3. **Configuration**:
   - Python version
   - Operating system
   - Ollama version
   - Model versions

### Community Resources

- Ollama Docs: https://ollama.ai/docs
- LangChain Docs: https://python.langchain.com
- Flask Docs: https://flask.palletsprojects.com

---

## Emergency Reset

If everything fails, complete reset:

```bash
# 1. Stop all processes
# Kill Ollama and Flask

# 2. Remove virtual environment
rm -rf venv

# 3. Clear caches
rm -rf faiss_index
rm -rf __pycache__

# 4. Fresh start
python -m venv venv
source venv/bin/activate  # or venv\Scripts\activate on Windows
pip install -r requirements.txt
python main_BUPA_ollama.py
```

---

**Still stuck? Check the QUICKSTART.md or README.md for more guidance!**
