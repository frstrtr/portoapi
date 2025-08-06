#!/usr/bin/env python3
"""
Resource Pool Enhancement for existing Gas Station
Adds resource pool management capabilities to the existing gas station
"""

import os
import time
import logging
from decimal import Decimal
from typing import Optional, Dict, Any, List
from dotenv import load_dotenv

# Import existing gas station
from src.core.services.gas_station import GasStationManager
from src.core.config import config

logger = logging.getLogger(__name__)

class ResourcePoolEnhancement:
    """Enhancement to add resource pool capabilities to existing gas station"""
    
    def __init__(self):
        load_dotenv()
        self.gas_station = GasStationManager()
        self.tron_config = config.tron
        
    def get_current_resources(self) -> Dict[str, Any]:
        """Get current resource status of gas wallet"""
        try:
            gas_account = self.gas_station._get_gas_wallet_account()
            account_info = self.gas_station.client.get_account(gas_account.address)
            resource_info = self.gas_station.client.get_account_resource(gas_account.address)
            
            # Parse account balance
            balance = account_info.get('balance', 0) / 1_000_000
            
            # Parse resource information
            energy_limit = resource_info.get('EnergyLimit', 0)
            energy_used = resource_info.get('EnergyUsed', 0)
            net_limit = resource_info.get('NetLimit', 0)
            net_used = resource_info.get('NetUsed', 0)
            free_net_limit = resource_info.get('freeNetLimit', 0)
            
            # Parse frozen/staked resources
            frozen_energy = 0
            frozen_bandwidth = 0
            
            frozen_v2 = account_info.get('frozenV2', [])
            for freeze in frozen_v2:
                freeze_type = freeze.get('type')
                amount = freeze.get('amount', 0) / 1_000_000
                if freeze_type == 'ENERGY':
                    frozen_energy += amount
                elif freeze_type == 'BANDWIDTH':
                    frozen_bandwidth += amount
            
            return {
                'address': gas_account.address,
                'balance_trx': balance,
                'energy': {
                    'limit': energy_limit,
                    'used': energy_used,
                    'available': energy_limit - energy_used,
                    'staked_trx': frozen_energy
                },
                'bandwidth': {
                    'limit': net_limit,
                    'free_limit': free_net_limit,
                    'used': net_used,
                    'available': (net_limit + free_net_limit) - net_used,
                    'staked_trx': frozen_bandwidth
                },
                'total_staked_trx': frozen_energy + frozen_bandwidth
            }
            
        except Exception as e:
            logger.error(f"Error getting resource status: {e}")
            return {}
    
    def create_energy_pool(self, amount_trx: float) -> Optional[str]:
        """Create energy resource pool by staking TRX"""
        try:
            logger.info(f"Creating energy pool: {amount_trx} TRX")
            
            gas_account = self.gas_station._get_gas_wallet_account()
            amount_sun = int(amount_trx * 1_000_000)
            
            # Build freeze transaction for energy
            freeze_txn = (
                self.gas_station.client.trx.freeze_balance_v2(
                    owner=gas_account.address,
                    frozen_balance=amount_sun,
                    resource="ENERGY"
                )
                .memo("Gas Station Energy Pool")
                .build()
                .sign(self.tron_config.gas_wallet_private_key)
            )
            
            result = freeze_txn.broadcast()
            txid = result["txid"]
            
            # Wait for confirmation
            if self.gas_station._wait_for_transaction(txid, "Energy pool creation"):
                logger.info(f"Energy pool created successfully. TX: {txid}")
                return txid
            else:
                logger.error("Energy pool creation transaction failed")
                return None
                
        except Exception as e:
            logger.error(f"Failed to create energy pool: {e}")
            return None
    
    def create_bandwidth_pool(self, amount_trx: float) -> Optional[str]:
        """Create bandwidth resource pool by staking TRX"""
        try:
            logger.info(f"Creating bandwidth pool: {amount_trx} TRX")
            
            gas_account = self.gas_station._get_gas_wallet_account()
            amount_sun = int(amount_trx * 1_000_000)
            
            # Build freeze transaction for bandwidth
            freeze_txn = (
                self.gas_station.client.trx.freeze_balance_v2(
                    owner=gas_account.address,
                    frozen_balance=amount_sun,
                    resource="BANDWIDTH"
                )
                .memo("Gas Station Bandwidth Pool")
                .build()
                .sign(self.tron_config.gas_wallet_private_key)
            )
            
            result = freeze_txn.broadcast()
            txid = result["txid"]
            
            # Wait for confirmation
            if self.gas_station._wait_for_transaction(txid, "Bandwidth pool creation"):
                logger.info(f"Bandwidth pool created successfully. TX: {txid}")
                return txid
            else:
                logger.error("Bandwidth pool creation transaction failed")
                return None
                
        except Exception as e:
            logger.error(f"Failed to create bandwidth pool: {e}")
            return None
    
    def calculate_optimal_pools(self, expected_users: int) -> Dict[str, float]:
        """Calculate optimal pool sizes for expected number of users"""
        
        # Constants based on TRON network
        energy_per_trx = 32_000  # Approximate energy gained per TRX staked
        bandwidth_per_trx = 1_000  # Approximate bandwidth gained per TRX staked
        
        # Resource requirements per user transaction
        energy_per_transaction = 65_000  # Typical smart contract interaction
        bandwidth_per_transaction = 345  # Typical transaction bandwidth
        
        # Calculate required pool sizes
        total_energy_needed = expected_users * energy_per_transaction
        total_bandwidth_needed = expected_users * bandwidth_per_transaction
        
        energy_pool_trx = total_energy_needed / energy_per_trx
        bandwidth_pool_trx = total_bandwidth_needed / bandwidth_per_trx
        
        # Add 20% buffer for safety
        energy_pool_trx *= 1.2
        bandwidth_pool_trx *= 1.2
        
        return {
            'energy_pool_trx': energy_pool_trx,
            'bandwidth_pool_trx': bandwidth_pool_trx,
            'total_pool_trx': energy_pool_trx + bandwidth_pool_trx,
            'activation_trx_per_user': 1.0,
            'total_trx_needed': energy_pool_trx + bandwidth_pool_trx + (expected_users * 1.0)
        }
    
    def setup_optimal_pools(self, expected_users: int) -> bool:
        """Setup optimal resource pools for expected number of users"""
        try:
            # Calculate optimal pool sizes
            pool_calc = self.calculate_optimal_pools(expected_users)
            
            logger.info(f"Setting up pools for {expected_users} users:")
            logger.info(f"Energy pool: {pool_calc['energy_pool_trx']:.1f} TRX")
            logger.info(f"Bandwidth pool: {pool_calc['bandwidth_pool_trx']:.1f} TRX")
            logger.info(f"Total pool investment: {pool_calc['total_pool_trx']:.1f} TRX")
            
            # Check if we have enough balance
            resources = self.get_current_resources()
            if not resources:
                logger.error("Could not get current resource status")
                return False
            
            available_balance = resources['balance_trx']
            if available_balance < pool_calc['total_pool_trx']:
                logger.error(f"Insufficient balance. Need {pool_calc['total_pool_trx']:.1f} TRX, have {available_balance:.1f} TRX")
                return False
            
            # Create energy pool
            energy_txid = self.create_energy_pool(pool_calc['energy_pool_trx'])
            if not energy_txid:
                logger.error("Failed to create energy pool")
                return False
            
            # Wait between transactions
            time.sleep(3)
            
            # Create bandwidth pool
            bandwidth_txid = self.create_bandwidth_pool(pool_calc['bandwidth_pool_trx'])
            if not bandwidth_txid:
                logger.error("Failed to create bandwidth pool")
                return False
            
            logger.info("Resource pools setup completed successfully!")
            logger.info(f"Energy pool TX: {energy_txid}")
            logger.info(f"Bandwidth pool TX: {bandwidth_txid}")
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to setup optimal pools: {e}")
            return False
    
    def enhanced_user_setup(self, user_address: str, 
                           activation_amount: float = 1.0,
                           energy_amount: int = 32_000,
                           bandwidth_amount: int = 1_000) -> bool:
        """Enhanced user setup using resource pools (same interface as existing)"""
        try:
            logger.info(f"Enhanced setup for user: {user_address}")
            
            gas_account = self.gas_station._get_gas_wallet_account()
            
            # Step 1: Send TRX for activation (same as before)
            activation_sun = int(activation_amount * 1_000_000)
            transfer_txn = (
                self.gas_station.client.trx.transfer(
                    from_=gas_account.address,
                    to=user_address,
                    amount=activation_sun
                )
                .memo(f"Activation for {user_address[:10]}...")
                .build()
                .sign(self.tron_config.gas_wallet_private_key)
            )
            
            result = transfer_txn.broadcast()
            activation_txid = result["txid"]
            
            if not self.gas_station._wait_for_transaction(activation_txid, "User activation"):
                logger.error("User activation failed")
                return False
            
            # Step 2: Delegate energy from pool (enhanced approach)
            delegate_energy_txn = (
                self.gas_station.client.trx.delegate_resource(
                    owner=gas_account.address,
                    receiver=user_address,
                    balance=energy_amount,
                    resource="ENERGY"
                )
                .memo(f"Energy delegation to {user_address[:10]}...")
                .build()
                .sign(self.tron_config.gas_wallet_private_key)
            )
            
            energy_result = delegate_energy_txn.broadcast()
            energy_txid = energy_result["txid"]
            
            if not self.gas_station._wait_for_transaction(energy_txid, "Energy delegation"):
                logger.error("Energy delegation failed")
                return False
            
            # Step 3: Delegate bandwidth from pool
            delegate_bw_txn = (
                self.gas_station.client.trx.delegate_resource(
                    owner=gas_account.address,
                    receiver=user_address,
                    balance=bandwidth_amount,
                    resource="BANDWIDTH"
                )
                .memo(f"Bandwidth delegation to {user_address[:10]}...")
                .build()
                .sign(self.tron_config.gas_wallet_private_key)
            )
            
            bw_result = delegate_bw_txn.broadcast()
            bw_txid = bw_result["txid"]
            
            if self.gas_station._wait_for_transaction(bw_txid, "Bandwidth delegation"):
                logger.info(f"Enhanced user setup completed for {user_address}")
                logger.info(f"Activation TX: {activation_txid}")
                logger.info(f"Energy TX: {energy_txid}")
                logger.info(f"Bandwidth TX: {bw_txid}")
                return True
            else:
                logger.error("Bandwidth delegation failed")
                return False
            
        except Exception as e:
            logger.error(f"Enhanced user setup failed: {e}")
            return False
    
    def display_pool_status(self):
        """Display comprehensive resource pool status"""
        print("\n" + "="*70)
        print("🏭 ENHANCED GAS STATION - RESOURCE POOL STATUS")
        print("="*70)
        
        resources = self.get_current_resources()
        if not resources:
            print("❌ Could not retrieve resource status")
            return
        
        print(f"📍 Wallet: {resources['address']}")
        print(f"💰 Available Balance: {resources['balance_trx']:,.6f} TRX")
        print(f"🔒 Total Staked: {resources['total_staked_trx']:,.1f} TRX")
        
        energy = resources['energy']
        print(f"\n⚡ ENERGY POOL:")
        print(f"   💎 Staked: {energy['staked_trx']:,.1f} TRX")
        print(f"   🔋 Available: {energy['available']:,} units")
        print(f"   ⚖️ Used: {energy['used']:,} / {energy['limit']:,} units")
        print(f"   📊 Usage: {(energy['used'] / energy['limit'] * 100) if energy['limit'] > 0 else 0:.1f}%")
        
        bandwidth = resources['bandwidth']
        total_bw = bandwidth['limit'] + bandwidth['free_limit']
        print(f"\n📡 BANDWIDTH POOL:")
        print(f"   💎 Staked: {bandwidth['staked_trx']:,.1f} TRX")
        print(f"   📶 Available: {bandwidth['available']:,} units")
        print(f"   ⚖️ Used: {bandwidth['used']:,} / {total_bw:,} units")
        print(f"   📊 Usage: {(bandwidth['used'] / total_bw * 100) if total_bw > 0 else 0:.1f}%")
        
        # Calculate capacity
        energy_tx_capacity = energy['available'] // 65_000 if energy['available'] > 0 else 0
        bandwidth_tx_capacity = bandwidth['available'] // 345 if bandwidth['available'] > 0 else 0
        activation_capacity = int(resources['balance_trx'] / 1.0)
        
        bottleneck_capacity = min(energy_tx_capacity, bandwidth_tx_capacity, activation_capacity)
        
        print(f"\n📊 CURRENT CAPACITY:")
        print(f"   ⚡ Energy-limited transactions: {energy_tx_capacity:,}")
        print(f"   📡 Bandwidth-limited transactions: {bandwidth_tx_capacity:,}")
        print(f"   💰 Activation-limited users: {activation_capacity:,}")
        print(f"   🎯 Current bottleneck: {bottleneck_capacity:,} users")
        
        # Health indicators
        energy_health = "🟢" if energy['available'] > 500_000 else "🟡" if energy['available'] > 100_000 else "🔴"
        bandwidth_health = "🟢" if bandwidth['available'] > 10_000 else "🟡" if bandwidth['available'] > 2_000 else "🔴"
        balance_health = "🟢" if resources['balance_trx'] > 100 else "🟡" if resources['balance_trx'] > 10 else "🔴"
        
        print(f"\n❤️ HEALTH STATUS:")
        print(f"   {energy_health} Energy Pool: {'Healthy' if energy_health == '🟢' else 'Low' if energy_health == '🟡' else 'Critical'}")
        print(f"   {bandwidth_health} Bandwidth Pool: {'Healthy' if bandwidth_health == '🟢' else 'Low' if bandwidth_health == '🟡' else 'Critical'}")
        print(f"   {balance_health} Balance: {'Healthy' if balance_health == '🟢' else 'Low' if balance_health == '🟡' else 'Critical'}")


def demo_resource_pools():
    """Demonstration of resource pool enhancement"""
    print("🚀 Enhanced Gas Station with Resource Pools")
    print("="*60)
    
    try:
        # Initialize enhancement
        enhancement = ResourcePoolEnhancement()
        
        # Display current status
        enhancement.display_pool_status()
        
        # Calculate optimal pools for different user counts
        print(f"\n💡 OPTIMAL POOL CALCULATIONS:")
        print("="*60)
        
        for users in [100, 500, 1000, 2000]:
            calc = enhancement.calculate_optimal_pools(users)
            print(f"\nFor {users:,} users:")
            print(f"   Energy pool: {calc['energy_pool_trx']:,.0f} TRX")
            print(f"   Bandwidth pool: {calc['bandwidth_pool_trx']:,.0f} TRX")
            print(f"   Activation budget: {calc['activation_trx_per_user'] * users:,.0f} TRX")
            print(f"   Total needed: {calc['total_trx_needed']:,.0f} TRX")
        
        print(f"\n🎯 RECOMMENDED NEXT STEPS:")
        print("="*40)
        print("1. Choose target user count (e.g., 1000 users)")
        print("2. Run: enhancement.setup_optimal_pools(1000)")
        print("3. Use: enhancement.enhanced_user_setup(user_address)")
        print("4. Monitor with: enhancement.display_pool_status()")
        
    except Exception as e:
        logger.error(f"Demo error: {e}")
        print(f"❌ Demo failed: {e}")


if __name__ == "__main__":
    # Setup logging
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
    
    demo_resource_pools()
