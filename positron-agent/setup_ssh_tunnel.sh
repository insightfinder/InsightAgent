#!/bin/bash
# filepath: /home/mustafa/Documents/InsightFinderRepos/zabbix-test/setup_ssh_tunnel.sh

# SSH connection parameters
SSH_USER=""
SSH_HOST=""
SSH_PORT=""
SSH_PASSWORD=""
LOCAL_PORT=""
REMOTE_HOST=""
REMOTE_PORT=""

# Function to check if port forwarding is active
check_port_forwarding() {
    timeout 5 bash -c "</dev/tcp/127.0.0.1/$LOCAL_PORT" >/dev/null 2>&1
    return $?
}

# Function to check network connectivity to SSH host
check_ssh_connectivity() {
    echo "Testing connectivity to SSH host $SSH_HOST:$SSH_PORT..."
    timeout 10 bash -c "</dev/tcp/$SSH_HOST/$SSH_PORT" >/dev/null 2>&1
    if [ $? -eq 0 ]; then
        echo "✓ SSH host is reachable"
        return 0
    else
        echo "✗ Cannot reach SSH host $SSH_HOST:$SSH_PORT"
        return 1
    fi
}

# Function to kill existing SSH tunnels
cleanup_existing_tunnels() {
    echo "Cleaning up existing SSH tunnels..."
    pkill -f "ssh.*-L.*$LOCAL_PORT:" >/dev/null 2>&1
    sleep 2
}

# Function to setup SSH port forwarding
setup_ssh_tunnel() {
    echo "Setting up SSH port forwarding from EC2..."
    
    # Check if sshpass is available
    if ! command -v sshpass &> /dev/null; then
        echo "Error: sshpass not found. Installing..."
        sudo dnf install -y sshpass
        if [ $? -ne 0 ]; then
            echo "Failed to install sshpass"
            exit 1
        fi
    fi
    
    # Check network connectivity first
    if ! check_ssh_connectivity; then
        echo "Network connectivity test failed. Check:"
        echo "1. EC2 security groups allow outbound traffic on port $SSH_PORT"
        echo "2. SSH host $SSH_HOST is accessible from this EC2 instance"
        return 1
    fi
    
    # Clean up any existing tunnels first
    cleanup_existing_tunnels
    
    echo "Establishing SSH tunnel: localhost:$LOCAL_PORT -> $REMOTE_HOST:$REMOTE_PORT via $SSH_USER@$SSH_HOST:$SSH_PORT"
    
    # Start SSH port forwarding in background with EC2-optimized settings
    sshpass -p "$SSH_PASSWORD" ssh -f -N -L "$LOCAL_PORT:$REMOTE_HOST:$REMOTE_PORT" \
        "$SSH_USER@$SSH_HOST" -p "$SSH_PORT" \
        -o StrictHostKeyChecking=no \
        -o UserKnownHostsFile=/dev/null \
        -o ServerAliveInterval=30 \
        -o ServerAliveCountMax=6 \
        -o ConnectTimeout=30 \
        -o TCPKeepAlive=yes \
        -o ExitOnForwardFailure=yes \
        -o GatewayPorts=no
    
    SSH_EXIT_CODE=$?
    
    if [ $SSH_EXIT_CODE -ne 0 ]; then
        echo "SSH command failed with exit code $SSH_EXIT_CODE"
        return 1
    fi
    
    # Wait for connection to establish
    echo "Waiting for tunnel to establish..."
    sleep 8
    
    # Verify the connection multiple times
    for i in {1..5}; do
        echo "Testing connection attempt $i/5..."
        if check_port_forwarding; then
            echo "✓ SSH port forwarding established successfully on port $LOCAL_PORT"
            
            # Show active SSH processes for debugging
            echo "Active SSH tunnel processes:"
            pgrep -f "ssh.*-L.*$LOCAL_PORT:" | head -3 | xargs ps -p 2>/dev/null || echo "No processes found"
            
            # Test actual HTTP connectivity through tunnel
            echo "Testing HTTP connectivity through tunnel..."
            if timeout 10 curl -s -o /dev/null -w "%{http_code}" "https://127.0.0.1:$LOCAL_PORT/" | grep -q "200\|302\|404"; then
                echo "✓ HTTP tunnel is working"
                return 0
            else
                echo "⚠ SSH tunnel established but HTTP test failed"
                return 0  # Still return success as tunnel is up
            fi
        fi
        echo "Attempt $i failed, retrying in 3 seconds..."
        sleep 3
    done
    
    echo "✗ Failed to establish SSH port forwarding after 5 attempts"
    
    # Debugging information
    echo "=== Debugging Information ==="
    echo "EC2 Instance networking:"
    curl -s http://169.254.169.254/latest/meta-data/public-ipv4 2>/dev/null && echo " (Public IP)" || echo "No public IP"
    curl -s http://169.254.169.254/latest/meta-data/local-ipv4 2>/dev/null && echo " (Private IP)" || echo "No private IP"
    
    echo "SSH processes:"
    pgrep -f "ssh.*-L" | xargs ps -p 2>/dev/null || echo "No SSH processes found"
    
    echo "Network connections on port $LOCAL_PORT:"
    netstat -tlnp 2>/dev/null | grep ":$LOCAL_PORT " || echo "No connections found"
    
    return 1
}

# Main execution
echo "=== SSH Tunnel Setup Script for EC2 ==="
echo "Target: $SSH_USER@$SSH_HOST:$SSH_PORT"
echo "Tunnel: localhost:$LOCAL_PORT -> $REMOTE_HOST:$REMOTE_PORT"

if check_port_forwarding; then
    echo "✓ SSH port forwarding is already active on port $LOCAL_PORT"
    exit 0
else
    echo "SSH port forwarding not detected, setting up..."
    setup_ssh_tunnel
    exit $?
fi