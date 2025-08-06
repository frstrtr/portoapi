#!/usr/bin/env python3
"""
Enhanced Gas Station with Resource Pool Management
Implements efficient resource delegation using pre-staked pools
"""

import os
import time
from decimal import Decimal
from typing import Optional, Dict, Any
from dotenv import load_dotenv

try:
    from tronpy import Tron
    from tronpy.keys import PrivateKey
    from tronpy.exceptions import TronError
    TRONPY_AVAILABLE = True
except ImportError:
    TRONPY_AVAILABLE = False
    print("⚠️  TronPy not available. Install with: pip install tronpy")

class ResourcePoolGasStation:
    """Enhanced gas station using resource pools for efficiency"""
    
    def __init__(self, network: str = 'nile'):
        load_dotenv()
        
        if not TRONPY_AVAILABLE:
            raise ImportError("TronPy library required")
            
        self.network = network
        self.tron = Tron(network=network)
        
        # Load gas station wallet
        private_key = os.getenv('GAS_WALLET_PRIVATE_KEY')
        if not private_key:
            raise ValueError("GAS_WALLET_PRIVATE_KEY not found in .env")
            
        self.priv_key = PrivateKey(bytes.fromhex(private_key))
        self.address = self.priv_key.public_key.to_base58check_address()
        
        print(f"🏭 Resource Pool Gas Station initialized")
        print(f"📍 Network: {network}")
        print(f"💰 Wallet: {self.address}")
        
    def get_account_status(self) -> Dict[str, Any]:
        """Get comprehensive account status"""
        try:
            account = self.tron.get_account(self.address)
            resources = self.tron.get_account_resource(self.address)
            
            balance = account.get('balance', 0) / 1_000_000
            
            # Parse resource information
            energy_limit = resources.get('EnergyLimit', 0)
            energy_used = resources.get('EnergyUsed', 0)
            net_limit = resources.get('NetLimit', 0)
            net_used = resources.get('NetUsed', 0)
            free_net_limit = resources.get('freeNetLimit', 0)
            
            # Parse ALL frozen resources according to TRON Staking 2.0
            frozen_energy = 0
            frozen_bandwidth = 0
            frozen_tron_power = 0
            frozen_other = 0      # For any other unrecognized types
            
            # Check frozenV2 (comprehensive parsing per Staking 2.0)
            frozen_v2 = account.get('frozenV2', [])
            for freeze in frozen_v2:
                freeze_type = freeze.get('type')
                amount = freeze.get('amount', 0) / 1_000_000
                
                # Log the actual type for debugging
                print(f"DEBUG: Freeze type='{freeze_type}', amount={amount:,.1f} TRX")
                
                if freeze_type == 'ENERGY':
                    frozen_energy += amount
                elif freeze_type == 'BANDWIDTH':
                    frozen_bandwidth += amount
                elif freeze_type == 'NO_TYPE' or freeze_type is None or freeze_type == '':
                    # NO_TYPE/None = Type 0 = BANDWIDTH staking in Staking 2.0
                    frozen_bandwidth += amount
                elif freeze_type == 'TRON_POWER':
                    frozen_tron_power += amount
                else:
                    # Any other unrecognized types
                    print(f"DEBUG: Unrecognized freeze type: '{freeze_type}'")
                    frozen_other += amount
            
            # In Staking 2.0, each stake type can only delegate to its own resource type
            # Energy stakes can only delegate to energy users
            # Bandwidth stakes can only delegate to bandwidth users
            total_delegatable_energy = frozen_energy  # Only energy stakes can delegate energy
            total_delegatable_bandwidth = frozen_bandwidth + frozen_other  # Bandwidth + unrecognized
            total_delegatable = total_delegatable_energy + total_delegatable_bandwidth
            
            # Calculate what's actually being used from resource limits
            effective_energy_stake = energy_limit / 32_000 if energy_limit > 0 else 0
            effective_bandwidth_stake = net_limit / 1_000 if net_limit > 0 else 0
            
            # Total amounts
            total_frozen = frozen_energy + frozen_bandwidth + frozen_other + frozen_tron_power
            total_effective = effective_energy_stake + effective_bandwidth_stake
            
            return {
                'balance': balance,
                'energy': {
                    'limit': energy_limit,
                    'used': energy_used,
                    'available': energy_limit - energy_used,
                    'staked': effective_energy_stake,  # What's currently allocated to energy
                    'frozen_declared': frozen_energy,   # TRX explicitly staked for energy
                    'delegatable_pool': total_delegatable_energy  # Energy stakes available for delegation
                },
                'bandwidth': {
                    'limit': net_limit,
                    'free_limit': free_net_limit,
                    'used': net_used,
                    'available': (net_limit + free_net_limit) - net_used,
                    'staked': effective_bandwidth_stake,  # What's currently allocated to bandwidth
                    'frozen_declared': frozen_bandwidth + frozen_other,  # All bandwidth-compatible stakes
                    'delegatable_pool': total_delegatable_bandwidth  # Bandwidth stakes available for delegation
                },
                'total_staked': total_effective,  # Currently working
                'total_frozen': total_frozen,     # All frozen amounts
                'total_delegatable': total_delegatable,  # Total available for delegation (both types)
                'debug_info': {
                    'frozenV2_count': len(frozen_v2),
                    'frozen_energy': frozen_energy,
                    'frozen_bandwidth': frozen_bandwidth,
                    'frozen_other': frozen_other,  # Unrecognized types
                    'frozen_tron_power': frozen_tron_power,
                    'effective_energy_stake': effective_energy_stake,
                    'effective_bandwidth_stake': effective_bandwidth_stake,
                    'total_frozen_declared': total_frozen,
                    'total_effective_working': total_effective,
                    'total_delegatable_pool': total_delegatable,
                    'delegatable_energy_pool': total_delegatable_energy,
                    'delegatable_bandwidth_pool': total_delegatable_bandwidth,
                    'delegation_utilization': (total_effective / total_delegatable * 100) if total_delegatable > 0 else 0
                }
            }
            
        except Exception as e:
            print(f"❌ Error getting account status: {e}")
            return {}
    
    def create_energy_pool(self, amount_trx: float) -> bool:
        """Create energy pool by staking TRX"""
        try:
            print(f"🔋 Creating energy pool: {amount_trx} TRX")
            
            # Convert TRX to sun (1 TRX = 1,000,000 sun)
            amount_sun = int(amount_trx * 1_000_000)
            
            # Build freeze transaction for energy
            txn = (
                self.tron.trx.freeze_balance_v2(
                    frozen_balance=amount_sun,
                    resource="ENERGY"
                )
                .memo("Gas Station Energy Pool")
                .build()
                .inspect()
                .sign(self.priv_key)
            )
            
            result = txn.broadcast()
            print(f"✅ Energy pool created. TX: {result['txid']}")
            
            # Wait for confirmation
            time.sleep(3)
            return True
            
        except Exception as e:
            print(f"❌ Failed to create energy pool: {e}")
            return False
    
    def create_bandwidth_pool(self, amount_trx: float) -> bool:
        """Create bandwidth pool by staking TRX"""
        try:
            print(f"📡 Creating bandwidth pool: {amount_trx} TRX")
            
            # Convert TRX to sun
            amount_sun = int(amount_trx * 1_000_000)
            
            # Build freeze transaction for bandwidth
            txn = (
                self.tron.trx.freeze_balance_v2(
                    frozen_balance=amount_sun,
                    resource="BANDWIDTH"
                )
                .memo("Gas Station Bandwidth Pool")
                .build()
                .inspect()
                .sign(self.priv_key)
            )
            
            result = txn.broadcast()
            print(f"✅ Bandwidth pool created. TX: {result['txid']}")
            
            # Wait for confirmation
            time.sleep(3)
            return True
            
        except Exception as e:
            print(f"❌ Failed to create bandwidth pool: {e}")
            return False
    
    def delegate_energy_to_user(self, user_address: str, amount: int = 32000) -> bool:
        """Delegate energy from pool to user"""
        try:
            print(f"⚡ Delegating {amount} energy to {user_address}")
            
            txn = (
                self.tron.trx.delegate_resource(
                    resource="ENERGY",
                    balance=amount,
                    receiver_address=user_address
                )
                .memo(f"Energy delegation to {user_address[:10]}...")
                .build()
                .inspect()
                .sign(self.priv_key)
            )
            
            result = txn.broadcast()
            print(f"✅ Energy delegated. TX: {result['txid']}")
            return True
            
        except Exception as e:
            print(f"❌ Failed to delegate energy: {e}")
            return False
    
    def delegate_bandwidth_to_user(self, user_address: str, amount: int = 1000) -> bool:
        """Delegate bandwidth from pool to user"""
        try:
            print(f"📊 Delegating {amount} bandwidth to {user_address}")
            
            txn = (
                self.tron.trx.delegate_resource(
                    resource="BANDWIDTH",
                    balance=amount,
                    receiver_address=user_address
                )
                .memo(f"Bandwidth delegation to {user_address[:10]}...")
                .build()
                .inspect()
                .sign(self.priv_key)
            )
            
            result = txn.broadcast()
            print(f"✅ Bandwidth delegated. TX: {result['txid']}")
            return True
            
        except Exception as e:
            print(f"❌ Failed to delegate bandwidth: {e}")
            return False
    
    def setup_user_account(self, user_address: str, 
                          activation_amount: float = 1.0,
                          energy_amount: int = 32000,
                          bandwidth_amount: int = 1000) -> bool:
        """Complete user setup: activation + resource delegation"""
        try:
            print(f"\n🚀 Setting up user account: {user_address}")
            
            # Step 1: Send TRX for activation
            activation_sun = int(activation_amount * 1_000_000)
            
            txn = (
                self.tron.trx.transfer(
                    to=user_address,
                    amount=activation_sun
                )
                .memo(f"Account activation for {user_address[:10]}...")
                .build()
                .inspect()
                .sign(self.priv_key)
            )
            
            result = txn.broadcast()
            print(f"💰 Activation TRX sent. TX: {result['txid']}")
            
            # Wait for confirmation
            time.sleep(3)
            
            # Step 2: Delegate energy from pool
            if not self.delegate_energy_to_user(user_address, energy_amount):
                print("⚠️  Energy delegation failed")
                return False
            
            # Wait between operations
            time.sleep(2)
            
            # Step 3: Delegate bandwidth from pool
            if not self.delegate_bandwidth_to_user(user_address, bandwidth_amount):
                print("⚠️  Bandwidth delegation failed")
                return False
            
            print(f"✅ User {user_address[:10]}... fully set up!")
            return True
            
        except Exception as e:
            print(f"❌ Failed to setup user account: {e}")
            return False
    
    def display_status(self):
        """Display comprehensive gas station status"""
        print("\n" + "="*60)
        print("🏭 RESOURCE POOL GAS STATION STATUS")
        print("="*60)
        
        status = self.get_account_status()
        if not status:
            print("❌ Could not retrieve status")
            return
        
        print(f"💰 Balance: {status['balance']:,.6f} TRX")
        print(f"🔒 Total Staked: {status['total_staked']:,.1f} TRX")
        
        energy = status['energy']
        print(f"\n⚡ ENERGY POOL:")
        print(f"   Staked: {energy['staked']:,.1f} TRX")
        print(f"   Available: {energy['available']:,} units")
        print(f"   Used: {energy['used']:,} units")
        print(f"   Limit: {energy['limit']:,} units")
        
        bandwidth = status['bandwidth']
        print(f"\n📡 BANDWIDTH POOL:")
        print(f"   Staked: {bandwidth['staked']:,.1f} TRX")
        print(f"   Available: {bandwidth['available']:,} units")
        print(f"   Used: {bandwidth['used']:,} units")
        print(f"   Net Limit: {bandwidth['limit']:,} units")
        print(f"   Free Limit: {bandwidth['free_limit']:,} units")
        
        # Calculate capacity estimates
        energy_capacity = energy['available'] // 65000  # ~65k energy per tx
        bandwidth_capacity = bandwidth['available'] // 345  # ~345 bandwidth per tx
        activation_capacity = int(status['balance'] / 1.0)  # 1 TRX per activation
        
        print(f"\n📊 CAPACITY ESTIMATES:")
        print(f"   Energy-limited transactions: {energy_capacity:,}")
        print(f"   Bandwidth-limited transactions: {bandwidth_capacity:,}")
        print(f"   Activation-limited users: {activation_capacity:,}")
        print(f"   Bottleneck: {min(energy_capacity, bandwidth_capacity, activation_capacity):,}")
        
        # Show debug information
        debug = status['debug_info']
        energy = status['energy']
        bandwidth = status['bandwidth']
        
        print(f"\n🔍 STAKING 2.0 ANALYSIS (CORRECTED):")
        print(f"   Available balance: {status['balance']:,.1f} TRX")
        print(f"   Energy delegation pool: {energy['delegatable_pool']:,.1f} TRX")
        print(f"   Bandwidth delegation pool: {bandwidth['delegatable_pool']:,.1f} TRX")
        print(f"   Total delegatable: {debug['total_delegatable_pool']:,.1f} TRX")
        print(f"   Currently delegated: {debug['total_effective_working']:,.1f} TRX")
        print(f"   Delegation utilization: {debug['delegation_utilization']:.1f}%")
        
        print(f"\n📋 STAKING BREAKDOWN:")
        print(f"   Energy stakes: {debug['frozen_energy']:,.1f} TRX → Can only delegate ENERGY")
        print(f"   Bandwidth stakes: {debug['frozen_bandwidth']:,.1f} TRX → Can only delegate BANDWIDTH") 
        print(f"   Other stakes: {debug['frozen_other']:,.1f} TRX")
        print(f"   TRON Power (voting): {debug['frozen_tron_power']:,.1f} TRX")
        
        print(f"\n⚡ CURRENT DELEGATION:")
        print(f"   Energy allocated: {debug['effective_energy_stake']:,.1f} TRX")
        print(f"   Bandwidth allocated: {debug['effective_bandwidth_stake']:,.1f} TRX")
        
        # Show delegation potential with correct limits
        unused_energy = energy['delegatable_pool'] - debug['effective_energy_stake']
        unused_bandwidth = bandwidth['delegatable_pool'] - debug['effective_bandwidth_stake']
        
        if unused_energy > 100 or unused_bandwidth > 100:
            print(f"\n🚀 DELEGATION OPPORTUNITY (CORRECTED):")
            print(f"   Unused ENERGY delegation capacity: {unused_energy:,.0f} TRX")
            print(f"   Unused BANDWIDTH delegation capacity: {unused_bandwidth:,.0f} TRX")
            
            # Calculate what each pool could provide
            potential_energy_users = int(unused_energy * 32_000 / 65_000)  # 32k stake, 65k energy per tx
            potential_bandwidth_users = int(unused_bandwidth * 1_000 / 345)  # 1k stake, 345 bandwidth per tx
            
            print(f"   Could support {potential_energy_users:,} more ENERGY users")
            print(f"   Could support {potential_bandwidth_users:,} more BANDWIDTH users")
            print(f"   ⚠️  Each stake type can ONLY delegate to its own resource type!")
        
        # Show total capacity potential
        total_controlled = status['balance'] + debug['total_delegatable_pool'] + debug['frozen_tron_power']
        
        print(f"\n💰 TOTAL ASSETS (Staking 2.0):")
        print(f"   Available balance: {status['balance']:,.1f} TRX")
        print(f"   Energy delegation pool: {energy['delegatable_pool']:,.1f} TRX")
        print(f"   Bandwidth delegation pool: {bandwidth['delegatable_pool']:,.1f} TRX")
        print(f"   TRON Power (voting): {debug['frozen_tron_power']:,.1f} TRX")
        print(f"   Total controlled: {total_controlled:,.1f} TRX")
        
        if debug['total_delegatable_pool'] > 1000:
            print(f"\n✅ EXCELLENT! You have massive delegation pools!")
            print(f"   Energy pool: {energy['delegatable_pool']:,.0f} TRX for energy delegation")
            print(f"   Bandwidth pool: {bandwidth['delegatable_pool']:,.0f} TRX for bandwidth delegation")
            print(f"   This gives you enterprise-level gas station capabilities.")
            print(f"   Remember: Each pool can only delegate to its matching resource type!")


def demo_enhanced_gas_station():
    """Demonstration of enhanced gas station"""
    print("🏭 Enhanced Gas Station Demo")
    print("="*50)
    
    if not TRONPY_AVAILABLE:
        print("❌ TronPy not available. This is a simulation.")
        return
    
    try:
        # Initialize gas station
        gas_station = ResourcePoolGasStation('nile')
        
        # Display current status
        gas_station.display_status()
        
        print("\n💡 RECOMMENDED SETUP:")
        print("1. Create energy pool: 2000 TRX")
        print("2. Create bandwidth pool: 1000 TRX")
        print("3. Keep ~1000 TRX for user activations")
        
        # Simulated user setup
        test_user = "TTestUserAddress1234567890123456789012345"
        print(f"\n🧪 DEMO: Would setup user {test_user[:15]}...")
        print("   - Send 1.0 TRX for activation")
        print("   - Delegate 32,000 energy from pool")
        print("   - Delegate 1,000 bandwidth from pool")
        
    except Exception as e:
        print(f"❌ Demo error: {e}")


if __name__ == "__main__":
    demo_enhanced_gas_station()
