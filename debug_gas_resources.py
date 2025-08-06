#!/usr/bin/env python3
"""
Debug Gas Station Resource Reading
Comprehensive analysis of staked TRX amounts
"""

import os
import sys
sys.path.append('/home/user0/Documents/github/portoapi')

from dotenv import load_dotenv
from src.core.services.gas_station import GasStationManager

def debug_gas_station_resources():
    """Debug gas station resource reading"""
    print("🔍 GAS STATION RESOURCE DEBUG")
    print("="*50)
    
    try:
        load_dotenv()
        
        # Initialize gas station
        gas_station = GasStationManager()
        
        # Get gas wallet account
        gas_account = gas_station._get_gas_wallet_account()
        print(f"💰 Gas Wallet: {gas_account.address}")
        
        # Get raw account data
        account_info = gas_station.client.get_account(gas_account.address)
        resource_info = gas_station.client.get_account_resource(gas_account.address)
        
        # Basic balance
        balance = account_info.get('balance', 0) / 1_000_000
        print(f"💵 Available Balance: {balance:,.6f} TRX")
        
        print(f"\n🔍 RAW ACCOUNT DATA ANALYSIS:")
        print("="*40)
        
        # Check all possible frozen/staked fields
        frozen_v2 = account_info.get('frozenV2', [])
        print(f"FrozenV2 entries: {len(frozen_v2)}")
        
        total_frozen_v2 = 0
        for i, freeze in enumerate(frozen_v2):
            freeze_type = freeze.get('type', 'UNKNOWN')
            amount = freeze.get('amount', 0) / 1_000_000
            total_frozen_v2 += amount
            print(f"  Entry {i+1}: {freeze_type} = {amount:,.1f} TRX")
        
        # Check legacy frozen
        legacy_frozen = account_info.get('frozen', [])
        print(f"\nLegacy frozen entries: {len(legacy_frozen)}")
        
        total_legacy = 0
        for i, freeze in enumerate(legacy_frozen):
            amount = freeze.get('frozen_balance', 0) / 1_000_000
            total_legacy += amount
            expire_time = freeze.get('expire_time', 0)
            print(f"  Entry {i+1}: {amount:,.1f} TRX (expires: {expire_time})")
        
        # Check other frozen fields
        if 'frozen_balance' in account_info:
            frozen_balance = account_info['frozen_balance'] / 1_000_000
            print(f"\nDirect frozen_balance: {frozen_balance:,.1f} TRX")
        else:
            frozen_balance = 0
            print(f"\nNo direct frozen_balance found")
        
        # Check delegated resources
        delegated_frozen_v2 = account_info.get('delegatedFrozenV2BalanceForEnergy', 0) / 1_000_000
        delegated_bandwidth = account_info.get('delegatedFrozenV2BalanceForBandwidth', 0) / 1_000_000
        
        print(f"\nDelegated resources:")
        print(f"  Energy delegated out: {delegated_frozen_v2:,.1f} TRX")
        print(f"  Bandwidth delegated out: {delegated_bandwidth:,.1f} TRX")
        
        print(f"\n⚡ RESOURCE LIMITS ANALYSIS:")
        print("="*40)
        
        # Resource limits
        energy_limit = resource_info.get('EnergyLimit', 0)
        energy_used = resource_info.get('EnergyUsed', 0)
        net_limit = resource_info.get('NetLimit', 0)
        net_used = resource_info.get('NetUsed', 0)
        free_net_limit = resource_info.get('freeNetLimit', 0)
        
        print(f"Energy limit: {energy_limit:,} units")
        print(f"Energy used: {energy_used:,} units")
        print(f"Net limit: {net_limit:,} units")
        print(f"Net used: {net_used:,} units")
        print(f"Free net limit: {free_net_limit:,} units")
        
        # Calculate stake from resource limits
        # TRON ratios: ~32,000 energy per TRX, ~1,000 bandwidth per TRX
        calculated_energy_stake = energy_limit / 32_000 if energy_limit > 0 else 0
        calculated_net_stake = net_limit / 1_000 if net_limit > 0 else 0
        
        print(f"\n📊 CALCULATED STAKES:")
        print("="*30)
        print(f"From energy limit: {calculated_energy_stake:,.1f} TRX")
        print(f"From net limit: {calculated_net_stake:,.1f} TRX")
        print(f"Total calculated: {calculated_energy_stake + calculated_net_stake:,.1f} TRX")
        
        print(f"\n📋 SUMMARY:")
        print("="*20)
        print(f"Available balance: {balance:,.1f} TRX")
        print(f"FrozenV2 total: {total_frozen_v2:,.1f} TRX")
        print(f"Legacy frozen: {total_legacy:,.1f} TRX")
        print(f"Direct frozen: {frozen_balance:,.1f} TRX")
        print(f"Delegated out: {delegated_frozen_v2 + delegated_bandwidth:,.1f} TRX")
        print(f"Calculated from limits: {calculated_energy_stake + calculated_net_stake:,.1f} TRX")
        
        # The actual staked amount
        actual_staked = max(
            total_frozen_v2,
            calculated_energy_stake + calculated_net_stake,
            total_legacy + frozen_balance
        )
        
        print(f"\n🎯 ACTUAL STAKED AMOUNT: {actual_staked:,.1f} TRX")
        print(f"Total controlled: {balance + actual_staked:,.1f} TRX")
        
        # Show raw data for debugging
        print(f"\n🔧 RAW DATA (for debugging):")
        print("="*35)
        print(f"Account keys: {list(account_info.keys())}")
        print(f"Resource keys: {list(resource_info.keys())}")
        
        # Print any unusual fields
        for key, value in account_info.items():
            if 'frozen' in key.lower() or 'stake' in key.lower() or 'delegate' in key.lower():
                if isinstance(value, (int, float)) and value > 0:
                    print(f"  {key}: {value}")
                elif isinstance(value, list) and len(value) > 0:
                    print(f"  {key}: {len(value)} entries")
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    debug_gas_station_resources()
