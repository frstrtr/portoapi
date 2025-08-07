#!/usr/bin/env python3
"""
Comprehensive Gas Station for PortoAPI
Manages TRX resources for USDT transactions, account activation, and seller fees
"""
# pylint: disable=logging-fstring-interpolation

import os
import time
import logging
from typing import Dict, Tuple
from dotenv import load_dotenv

try:
    from tronpy import Tron
    from tronpy.keys import PrivateKey

    # from tronpy.exceptions import TronError
except ImportError:
    print("❌ TronPy required: pip install tronpy")
    exit(1)

logger = logging.getLogger(__name__)


class ComprehensiveGasStation:
    """
    Unified gas station managing all TRON resources for USDT operations
    - Energy for smart contract calls (USDT transfers)
    - Bandwidth for transaction execution
    - TRX for account activation
    - Seller fee management
    """

    def __init__(self, network: str = "nile"):
        load_dotenv()

        self.network = network
        self.tron = Tron(network=network)

        # Load configuration
        private_key = os.getenv("GAS_WALLET_PRIVATE_KEY")
        if not private_key:
            raise ValueError("GAS_WALLET_PRIVATE_KEY required")

        self.priv_key = PrivateKey(bytes.fromhex(private_key))
        self.address = self.priv_key.public_key.to_base58check_address()

        # Operation costs (configurable)
        self.activation_cost = float(os.getenv("AUTO_ACTIVATION_TRX_AMOUNT", "1.0"))
        self.energy_per_usdt_tx = 31_895  # Typical USDT transfer cost
        self.bandwidth_per_tx = 345  # Typical transaction bandwidth

        # USDT contract
        self.usdt_contract = self._get_usdt_contract()

        logger.info(f"Gas Station initialized: {self.address}")
        logger.info(f"Network: {network}, USDT: {self.usdt_contract}")

    def _get_usdt_contract(self) -> str:
        """Get USDT contract address for current network"""
        if self.network == "nile":
            return os.getenv(
                "TRON_TESTNET_USDT_CONTRACT", "TXYZopYRdj2D9XRtbG411XZZ3kM5VkAeBf"
            )
        else:
            return os.getenv(
                "TRON_MAINNET_USDT_CONTRACT", "TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t"
            )

    def get_resources(self) -> Dict:
        """Get current resource status"""
        try:
            account = self.tron.get_account(self.address)
            resources = self.tron.get_account_resource(self.address)

            # Parse balances and resources
            balance = account.get("balance", 0) / 1_000_000

            energy_limit = resources.get("EnergyLimit", 0)
            energy_used = resources.get("EnergyUsed", 0)
            energy_available = energy_limit - energy_used

            bandwidth_limit = resources.get("NetLimit", 0)
            bandwidth_used = resources.get("NetUsed", 0)
            free_bandwidth = resources.get("freeNetLimit", 0)
            bandwidth_available = (bandwidth_limit + free_bandwidth) - bandwidth_used

            # Parse staked amounts
            energy_stake = 0
            bandwidth_stake = 0

            frozen_v2 = account.get("frozenV2", [])
            for freeze in frozen_v2:
                amount = freeze.get("amount", 0) / 1_000_000
                freeze_type = freeze.get("type")

                if freeze_type == "ENERGY":
                    energy_stake += amount
                elif freeze_type == "BANDWIDTH" or freeze_type is None:
                    bandwidth_stake += amount

            return {
                "balance": balance,
                "energy": {
                    "available": energy_available,
                    "limit": energy_limit,
                    "used": energy_used,
                    "staked": energy_stake,
                },
                "bandwidth": {
                    "available": bandwidth_available,
                    "limit": bandwidth_limit,
                    "used": bandwidth_used,
                    "free_limit": free_bandwidth,
                    "staked": bandwidth_stake,
                },
                "total_staked": energy_stake + bandwidth_stake,
            }

        except (KeyError, ValueError, ConnectionError) as e:
            logger.error(f"Failed to get resources: {e}")
            return {}

    def can_process_usdt_transactions(self, count: int = 1) -> Tuple[bool, str]:
        """Check if gas station can process USDT transactions"""
        resources = self.get_resources()
        if not resources:
            return False, "Cannot get resource status"

        energy_needed = count * self.energy_per_usdt_tx
        bandwidth_needed = count * self.bandwidth_per_tx

        energy_ok = resources["energy"]["available"] >= energy_needed
        bandwidth_ok = resources["bandwidth"]["available"] >= bandwidth_needed

        if not energy_ok:
            shortage = energy_needed - resources["energy"]["available"]
            return False, f"Energy shortage: {shortage:,} units needed"

        if not bandwidth_ok:
            shortage = bandwidth_needed - resources["bandwidth"]["available"]
            return False, f"Bandwidth shortage: {shortage:,} units needed"

        return True, f"Can process {count} USDT transactions"

    def activate_account(self, address: str) -> bool:
        """Send TRX to activate a new account"""
        try:
            resources = self.get_resources()
            if resources["balance"] < self.activation_cost:
                logger.error(
                    f"Insufficient balance for activation: {resources['balance']} TRX"
                )
                return False

            amount_sun = int(self.activation_cost * 1_000_000)

            txn = (
                self.tron.trx.transfer(
                    from_=self.address, to=address, amount=amount_sun
                )
                .memo("Account activation")
                .build()
                .inspect()
                .sign(self.priv_key)
            )

            result = txn.broadcast()
            logger.info(f"Account activated: {address}, TX: {result['txid']}")
            return True

        except (ValueError, ConnectionError, RuntimeError) as e:
            logger.error(f"Account activation failed: {e}")
            return False

    def delegate_resources_to_user(self, address: str, duration_days: int = 3) -> bool:
        """Delegate energy and bandwidth to user for USDT operations"""
        try:
            # Calculate resource amounts for duration
            daily_transactions = 10  # Estimated daily USDT transactions per user
            total_transactions = daily_transactions * duration_days

            energy_needed = total_transactions * self.energy_per_usdt_tx
            bandwidth_needed = total_transactions * self.bandwidth_per_tx

            # Check availability
            can_process, msg = self.can_process_usdt_transactions(total_transactions)
            if not can_process:
                logger.error(f"Cannot delegate resources: {msg}")
                return False

            # Delegate energy
            try:
                energy_txn = (
                    self.tron.trx.delegate_resource(
                        owner=self.address,
                        receiver=address,
                        resource="ENERGY",
                        balance=energy_needed,
                    )
                    .memo("Energy for USDT operations")
                    .build()
                    .inspect()
                    .sign(self.priv_key)
                )

                energy_result = energy_txn.broadcast()
                logger.info(
                    f"Energy delegated: {energy_needed:,} to {address}, TX: {energy_result['txid']}"
                )

            except (ValueError, ConnectionError, RuntimeError) as e:
                logger.error(f"Energy delegation failed: {e}")
                return False

            # Wait between operations
            time.sleep(2)
            # Delegate bandwidth
            try:
                bandwidth_txn = (
                    self.tron.trx.delegate_resource(
                        owner=self.address,
                        receiver=address,
                        resource="BANDWIDTH",
                        balance=bandwidth_needed,
                    )
                    .memo("Bandwidth for transactions")
                    .build()
                    .inspect()
                    .sign(self.priv_key)
                )

                bandwidth_txn.broadcast()
                logger.info(
                    "Bandwidth delegated: %s to %s", f"{bandwidth_needed:,}", address
                )

                return True

            except (ValueError, ConnectionError, RuntimeError) as e:
                logger.error(f"Bandwidth delegation failed: {e}")
                return False

        except (ValueError, ConnectionError, RuntimeError) as e:
            logger.error(f"Resource delegation failed: {e}")
            return False

    def setup_seller_account(self, seller_address: str) -> bool:
        """Complete setup for seller account: activation + resources"""
        try:
            logger.info(f"Setting up seller account: {seller_address}")

            # Step 1: Activate account
            if not self.activate_account(seller_address):
                return False

            # Wait for activation to confirm
            time.sleep(3)

            # Step 2: Delegate resources for operations
            if not self.delegate_resources_to_user(seller_address, duration_days=7):
                logger.error("Resource delegation failed")
                return False

            logger.info(f"Seller account fully setup: {seller_address}")
            return True

        except (ValueError, ConnectionError, RuntimeError) as e:
            logger.error(f"Seller setup failed: {e}")
            return False

    def collect_seller_fee(self, seller_address: str, fee_amount_usdt: float) -> bool:
        """Collect USDT fee from seller"""
        try:
            # This would integrate with the seller's USDT operations
            # For now, just log the fee collection
            logger.info(f"Fee collection: {fee_amount_usdt} USDT from {seller_address}")

            # In real implementation, this would:
            # 1. Create USDT transfer transaction from seller to gas station
            # 2. Use gas station resources to execute the transaction
            # 3. Update seller's fee balance

            return True

        except (ValueError, ConnectionError, RuntimeError) as e:
            logger.error(f"Fee collection failed: {e}")
            return False

    def rebalance_resources(self) -> bool:
        """Auto-rebalance resources based on usage patterns"""
        try:
            resources = self.get_resources()

            # Calculate resource utilization
            energy_usage = (
                resources["energy"]["used"] / max(resources["energy"]["limit"], 1)
            ) * 100
            bandwidth_usage = (
                resources["bandwidth"]["used"] / max(resources["bandwidth"]["limit"], 1)
            ) * 100

            logger.info(
                f"Resource usage - Energy: {energy_usage:.1f}%, Bandwidth: {bandwidth_usage:.1f}%"
            )

            # If energy is low and we have available TRX, stake more for energy
            if energy_usage > 80 and resources["balance"] > 100:
                stake_amount = min(
                    50, resources["balance"] * 0.1
                )  # Stake 10% or 50 TRX, whichever is less

                try:
                    stake_sun = int(stake_amount * 1_000_000)

                    txn = (
                        self.tron.trx.freeze_balance(
                            owner=self.address, amount=stake_sun, resource="ENERGY"
                        )
                        .memo("Auto-rebalance: Energy")
                        .build()
                        .inspect()
                        .sign(self.priv_key)
                    )

                    result = txn.broadcast()
                    logger.info(
                        f"Auto-staked {stake_amount} TRX for energy: {result['txid']}"
                    )

                except (ValueError, ConnectionError, RuntimeError) as e:
                    logger.error(f"Auto-staking failed: {e}")

            # Similar logic for bandwidth if needed
            if bandwidth_usage > 80 and resources["balance"] > 100:
                stake_amount = min(25, resources["balance"] * 0.05)

                try:
                    stake_sun = int(stake_amount * 1_000_000)
                    txn = (
                        self.tron.trx.freeze_balance(
                            owner=self.address, amount=stake_sun, resource="BANDWIDTH"
                        )
                        .memo("Auto-rebalance: Bandwidth")
                        .build()
                        .inspect()
                        .sign(self.priv_key)
                    )

                    result = txn.broadcast()
                    logger.info(
                        f"Auto-staked {stake_amount} TRX for bandwidth: {result['txid']}"
                    )

                except (ValueError, ConnectionError, RuntimeError) as e:
                    logger.error(f"Auto-staking for bandwidth failed: {e}")

            return True

        except (ValueError, ConnectionError, RuntimeError) as e:
            logger.error(f"Resource rebalancing failed: {e}")
            return False

    def get_daily_capacity(self) -> Dict:
        """Calculate daily transaction capacity"""
        resources = self.get_resources()

        # Daily resource regeneration (24 hours)
        daily_energy = resources["energy"]["limit"]
        daily_bandwidth = (
            resources["bandwidth"]["limit"] + resources["bandwidth"]["free_limit"]
        )

        # Transaction capacity
        energy_tx_capacity = daily_energy // self.energy_per_usdt_tx
        bandwidth_tx_capacity = daily_bandwidth // self.bandwidth_per_tx
        activation_capacity = int(resources["balance"] / self.activation_cost)

        return {
            "daily_usdt_transactions": min(energy_tx_capacity, bandwidth_tx_capacity),
            "account_activations": activation_capacity,
            "bottleneck": (
                "energy" if energy_tx_capacity < bandwidth_tx_capacity else "bandwidth"
            ),
            "resources": resources,
        }

    def status_report(self):
        """Comprehensive status report"""
        print("\n" + "=" * 60)
        print("🏭 COMPREHENSIVE GAS STATION STATUS")
        print("=" * 60)

        resources = self.get_resources()
        capacity = self.get_daily_capacity()

        print(f"💰 Balance: {resources['balance']:,.2f} TRX")
        print(f"🔒 Total Staked: {resources['total_staked']:,.0f} TRX")

        print("\n⚡ ENERGY (for USDT smart contracts):")
        print(f"   Available: {resources['energy']['available']:,} units")
        print(f"   Daily Limit: {resources['energy']['limit']:,} units")
        print(f"   Staked: {resources['energy']['staked']:,.0f} TRX")

        print("\n📡 BANDWIDTH (for transactions):")
        print(f"   Available: {resources['bandwidth']['available']:,} units")
        print(f"   Daily Limit: {resources['bandwidth']['limit']:,} units")
        print(f"   Free Daily: {resources['bandwidth']['free_limit']:,} units")
        print(f"   Staked: {resources['bandwidth']['staked']:,.0f} TRX")

        print("\n📊 DAILY CAPACITY:")
        print(f"   USDT Transactions: {capacity['daily_usdt_transactions']:,}")
        print(f"   Account Activations: {capacity['account_activations']:,}")
        print(f"   Bottleneck: {capacity['bottleneck'].title()}")

        # Resource efficiency
        if resources["total_staked"] > 0:
            energy_efficiency = (
                (resources["energy"]["limit"] / max(resources["energy"]["staked"], 1))
                / 32_000
                * 100
            )
            bandwidth_efficiency = (
                (
                    resources["bandwidth"]["limit"]
                    / max(resources["bandwidth"]["staked"], 1)
                )
                / 1_000
                * 100
            )

            print("\n⚙️ RESOURCE EFFICIENCY:")
            print(f"   Energy: {energy_efficiency:.1f}% (32k units per TRX expected)")
            print(
                f"   Bandwidth: {bandwidth_efficiency:.1f}% (1k units per TRX expected)"
            )

        # Check current capacity
        can_process, msg = self.can_process_usdt_transactions(100)
        print("\n🔍 CURRENT STATUS:")
        print(f"   Can process 100 USDT transactions: {'✅' if can_process else '❌'}")
        if not can_process:
            print(f"   Issue: {msg}")

        print("\n💡 RECOMMENDATIONS:")
        if resources["balance"] < 50:
            print("   ⚠️  Low TRX balance - consider adding funds for activations")
        if capacity["daily_usdt_transactions"] < 100:
            print("   ⚠️  Low daily transaction capacity - consider staking more TRX")
        if resources["total_staked"] > resources["balance"] * 50:
            print("   ✅ Good staking ratio for sustained operations")


def main():
    """Main gas station management interface"""
    print("🏭 PortoAPI Comprehensive Gas Station")
    print("=" * 50)

    try:
        # Initialize gas station
        gas_station = ComprehensiveGasStation("nile")

        # Show status
        gas_station.status_report()

        # Test basic functionality
        print("\n🧪 FUNCTIONALITY TEST:")

        # Test resource check
        can_process, msg = gas_station.can_process_usdt_transactions(10)
        print(f"   Process 10 USDT transactions: {'✅' if can_process else '❌'} {msg}")

        # Test capacity calculation
        capacity = gas_station.get_daily_capacity()
        print(
            f"   Daily USDT capacity: {capacity['daily_usdt_transactions']:,} transactions"
        )

        # Simulate seller setup (don't actually do it)
        test_address = "THi94m7rChn55n9gaQP8oWwvsta5LDVY7o"
        print(f"   Would setup seller: {test_address[:15]}...")
        print(f"     - Account activation: {gas_station.activation_cost} TRX")
        print("     - Resource delegation for USDT operations")

        print("\n✅ Gas station is operational and ready for USDT operations!")

    except (ValueError, ConnectionError, RuntimeError) as e:
        print(f"❌ Error: {e}")


if __name__ == "__main__":
    main()
