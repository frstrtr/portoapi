#!/usr/bin/env python3
"""
Configuration validation script for PortoAPI
Validates that all required configuration values are set correctly.
"""

import os
import sys
from typing import Dict, Any

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'src'))

from src.core.config import config


def test_database_connection() -> bool:
    """Test database connection"""
    print("\n� Testing Database Connection:")
    
    try:
        from src.core.database.db_service import db_service
        
        # Initialize database
        db_service.init_db()
        print("  ✅ Database connection successful")
        print(f"  ✅ Database file: {config.db.path}")
        return True
        
    except Exception as e:
        print(f"  ❌ Database connection failed: {e}")
        return False


def test_crypto_operations() -> bool:
    """Test cryptographic operations"""
    print("\n🔐 Testing Crypto Operations:")
    
    try:
        from src.core.crypto.hd_wallet_service import HDWalletService
        
        # Test HD wallet operations
        wallet_service = HDWalletService()
        
        # Test key generation
        test_mnemonic = "abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon about"
        master_key = wallet_service.from_mnemonic(test_mnemonic)
        derived_key = wallet_service.derive_key(master_key, "m/44'/195'/0'/0/0")
        address = wallet_service.get_address(derived_key)
        
        print("  ✅ Mnemonic processing successful")
        print("  ✅ HD key derivation successful") 
        print(f"  ✅ Address generation successful: {address[:10]}...")
        
        return True
        
    except Exception as e:
        print(f"  ❌ Crypto operations failed: {e}")
        return False


def test_tron_connection() -> bool:
    """Test TRON network connection"""
    print("\n🔗 Testing TRON Connection:")
    
    try:
        from src.core.services.gas_station import gas_station
        
        # Test connection health
        health = gas_station.check_connection_health()
        
        if health["connected"]:
            print(f"  ✅ Connected to TRON {config.tron.network} network")
            print(f"  ✅ Node type: {health['node_type']}")
            print(f"  ✅ Latency: {health['latency_ms']}ms")
            print(f"  ✅ Latest block: {health['latest_block']}...")
            
            # Test local node if enabled
            if config.tron.local_node_enabled:
                if config.tron.test_local_node_connection():
                    print(f"  ✅ Local TRON node available at {config.tron.local_full_node}")
                else:
                    print("  ⚠️  Local TRON node configured but not accessible")
            else:
                print("  ℹ️  Local TRON node disabled, using remote endpoints")
        else:
            print(f"  ❌ Connection failed: {health.get('error', 'Unknown error')}")
            return False
        
        # Test USDT contract access
        try:
            _ = gas_station.client.get_contract(config.tron.usdt_contract)
            print(f"  ✅ USDT contract accessible: {config.tron.usdt_contract}")
        except Exception as contract_error:
            print(f"  ⚠️  USDT contract warning: {contract_error}")
        
        return True
        
    except Exception as e:
        print(f"  ❌ Connection test failed: {e}")
        return False


def validate_configuration() -> Dict[str, Any]:
    """Validate all configuration settings"""
    print("🔍 Validating Configuration:")
    
    issues = []
    
    # Check required environment variables
    required_vars = [
        'DATABASE_PATH',
        'BOT_TOKEN', 
        'WEBHOOK_URL',
        'ADMIN_IDS',
        'GAS_STATION_PRIVATE_KEY',
        'TRON_NETWORK'
    ]
    
    for var in required_vars:
        if not os.getenv(var):
            issues.append(f"Missing environment variable: {var}")
    
    # Validate network setting
    if config.tron.network not in ['mainnet', 'testnet']:
        issues.append(f"Invalid TRON network: {config.tron.network}")
    
    # Validate admin IDs format
    try:
        admin_ids = [int(x.strip()) for x in config.bot.admin_ids.split(',')]
        print(f"  ✅ Admin IDs configured: {len(admin_ids)} admins")
    except ValueError:
        issues.append("Invalid ADMIN_IDS format (should be comma-separated integers)")
    
    # Validate gas station configuration
    if len(config.tron.gas_station_private_key) != 64:
        issues.append("Invalid gas station private key length")
    
    # Check local node configuration if enabled
    if config.tron.local_node_enabled:
        if not config.tron.local_full_node or not config.tron.local_solidity_node:
            issues.append("Local node enabled but endpoints not configured")
    
    if issues:
        print("  ❌ Configuration issues found:")
        for issue in issues:
            print(f"    - {issue}")
        return {"valid": False, "issues": issues}
    else:
        print("  ✅ Configuration is valid")
        return {"valid": True, "issues": []}


def main():
    """Main validation function"""
    print("🚀 PortoAPI Configuration Validator")
    print("=" * 50)
    
    # Test configuration
    config_result = validate_configuration()
    
    # Test components if config is valid
    if config_result["valid"]:
        db_ok = test_database_connection()
        crypto_ok = test_crypto_operations()
        tron_ok = test_tron_connection()
        
        if db_ok and crypto_ok and tron_ok:
            print("\n🎉 All checks passed! PortoAPI is ready to run.")
            sys.exit(0)
        else:
            print("\n⚠️  Configuration valid but connection issues detected.")
            sys.exit(1)
    else:
        print("\n❌ Configuration validation failed. Please fix errors above.")
        sys.exit(1)

if __name__ == "__main__":
    main()
