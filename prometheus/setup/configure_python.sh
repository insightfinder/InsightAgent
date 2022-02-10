#!/usr/bin/env bash

ORIGIN="$(pwd)"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" &>/dev/null && pwd)"

# Check if python3 and pip3 installed
if [[ -z $(command -v python3) ]]; then
  echo "Python3 not installed. Install and run again. Exiting..."
  exit 1
fi
if [[ -z $(command -v pip3) ]]; then
  echo "Pip3 not installed. Install and run again. Exiting..."
  exit 1
fi

# Change to agent directory
cd $SCRIPT_DIR && cd ..

# Check if virtualenv is configured, if not set it up
if [[ ! -d venv ]]; then
  echo "Setting up virtual env"
  mkdir venv
  python3 -m venv ./venv
else
  echo "Virtual env detected: ./venv/"
fi

# Install python requirements
if [[ -f requirements.txt ]]; then
  source ./venv/bin/activate
  pip3 install -r requirements.txt --no-index --find-links=./offline/pip/packages/
else
  echo "Unable to install requirements: missing requirements.txt"
fi

# Set up conf.d/config.ini from template
if [[ ! -f conf.d/config.ini ]]; then
  cp conf.d/config.ini.template conf.d/config.ini
fi

# Return to original directory
cd $ORIGIN
