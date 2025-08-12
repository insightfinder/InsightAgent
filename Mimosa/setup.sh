#!/bin/bash

echo "Mimosa Agent Setup Script"
echo "=========================="

# Check if Python 3 is available
if ! command -v python3 &> /dev/null; then
    echo "❌ Python 3 is not installed. Please install Python 3.6 or higher."
    exit 1
fi

echo "✅ Python 3 found: $(python3 --version)"

# Check if pip is available
if ! command -v pip3 &> /dev/null; then
    echo "❌ pip3 is not installed. Please install pip3."
    exit 1
fi

echo "✅ pip3 found"

# Install required packages
echo ""
echo "Installing required Python packages..."
pip3 install -r requirements.txt

if [ $? -eq 0 ]; then
    echo "✅ Python packages installed successfully"
else
    echo "❌ Failed to install Python packages"
    exit 1
fi

# Create config file if it doesn't exist
if [ ! -f "conf.d/config.ini" ]; then
    echo ""
    echo "Creating configuration file..."
    cp conf.d/config.ini.template conf.d/config.ini
    echo "✅ Configuration file created at conf.d/config.ini"
    echo ""
    echo "⚠️  IMPORTANT: Please edit conf.d/config.ini with your Mimosa device and InsightFinder settings before running the agent."
else
    echo "✅ Configuration file already exists"
fi

# Make scripts executable
chmod +x getmessages_mimosa.py
chmod +x test_connection.py

echo ""
echo "Setup complete! 🎉"
echo ""
echo "Next steps:"
echo "1. Edit conf.d/config.ini with your settings"
echo "2. Test the connection: python3 test_connection.py"
echo "3. Run the agent: python3 getmessages_mimosa.py"
echo ""
echo "For more information, see README.md"
