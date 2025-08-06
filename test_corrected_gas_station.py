#!/usr/bin/env python3
"""
Test Enhanced Gas Station with NO_TYPE = BANDWIDTH understanding
"""

import os
from dotenv import load_dotenv
from tronpy import Tron
from tronpy.keys import PrivateKey

def test_gas_station_corrected():
    """Test gas station with corrected NO_TYPE understanding"""
    print("🧪 TESTING: Enhanced Gas Station with Corrected NO_TYPE Understanding")
    print("="*70)
    
    # Load environment
    load_dotenv()
    
    # Connect to local Nile node
    tron = Tron(network='nile')
    
    # Get gas station address
    private_key = os.getenv('GAS_WALLET_PRIVATE_KEY')
    priv_key = PrivateKey(bytes.fromhex(private_key))
    gas_address = priv_key.public_key.to_base58check_address()
    
    print(f"Gas Station Address: {gas_address}")
    
    # Get account data
    account = tron.get_account(gas_address)
    
    # Parse with corrected understanding
    balance = account.get('balance', 0) / 1_000_000
    
    frozen_energy = 0       # Type='ENERGY' (Type 1)
    frozen_bandwidth = 0    # Type='BANDWIDTH' (Type 0) AND NO_TYPE (also Type 0)
    frozen_tron_power = 0   # Type='TRON_POWER' (Type 2)
    frozen_other = 0        # Any other unrecognized types
    
    # Parse frozenV2 with correct NO_TYPE understanding
    frozen_v2 = account.get('frozenV2', [])
    for freeze in frozen_v2:
        freeze_type = freeze.get('type')
        amount = freeze.get('amount', 0) / 1_000_000
        
        print(f"🔍 Freeze type='{freeze_type}', amount={amount:,.1f} TRX")
        
        if freeze_type == 'ENERGY':
            frozen_energy += amount
        elif freeze_type == 'BANDWIDTH':
            frozen_bandwidth += amount
        elif freeze_type == 'NO_TYPE' or freeze_type is None or freeze_type == '':
            # NO_TYPE = Type 0 = BANDWIDTH staking in Staking 2.0
            # Also handle None (which appears as 'None' in output) and empty string
            print(f"   ✅ {freeze_type} identified as BANDWIDTH (Type 0) stake")
            frozen_bandwidth += amount
        elif freeze_type == 'TRON_POWER':
            frozen_tron_power += amount
        else:
            frozen_other += amount
    
    # Calculate totals
    total_delegatable = frozen_energy + frozen_bandwidth + frozen_other
    total_frozen = total_delegatable + frozen_tron_power
    
    print(f"\n📊 CORRECTED BREAKDOWN:")
    print(f"   Available Balance: {balance:,.1f} TRX")
    print(f"   Energy Stakes (Type 1): {frozen_energy:,.1f} TRX")
    print(f"   Bandwidth Stakes (Type 0 + NO_TYPE): {frozen_bandwidth:,.1f} TRX")
    print(f"   TRON Power (Type 2): {frozen_tron_power:,.1f} TRX")
    print(f"   Other: {frozen_other:,.1f} TRX")
    print(f"   Total Frozen: {total_frozen:,.1f} TRX")
    
    print(f"\n🚀 DELEGATION CAPACITY:")
    print(f"   Total Delegatable Pool: {total_delegatable:,.1f} TRX")
    print(f"   Can delegate to ENERGY users: {total_delegatable:,.1f} TRX")
    print(f"   Can delegate to BANDWIDTH users: {total_delegatable:,.1f} TRX")
    print(f"   (In Staking 2.0: ANY stake can delegate to energy OR bandwidth)")
    
    # Calculate user capacity
    if total_delegatable > 0:
        energy_users = int(total_delegatable * 32000 / 65000)  # 32k stake, 65k energy per tx
        bandwidth_users = int(total_delegatable * 1000 / 345)  # 1k stake, 345 bandwidth per tx
        activation_users = int(balance / 1.0)  # 1 TRX per activation
        
        print(f"\n👥 USER ONBOARDING CAPACITY:")
        print(f"   Energy-focused users: {energy_users:,}")
        print(f"   Bandwidth-focused users: {bandwidth_users:,}")
        print(f"   Activation-limited: {activation_users:,}")
        print(f"   Bottleneck: {min(energy_users, bandwidth_users, activation_users):,} users")
        
        if total_delegatable > 10000:
            print(f"\n🎯 ENTERPRISE SCALE CONFIRMED!")
            print(f"   This gas station can support {min(energy_users, bandwidth_users):,}+ users")
            print(f"   Massive delegation pool available: {total_delegatable:,.0f} TRX")

if __name__ == "__main__":
    test_gas_station_corrected()
