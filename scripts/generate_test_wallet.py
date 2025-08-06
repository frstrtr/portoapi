#!/usr/bin/env python3
"""
Generate a test wallet for Nile testnet development
"""

import sys
import os
import requests
import qrcode
from io import StringIO

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'src'))

try:
    from tronpy.keys import PrivateKey
except ImportError:
    print("❌ tronpy not installed. Install with: pip install tronpy")
    sys.exit(1)

def generate_test_wallet():
    """Generate a new TRON wallet for testing"""
    
    # Generate new private key
    private_key = PrivateKey.random()
    address = private_key.public_key.to_base58check_address()
    
    print("🔑 Generated Test Wallet for Nile Testnet")
    print("=" * 50)
    print(f"Address: {address}")
    print(f"Private Key: {private_key}")
    print(f"Private Key (hex): {private_key.hex()}")
    
    # Generate QR code for address
    try:
        qr = qrcode.QRCode(version=1, box_size=10, border=5)
        qr.add_data(address)
        qr.make(fit=True)
        
        # Print QR code to console
        f = StringIO()
        qr.print_ascii(out=f)
        f.seek(0)
        print(f"\n📱 Address QR Code:")
        print(f.read())
    except ImportError:
        print("\n📱 Install qrcode for QR code display: pip install qrcode[pil]")
    
    print(f"\n💡 Next Steps:")
    print(f"1. Add to .env file:")
    print(f"   GAS_WALLET_PRIVATE_KEY={private_key}")
    print(f"")
    print(f"2. Get test TRX from faucet:")
    print(f"   https://nileex.io/join/getJoinPage")
    print(f"   Send TRX to: {address}")
    print(f"")
    print(f"3. Verify balance:")
    print(f"   curl -X POST http://192.168.86.154:8090/wallet/getaccount \\")
    print(f"        -H 'Content-Type: application/json' \\")
    print(f"        -d '{{\"address\":\"{address}\"}}'")
    
    # Test connection to your Nile node
    test_nile_node_connection(address)
    
    return {
        "address": address,
        "private_key": str(private_key),
        "private_key_hex": private_key.hex()
    }

def test_nile_node_connection(address):
    """Test connection to the Nile node"""
    print(f"\n🔍 Testing Nile Node Connection...")
    
    try:
        # Test if node is responding
        response = requests.post(
            "http://192.168.86.154:8090/wallet/getnowblock",
            timeout=10
        )
        
        if response.status_code == 200:
            block_data = response.json()
            block_height = block_data.get('block_header', {}).get('raw_data', {}).get('number', 0)
            print(f"✅ Nile node responding correctly")
            print(f"   Latest block: {block_height:,}")
            
            # Test account query (should return empty for new address)
            account_response = requests.post(
                "http://192.168.86.154:8090/wallet/getaccount",
                json={"address": address},
                timeout=10
            )
            
            if account_response.status_code == 200:
                print(f"✅ Account queries working")
            else:
                print(f"⚠️ Account query returned: {account_response.status_code}")
                
        else:
            print(f"❌ Nile node returned HTTP {response.status_code}")
            print(f"   Check if node at 192.168.86.154 is running")
            
    except requests.exceptions.ConnectionError:
        print(f"❌ Cannot connect to Nile node at 192.168.86.154")
        print(f"   Make sure the TRON node is running and accessible")
    except Exception as e:
        print(f"❌ Error testing node: {e}")

def create_env_snippet(wallet_info):
    """Create .env configuration snippet"""
    print("\n📝 Configuration for .env file:")
    print("=" * 50)
    
    env_content = f"""# Development Configuration for Nile Testnet
# Copy this file to .env and configure other values

# =============================================
# Telegram Bot Configuration
# =============================================
TELEGRAM_BOT_TOKEN=your_bot_token_from_botfather
TELEGRAM_BOT_NAME=your_bot_username
TELEGRAM_BOT_ID=your_bot_id
BOT_WEBHOOK_URL=https://yourdomain.com/webhook/telegram
BOT_SECRET_TOKEN=your_secure_webhook_secret

# =============================================
# API Configuration
# =============================================
API_HOST=0.0.0.0
API_PORT=8000
API_DEBUG=true
API_BASE_URL=http://localhost:8000/api/v1
SETUP_URL_BASE=http://localhost:8000

# =============================================
# Database Configuration
# =============================================
DATABASE_URL=sqlite:///./data/database_development.sqlite3
DATABASE_ECHO=false

# =============================================
# TRON Network Configuration
# =============================================
TRON_NETWORK=testnet
TRON_API_KEY=your_trongrid_api_key_optional

# =============================================
# Local TRON Nodes Configuration
# =============================================
TRON_LOCAL_NODE_ENABLED=true

# Mainnet Local Node
TRON_MAINNET_LOCAL_FULL_NODE=http://192.168.86.20:8090
TRON_MAINNET_LOCAL_SOLIDITY_NODE=http://192.168.86.20:8091
TRON_MAINNET_LOCAL_EVENT_SERVER=http://192.168.86.20:8092
TRON_MAINNET_LOCAL_GRPC_ENDPOINT=192.168.86.20:50051

# Nile Testnet Local Node (Development)
TRON_TESTNET_LOCAL_FULL_NODE=http://192.168.86.154:8090
TRON_TESTNET_LOCAL_SOLIDITY_NODE=http://192.168.86.154:8091
TRON_TESTNET_LOCAL_EVENT_SERVER=http://192.168.86.154:8092
TRON_TESTNET_LOCAL_GRPC_ENDPOINT=192.168.86.154:50051

# Connection Settings
TRON_LOCAL_TIMEOUT=10
TRON_LOCAL_MAX_RETRIES=3

# =============================================
# Remote API Fallbacks
# =============================================
TRON_REMOTE_MAINNET_FULL_NODE=https://api.trongrid.io
TRON_REMOTE_MAINNET_SOLIDITY_NODE=https://api.trongrid.io
TRON_REMOTE_MAINNET_EVENT_SERVER=https://api.trongrid.io
TRON_MAINNET_USDT_CONTRACT=TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t

TRON_REMOTE_TESTNET_FULL_NODE=https://nile.trongrid.io
TRON_REMOTE_TESTNET_SOLIDITY_NODE=https://nile.trongrid.io
TRON_REMOTE_TESTNET_EVENT_SERVER=https://nile.trongrid.io
TRON_TESTNET_USDT_CONTRACT=TXYZopYRdj2D9XRtbG411XZZ3kM5VkAeBf

# =============================================
# Gas Station Configuration
# =============================================
GAS_STATION_TYPE=single
GAS_WALLET_PRIVATE_KEY={wallet_info['private_key']}

# Resource Amounts (Lower for testnet)
AUTO_ACTIVATION_TRX_AMOUNT=1.0
ENERGY_DELEGATION_TRX_AMOUNT=1.0
BANDWIDTH_DELEGATION_TRX_AMOUNT=0.5

# =============================================
# Application Settings
# =============================================
ADMIN_IDS=your_telegram_user_id

# Logging Configuration
LOG_LEVEL=DEBUG
LOG_FILE=logs/portoapi_development.log

# Keeper Bot Settings
KEEPER_CHECK_INTERVAL=30
KEEPER_ENABLED=true

# Development Settings
DEBUG=true
DATABASE_ECHO=false"""
    
    print(env_content)
    
    # Write to file
    try:
        with open(".env.development", "w", encoding="utf-8") as f:
            f.write(env_content.strip())
        print("\n💾 Saved configuration to .env.development")
        print("   Copy to .env: cp .env.development .env")
    except Exception as e:
        print(f"\n⚠️ Could not save to file: {e}")

def main():
    """Main function"""
    print("🚀 PortoAPI Nile Testnet Wallet Generator")
    print(f"Creating wallet for development with node at 192.168.86.154")
    
    wallet_info = generate_test_wallet()
    create_env_snippet(wallet_info)
    
    print(f"\n🎯 Ready for Nile Development!")
    print("Next: Get test TRX from https://nileex.io/join/getJoinPage")

if __name__ == "__main__":
    main()
