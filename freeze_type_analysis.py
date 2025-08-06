#!/usr/bin/env python3
"""
TRON Freeze Type Analysis - Understanding Staking 2.0 Resource Types

Analyzes the actual freeze types returned by TRON node to understand:
1. What "UNKNOWN" type represents in Staking 2.0
2. How different freeze types relate to delegation capabilities
3. Proper categorization of all staked resources
"""

import os
from dotenv import load_dotenv
from tronpy import Tron
from tronpy.providers import HTTPProvider
from tronpy.keys import PrivateKey

def analyze_freeze_types():
    """Analyze what different freeze types mean in TRON Staking 2.0"""
    
    # Load environment
    load_dotenv()
    
    # Connect to local Nile node
    provider = HTTPProvider(endpoint_uri="http://192.168.86.154:8090")
    tron = Tron(provider=provider, network='nile')
    
    # Get gas station address from private key
    private_key = os.getenv('GAS_WALLET_PRIVATE_KEY')
    priv_key = PrivateKey(bytes.fromhex(private_key))
    gas_station_address = priv_key.public_key.to_base58check_address()
    
    print("=== TRON Staking 2.0 Freeze Type Analysis ===\n")
    
    # Get account data
    account_data = tron.get_account(gas_station_address)
    
    # Extract basic balance
    balance_sun = account_data.get('balance', 0)
    balance_trx = balance_sun / 1_000_000
    
    print(f"Available Balance: {balance_trx:,.1f} TRX")
    
    # Analyze frozenV2 data
    frozen_v2 = account_data.get('frozenV2', [])
    print(f"\nFrozenV2 Entries: {len(frozen_v2)}")
    
    total_frozen = 0
    freeze_breakdown = {}
    
    for i, freeze_entry in enumerate(frozen_v2):
        freeze_type = freeze_entry.get('type', 'NO_TYPE')
        amount_sun = int(freeze_entry.get('amount', 0))
        amount_trx = amount_sun / 1_000_000
        
        total_frozen += amount_trx
        
        if freeze_type not in freeze_breakdown:
            freeze_breakdown[freeze_type] = 0
        freeze_breakdown[freeze_type] += amount_trx
        
        print(f"Entry {i+1}: Type='{freeze_type}', Amount={amount_trx:,.0f} TRX")
    
    print(f"\n=== Freeze Type Breakdown ===")
    for freeze_type, amount in freeze_breakdown.items():
        percentage = (amount / total_frozen * 100) if total_frozen > 0 else 0
        print(f"{freeze_type}: {amount:,.0f} TRX ({percentage:.1f}%)")
    
    print(f"\nTotal Frozen: {total_frozen:,.0f} TRX")
    
    # Analyze delegation potential under Staking 2.0
    print(f"\n=== TRON Staking 2.0 Analysis ===")
    
    # In Staking 2.0, ANY staked TRX can delegate to energy OR bandwidth
    # The key insight: freeze type doesn't limit delegation capability
    
    # Check current delegations
    delegated_resource = account_data.get('delegated_frozenV2_balance_for_energy', 0) / 1_000_000
    
    print(f"Currently Delegated: {delegated_resource:,.1f} TRX")
    print(f"Available for Delegation: {total_frozen - delegated_resource:,.1f} TRX")
    
    # Understand what each type represents
    print("\n=== Type Interpretation (CORRECTED) ===")
    
    for freeze_type in freeze_breakdown:
        if freeze_type == "ENERGY":
            print("ENERGY: Type 1 - Energy staking - can delegate to energy users")
        elif freeze_type == "BANDWIDTH":
            print("BANDWIDTH: Type 0 - Bandwidth staking - can delegate to bandwidth users")  
        elif freeze_type == "TRON_POWER":
            print("TRON_POWER: Type 2 - Governance voting power - typically cannot delegate")
        elif freeze_type == "NO_TYPE":
            print("NO_TYPE: Type 0 - BANDWIDTH staking in Staking 2.0!")
            print("         This is equivalent to BANDWIDTH type - can delegate to bandwidth users")
            print("         NO_TYPE is how the node represents type 0 (BANDWIDTH) stakes")
        else:
            print(f"{freeze_type}: Unrecognized type - investigate TRON documentation")
    
    # Calculate true delegation capacity
    print("\n=== Delegation Capacity (CORRECTED) ===")
    
    # Under Staking 2.0, all non-TRON_POWER stakes can typically delegate
    # NO_TYPE is actually BANDWIDTH (type 0) staking
    delegatable_types = ['ENERGY', 'BANDWIDTH', 'NO_TYPE']
    total_delegatable = sum(freeze_breakdown.get(t, 0) for t in delegatable_types)
    
    print(f"Total Delegatable Pool: {total_delegatable:,.0f} TRX")
    print(f"Current Utilization: {delegated_resource:,.1f} TRX ({delegated_resource/total_delegatable*100:.2f}%)")
    print(f"Unused Capacity: {total_delegatable - delegated_resource:,.0f} TRX")
    
    # Energy calculations
    trx_to_energy_ratio = 1  # 1 TRX staked ≈ 1 energy per day
    potential_daily_energy = total_delegatable * trx_to_energy_ratio
    
    print(f"\nPotential Daily Energy: {potential_daily_energy:,.0f} energy units")
    
    # User onboarding capacity (assuming 15 energy per user)
    energy_per_user = 15
    max_users = potential_daily_energy / energy_per_user
    
    print(f"Theoretical User Capacity: {max_users:,.0f} users/day")
    
    return {
        'available_balance': balance_trx,
        'total_frozen': total_frozen,
        'freeze_breakdown': freeze_breakdown,
        'delegated_current': delegated_resource,
        'delegatable_pool': total_delegatable,
        'utilization_percent': delegated_resource/total_delegatable*100 if total_delegatable > 0 else 0
    }

if __name__ == "__main__":
    try:
        result = analyze_freeze_types()
        print(f"\n=== Summary ===")
        print(f"Gas Station has {result['delegatable_pool']:,.0f} TRX available for delegation")
        print(f"Currently using only {result['utilization_percent']:.2f}% of capacity")
        print(f"Massive untapped potential for user onboarding!")
        
    except Exception as e:
        print(f"Error analyzing freeze types: {e}")
        import traceback
        traceback.print_exc()
