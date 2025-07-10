#!/bin/bash

# Enhanced startup script for Zabbix Webhook Agent with systemd service management

set -e  # Exit on any error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SERVICE_NAME="zabbix-webhook-agent"
SERVICE_FILE="$SCRIPT_DIR/config/systemd/zabbix-webhook-agent.service"
SYSTEMD_SERVICE_PATH="/etc/systemd/system/$SERVICE_NAME.service"

# Function to print colored output
print_status() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Function to check if running as root
check_root() {
    if [[ $EUID -eq 0 ]]; then
        print_error "This script should not be run as root for security reasons."
        print_status "Run without sudo. The script will ask for sudo when needed."
        exit 1
    fi
}

# Function to check if service is running
is_service_running() {
    systemctl is-active --quiet "$SERVICE_NAME" 2>/dev/null
}

# Function to check if service exists
service_exists() {
    systemctl list-unit-files --type=service | grep -q "^$SERVICE_NAME.service"
}

# Function to get current user and group
get_user_info() {
    CURRENT_USER=$(whoami)
    CURRENT_GROUP=$(id -gn)
    print_status "Current user: $CURRENT_USER, group: $CURRENT_GROUP"
}

# Function to setup virtual environment
setup_venv() {
    if [ ! -d "venv" ]; then
        print_status "Creating virtual environment..."
        python3 -m venv venv
        print_success "Virtual environment created"
    else
        print_status "Virtual environment already exists"
    fi

    # Activate virtual environment
    source venv/bin/activate
    
    # Verify we're in the virtual environment
    if [[ "$VIRTUAL_ENV" != *"venv" ]]; then
        print_error "Failed to activate virtual environment"
        exit 1
    fi
    
    print_status "Using Python: $(which python)"
    print_status "Using pip: $(which pip)"
    
    # Install/update dependencies in virtual environment (not user site-packages)
    print_status "Installing/updating dependencies in virtual environment..."
    pip install --upgrade pip
    pip install --no-user -r requirements.txt
    
    # Verify uvicorn is installed in venv
    if [ ! -f "venv/bin/uvicorn" ]; then
        print_error "uvicorn not found in virtual environment after installation"
        print_status "Attempting to reinstall uvicorn..."
        pip install --no-user --force-reinstall uvicorn[standard]
    fi
    
    if [ -f "venv/bin/uvicorn" ]; then
        print_success "Dependencies installed successfully in virtual environment"
        print_status "uvicorn location: $(realpath venv/bin/uvicorn)"
    else
        print_error "Failed to install uvicorn in virtual environment"
        exit 1
    fi
}

# Function to clean and recreate virtual environment
clean_venv() {
    print_status "Cleaning virtual environment..."
    if [ -d "venv" ]; then
        print_status "Removing existing virtual environment..."
        rm -rf venv
    fi
    setup_venv
}

# Function to setup environment file
setup_env() {
    if [ ! -f ".env" ]; then
        if [ -f ".env.example" ]; then
            print_warning ".env file not found. Copying from .env.example..."
            cp .env.example .env
            print_warning "Please edit .env file with your configuration."
            return 1
        else
            print_error ".env.example file not found. Cannot create .env file."
            exit 1
        fi
    else
        print_status ".env file exists"
    fi
    return 0
}

# Function to create systemd service file
setup_systemd_service() {
    if [ ! -f "$SERVICE_FILE" ]; then
        print_error "Service template file not found at $SERVICE_FILE"
        exit 1
    fi

    print_status "Setting up systemd service..."
    
    # Create temporary service file with correct paths
    TEMP_SERVICE=$(mktemp)
    sed -e "s|USER_PLACEHOLDER|$CURRENT_USER|g" \
        -e "s|GROUP_PLACEHOLDER|$CURRENT_GROUP|g" \
        -e "s|WORKING_DIR_PLACEHOLDER|$SCRIPT_DIR|g" \
        "$SERVICE_FILE" > "$TEMP_SERVICE"

    # Check if service file needs to be installed or updated
    if [ ! -f "$SYSTEMD_SERVICE_PATH" ] || ! cmp -s "$TEMP_SERVICE" "$SYSTEMD_SERVICE_PATH"; then
        print_status "Installing/updating systemd service file..."
        sudo cp "$TEMP_SERVICE" "$SYSTEMD_SERVICE_PATH"
        sudo systemctl daemon-reload
        print_success "Service file installed"
    else
        print_status "Service file is up to date"
    fi

    rm "$TEMP_SERVICE"

    # Enable service if not already enabled
    if ! systemctl is-enabled --quiet "$SERVICE_NAME" 2>/dev/null; then
        print_status "Enabling service to start on boot..."
        sudo systemctl enable "$SERVICE_NAME"
        print_success "Service enabled"
    else
        print_status "Service is already enabled"
    fi
}

# Function to start the service
start_service() {
    if is_service_running; then
        print_success "Service is already running"
        print_status "Service status:"
        systemctl status "$SERVICE_NAME" --no-pager -l
    else
        print_status "Starting service..."
        sudo systemctl start "$SERVICE_NAME"
        sleep 2
        
        if is_service_running; then
            print_success "Service started successfully"
        else
            print_error "Failed to start service"
            print_status "Check service logs:"
            sudo journalctl -u "$SERVICE_NAME" --no-pager -l -n 20
            exit 1
        fi
    fi
}

# Function to stop the service
stop_service() {
    if is_service_running; then
        print_status "Stopping service..."
        sudo systemctl stop "$SERVICE_NAME"
        print_success "Service stopped"
    else
        print_status "Service is not running"
    fi
}

# Function to restart the service
restart_service() {
    print_status "Restarting service..."
    sudo systemctl restart "$SERVICE_NAME"
    sleep 2
    
    if is_service_running; then
        print_success "Service restarted successfully"
    else
        print_error "Failed to restart service"
        exit 1
    fi
}

# Function to show service status
show_status() {
    if service_exists; then
        print_status "Service status:"
        systemctl status "$SERVICE_NAME" --no-pager -l
        echo
        print_status "Recent logs:"
        sudo journalctl -u "$SERVICE_NAME" --no-pager -l -n 10
    else
        print_warning "Service is not installed"
    fi
}

# Function to show logs
show_logs() {
    if service_exists; then
        print_status "Showing service logs (last 50 lines):"
        sudo journalctl -u "$SERVICE_NAME" --no-pager -l -n 50
    else
        print_warning "Service is not installed"
    fi
}

# Function to run in development mode
run_dev() {
    print_status "Running in development mode..."
    
    # Setup environment
    setup_venv
    if ! setup_env; then
        print_error "Please configure .env file before running in development mode"
        exit 1
    fi

    # Activate virtual environment
    source venv/bin/activate
    
    # Start the server in development mode
    print_status "Starting FastAPI server in development mode..."
    uvicorn main:app --host 0.0.0.0 --port 80 --reload
}

# Main script logic
main() {
    echo "==============================================="
    echo "     Zabbix Webhook Agent Management Script    "
    echo "==============================================="
    echo

    # Check if not running as root
    check_root
    
    # Get user information
    get_user_info
    
    # Change to script directory
    cd "$SCRIPT_DIR"

    # Parse command line arguments
    case "${1:-start}" in
        "start")
            print_status "Starting Zabbix Webhook Agent..."
            setup_venv
            if ! setup_env; then
                print_error "Please configure .env file before starting the service"
                exit 1
            fi
            setup_systemd_service
            start_service
            print_success "Zabbix Webhook Agent is running as a systemd service"
            print_status "Use 'sudo systemctl status $SERVICE_NAME' to check status"
            print_status "Use 'sudo journalctl -u $SERVICE_NAME -f' to follow logs"
            ;;
        "stop")
            stop_service
            ;;
        "restart")
            setup_venv
            setup_systemd_service
            restart_service
            ;;
        "status")
            show_status
            ;;
        "logs")
            show_logs
            ;;
        "dev")
            run_dev
            ;;
        "install")
            print_status "Installing Zabbix Webhook Agent..."
            setup_venv
            if ! setup_env; then
                print_warning "Environment file created. Please configure it and run the script again."
                exit 0
            fi
            setup_systemd_service
            print_success "Zabbix Webhook Agent installed successfully"
            print_status "Run './start.sh start' to start the service"
            ;;
        "reinstall")
            print_status "Reinstalling Zabbix Webhook Agent (clean install)..."
            clean_venv
            if ! setup_env; then
                print_warning "Environment file created. Please configure it and run the script again."
                exit 0
            fi
            setup_systemd_service
            print_success "Zabbix Webhook Agent reinstalled successfully"
            print_status "Run './start.sh start' to start the service"
            ;;
        "uninstall")
            print_status "Uninstalling Zabbix Webhook Agent..."
            stop_service
            if service_exists; then
                sudo systemctl disable "$SERVICE_NAME"
                sudo rm -f "$SYSTEMD_SERVICE_PATH"
                sudo systemctl daemon-reload
                print_success "Service uninstalled"
            fi
            ;;
        "help"|"-h"|"--help")
            echo "Usage: $0 [COMMAND]"
            echo
            echo "Commands:"
            echo "  start     Start the service (default)"
            echo "  stop      Stop the service"
            echo "  restart   Restart the service"
            echo "  status    Show service status"
            echo "  logs      Show service logs"
            echo "  dev       Run in development mode (no systemd)"
            echo "  install   Install and setup the service"
            echo "  reinstall Clean install (removes venv and reinstalls)"
            echo "  uninstall Remove the service"
            echo "  help      Show this help message"
            echo
            exit 0
            ;;
        *)
            print_error "Unknown command: $1"
            print_status "Use '$0 help' for usage information"
            exit 1
            ;;
    esac
}

# Run main function
main "$@"
