#!/usr/bin/env python3
"""Enhanced Gas Station with Resource Pool Management

This module demonstrates how to implement an efficient gas station using
resource staking pools instead of direct TRX delegation for each user.
"""

import os
import sys
sys.path.append('src')

from dotenv import load_dotenv
load_dotenv()

from tronpy import Tron
from tronpy.keys import PrivateKey
import time
import logging

logger = logging.getLogger(__name__)

class ResourcePoolGasStation:
    """
    Advanced Gas Station that uses staked resource pools for efficient delegation
    
    Instead of staking TRX for each user individually, this maintains large
    resource pools (staked TRX) and delegates from those pools.
    """
    
    def __init__(self):
        self.private_key = os.getenv('GAS_WALLET_PRIVATE_KEY')
        self.network = os.getenv('TRON_NETWORK', 'testnet')
        
        # Initialize TRON client
        if self.network == 'testnet':
            try:
                # Try local node first
                self.tron = Tron(network='nile')
                local_node = os.getenv('TRON_TESTNET_LOCAL_FULL_NODE')
                if local_node:
                    # Note: TronPy doesn't easily allow custom endpoints, 
                    # but we can test connectivity
                    print(f"🔗 Using Nile testnet (preferring local: {local_node})")
            except:
                self.tron = Tron(network='nile')
        else:
            self.tron = Tron()
            
        # Get wallet account
        priv_key = PrivateKey(bytes.fromhex(self.private_key))
        self.account = self.tron.generate_address_from_private_key(self.private_key)
        self.address = self.account['base58check_address']
        
        print(f"💰 Gas Station Wallet: {self.address}")
        
    def get_account_resources(self, address=None):
        """Get current energy and bandwidth resources for an address"""
        if address is None:
            address = self.address
            
        try:
            account = self.tron.get_account(address)
            resources = self.tron.get_account_resource(address)
            
            # Current energy and bandwidth
            energy_limit = resources.get('EnergyLimit', 0)
            energy_used = resources.get('EnergyUsed', 0)
            bandwidth_limit = resources.get('NetLimit', 0) + resources.get('freeNetLimit', 0)
            bandwidth_used = resources.get('NetUsed', 0)
            
            # Frozen/staked resources
            frozen_energy = 0
            frozen_bandwidth = 0
            
            frozen_v2 = account.get('frozenV2', [])
            for freeze in frozen_v2:
                if freeze.get('type') == 'ENERGY':
                    frozen_energy += freeze.get('amount', 0)
                elif freeze.get('type') == 'BANDWIDTH':
                    frozen_bandwidth += freeze.get('amount', 0)
            
            return {
                'energy': {
                    'available': energy_limit - energy_used,
                    'total': energy_limit,
                    'used': energy_used,
                    'staked_trx': frozen_energy / 1_000_000
                },
                'bandwidth': {
                    'available': bandwidth_limit - bandwidth_used,
                    'total': bandwidth_limit,
                    'used': bandwidth_used,
                    'staked_trx': frozen_bandwidth / 1_000_000
                }
            }
        except Exception as e:
            print(f"❌ Error getting resources: {e}")
            return None
    
    def stake_for_resources(self, amount_trx, resource_type='ENERGY'):
        """
        Stake TRX to get energy or bandwidth resources
        
        This creates a resource pool that can be delegated to users
        """
        try:
            amount_sun = int(amount_trx * 1_000_000)
            
            print(f"🔄 Staking {amount_trx} TRX for {resource_type}...")
            
            # Create freeze transaction
            txn = self.tron.trx.freeze_balance(
                owner=self.address,
                frozen_balance=amount_sun,
                frozen_duration=3,  # Minimum 3 days
                resource=resource_type
            ).build().sign(self.private_key)
            
            result = txn.broadcast()
            txid = result['txid']
            
            print(f"✅ Staking transaction: {txid}")
            
            # Wait for confirmation
            if self._wait_for_transaction(txid):
                print(f"✅ Successfully staked {amount_trx} TRX for {resource_type}")
                return True
            else:
                print(f"❌ Staking transaction failed")
                return False
                
        except Exception as e:
            print(f"❌ Error staking: {e}")
            return False
    
    def delegate_resources(self, to_address, energy_amount=None, bandwidth_amount=None):
        """
        Delegate resources from staked pools to a user
        
        This is much more efficient than staking TRX for each user
        """
        try:
            results = []
            
            if energy_amount and energy_amount > 0:
                print(f"⚡ Delegating {energy_amount} TRX worth of ENERGY to {to_address}")
                
                energy_sun = int(energy_amount * 1_000_000)
                txn = self.tron.trx.delegate_resource(
                    owner=self.address,
                    receiver=to_address,
                    balance=energy_sun,
                    resource='ENERGY'
                ).build().sign(self.private_key)
                
                result = txn.broadcast()
                energy_txid = result['txid']
                results.append(('ENERGY', energy_txid))
                
                if self._wait_for_transaction(energy_txid):
                    print(f"✅ Energy delegation successful: {energy_txid}")
                else:
                    print(f"❌ Energy delegation failed")
                    return False
            
            if bandwidth_amount and bandwidth_amount > 0:
                print(f"📡 Delegating {bandwidth_amount} TRX worth of BANDWIDTH to {to_address}")
                
                bandwidth_sun = int(bandwidth_amount * 1_000_000)
                txn = self.tron.trx.delegate_resource(
                    owner=self.address,
                    receiver=to_address,
                    balance=bandwidth_sun,
                    resource='BANDWIDTH'
                ).build().sign(self.private_key)
                
                result = txn.broadcast()
                bandwidth_txid = result['txid']
                results.append(('BANDWIDTH', bandwidth_txid))
                
                if self._wait_for_transaction(bandwidth_txid):
                    print(f"✅ Bandwidth delegation successful: {bandwidth_txid}")
                else:
                    print(f"❌ Bandwidth delegation failed")
                    return False
            
            return True
            
        except Exception as e:
            print(f"❌ Error delegating resources: {e}")
            return False
    
    def activate_account(self, address, amount_trx=1.0):
        """Activate a TRON account by sending TRX"""
        try:
            amount_sun = int(amount_trx * 1_000_000)
            
            print(f"🔄 Activating account {address} with {amount_trx} TRX...")
            
            txn = self.tron.trx.transfer(
                from_=self.address,
                to=address,
                amount=amount_sun
            ).build().sign(self.private_key)
            
            result = txn.broadcast()
            txid = result['txid']
            
            if self._wait_for_transaction(txid):
                print(f"✅ Account activation successful: {txid}")
                return True
            else:
                print(f"❌ Account activation failed")
                return False
                
        except Exception as e:
            print(f"❌ Error activating account: {e}")
            return False
    
    def full_user_setup(self, user_address, activation_trx=1.0, energy_trx=1.0, bandwidth_trx=0.5):
        """
        Complete user setup: activation + resource delegation
        
        This is the main function for gas station operations
        """
        print(f"🚀 Setting up user: {user_address}")
        print(f"   Activation: {activation_trx} TRX")
        print(f"   Energy: {energy_trx} TRX")
        print(f"   Bandwidth: {bandwidth_trx} TRX")
        
        # Step 1: Activate account
        if not self.activate_account(user_address, activation_trx):
            return False
        
        # Step 2: Delegate resources
        if not self.delegate_resources(user_address, energy_trx, bandwidth_trx):
            return False
        
        print(f"✅ User setup complete for {user_address}")
        return True
    
    def _wait_for_transaction(self, txid, max_attempts=15):
        """Wait for transaction confirmation"""
        for attempt in range(max_attempts):
            try:
                info = self.tron.get_transaction_info(txid)
                if info and info.get('receipt', {}).get('result') == 'SUCCESS':
                    return True
                time.sleep(2)
            except:
                time.sleep(2)
        return False
    
    def show_status(self):
        """Show current gas station status"""
        print(f"\\n📊 Gas Station Status")
        print(f"=" * 50)
        
        # Get balance
        balance = self.tron.get_account(self.address).get('balance', 0) / 1_000_000
        print(f"💰 TRX Balance: {balance:,.6f} TRX")
        
        # Get resources
        resources = self.get_account_resources()
        if resources:
            print(f"⚡ Energy Pool: {resources['energy']['staked_trx']:,.1f} TRX staked")
            print(f"   Available: {resources['energy']['available']:,} / {resources['energy']['total']:,}")
            print(f"📡 Bandwidth Pool: {resources['bandwidth']['staked_trx']:,.1f} TRX staked")
            print(f"   Available: {resources['bandwidth']['available']:,} / {resources['bandwidth']['total']:,}")
        
        print(f"\\n🎯 Operational Capacity:")
        print(f"   Account activations: {int(balance / 1.0):,} (1.0 TRX each)")
        print(f"   Energy delegations: {int(balance / 1.0):,} (1.0 TRX each)")
        print(f"   Bandwidth delegations: {int(balance / 0.5):,} (0.5 TRX each)")

def main():
    """Demonstrate enhanced gas station functionality"""
    print("🏭 Enhanced Gas Station with Resource Pools")
    print("=" * 60)
    
    # Initialize gas station
    gas_station = ResourcePoolGasStation()
    
    # Show current status
    gas_station.show_status()
    
    print(f"\\n💡 Resource Pool Strategy:")
    print(f"Instead of staking TRX for each user individually:")
    print(f"1. Pre-stake large amounts for ENERGY and BANDWIDTH pools")
    print(f"2. Delegate from pools to users as needed")
    print(f"3. More efficient: lower transaction costs, better resource utilization")
    
    # Example: Stake resources for pools (uncomment to test)
    # print(f"\\n🔄 Example: Staking for resource pools...")
    # gas_station.stake_for_resources(100, 'ENERGY')     # Stake 100 TRX for energy pool
    # gas_station.stake_for_resources(50, 'BANDWIDTH')   # Stake 50 TRX for bandwidth pool
    
    # Example user setup (uncomment to test with real address)
    # test_address = "TYourTestAddressHere"
    # gas_station.full_user_setup(test_address, 1.0, 1.0, 0.5)

if __name__ == "__main__":
    main()
