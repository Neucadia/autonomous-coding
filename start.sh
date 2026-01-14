#!/bin/bash
cd "$(dirname "$0")"

echo ""
echo "========================================"
echo "  Autonomous Coding Agent"
echo "========================================"
echo ""

# Check if Claude CLI is installed
if ! command -v claude &> /dev/null; then
    echo "[ERROR] Claude CLI not found"
    echo ""
    echo "Please install Claude CLI first:"
    echo "  curl -fsSL https://claude.ai/install.sh | bash"
    echo ""
    echo "Then run this script again."
    exit 1
fi

echo "[OK] Claude CLI found"

# Load environment variables from .env files if they exist
if [ -f ".env" ]; then
    echo "[OK] Loading .env file"
    set -a
    source .env
    set +a
fi

if [ -f ".env.local" ]; then
    echo "[OK] Loading .env.local file"
    set -a
    source .env.local
    set +a
fi

# Check authentication - prefer OAuth token, allow API key with warning
#if [ -n "$CLAUDE_CODE_OAUTH_TOKEN" ]; then
#    echo "[OK] Claude authenticated (OAuth token)"
#elif [ -n "$ANTHROPIC_API_KEY" ]; then
#    echo "[!] Using ANTHROPIC_API_KEY"
#    echo ""
#    echo "WARNING: Using the Anthropic API key directly will cost significantly"
#    echo "more than using Claude Code with OAuth authentication."
#    echo ""
#    echo "For cost-effective usage, run 'claude setup-token' to create"
#    echo "a CLAUDE_CODE_OAUTH_TOKEN environment variable."
#    echo ""
#    read -p "Continue with ANTHROPIC_API_KEY? (y/n): " API_KEY_CHOICE

#    if [[ "$API_KEY_CHOICE" =~ ^[Yy]$ ]]; then
#        echo ""
#        echo "[OK] Proceeding with ANTHROPIC_API_KEY"
#    else
#        echo ""
#        echo "To use OAuth instead, unset ANTHROPIC_API_KEY and run 'claude setup-token'."
#        exit 1
#    fi
#else
#    echo "[!] Not authenticated with Claude"
#    echo ""
#    echo "Please run 'claude setup-token' to create a CLAUDE_CODE_OAUTH_TOKEN"
#    echo "environment variable, then run this script again."
#    exit 1
#fi

echo ""

# Check if venv exists, create if not
if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
fi

# Activate the virtual environment
source venv/bin/activate

# Upgrade pip in the virtual environment
pip install --upgrade pip --quiet

# Install dependencies
echo "Installing dependencies..."
pip install -r requirements.txt --quiet

# Run the app
python start.py
