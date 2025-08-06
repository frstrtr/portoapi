# Основной скрипт воркера для мониторинга блокчейна

import time
import logging
from tronpy import Tron
from tronpy.providers import HTTPProvider

# Import configuration
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.core.database.db_service import get_db, get_invoices_by_seller, get_invoice, update_invoice, create_transaction
from src.core.database.models import Invoice
from src.core.services.gas_station import auto_activate_on_usdt_receive
from src.core.config import config

# Setup logging
logging.basicConfig(
    level=getattr(logging, config.log_level),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.FileHandler(config.log_file, encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger("keeper_bot")

class KeeperBot:
    """Blockchain monitoring bot for invoice payments"""
    
    def __init__(self):
        self.tron_config = config.tron
        self.client = self._get_tron_client()
        self.usdt_contract_address = self.tron_config.usdt_contract
        logger.info("Keeper bot initialized for %s network", self.tron_config.network)
        logger.info("USDT contract: %s", self.usdt_contract_address)
    
    def _get_tron_client(self) -> Tron:
        """Create and configure TRON client"""
        client_config = self.tron_config.get_tron_client_config()
        
        # Create provider with API key if available
        if client_config.get("api_key"):
            provider = HTTPProvider(
                endpoint_uri=client_config["full_node"],
                api_key=client_config["api_key"]
            )
            client = Tron(provider=provider)
# Основной скрипт воркера для мониторинга блокчейна

import time
import logging
from datetime import datetime
from tronpy import Tron
from tronpy.providers import HTTPProvider

# Import configuration
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.core.database.db_service import get_db, get_invoices_by_seller, get_invoice, update_invoice, create_transaction
from src.core.database.models import Invoice
from src.core.services.gas_station import auto_activate_on_usdt_receive
from src.core.config import config

# Setup logging
logging.basicConfig(
    level=getattr(logging, config.log_level),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.FileHandler(config.log_file, encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger("keeper_bot")

class KeeperBot:
    """Blockchain monitoring bot for invoice payments"""
    
    def __init__(self):
        self.tron_config = config.tron
        self.client = self._get_tron_client()
        self.usdt_contract_address = self.tron_config.usdt_contract
        logger.info("Keeper bot initialized for %s network", self.tron_config.network)
        logger.info("USDT contract: %s", self.usdt_contract_address)
    
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
                
                logger.info("Keeper bot connected to local TRON node at %s", client_config["full_node"])
                return client
                
        except Exception as e:
            logger.warning("Keeper bot failed to connect to local TRON node: %s", e)
            
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
            logger.info("Keeper bot connected to remote TRON %s network with API key", self.tron_config.network)
        else:
            provider = HTTPProvider(endpoint_uri=client_config["full_node"])
            client = Tron(provider=provider)
            logger.info("Keeper bot connected to remote TRON %s network", self.tron_config.network)
        
        return client
    
    def notify_invoice_paid(self, invoice_id: int, tx_hash: str, amount: float):
        """Notify about paid invoice"""
        logger.info("Invoice %s paid: tx=%s, amount=%s", invoice_id, tx_hash, amount)
        # TODO: реализовать отправку уведомления (например, через Redis или очередь)
    
    def handle_invoice_payment(self, db, contract, inv, address: str, not_activated: bool):
        """Handle payment for an invoice"""
        # Prevent repeated activation attempts by marking the invoice as 'activating'
        if not_activated and inv.status != 'activating':
            update_invoice(db, inv.id, status='activating')
            try:
                auto_activate_on_usdt_receive(address)
            except Exception as e:
                logger.error("Activation failed for %s: %s", address, e)
                return
        
        update_invoice(db, inv.id, status='paid')
        
        try:
            # Get USDT transfer events for this address
            txs = contract.functions.transferEvent(address)
            for tx in txs:
                if tx['to'] == address and float(tx['value'])/1_000_000 >= inv.amount:
                    # Convert block_timestamp to datetime if needed
                    received_at = tx['block_timestamp']
                    if isinstance(received_at, (int, float)):
                        received_at = datetime.fromtimestamp(received_at / 1000.0)
                    
                    create_transaction(
                        db,
                        invoice_id=inv.id,
                        tx_hash=tx['transaction_id'],
                        sender_address=tx['from'],
                        amount_received=float(tx['value'])/1_000_000,
                        received_at=received_at
                    )
                    
                    self.notify_invoice_paid(
                        inv.id, 
                        tx['transaction_id'], 
                        float(tx['value'])/1_000_000
                    )
                    break
        except Exception as e:
            logger.error("Error fetching transactions for %s: %s", address, e)
    
    def process_invoice(self, db, contract, invoice):
        """Process a single invoice for payments"""
        if invoice.status != 'pending':
            return
        
        address = invoice.address
        
        try:
            balance = contract.functions.balanceOf(address)()
            balance = balance / 1_000_000
        except Exception as e:
            logger.error("Error checking balance for %s: %s", address, e)
            return

        try:
            account_info = self.client.get_account(address)
            not_activated = account_info is None
        except Exception as e:
            logger.error("Error checking TRX account for %s: %s", address, e)
            not_activated = True

        if balance > 0:
            logger.info("Invoice %s paid with %s USDT at address %s", 
                       invoice.id, balance, address)
            inv = get_invoice(db, invoice.id)
            self.handle_invoice_payment(db, contract, inv, address, not_activated)
    
    def check_pending_invoices(self):
        """Check all pending invoices for payments"""
        logger.info("Checking pending invoices...")
        
        try:
            contract = self.client.get_contract(self.usdt_contract_address)
            
            with next(get_db()) as db:
                # Group by sellers for using get_invoices_by_seller
                sellers = db.query(Invoice.seller_id).filter(Invoice.status == 'pending').distinct()
                
                for seller_row in sellers:
                    seller_id = seller_row.seller_id
                    pending_invoices = get_invoices_by_seller(db, seller_id)
                    pending_invoices = [inv for inv in pending_invoices if inv.status == 'pending']
                    
                    if pending_invoices:
                        logger.info("Processing %s pending invoices for seller %s", 
                                   len(pending_invoices), seller_id)
                        
                        for invoice in pending_invoices:
                            self.process_invoice(db, contract, invoice)
                            time.sleep(0.1)  # Small delay to avoid rate limiting
                
        except Exception as e:
            logger.error("Error in check_pending_invoices: %s", e)
    
    def run(self, check_interval: int = 60):
        """Main loop for the keeper bot"""
        logger.info("Keeper Bot started. Monitoring pending invoices...")
        logger.info("Check interval: %s seconds", check_interval)
        
        while True:
            try:
                self.check_pending_invoices()
                time.sleep(check_interval)
            except KeyboardInterrupt:
                logger.info("Keeper Bot stopped by user")
                break
            except Exception as e:
                logger.error("Unexpected error in keeper bot: %s", e)
                logger.info("Continuing after error...")
                time.sleep(check_interval)

# Legacy functions for backward compatibility
def notify_invoice_paid(invoice_id: int, tx_hash: str, amount: float):
    """Legacy function for backward compatibility"""
    logger.info("Invoice %s paid: tx=%s, amount=%s", invoice_id, tx_hash, amount)

def main():
    """Main entry point"""
    keeper = KeeperBot()
    keeper.run()

if __name__ == "__main__":
    main()
