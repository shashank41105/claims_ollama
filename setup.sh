#!/bin/bash

# ClaimTrackr Setup Script
# This script automates the setup process for ClaimTrackr

echo "======================================================"
echo "  ClaimTrackr - AI-Powered Claims Processing Setup  "
echo "======================================================"
echo ""

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Function to check if command exists
command_exists() {
    command -v "$1" >/dev/null 2>&1
}

# Check Python installation
echo -e "${YELLOW}[1/6] Checking Python installation...${NC}"
if command_exists python3; then
    PYTHON_VERSION=$(python3 --version | cut -d' ' -f2)
    echo -e "${GREEN}✓ Python $PYTHON_VERSION found${NC}"
else
    echo -e "${RED}✗ Python 3 not found. Please install Python 3.8 or higher.${NC}"
    exit 1
fi

# Check Ollama installation
echo -e "${YELLOW}[2/6] Checking Ollama installation...${NC}"
if command_exists ollama; then
    echo -e "${GREEN}✓ Ollama is installed${NC}"
else
    echo -e "${RED}✗ Ollama not found.${NC}"
    echo "Would you like to install Ollama? (y/n)"
    read -r install_ollama
    if [ "$install_ollama" = "y" ]; then
        echo "Installing Ollama..."
        curl -fsSL https://ollama.ai/install.sh | sh
    else
        echo "Please install Ollama from https://ollama.ai"
        exit 1
    fi
fi

# Check if Ollama is running
echo -e "${YELLOW}[3/6] Checking Ollama service...${NC}"
if curl -s http://localhost:11434/api/tags > /dev/null 2>&1; then
    echo -e "${GREEN}✓ Ollama service is running${NC}"
else
    echo -e "${YELLOW}⚠ Ollama service is not running${NC}"
    echo "Starting Ollama in the background..."
    nohup ollama serve > /dev/null 2>&1 &
    sleep 3
    if curl -s http://localhost:11434/api/tags > /dev/null 2>&1; then
        echo -e "${GREEN}✓ Ollama service started successfully${NC}"
    else
        echo -e "${RED}✗ Failed to start Ollama service${NC}"
        echo "Please run 'ollama serve' manually in a separate terminal"
    fi
fi

# Pull required models
echo -e "${YELLOW}[4/6] Checking and pulling required models...${NC}"
MODELS=("llama3.1" "llama3.2" "nomic-embed-text")
for model in "${MODELS[@]}"; do
    if ollama list | grep -q "$model"; then
        echo -e "${GREEN}✓ Model $model already exists${NC}"
    else
        echo -e "${YELLOW}Pulling model $model (this may take a while)...${NC}"
        ollama pull "$model"
        if [ $? -eq 0 ]; then
            echo -e "${GREEN}✓ Model $model pulled successfully${NC}"
        else
            echo -e "${RED}✗ Failed to pull model $model${NC}"
        fi
    fi
done

# Create virtual environment
echo -e "${YELLOW}[5/6] Setting up Python virtual environment...${NC}"
if [ ! -d "venv" ]; then
    python3 -m venv venv
    echo -e "${GREEN}✓ Virtual environment created${NC}"
else
    echo -e "${GREEN}✓ Virtual environment already exists${NC}"
fi

# Activate virtual environment and install dependencies
echo -e "${YELLOW}Installing Python dependencies...${NC}"
source venv/bin/activate
pip install --upgrade pip > /dev/null 2>&1
pip install -r requirements.txt
if [ $? -eq 0 ]; then
    echo -e "${GREEN}✓ Dependencies installed successfully${NC}"
else
    echo -e "${RED}✗ Failed to install dependencies${NC}"
    exit 1
fi

# Create necessary directories
echo -e "${YELLOW}[6/6] Creating necessary directories...${NC}"
mkdir -p documents
mkdir -p Bills
echo -e "${GREEN}✓ Directories created${NC}"

# Success message
echo ""
echo "======================================================"
echo -e "${GREEN}         Setup completed successfully!${NC}"
echo "======================================================"
echo ""
echo "Next steps:"
echo "1. Add your insurance policy PDF files to the 'documents' folder"
echo "2. Activate the virtual environment:"
echo "   source venv/bin/activate"
echo "3. Run the application:"
echo "   python main_BUPA_ollama.py"
echo "4. Open your browser to http://localhost:8081"
echo ""
echo -e "${YELLOW}Note: Keep Ollama running in the background${NC}"
echo "======================================================"
