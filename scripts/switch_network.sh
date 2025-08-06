#!/bin/bash
# Network switching utility for PortoAPI

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
ENV_FILE="$PROJECT_ROOT/.env"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Function to print colored output
print_status() {
    echo -e "${GREEN}✅${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}⚠️${NC} $1"
}

print_error() {
    echo -e "${RED}❌${NC} $1"
}

print_info() {
    echo -e "${BLUE}ℹ️${NC} $1"
}

# Function to update .env file
update_env() {
    local key="$1"
    local value="$2"
    
    if [ -f "$ENV_FILE" ]; then
        # Check if key exists
        if grep -q "^${key}=" "$ENV_FILE"; then
            # Update existing key
            sed -i "s/^${key}=.*/${key}=${value}/" "$ENV_FILE"
        else
            # Add new key
            echo "${key}=${value}" >> "$ENV_FILE"
        fi
    else
        print_warning ".env file not found, creating new one"
        echo "${key}=${value}" > "$ENV_FILE"
    fi
}

# Function to switch to testnet (Nile)
switch_to_testnet() {
    print_info "Switching to TRON Nile Testnet (Development)..."
    
    update_env "TRON_NETWORK" "testnet"
    update_env "TRON_LOCAL_NODE_ENABLED" "true"
    
    print_status "Switched to Nile Testnet"
    print_info "Using local node: http://192.168.86.154:8090"
    print_info "Remote fallback: https://nile.trongrid.io"
    
    echo ""
    print_info "For development setup:"
    echo "  1. Get test TRX: https://nileex.io/join/getJoinPage"
    echo "  2. Generate wallet: python scripts/generate_test_wallet.py"
    echo "  3. Test network: python scripts/test_network_nodes.py"
}

# Function to switch to mainnet
switch_to_mainnet() {
    print_warning "Switching to TRON Mainnet (Production)..."
    read -p "Are you sure you want to switch to mainnet? (y/N): " -n 1 -r
    echo
    
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        update_env "TRON_NETWORK" "mainnet"
        update_env "TRON_LOCAL_NODE_ENABLED" "true"
        
        print_status "Switched to Mainnet"
        print_info "Using local node: http://192.168.86.20:8090"
        print_info "Remote fallback: https://api.trongrid.io"
        
        echo ""
        print_warning "You are now on MAINNET - real TRX will be used!"
        print_info "Make sure your GAS_WALLET_PRIVATE_KEY has real TRX"
    else
        print_info "Cancelled mainnet switch"
    fi
}

# Function to show current status
show_status() {
    if [ ! -f "$ENV_FILE" ]; then
        print_error ".env file not found"
        return 1
    fi
    
    local network=$(grep "^TRON_NETWORK=" "$ENV_FILE" 2>/dev/null | cut -d'=' -f2 || echo "not set")
    local local_enabled=$(grep "^TRON_LOCAL_NODE_ENABLED=" "$ENV_FILE" 2>/dev/null | cut -d'=' -f2 || echo "not set")
    
    echo "🔍 Current PortoAPI Network Configuration"
    echo "==========================================="
    echo "Network: $network"
    echo "Local Node Enabled: $local_enabled"
    
    if [ "$network" = "mainnet" ]; then
        local mainnet_node=$(grep "^TRON_MAINNET_LOCAL_FULL_NODE=" "$ENV_FILE" 2>/dev/null | cut -d'=' -f2 || echo "not configured")
        echo "Local Node: $mainnet_node"
        echo "Remote Fallback: https://api.trongrid.io"
    elif [ "$network" = "testnet" ]; then
        local testnet_node=$(grep "^TRON_TESTNET_LOCAL_FULL_NODE=" "$ENV_FILE" 2>/dev/null | cut -d'=' -f2 || echo "not configured")
        echo "Local Node: $testnet_node"
        echo "Remote Fallback: https://nile.trongrid.io"
    fi
    
    echo ""
    print_info "Test connections: python scripts/test_network_nodes.py"
}

# Function to test networks
test_networks() {
    print_info "Testing both networks..."
    if [ -f "$PROJECT_ROOT/scripts/test_network_nodes.py" ]; then
        cd "$PROJECT_ROOT"
        python scripts/test_network_nodes.py
    else
        print_error "Test script not found: scripts/test_network_nodes.py"
    fi
}

# Main function
main() {
    case "${1:-status}" in
        "testnet"|"nile"|"development"|"dev")
            switch_to_testnet
            ;;
        "mainnet"|"production"|"prod")
            switch_to_mainnet
            ;;
        "status"|"show")
            show_status
            ;;
        "test")
            test_networks
            ;;
        "help"|"--help"|"-h")
            echo "PortoAPI Network Switcher"
            echo ""
            echo "Usage: $0 [command]"
            echo ""
            echo "Commands:"
            echo "  testnet     Switch to Nile testnet (development)"
            echo "  mainnet     Switch to mainnet (production)"
            echo "  status      Show current network configuration"
            echo "  test        Test network connections"
            echo "  help        Show this help message"
            echo ""
            echo "Examples:"
            echo "  $0 testnet     # Switch to development"
            echo "  $0 mainnet     # Switch to production (with confirmation)"
            echo "  $0 status      # Show current settings"
            echo "  $0 test        # Test all network connections"
            ;;
        *)
            print_error "Unknown command: $1"
            echo "Use '$0 help' for available commands"
            exit 1
            ;;
    esac
}

# Run main function with all arguments
main "$@"
