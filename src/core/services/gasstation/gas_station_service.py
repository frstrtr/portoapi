#!/usr/bin/env python3
"""
Comprehensive Gas Station Service for PortoAPI
Manages TRX resources for USDT transactions, account activation, and seller fees
"""

#pylint: lazyformat disable

import os
import time
import logging
from typing import Dict, Tuple, Optional
from decimal import Decimal
from dotenv import load_dotenv

try:
    from tronpy import Tron
    from tronpy.keys import PrivateKey
except ImportError:
    raise ImportError("TronPy required: pip install tronpy")

logger = logging.getLogger(__name__)


class GasStationService:
    """
    Unified gas station managing all TRON resources for USDT operations
    - Energy for smart contract calls (USDT transfers)
    - Bandwidth for transaction execution
    - TRX for account activation
    - Seller fee management
    """

    def __init__(self, config=None):
        """Initialize gas station with configuration"""
        load_dotenv()

        if config:
            self.network = getattr(config, "network", "testnet")
            self.private_key = getattr(config, "gas_wallet_private_key", None)
            self.activation_cost = getattr(config, "auto_activation_trx_amount", 1.0)
        else:
            # Fallback to environment variables
            self.network = os.getenv("TRON_NETWORK", "testnet")
            self.private_key = os.getenv("GAS_WALLET_PRIVATE_KEY")
            self.activation_cost = float(os.getenv("AUTO_ACTIVATION_TRX_AMOUNT", "1.0"))

        if not self.private_key:
            raise ValueError("Gas wallet private key is required")

        # Initialize TRON client using the same configuration as keeper bot
        tron_network = "nile" if self.network == "testnet" else "mainnet"  # Default network name
        
        if config:
            # Use the provided config's TRON client settings
            client_config = getattr(config, 'get_tron_client_config', lambda: {})()
            if client_config and client_config.get('node_type') == 'local':
                from tronpy.providers import HTTPProvider
                provider = HTTPProvider(endpoint_uri=client_config['full_node'])
                self.tron = Tron(provider=provider)
                tron_network = f"local:{client_config['full_node']}"
                logger.info(f"Gas station connected to local TRON node: {client_config['full_node']}")
            else:
                # Fallback to remote
                fallback_config = getattr(config, 'get_fallback_client_config', lambda: {})()
                if fallback_config and fallback_config.get('api_key'):
                    from tronpy.providers import HTTPProvider
                    provider = HTTPProvider(
                        endpoint_uri=fallback_config['full_node'],
                        api_key=fallback_config['api_key']
                    )
                    self.tron = Tron(provider=provider)
                    tron_network = f"remote:{fallback_config['full_node']}"
                    logger.info(f"Gas station connected to remote TRON with API key")
                else:
                    self.tron = Tron(network=tron_network)
                    logger.info(f"Gas station connected to default TRON {tron_network}")
        else:
            # Fallback to default public endpoints
            self.tron = Tron(network=tron_network)
            logger.info(f"Gas station using default TRON {tron_network}")

        # Setup wallet
        self.priv_key = PrivateKey(bytes.fromhex(self.private_key))
        self.address = self.priv_key.public_key.to_base58check_address()

        # Operation costs (based on network analysis)
        self.energy_per_usdt_tx = 31_895  # Typical USDT transfer energy cost
        self.bandwidth_per_tx = 345  # Typical transaction bandwidth cost

        # USDT contract address
        self.usdt_contract = self._get_usdt_contract()

        logger.info(f"Gas Station initialized: {self.address}")
        logger.info(f"Network: {tron_network}, USDT: {self.usdt_contract}")

    def _get_usdt_contract(self) -> str:
        """Get USDT contract address for current network"""
        if self.network == "testnet":
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
            # Add timeout for network calls
            import time
            start_time = time.time()
            
            account = self.tron.get_account(self.address)
            
            # Check if call took too long
            if time.time() - start_time > 10:  # 10 second timeout
                logger.warning("TRON account call took longer than 10 seconds")
            
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

            # Parse staked amounts (Staking 2.0 format)
            energy_stake = 0
            bandwidth_stake = 0

            frozen_v2 = account.get("frozenV2", [])
            for freeze in frozen_v2:
                amount = freeze.get("amount", 0) / 1_000_000
                freeze_type = freeze.get("type")

                if freeze_type == "ENERGY":
                    energy_stake += amount
                elif freeze_type == "BANDWIDTH" or freeze_type is None:
                    # None type = Type 0 = BANDWIDTH staking in Staking 2.0
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

        except Exception as e:
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

    def activate_account(self, address: str) -> Tuple[bool, Optional[str]]:
        """Send TRX to activate a new account"""
        try:
            resources = self.get_resources()
            if resources["balance"] < self.activation_cost:
                error_msg = (
                    f"Insufficient balance for activation: {resources['balance']} TRX"
                )
                logger.error(error_msg)
                return False, None

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
            txid = result.get("txid")
            logger.info(f"Account activated: {address}, TX: {txid}")
            return True, txid

        except Exception as e:
            logger.error(f"Account activation failed: {e}")
            return False, None

    def delegate_resources_to_user(
        self, address: str, duration_days: int = 3
    ) -> Tuple[bool, Optional[str]]:
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
                return False, None

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
                energy_txid = energy_result.get("txid")
                logger.info(
                    f"Energy delegated: {energy_needed:,} to {address}, TX: {energy_txid}"
                )

            except Exception as e:
                logger.error(f"Energy delegation failed: {e}")
                return False, None

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

                bandwidth_result = bandwidth_txn.broadcast()
                bandwidth_txid = bandwidth_result.get("txid")
                logger.info(
                    f"Bandwidth delegated: {bandwidth_needed:,} to {address}, TX: {bandwidth_txid}"
                )

                return True, energy_txid  # Return first transaction ID

            except Exception as e:
                logger.error(f"Bandwidth delegation failed: {e}")
                return False, None

        except Exception as e:
            logger.error(f"Resource delegation failed: {e}")
            return False, None

    def setup_seller_account(self, seller_address: str) -> Tuple[bool, Dict[str, str]]:
        """Complete setup for seller account: activation + resources"""
        try:
            logger.info(f"Setting up seller account: {seller_address}")
            transactions = {}

            # Step 1: Activate account
            success, activation_txid = self.activate_account(seller_address)
            if not success:
                return False, {}

            transactions["activation"] = activation_txid

            # Wait for activation to confirm
            time.sleep(3)

            # Step 2: Delegate resources for operations
            success, delegation_txid = self.delegate_resources_to_user(
                seller_address, duration_days=7
            )
            if not success:
                logger.error("Resource delegation failed")
                return False, transactions

            transactions["delegation"] = delegation_txid

            logger.info(f"Seller account fully setup: {seller_address}")
            return True, transactions

        except Exception as e:
            logger.error(f"Seller setup failed: {e}")
            return False, {}

    def get_daily_capacity(self) -> Dict:
        """Calculate daily transaction capacity"""
        resources = self.get_resources()

        # Daily resource regeneration (24 hours)
        daily_energy = resources["energy"]["limit"]
        daily_bandwidth = (
            resources["bandwidth"]["limit"] + resources["bandwidth"]["free_limit"]
        )

        # Transaction capacity
        energy_tx_capacity = (
            daily_energy // self.energy_per_usdt_tx if daily_energy > 0 else 0
        )
        bandwidth_tx_capacity = (
            daily_bandwidth // self.bandwidth_per_tx if daily_bandwidth > 0 else 0
        )
        activation_capacity = (
            int(resources["balance"] / self.activation_cost)
            if self.activation_cost > 0
            else 0
        )

        return {
            "daily_usdt_transactions": min(energy_tx_capacity, bandwidth_tx_capacity),
            "account_activations": activation_capacity,
            "bottleneck": (
                "energy" if energy_tx_capacity < bandwidth_tx_capacity else "bandwidth"
            ),
            "energy_capacity": energy_tx_capacity,
            "bandwidth_capacity": bandwidth_tx_capacity,
            "resources": resources,
        }

    def get_status(self) -> Dict:
        """Get comprehensive gas station status"""
        resources = self.get_resources()
        capacity = self.get_daily_capacity()

        # Calculate efficiency
        energy_efficiency = 0
        bandwidth_efficiency = 0

        if resources["energy"]["staked"] > 0:
            energy_efficiency = (
                resources["energy"]["limit"] / (resources["energy"]["staked"] * 32_000)
            ) * 100

        if resources["bandwidth"]["staked"] > 0:
            bandwidth_efficiency = (
                resources["bandwidth"]["limit"]
                / (resources["bandwidth"]["staked"] * 1_000)
            ) * 100

        # Check operational status
        can_process_100, status_msg = self.can_process_usdt_transactions(100)

        return {
            "address": self.address,
            "network": self.network,
            "balance": resources["balance"],
            "total_staked": resources["total_staked"],
            "resources": resources,
            "capacity": capacity,
            "efficiency": {
                "energy": energy_efficiency,
                "bandwidth": bandwidth_efficiency,
            },
            "operational": {
                "can_process_100_tx": can_process_100,
                "status_message": status_msg,
            },
            "contracts": {"usdt": self.usdt_contract},
        }

    def auto_rebalance(self) -> bool:
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

            rebalanced = False

            # Auto-stake for energy if usage is high
            if energy_usage > 80 and resources["balance"] > 100:
                stake_amount = min(50, resources["balance"] * 0.1)

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
                        f"Auto-staked {stake_amount} TRX for energy: {result.get('txid')}"
                    )
                    rebalanced = True

                except Exception as e:
                    logger.error(f"Auto-staking for energy failed: {e}")

            # Auto-stake for bandwidth if usage is high
            if bandwidth_usage > 80 and resources["balance"] > 50:
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
                        f"Auto-staked {stake_amount} TRX for bandwidth: {result.get('txid')}"
                    )
                    rebalanced = True

                except Exception as e:
                    logger.error(f"Auto-staking for bandwidth failed: {e}")

            return rebalanced

        except Exception as e:
            logger.error(f"Resource rebalancing failed: {e}")
            return False
