# Основной скрипт воркера для мониторинга блокчейна

import time
import logging
from datetime import datetime, timezone
from tronpy import Tron
from tronpy.providers import HTTPProvider
from tronpy.keys import PrivateKey

# Import configuration
import sys
import os
import re

# Add project root to Python path
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, project_root)

from src.core.database.db_service import get_db, get_invoices_by_seller, get_invoice, update_invoice, create_transaction, get_seller, update_seller, get_transactions_by_invoice
from src.core.database.models import Invoice, Wallet
from src.core.services.gas_station import auto_activate_on_usdt_receive
from src.core.config import config
from bip_utils import Bip44, Bip44Coins, Bip44Changes, Bip39SeedGenerator

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
    """Blockchain monitoring bot for invoice payments and TRX deposit forwarding"""
    
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
    
    def _check_client_health(self) -> bool:
        """Check if current client connection is healthy"""
        try:
            self.client.get_latest_block()
            return True
        except Exception as e:
            logger.warning("Client health check failed: %s", e)
            return False
    
    def _reconnect_if_needed(self):
        """Reconnect if current client is unhealthy"""
        if not self._check_client_health():
            logger.info("Client connection unhealthy, attempting to reconnect...")
            old_client = self.client
            self.client = self._get_tron_client()
            if self.client != old_client:
                logger.info("Successfully reconnected to TRON network")
    
    def notify_invoice_paid(self, invoice_id: int, tx_hash: str, amount: float):
        """Notify about paid invoice"""
        logger.info("Invoice %s paid: tx=%s, amount=%s", invoice_id, tx_hash, amount)
        # TODO: реализовать отправку уведомления (например, через Redis или очередь)
    
    def handle_invoice_payment(self, db, contract, inv, address: str, not_activated: bool):
        """Handle payment for an invoice using balance-delta approach.
        - Computes current USDT balance for the invoice address
        - Records a synthetic transaction for any positive delta since last recorded total
        - Updates invoice status to 'partial' or 'paid'
        - Triggers auto-activation when needed
        """
        # Prevent repeated activation attempts by marking the invoice as 'activating'
        if not_activated and inv.status not in ('activating', 'paid'):
            update_invoice(db, inv.id, status='activating')
            try:
                auto_activate_on_usdt_receive(address)
            except Exception as e:
                logger.error("Activation failed for %s: %s", address, e)
                # continue to record payments

        # Current on-chain USDT balance
        try:
            raw_balance = contract.functions.balanceOf(address)
            current_received = float(raw_balance) / 1_000_000 if isinstance(raw_balance, (int, float)) else float(raw_balance) / 1_000_000
        except Exception as e:
            logger.error("Failed to read USDT balance for %s: %s", address, e)
            return

        # Previously recorded total
        try:
            tx_list = get_transactions_by_invoice(db, inv.id)
            already_recorded = sum(float(t.amount_received or 0) for t in tx_list)
        except Exception as e:
            logger.error("Failed to aggregate prior transactions for invoice %s: %s", inv.id, e)
            already_recorded = 0.0

        delta = current_received - already_recorded
        if delta > 0:
            # Create an idempotent synthetic tx id based on latest block and observed balance
            try:
                latest = self.client.get_latest_block()
                block_num = (
                    latest.get('block_header', {}).get('raw_data', {}).get('number')
                    if isinstance(latest, dict) else None
                )
            except Exception:
                block_num = None
            suffix = block_num if block_num is not None else int(time.time())
            synthetic_txid = f"synthetic:{address}:{suffix}:{int(current_received * 1_000_000)}"
            try:
                create_transaction(
                    db,
                    invoice_id=inv.id,
                    tx_hash=synthetic_txid,
                    sender_address='multiple',
                    amount_received=delta,
                    received_at=datetime.now(timezone.utc),
                )
                logger.info("Recorded synthetic USDT receipt for invoice %s: +%.6f USDT (total %.6f)", inv.id, delta, current_received)
            except Exception as e:
                # If unique constraint prevents insert, it's likely already recorded for this observed state
                logger.debug("Skipping duplicate synthetic tx for invoice %s: %s", inv.id, e)

        # Recompute total after potential insert
        try:
            tx_list = get_transactions_by_invoice(db, inv.id)
            total_received = sum(float(t.amount_received or 0) for t in tx_list)
        except Exception:
            total_received = already_recorded + max(0.0, delta)

        # Update invoice status
        try:
            if total_received >= float(inv.amount):
                if inv.status != 'paid':
                    update_invoice(db, inv.id, status='paid')
                    # best-effort tx hash notification
                    last_tx_hash = tx_list[-1].tx_hash if tx_list else ''
                    self.notify_invoice_paid(inv.id, tx_hash=last_tx_hash, amount=total_received)
                    logger.info("Invoice %s fully paid: received %.6f / required %.6f", inv.id, total_received, float(inv.amount))
            elif total_received > 0:
                # Allow transition to partial from pending or activating
                if inv.status not in ('partial', 'paid'):
                    update_invoice(db, inv.id, status='partial')
                    logger.info("Invoice %s partially paid: received %.6f / required %.6f (prev status %s)", inv.id, total_received, float(inv.amount), inv.status)
        except Exception as e:
            logger.error("Failed to update status for invoice %s: %s", inv.id, e)
    
    def process_invoice(self, db, contract, invoice):
        """Process a single invoice for payments"""
        if invoice.status not in ('pending', 'partial', 'activating'):
            return
        
        address = invoice.address
        
        try:
            raw_balance = contract.functions.balanceOf(address)
            if isinstance(raw_balance, (int, float)):
                balance = raw_balance / 1_000_000
            else:
                # Attempt coercion if library returns Decimal-like
                try:
                    balance = float(raw_balance) / 1_000_000
                except Exception:
                    logger.error("Unexpected balanceOf return type %s for %s", type(raw_balance), address)
                    balance = 0.0
        except Exception as e:
            logger.error("Error checking balance for %s: %s", address, e)
            # Try to reconnect on balance check failure
            self._reconnect_if_needed()
            return

        try:
            account_info = self.client.get_account(address)
            not_activated = account_info is None
        except Exception as e:
            # Downgrade specific 'account not found' noise and treat as not activated
            msg = str(e).lower()
            if 'account not found' in msg or 'does not exist' in msg:
                logger.info("Account not yet activated on-chain for %s (invoice %s)", address, invoice.id)
            else:
                logger.error("Error checking TRX account for %s: %s", address, e)
            # Try to reconnect on account check failure
            self._reconnect_if_needed()
            not_activated = True

        # Proactive activation & resource delegation BEFORE any USDT arrives
        # so incoming TRC20 transfer will succeed without sender providing TRX.
        if not_activated and balance == 0 and invoice.status not in ('activating', 'paid', 'swept'):
            try:
                logger.info("Proactive activation attempt for address %s (invoice %s)", address, invoice.id)
                update_invoice(db, invoice.id, status='activating')
                ok = auto_activate_on_usdt_receive(address)
                if ok:
                    logger.info("Proactive activation successful for %s (invoice %s)", address, invoice.id)
                    # Return to pending until payment detected; keep 'partial' if it was partial
                    refreshed = get_invoice(db, invoice.id)
                    if refreshed.status == 'activating':
                        update_invoice(db, invoice.id, status='pending')
                else:
                    logger.warning("Proactive activation failed for %s (invoice %s)", address, invoice.id)
            except Exception as e:
                logger.error("Error during proactive activation for %s (invoice %s): %s", address, invoice.id, e)

        if balance > 0:
            logger.info("Invoice %s has received %s USDT at address %s", 
                       invoice.id, balance, address)
            inv = get_invoice(db, invoice.id)
            self.handle_invoice_payment(db, contract, inv, address, not_activated)
        elif invoice.status == 'partial':
            # No on-chain balance reported now, keep status until events are processed
            logger.debug("Invoice %s previously partial, waiting for more funds", invoice.id)
    
    def check_pending_invoices(self):
        """Check all pending/activating/partial invoices for payments"""
        logger.info("Checking pending invoices...")
        
        try:
            contract = self.client.get_contract(self.usdt_contract_address)
            
            with next(get_db()) as db:
                # Include invoices in pending, activating, or partial states
                target_statuses = ('pending', 'activating', 'partial')
                sellers = (
                    db.query(Invoice.seller_id)
                    .filter(Invoice.status.in_(target_statuses))
                    .distinct()
                )
                
                for seller_row in sellers:
                    seller_id = seller_row.seller_id
                    candidate_invoices = [
                        inv for inv in get_invoices_by_seller(db, seller_id)
                        if inv.status in target_statuses
                    ]
                    if candidate_invoices:
                        logger.info(
                            "Processing %s invoices (statuses in %s) for seller %s",
                            len(candidate_invoices), target_statuses, seller_id
                        )
                        for invoice in candidate_invoices:
                            self.process_invoice(db, contract, invoice)
                            time.sleep(0.1)  # Small delay to avoid rate limiting
                
        except Exception as e:
            logger.error("Error in check_pending_invoices: %s", e)
    
    def _get_hot_wallet_address(self) -> str:
        """Resolve the gas station hot wallet address from config"""
        if self.tron_config.gas_wallet_private_key:
            try:
                pk = PrivateKey(bytes.fromhex(self.tron_config.gas_wallet_private_key))
                return pk.public_key.to_base58check_address()
            except Exception:
                logger.error("Invalid GAS_WALLET_PRIVATE_KEY configured")
        if self.tron_config.gas_wallet_mnemonic:
            try:
                seed_bytes = Bip39SeedGenerator(self.tron_config.gas_wallet_mnemonic).Generate()
                bip44_ctx = Bip44.FromSeed(seed_bytes, Bip44Coins.TRON)
                node = bip44_ctx.Purpose().Coin().Account(0).Change(Bip44Changes.CHAIN_EXT).AddressIndex(0)
                return node.PublicKey().ToAddress()
            except Exception as e:
                logger.error("Failed to derive hot wallet address from mnemonic: %s", e)
        raise ValueError("No valid gas wallet credentials configured")

    def _derive_privkey_hex_from_path(self, derivation_path: str) -> str:
        """Derive a private key (hex) for a BIP44 derivation path using master mnemonic"""
        if not self.tron_config.gas_wallet_mnemonic:
            raise ValueError("GAS_WALLET_MNEMONIC required to derive deposit private keys")
        m = re.match(r"m/44'/195'/(\d+)'/0/0", derivation_path)
        if not m:
            raise ValueError(f"Unsupported derivation path: {derivation_path}")
        account = int(m.group(1))
        seed_bytes = Bip39SeedGenerator(self.tron_config.gas_wallet_mnemonic).Generate()
        bip44_ctx = Bip44.FromSeed(seed_bytes, Bip44Coins.TRON)
        node = bip44_ctx.Purpose().Coin().Account(account).Change(Bip44Changes.CHAIN_EXT).AddressIndex(0)
        return node.PrivateKey().Raw().ToHex()

    def forward_trx_deposits(self, min_reserve_sun: int = 200_000, min_threshold_sun: int = 0):
        """Scan seller TRX deposit addresses and forward balances to hot wallet.
        - min_reserve_sun: keep this many sun on deposit address to cover bandwidth/fees
        - min_threshold_sun: skip forwarding if balance <= reserve + threshold
        Also credits the seller's gas_deposit_balance with the forwarded amount.
        """
        try:
            hot_wallet = self._get_hot_wallet_address()
        except Exception as e:
            logger.error("Cannot resolve hot wallet: %s", e)
            return

        try:
            with next(get_db()) as db:
                wallets = db.query(Wallet).filter(Wallet.deposit_type == 'TRX').all()
                if not wallets:
                    return
                for w in wallets:
                    addr = w.address
                    try:
                        acc = self.client.get_account(addr)
                        balance_sun = int(acc.get('balance', 0) or 0)
                    except Exception as e:
                        logger.warning("Failed to fetch TRX balance for %s: %s", addr, e)
                        continue
                    if balance_sun <= (min_reserve_sun + min_threshold_sun):
                        continue
                    amount_sun = balance_sun - min_reserve_sun
                    try:
                        if not w.derivation_path:
                            logger.warning("Wallet %s has no derivation path; cannot derive key", addr)
                            continue
                        priv_hex = self._derive_privkey_hex_from_path(w.derivation_path)
                        pk_obj = PrivateKey(bytes.fromhex(priv_hex))
                        # Build and send transfer
                        txn = (
                            self.client.trx.transfer(
                                addr,
                                hot_wallet,
                                amount_sun
                            )
                            .build()
                            .sign(pk_obj)
                        )
                        res = txn.broadcast()
                        txid = res.get('txid') if isinstance(res, dict) else None
                        amount_trx = amount_sun / 1_000_000
                        # Credit seller balance
                        try:
                            seller = get_seller(db, w.seller_id)
                            current = float(seller.gas_deposit_balance or 0)
                            update_seller(db, w.seller_id, gas_deposit_balance=current + amount_trx)
                            logger.info(
                                "Credited %.6f TRX to seller %s after forwarding (tx: %s)",
                                amount_trx, w.seller_id, txid
                            )
                        except Exception as ce:
                            logger.error("Failed to credit seller %s: %s", w.seller_id, ce)
                        logger.info("Forwarded %.2f TRX from %s -> %s (tx: %s)", amount_trx, addr, hot_wallet, txid)
                    except Exception as e:
                        logger.error("Failed to forward TRX from %s: %s", addr, e)
                        continue
        except Exception as e:
            logger.error("Error in forward_trx_deposits: %s", e)

    def run(self, check_interval: int = 60):
        """Main loop for the keeper bot"""
        logger.info("Keeper Bot started. Monitoring pending invoices...")
        logger.info("Check interval: %s seconds", check_interval)
        
        connection_check_counter = 0
        connection_check_interval = 10  # Check connection health every 10 cycles
        forward_counter = 0
        forward_interval = 1  # Forward TRX deposits every cycle for faster crediting
        
        while True:
            try:
                # Periodically check and reconnect if needed
                connection_check_counter += 1
                if connection_check_counter >= connection_check_interval:
                    self._reconnect_if_needed()
                    connection_check_counter = 0
                
                # Process invoices (USDT)
                self.check_pending_invoices()
                
                # Periodically forward TRX deposits
                forward_counter += 1
                if forward_counter >= forward_interval:
                    self.forward_trx_deposits()
                    forward_counter = 0
                
                time.sleep(check_interval)
            except KeyboardInterrupt:
                logger.info("Keeper Bot stopped by user")
                break
            except (ConnectionError, ValueError, RuntimeError) as e:
                logger.error("Unexpected error in keeper bot: %s", e)
                logger.info("Continuing after error...")
                # Reset connection on unexpected errors
                try:
                    self._reconnect_if_needed()
                except (ConnectionError, ValueError, RuntimeError) as reconnect_error:
                    logger.error("Failed to reconnect after error: %s", reconnect_error)
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
