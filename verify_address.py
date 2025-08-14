#!/usr/bin/env python3
"""
Quick verification test for address TB8sKQteRTgqn2sXM5B4JDuoxNA6FzSP2z
"""

import os
import sys

# Add the src directory to Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from core.services.gas_station import GasStationManager

def verify_address():
    gas_station = GasStationManager()
    test_address = "TB8sKQteRTgqn2sXM5B4JDuoxNA6FzSP2z"
    
    print(f"🔍 Verifying address: {test_address}")
    print("-" * 60)
    
    # Check activation status
    is_activated = gas_station._check_address_exists(test_address)
    print(f"Is Activated: {is_activated}")
    
    # Check activation with details
    activated_detailed, account_data = gas_station.check_account_activated_with_details(test_address)
    print(f"Detailed Activation Check: {activated_detailed}")
    if account_data:
        print(f"Account Data Found: Yes")
        balance = account_data.get('balance', 0)
        print(f"Account Balance: {balance / 1_000_000:.6f} TRX")
    else:
        print(f"Account Data Found: No")
    
    # Check resources
    resources = gas_station._get_account_resources(test_address)
    print(f"Energy: {resources.get('energy_available', 0):,}")
    print(f"Bandwidth: {resources.get('bandwidth_available', 0):,}")
    
    # Overall status
    ready = (is_activated or activated_detailed) and resources.get('energy_available', 0) > 15000
    print(f"Ready for USDT: {'✅ YES' if ready else '❌ NO'}")

if __name__ == "__main__":
    verify_address()
