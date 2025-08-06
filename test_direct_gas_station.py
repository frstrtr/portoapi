#!/usr/bin/env python3
"""
Direct test of enhanced gas station
"""

import sys
import os
sys.path.append('/home/user0/Documents/github/portoapi')

# Set up environment
os.environ['GAS_WALLET_PRIVATE_KEY'] = open('/home/user0/Documents/github/portoapi/.env').read().split('GAS_WALLET_PRIVATE_KEY=')[1].split('\n')[0]

from enhanced_gas_station_v2 import ResourcePoolGasStation

def test_direct():
    """Direct test of the enhanced gas station"""
    print("🧪 DIRECT TEST: Enhanced Gas Station")
    print("="*50)
    
    try:
        # Initialize gas station
        gas_station = ResourcePoolGasStation('nile')
        
        # Get status
        status = gas_station.get_account_status()
        
        print("\n📊 ACCOUNT STATUS:")
        print(f"   Balance: {status['balance']:,.1f} TRX")
        print(f"   Total Frozen: {status['total_frozen']:,.1f} TRX")
        print(f"   Total Delegatable: {status['total_delegatable']:,.1f} TRX")
        
        # Display full status
        gas_station.display_status()
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_direct()
