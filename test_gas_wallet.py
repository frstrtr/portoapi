#!/usr/bin/env python3
"""Test gas station wallet functionality"""

import os
from dotenv import load_dotenv
load_dotenv()

def test_gas_wallet():
    print("🔧 Gas Station Wallet Test")
    print("=" * 40)
    
    # Check environment variables
    private_key = os.getenv('GAS_WALLET_PRIVATE_KEY')
    network = os.getenv('TRON_NETWORK', 'testnet')
    local_enabled = os.getenv('TRON_LOCAL_NODE_ENABLED', 'true')
    
    print(f"Network: {network}")
    print(f"Local node enabled: {local_enabled}")
    print(f"Private key configured: {'Yes' if private_key else 'No'}")
    
    if not private_key:
        print("❌ No gas wallet private key found in .env")
        return
    
    try:
        # Import TronPy
        from tronpy import Tron
        from tronpy.keys import PrivateKey
        
        # Get wallet address
        priv_key = PrivateKey(bytes.fromhex(private_key))
        address = priv_key.public_key.to_base58check_address()
        print(f"💰 Gas wallet address: {address}")
        
        # Initialize TRON client
        if network == 'testnet':
            # Try local first
            local_node = os.getenv('TRON_TESTNET_LOCAL_FULL_NODE', 'http://192.168.86.154:8090')
            try:
                tron = Tron(provider={'full_node': local_node})
                print(f"🔗 Connected to local node: {local_node}")
            except Exception:
                tron = Tron(network='nile')
                print("🌍 Connected to remote Nile testnet")
        else:
            tron = Tron()
            print("🌍 Connected to mainnet")
        
        # Check balance (using correct method)
        account = tron.get_account(address)
        balance_sun = account.get('balance', 0)
        balance_trx = float(balance_sun) / 1_000_000
        
        print(f"💎 Current balance: {balance_trx:.6f} TRX ({balance_sun:,} SUN)")
        
        # Check configuration amounts
        auto_activation = float(os.getenv('AUTO_ACTIVATION_TRX_AMOUNT', '1.0'))
        energy_delegation = float(os.getenv('ENERGY_DELEGATION_TRX_AMOUNT', '1.0'))
        bandwidth_delegation = float(os.getenv('BANDWIDTH_DELEGATION_TRX_AMOUNT', '0.5'))
        
        print(f"\n⚙️ Gas Station Configuration:")
        print(f"Auto activation amount: {auto_activation} TRX")
        print(f"Energy delegation amount: {energy_delegation} TRX")
        print(f"Bandwidth delegation amount: {bandwidth_delegation} TRX")
        
        # Calculate available operations
        if balance_trx > 0:
            activations = int(balance_trx / auto_activation)
            energy_ops = int(balance_trx / energy_delegation)
            bandwidth_ops = int(balance_trx / bandwidth_delegation)
            
            print(f"\n📊 Available Operations:")
            print(f"Account activations: {activations}")
            print(f"Energy delegations: {energy_ops}")
            print(f"Bandwidth delegations: {bandwidth_ops}")
            
            if balance_trx >= 0.001:
                print("\n✅ Gas station ready for operations!")
            else:
                print("\n⚠️ Low balance - consider adding more test TRX")
        else:
            print("\n❌ No TRX balance - need to fund wallet")
            
    except ImportError as e:
        print(f"❌ Missing dependency: {e}")
        print("Install with: pip install tronpy")
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    test_gas_wallet()
