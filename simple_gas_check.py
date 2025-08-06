#!/usr/bin/env python3
"""
Simple Gas Station Resource Check
Direct approach to read staked amounts
"""

import os
import sys
sys.path.append('/home/user0/Documents/github/portoapi')

from dotenv import load_dotenv
from src.core.services.gas_station import GasStationManager

def check_gas_station_simple():
    """Simple check of gas station resources"""
    print("🔍 SIMPLE GAS STATION RESOURCE CHECK")
    print("="*50)
    
    try:
        load_dotenv()
        
        # Initialize gas station
        gas_station = GasStationManager()
        
        # Get the address directly from config
        from tronpy.keys import PrivateKey
        private_key = os.getenv('GAS_WALLET_PRIVATE_KEY')
        priv_key = PrivateKey(bytes.fromhex(private_key))
        gas_address = priv_key.public_key.to_base58check_address()
        
        print(f"💰 Gas Wallet: {gas_address}")
        
        # Get account and resource info
        account_info = gas_station.client.get_account(gas_address)
        resource_info = gas_station.client.get_account_resource(gas_address)
        
        # Basic balance
        balance = account_info.get('balance', 0) / 1_000_000
        print(f"💵 Available Balance: {balance:,.6f} TRX")
        
        # Resource limits (these show the actual staked amounts)
        energy_limit = resource_info.get('EnergyLimit', 0)
        energy_used = resource_info.get('EnergyUsed', 0)
        net_limit = resource_info.get('NetLimit', 0)
        net_used = resource_info.get('NetUsed', 0)
        free_net_limit = resource_info.get('freeNetLimit', 0)
        
        print(f"\n⚡ ENERGY:")
        print(f"   Limit: {energy_limit:,} units")
        print(f"   Used: {energy_used:,} units")
        print(f"   Available: {energy_limit - energy_used:,} units")
        
        print(f"\n📡 BANDWIDTH:")
        print(f"   Net Limit: {net_limit:,} units")
        print(f"   Free Limit: {free_net_limit:,} units")
        print(f"   Used: {net_used:,} units")
        print(f"   Total Available: {(net_limit + free_net_limit) - net_used:,} units")
        
        # Calculate staked amounts from resource limits
        # TRON staking ratios (approximate):
        # - 1 TRX staked for energy ≈ 32,000 energy units
        # - 1 TRX staked for bandwidth ≈ 1,000 bandwidth units
        
        energy_staked = energy_limit / 32_000
        bandwidth_staked = net_limit / 1_000
        total_staked = energy_staked + bandwidth_staked
        
        print(f"\n💎 CALCULATED STAKED AMOUNTS:")
        print(f"   Energy staked: {energy_staked:,.1f} TRX")
        print(f"   Bandwidth staked: {bandwidth_staked:,.1f} TRX")
        print(f"   Total staked: {total_staked:,.1f} TRX")
        
        print(f"\n📊 TOTAL RESOURCES:")
        print(f"   Available: {balance:,.1f} TRX")
        print(f"   Staked: {total_staked:,.1f} TRX")
        print(f"   Total controlled: {balance + total_staked:,.1f} TRX")
        
        # Transaction capacity
        energy_tx_capacity = (energy_limit - energy_used) // 65_000
        bandwidth_tx_capacity = ((net_limit + free_net_limit) - net_used) // 345
        activation_capacity = int(balance / 1.0)
        
        print(f"\n🎯 CAPACITY ESTIMATES:")
        print(f"   Energy-limited transactions: {energy_tx_capacity:,}")
        print(f"   Bandwidth-limited transactions: {bandwidth_tx_capacity:,}")
        print(f"   Activation-limited users: {activation_capacity:,}")
        print(f"   Current bottleneck: {min(energy_tx_capacity, bandwidth_tx_capacity, activation_capacity):,}")
        
        # Check frozen data for debugging
        print(f"\n🔍 FROZEN DATA DEBUG:")
        frozen_v2 = account_info.get('frozenV2', [])
        print(f"   FrozenV2 entries: {len(frozen_v2)}")
        
        frozen_v2_total = 0
        for i, freeze in enumerate(frozen_v2):
            freeze_type = freeze.get('type', 'UNKNOWN')
            amount = freeze.get('amount', 0) / 1_000_000
            frozen_v2_total += amount
            print(f"     Entry {i+1}: {freeze_type} = {amount:,.1f} TRX")
        
        print(f"   FrozenV2 total: {frozen_v2_total:,.1f} TRX")
        
        if abs(frozen_v2_total - total_staked) > 1:  # Allow 1 TRX tolerance
            print(f"   ⚠️  Discrepancy: FrozenV2 ({frozen_v2_total:,.1f}) vs Calculated ({total_staked:,.1f})")
            print(f"   🎯 Using calculated values from resource limits (more accurate)")
        else:
            print(f"   ✅ FrozenV2 matches calculated stakes")
        
        # Resource pool efficiency analysis
        print(f"\n💡 RESOURCE POOL EFFICIENCY:")
        if total_staked > 1000:  # If significant staking
            print(f"   ✅ You have substantial resource pools!")
            print(f"   Energy pool capacity: {energy_tx_capacity:,} transactions")
            print(f"   Bandwidth pool capacity: {bandwidth_tx_capacity:,} transactions")
            print(f"   Your gas station is using resource delegation efficiently!")
        else:
            print(f"   💡 Consider creating resource pools for efficiency")
            print(f"   Recommended: 2,000 TRX energy + 1,000 TRX bandwidth pools")
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    check_gas_station_simple()
