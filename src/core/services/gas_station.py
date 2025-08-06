# Логика "Gas Station" (активация, делегирование)

from tronpy import Tron
from tronpy.providers import HTTPProvider
import time
import logging
from src.core.database.db_service import get_seller_wallet, create_seller_wallet
from src.core.config import config
from bip_utils import Bip44, Bip44Coins, Bip44Changes, Bip39SeedGenerator

logger = logging.getLogger(__name__)

class GasStationManager:
    """Manages gas station operations for TRON network"""
    
    def __init__(self):
        self.tron_config = config.tron
        self.client = self._get_tron_client()
        
    def _get_tron_client(self) -> Tron:
        """Create and configure TRON client with local node preference"""
        client = self._try_create_local_client()
        
        if client is None:
            logger.info("Local TRON node unavailable, using remote endpoints")
            client = self._create_remote_client()
        
        return client
    
    def _try_create_local_client(self) -> Tron:
        """Try to create a client using local TRON node"""
        if not self.tron_config.local_node_enabled:
            return None
        
        try:
            # Test local node connection first
            if not self.tron_config.test_local_node_connection():
                logger.warning("Local TRON node connection test failed")
                return None
            
            client_config = self.tron_config.get_tron_client_config()
            
            if client_config["node_type"] == "local":
                # Create provider for local node
                provider = HTTPProvider(endpoint_uri=client_config["full_node"])
                client = Tron(provider=provider)
                
                # Test the client with a simple call
                client.get_latest_block()
                
                logger.info("Connected to local TRON node at %s", client_config["full_node"])
                return client
                
        except Exception as e:
            logger.warning("Failed to connect to local TRON node: %s", e)
            
        return None
    
    def _create_remote_client(self) -> Tron:
        """Create client using remote endpoints (TronGrid/TronScan)"""
        client_config = self.tron_config.get_fallback_client_config()
        
        # Create provider with API key if available
        if client_config.get("api_key"):
            provider = HTTPProvider(
                endpoint_uri=client_config["full_node"],
                api_key=client_config["api_key"]
            )
            client = Tron(provider=provider)
            logger.info("Connected to remote TRON %s network with API key", self.tron_config.network)
        else:
            provider = HTTPProvider(endpoint_uri=client_config["full_node"])
            client = Tron(provider=provider)
            logger.info("Connected to remote TRON %s network", self.tron_config.network)
        
        return client
    
    def check_connection_health(self) -> dict:
        """Check the health of current TRON connection"""
        health_info = {
            "connected": False,
            "node_type": "unknown",
            "latency_ms": None,
            "latest_block": None,
            "error": None
        }
        
        try:
            start_time = time.time()
            
            # Test with simple call
            latest_block = self.client.get_latest_block()
            
            end_time = time.time()
            latency_ms = round((end_time - start_time) * 1000, 2)
            
            # Determine node type based on configuration
            client_config = self.tron_config.get_tron_client_config()
            node_type = client_config.get("node_type", "unknown")
            
            health_info.update({
                "connected": True,
                "node_type": node_type,
                "latency_ms": latency_ms,
                "latest_block": latest_block.get("blockID", "")[:16] if latest_block else None
            })
            
        except Exception as e:
            health_info["error"] = str(e)
            logger.warning("TRON connection health check failed: %s", e)
        
        return health_info
    
    def reconnect_if_needed(self) -> bool:
        """Reconnect to TRON network if current connection fails"""
        health = self.check_connection_health()
        
        if not health["connected"]:
            logger.warning("TRON connection unhealthy, attempting reconnection...")
            
            try:
                # Try to reconnect
                old_client = self.client
                self.client = self._get_tron_client()
                
                # Test new connection
                new_health = self.check_connection_health()
                
                if new_health["connected"]:
                    logger.info("Successfully reconnected to TRON network (type: %s)", 
                               new_health["node_type"])
                    return True
                else:
                    # Restore old client if new one also fails
                    self.client = old_client
                    logger.error("Failed to reconnect to TRON network")
                    return False
                    
            except Exception as e:
                logger.error("Error during TRON reconnection: %s", e)
                return False
        
        return True
    
    def _get_gas_wallet_account(self):
        """Get gas wallet account for single wallet mode"""
        if self.tron_config.gas_station_type != "single":
            raise ValueError("Gas wallet account only available in single wallet mode")
        
        if self.tron_config.gas_wallet_private_key:
            return self.client.generate_address(self.tron_config.gas_wallet_private_key)
        elif self.tron_config.gas_wallet_mnemonic:
            # Generate address from mnemonic
            seed_bytes = Bip39SeedGenerator(self.tron_config.gas_wallet_mnemonic).Generate()
            bip44_ctx = Bip44.FromSeed(seed_bytes, Bip44Coins.TRON)
            account_ctx = bip44_ctx.Purpose().Coin().Account(0)
            address = account_ctx.Change(Bip44Changes.CHAIN_EXT).AddressIndex(0).PublicKey().ToAddress()
            
            # Create a simple address object
            class AddressInfo:
                def __init__(self, address):
                    self.address = address
            
            return AddressInfo(address)
        else:
            raise ValueError("No gas wallet credentials configured")
    
    def prepare_for_sweep(self, invoice_address: str) -> bool:
        """
        Активирует адрес invoice_address, делегирует энергию и bandwidth.
        Возвращает True при успехе.
        """
        logger.info("Preparing sweep for address: %s", invoice_address)
        
        try:
            if self.tron_config.gas_station_type == "single":
                return self._prepare_for_sweep_single(invoice_address)
            elif self.tron_config.gas_station_type == "multisig":
                return self._prepare_for_sweep_multisig(invoice_address)
            else:
                logger.error("Unknown gas station type: %s", self.tron_config.gas_station_type)
                return False
            
        except ConnectionError as e:
            logger.error("Connection error in prepare_for_sweep: %s", e)
            return False
        except ValueError as e:
            logger.error("Value error in prepare_for_sweep: %s", e)
            return False
        except Exception as e:
            logger.error("Error in prepare_for_sweep: %s", e)
            return False
    
    def _prepare_for_sweep_single(self, invoice_address: str) -> bool:
        """Handle sweep preparation for single wallet mode"""
        if not self.tron_config.gas_wallet_private_key:
            logger.error("Gas wallet private key not configured for single wallet mode")
            return False
        
        try:
            # 1. Send TRX for activation
            activation_amount = int(self.tron_config.auto_activation_amount * 1_000_000)
            txn = (
                self.client.trx.transfer(
                    self._get_gas_wallet_account().address,
                    invoice_address,
                    activation_amount
                )
                .build()
                .sign(self.tron_config.gas_wallet_private_key)
            )
            result = txn.broadcast()
            txid = result["txid"]
            
            # Wait for confirmation
            if not self._wait_for_transaction(txid, "TRX activation"):
                return False
            
            # 2. Delegate energy
            energy_amount = int(self.tron_config.energy_delegation_amount * 1_000_000)
            delegate_energy_txn = (
                self.client.trx.delegate_resource(
                    owner=self._get_gas_wallet_account().address,
                    receiver=invoice_address,
                    balance=energy_amount,
                    resource="ENERGY",
                )
                .build()
                .sign(self.tron_config.gas_wallet_private_key)
            )
            energy_result = delegate_energy_txn.broadcast()
            energy_txid = energy_result["txid"]
            
            if not self._wait_for_transaction(energy_txid, "ENERGY delegation"):
                return False
            
            # 3. Delegate bandwidth
            bandwidth_amount = int(self.tron_config.bandwidth_delegation_amount * 1_000_000)
            delegate_bw_txn = (
                self.client.trx.delegate_resource(
                    owner=self._get_gas_wallet_account().address,
                    receiver=invoice_address,
                    balance=bandwidth_amount,
                    resource="BANDWIDTH",
                )
                .build()
                .sign(self.tron_config.gas_wallet_private_key)
            )
            bw_result = delegate_bw_txn.broadcast()
            bw_txid = bw_result["txid"]
            
            if self._wait_for_transaction(bw_txid, "BANDWIDTH delegation"):
                logger.info("Successfully prepared sweep for %s", invoice_address)
                return True
            
            return False
            
        except Exception as e:
            logger.error("Error in single wallet sweep preparation: %s", e)
            return False
    
    def _prepare_for_sweep_multisig(self, invoice_address: str) -> bool:
        """Handle sweep preparation for multisig mode"""
        # Implementation for multisig operations
        # This would involve creating multisig transactions and collecting signatures
        # Placeholder for future multisig implementation
        logger.warning("Multisig sweep preparation not implemented yet for %s", invoice_address)
        return False
    
    def _wait_for_transaction(self, txid: str, operation: str, max_attempts: int = 30) -> bool:
        """Wait for transaction confirmation"""
        logger.info("Waiting for %s transaction: %s", operation, txid)
        
        for _ in range(max_attempts):
            try:
                receipt = self.client.get_transaction_info(txid)
                if receipt and receipt.get("receipt", {}).get("result") == "SUCCESS":
                    logger.info("%s successful: %s", operation, txid)
                    return True
                time.sleep(2)
            except Exception as e:
                logger.warning("Error checking transaction %s: %s", txid, e)
                time.sleep(2)
        
        logger.error("%s failed or timed out: %s", operation, txid)
        return False
    
    def auto_activate_on_usdt_receive(self, invoice_address: str) -> bool:
        """
        Проверяет, активирован ли адрес, и если нет — вызывает prepare_for_sweep.
        """
        logger.info("Checking activation status for address: %s", invoice_address)
        
        try:
            acc_info = self.client.get_account(invoice_address)
            # Tron semantics: account is not activated ONLY if get_account returns None
            if acc_info is None:
                logger.info("Address %s not activated, activating...", invoice_address)
                return self.prepare_for_sweep(invoice_address)
            
            logger.info("Address %s already activated", invoice_address)
            return True
            
        except Exception as e:
            logger.error("Error in auto_activate_on_usdt_receive: %s", e)
            return False
    
    def get_or_create_tron_deposit_address(
        self, db, seller_id: int, deposit_type: str = "TRX", xpub: str = None, account: int = None
    ) -> str:
        """Generate or retrieve TRON deposit address"""
        # 1. Check if address already exists for this seller and deposit_type
        wallet = get_seller_wallet(db, seller_id, deposit_type)
        if wallet:
            return wallet.address

        # 2. Derive new address (account = seller_id or custom)
        if account is None:
            account = seller_id

        # Use xpub if provided, else derive from gas station mnemonic/seed
        if xpub:
            # Derive address from xpub using bip_utils
            pub_ctx = Bip44.FromExtendedKey(xpub, Bip44Coins.TRON)
            # Always use external chain (0), address index 0 for deposit
            address = pub_ctx.Change(Bip44Changes.CHAIN_EXT).AddressIndex(0).PublicKey().ToAddress()
            path = f"m/44'/195'/{account}'/0/0"
        else:
            # For admin/gas wallet, use mnemonic from config
            if not self.tron_config.gas_wallet_mnemonic:
                raise ValueError("GAS_WALLET_MNEMONIC not configured!")
            
            seed_bytes = Bip39SeedGenerator(self.tron_config.gas_wallet_mnemonic).Generate()
            bip44_ctx = Bip44.FromSeed(seed_bytes, Bip44Coins.TRON)
            account_ctx = bip44_ctx.Purpose().Coin().Account(account)
            # Get xpub for storage if needed
            xpub = account_ctx.PublicKey().ToExtended()
            # Derive address for deposit
            address = account_ctx.Change(Bip44Changes.CHAIN_EXT).AddressIndex(0).PublicKey().ToAddress()
            path = f"m/44'/195'/{account}'/0/0"

        # 3. Save to DB
        create_seller_wallet(
            db=db,
            seller_id=seller_id,
            address=address,
            derivation_path=path,
            deposit_type=deposit_type,
            xpub=xpub,
            account=account,
        )
        return address
    
    def calculate_trx_needed(self, seller) -> float:
        """Calculate TRX needed for operations based on seller configuration"""
        # Base amount for activation
        base_amount = self.tron_config.auto_activation_amount
        
        # Additional amounts for delegation
        energy_amount = self.tron_config.energy_delegation_amount
        bandwidth_amount = self.tron_config.bandwidth_delegation_amount
        
        total = base_amount + energy_amount + bandwidth_amount
        
        # You can expand this logic based on seller subscription/tariff
        if hasattr(seller, 'tariff_plan'):
            if seller.tariff_plan == 'premium':
                return total * 2
            elif seller.tariff_plan == 'standard':
                return total * 1.5
                
        return total

# Global gas station manager instance
gas_station = GasStationManager()

# Legacy functions for backward compatibility
def prepare_for_sweep(invoice_address: str) -> bool:
    """Legacy function for backward compatibility"""
    return gas_station.prepare_for_sweep(invoice_address)

def auto_activate_on_usdt_receive(invoice_address: str) -> bool:
    """Legacy function for backward compatibility"""
    return gas_station.auto_activate_on_usdt_receive(invoice_address)

def get_or_create_tron_deposit_address(db, seller_id: int, deposit_type: str = "TRX", xpub: str = None, account: int = None) -> str:
    """Legacy function for backward compatibility"""
    return gas_station.get_or_create_tron_deposit_address(db, seller_id, deposit_type, xpub, account)

def calculate_trx_needed(seller) -> float:
    """Legacy function for backward compatibility"""
    return gas_station.calculate_trx_needed(seller)
