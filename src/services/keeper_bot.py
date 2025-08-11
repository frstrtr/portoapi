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
from queue import Queue, Empty
from threading import Thread
from dataclasses import dataclass

# Add project root to Python path
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, project_root)

from src.core.database.db_service import get_db, get_invoices_by_seller, get_invoice, update_invoice, create_transaction, get_seller, update_seller, get_transactions_by_invoice
from src.core.database.models import Invoice, Wallet
from src.core.services.gas_station import auto_activate_on_usdt_receive
from src.core.config import config
from bip_utils import Bip44, Bip44Coins, Bip44Changes, Bip39SeedGenerator
import importlib as _importlib
_SELF_MODULE = _importlib.import_module(__name__)

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

# --- Lightweight background activation queue (threaded) ---

@dataclass
class ActivationJob:
    invoice_id: int
    address: str
    retries_left: int = 3
    backoff_sec: float = 5.0


class ActivationJobQueue:
    """Simple thread-based queue to run activation+delegation asynchronously.
    Avoids blocking the main keeper loop when nodes are slow to confirm/poll.
    """

    def __init__(self, worker_count: int = 1, default_retries: int = 3, backoff_sec: float = 5.0):
        self.q: Queue = Queue()
        self._in_flight: set[int] = set()  # invoice_ids in progress
        self._workers: list[Thread] = []
        self.sync_mode: bool = False  # when True, run jobs immediately in caller thread
        self._default_retries = default_retries
        self._default_backoff = backoff_sec
        for i in range(max(1, worker_count)):
            t = Thread(target=self._worker, name=f"activation-worker-{i}", daemon=True)
            t.start()
            self._workers.append(t)

    def enqueue(self, job: ActivationJob):
        if job.invoice_id in self._in_flight:
            return
        if self.sync_mode:
            # Run immediately in caller thread for deterministic tests
            self._in_flight.add(job.invoice_id)
            try:
                self._handle_job(job)
            finally:
                self._in_flight.discard(job.invoice_id)
        else:
            # Fill defaults if not provided
            if job.retries_left is None:
                job.retries_left = self._default_retries
            if job.backoff_sec is None:
                job.backoff_sec = self._default_backoff
            self._in_flight.add(job.invoice_id)
            self.q.put(job)

    def _handle_job(self, job: ActivationJob):
        ok = False
        try:
            ok = _SELF_MODULE.auto_activate_on_usdt_receive(job.address)
        except Exception as e:
            logger.warning("Background activation error for %s (invoice %s): %s", job.address, job.invoice_id, e)
            ok = False

        # Update invoice status based on result
        try:
            db = next(get_db())
            inv = get_invoice(db, job.invoice_id)
            if ok:
                # Return to pending unless already partial/paid
                if inv and inv.status == 'activating':
                    update_invoice(db, inv.id, status='pending')
                    logger.info("Activation completed in background for %s (invoice %s)", job.address, job.invoice_id)
            else:
                # Retry logic with simple backoff
                if job.retries_left > 0 and not self.sync_mode:
                    job.retries_left -= 1
                    logger.info("Requeue activation for %s (invoice %s), retries left %s", job.address, job.invoice_id, job.retries_left)
                    time.sleep(job.backoff_sec)
                    self.q.put(job)
                    return
                else:
                    # Give up: move invoice out of 'activating' to allow future attempts
                    if inv and inv.status == 'activating':
                        update_invoice(db, inv.id, status='pending')
                    logger.warning("Activation permanently failed for %s (invoice %s)", job.address, job.invoice_id)
        except Exception as ue:
            logger.error("Failed to update invoice after activation attempt %s: %s", job.invoice_id, ue)

    def _worker(self):
        while True:
            try:
                job: ActivationJob = self.q.get(timeout=1.0)  # type: ignore[assignment]
            except Empty:
                continue
            try:
                self._handle_job(job)
            finally:
                self._in_flight.discard(job.invoice_id)
                self.q.task_done()

    def wait_idle(self, timeout: float = 3.0):
        """Block briefly until the queue has processed current jobs or timeout."""
        end = time.time() + max(0.1, timeout)
        while time.time() < end:
            if self.q.empty() and not self._in_flight:
                return
            time.sleep(0.05)

class KeeperBot:
    """Blockchain monitoring bot for invoice payments and TRX deposit forwarding"""
    
    def __init__(self):
        self.tron_config = config.tron
        self.client = self._get_tron_client()
        self.usdt_contract_address = self.tron_config.usdt_contract
        # Background queue for activation jobs
        aq_workers = max(1, int(config.keeper.activation_queue_workers))
        self.activation_queue = ActivationJobQueue(
            worker_count=aq_workers,
            default_retries=int(config.keeper.activation_queue_retries),
            backoff_sec=float(config.keeper.activation_queue_backoff_sec),
        )
        # Allow forcing synchronous processing in tests via env
        self.activation_queue.sync_mode = bool(config.keeper.activation_queue_sync)
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
        """Handle payment for an invoice using a simple balance snapshot.
        - Reads current USDT balance for the invoice address
        - Records a single transaction reflecting the observed balance
        - Updates invoice status to 'partial' or 'paid'
        Note: Activation, if needed, is handled by process_invoice before calling this.
        """
        # Current on-chain USDT balance
        try:
            raw_balance = contract.functions.balanceOf(address)
            current_received = float(raw_balance) / 1_000_000 if isinstance(raw_balance, (int, float)) else float(raw_balance) / 1_000_000
        except Exception as e:
            logger.error("Failed to read USDT balance for %s: %s", address, e)
            return

        # Determine tx hash from recent transfer events (best effort)
        last_tx_hash = self._try_get_last_txid(contract, address)

        # Record a single transaction for the observed balance
        try:
            tx_hash_to_use = last_tx_hash or f"synthetic:{address}:{int(time.time())}:{int(current_received * 1_000_000)}"
            create_transaction(
                db,
                invoice_id=inv.id,
                tx_hash=tx_hash_to_use,
                sender_address='multiple',
                amount_received=current_received,
                received_at=datetime.now(timezone.utc),
            )
        except Exception as e:
            logger.debug("Failed to record transaction for invoice %s (may already exist): %s", inv.id, e)

        # Update invoice status and notify
        try:
            if current_received >= float(inv.amount):
                update_invoice(db, inv.id, status='paid')
                _SELF_MODULE.notify_invoice_paid(inv.id, last_tx_hash, current_received)
                logger.info("Invoice %s fully paid: received %.6f / required %.6f", inv.id, current_received, float(inv.amount))
            elif current_received > 0:
                if inv.status not in ('partial', 'paid'):
                    update_invoice(db, inv.id, status='partial')
                    logger.info("Invoice %s partially paid: received %.6f / required %.6f (prev status %s)", inv.id, current_received, float(inv.amount), inv.status)
        except Exception as e:
            logger.error("Failed to update status for invoice %s: %s", inv.id, e)

    def _try_get_last_txid(self, contract, to_address: str) -> str:
        """Best-effort derive latest transfer txid to 'to_address' from contract events."""
        try:
            events = contract.functions.transferEvent()
            if not isinstance(events, list):
                return ""
            picked = ""
            for ev in events:
                to_a = ev.get('to') or ev.get('to_address') or ev.get('toAddress')
                if to_a == to_address:
                    picked = ev.get('transaction_id') or ev.get('txID') or ev.get('txid') or picked
            return picked
        except Exception:
            return ""
    
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
            # Switch to background activation
            logger.info("Queueing proactive activation for address %s (invoice %s)", address, invoice.id)
            update_invoice(db, invoice.id, status='activating')
            self.activation_queue.enqueue(ActivationJob(invoice_id=invoice.id, address=address))

        if balance > 0:
            logger.info("Invoice %s has received %s USDT at address %s", 
                       invoice.id, balance, address)
            # If not activated yet, trigger activation synchronously but don't alter invoice status here
            if not_activated:
                try:
                    _SELF_MODULE.auto_activate_on_usdt_receive(address)
                except Exception as e:
                    logger.error("Activation (on first USDT) failed for %s: %s", address, e)
            # Use the invoice object passed from the query to keep stable IDs for mocks/tests
            self.handle_invoice_payment(db, contract, invoice, address, not_activated)
        elif invoice.status == 'partial':
            # No on-chain balance reported now, keep status until events are processed
            logger.debug("Invoice %s previously partial, waiting for more funds", invoice.id)
    
    def check_pending_invoices(self):
        """Check all pending/activating/partial invoices for payments"""
        logger.info("Checking pending invoices...")
        
        try:
            contract = self.client.get_contract(self.usdt_contract_address)
            
            db = next(get_db())
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

# Top-level shim for tests/backward compatibility
def check_pending_invoices():
    """Run a single invoice-check pass using a fresh KeeperBot instance.
    Also waits briefly for any background activation jobs to finish (test-friendly).
    """
    keeper = KeeperBot()
    # Respect config.keeper.activation_queue_sync; do not override here.
    keeper.check_pending_invoices()
    # Wait a bit for background activation queue to run (helps unit tests)
    try:
        keeper.activation_queue.wait_idle(timeout=1.5)
    except Exception:
        pass

def main():
    """Main entry point"""
    keeper = KeeperBot()
    keeper.run()

if __name__ == "__main__":
    main()
