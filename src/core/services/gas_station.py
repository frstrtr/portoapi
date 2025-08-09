# Логика "Gas Station" (активация, делегирование)

from tronpy import Tron
from tronpy.providers import HTTPProvider
from tronpy.keys import PrivateKey
import time
import logging
from src.core.database.db_service import get_seller_wallet, create_seller_wallet
from src.core.config import config
from bip_utils import Bip44, Bip44Coins, Bip44Changes, Bip39SeedGenerator
import requests  # added for direct RPC fallback
from types import SimpleNamespace
from sqlalchemy.exc import SQLAlchemyError

logger = logging.getLogger(__name__)

class GasStationManager:
    """Manages gas station operations for TRON network"""
    
    def __init__(self):
        self.tron_config = config.tron
        self.client = self._get_tron_client()
        self._gas_wallet_address = None  # cache
    
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
                # Create provider for local node (full node)
                provider = HTTPProvider(endpoint_uri=client_config["full_node"])
                client = Tron(provider=provider)
                
                # Test the client with a simple call
                client.get_latest_block()
                
                logger.info("Connected to local TRON node at %s", client_config["full_node"])
                return client
                
        except (requests.RequestException, ValueError, RuntimeError) as e:
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
            
        except (requests.RequestException, ValueError, KeyError, RuntimeError) as e:
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
                    
            except (requests.RequestException, RuntimeError) as e:
                logger.error("Error during TRON reconnection: %s", e)
                return False
        
        return True
    
    def _get_gas_wallet_account(self):
        """Get gas wallet account object with .address (supports pk or mnemonic)"""
        if self._gas_wallet_address:
            return SimpleNamespace(address=self._gas_wallet_address)

        if self.tron_config.gas_station_type != "single":
            raise ValueError("Gas wallet account only available in single wallet mode")

        # Private key path
        if self.tron_config.gas_wallet_private_key:
            try:
                pk = PrivateKey(bytes.fromhex(self.tron_config.gas_wallet_private_key))
                self._gas_wallet_address = pk.public_key.to_base58check_address()
            except ValueError as e:
                logger.error("Invalid GAS_WALLET_PRIVATE_KEY: %s", e)
                raise
        elif self.tron_config.gas_wallet_mnemonic:
            seed_bytes = Bip39SeedGenerator(self.tron_config.gas_wallet_mnemonic).Generate()
            bip44_ctx = Bip44.FromSeed(seed_bytes, Bip44Coins.TRON)
            account_ctx = bip44_ctx.Purpose().Coin().Account(0)
            self._gas_wallet_address = account_ctx.Change(Bip44Changes.CHAIN_EXT).AddressIndex(0).PublicKey().ToAddress()
        else:
            raise ValueError("No gas wallet credentials configured")

        return SimpleNamespace(address=self._gas_wallet_address)

    def get_gas_wallet_address(self) -> str:
        """Public accessor for gas wallet address (ensures cached)."""
        if not self._gas_wallet_address:
            _ = self._get_gas_wallet_account()
        return self._gas_wallet_address

    def _get_gas_wallet_private_key(self) -> PrivateKey:
        """Return tronpy PrivateKey for gas wallet (supports mnemonic fallback)."""
        if self.tron_config.gas_wallet_private_key:
            try:
                return PrivateKey(bytes.fromhex(self.tron_config.gas_wallet_private_key))
            except ValueError as e:
                logger.error("Invalid GAS_WALLET_PRIVATE_KEY: %s", e)
                raise
        if self.tron_config.gas_wallet_mnemonic:
            try:
                seed_bytes = Bip39SeedGenerator(self.tron_config.gas_wallet_mnemonic).Generate()
                bip44_ctx = Bip44.FromSeed(seed_bytes, Bip44Coins.TRON)
                account_ctx = bip44_ctx.Purpose().Coin().Account(0)
                addr_ctx = account_ctx.Change(Bip44Changes.CHAIN_EXT).AddressIndex(0)
                raw_hex = addr_ctx.PrivateKey().Raw().ToHex()
                return PrivateKey(bytes.fromhex(raw_hex))
            except (ValueError, RuntimeError) as e:
                logger.error("Failed to derive gas wallet private key from mnemonic: %s", e)
                raise
        raise ValueError("Gas wallet credentials not configured (private key or mnemonic required)")
    
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
        except (requests.RequestException, RuntimeError) as e:
            logger.error("Error in prepare_for_sweep: %s", e)
            return False
    
    def _prepare_for_sweep_single(self, invoice_address: str) -> bool:
        """Prepare target address for sweeping in single wallet mode.
        Rules:
        - If target account doesn't exist, send TRX activation transfer first.
        - After activation, delegate ENERGY and BANDWIDTH according to need for 1 USDT transfer.
        - If account already exists, skip activation and delegate only when needed.
        """
        if not (self.tron_config.gas_wallet_private_key or self.tron_config.gas_wallet_mnemonic):
            logger.error("Gas wallet credentials not configured for single wallet mode (need GAS_WALLET_PRIVATE_KEY or GAS_WALLET_MNEMONIC)")
            return False
        try:
            signing_pk = self._get_gas_wallet_private_key()
            owner_addr = signing_pk.public_key.to_base58check_address()

            # Check if target account exists
            need_activation = True
            try:
                acc = self.client.get_account(invoice_address)
                if acc:
                    need_activation = False
                    logger.info("[gas_station] Account %s already exists; activation transfer not required", invoice_address)
            except (requests.RequestException, ValueError, RuntimeError) as e:
                logger.info("[gas_station] Account %s not found on-chain: %s (will activate)", invoice_address, e)

            # Compute required TRX in gas wallet: delegation + optional activation + fee buffer
            activation_trx = self.tron_config.auto_activation_amount if need_activation else 0.0
            needed_trx = activation_trx + self.tron_config.energy_delegation_amount + self.tron_config.bandwidth_delegation_amount + 0.5
            try:
                owner_balance_trx = self.client.get_account_balance(owner_addr)
            except (requests.RequestException, ValueError, RuntimeError) as e:
                logger.warning("[gas_station] Could not fetch owner balance: %s", e)
                owner_balance_trx = -1
            if owner_balance_trx >= 0 and owner_balance_trx < needed_trx:
                logger.error(
                    "[gas_station] Insufficient TRX in gas wallet %.3f < needed %.3f (addr=%s)",
                    owner_balance_trx,
                    needed_trx,
                    owner_addr,
                )
                return False

            # Activation (if needed)
            if need_activation:
                activation_amount = int(self.tron_config.auto_activation_amount * 1_000_000)
                logger.info("[gas_station] Activating %s via TRX transfer %.6f TRX", invoice_address, self.tron_config.auto_activation_amount)
                try:
                    txn = (
                        self.client.trx.transfer(owner_addr, invoice_address, activation_amount)
                        .build()
                        .sign(signing_pk)
                    )
                    result = txn.broadcast()
                    txid = result.get("txid")
                    if not txid or not self._wait_for_transaction(txid, "TRX activation"):
                        return False
                except (requests.RequestException, ValueError, RuntimeError) as e:
                    logger.error("[gas_station] Activation transfer failed for %s: %s", invoice_address, e)
                    return False
                # Give the node a moment to reflect free bandwidth from activation
                time.sleep(2)

            # Delegate resources only if needed to execute a USDT transfer
            if not self._ensure_minimum_resources_for_usdt(owner_addr, invoice_address, signing_pk):
                return False

            logger.info("Successfully prepared (activated if needed + delegated) %s", invoice_address)
            return True
        except (requests.RequestException, RuntimeError) as e:
            logger.error("Error in single wallet sweep preparation: %s", e)
            return False
    
    def _prepare_for_sweep_multisig(self, invoice_address: str) -> bool:
        """Handle sweep preparation for multisig mode"""
        # Implementation for multisig operations
        # This would involve creating multisig transactions and collecting signatures
        # Placeholder for future multisig implementation
        logger.warning("Multisig sweep preparation not implemented yet for %s", invoice_address)
        return False
    
    def _wait_for_transaction(self, txid: str, operation: str, max_attempts: int = 40) -> bool:
        """Wait for transaction confirmation with resilient polling and multiple fallbacks.
        Tries tronpy, local solidity gettransactioninfobyid, local solidity gettransactionbyid,
        and remote equivalents. Treats contractRet SUCCESS as confirmation too.
        """
        logger.info("Waiting for %s transaction: %s", operation, txid)
        for attempt in range(max_attempts):
            # 1) Try tronpy client (may raise JSON errors on flaky nodes)
            try:
                receipt = self.client.get_transaction_info(txid)
                if receipt and receipt.get("receipt", {}).get("result") == "SUCCESS":
                    logger.info("%s successful: %s", operation, txid)
                    return True
            except (requests.RequestException, ValueError, RuntimeError) as e:
                # Quiet early errors
                if attempt < 5:
                    logger.debug("tronpy get_transaction_info error (attempt %d/%d): %s", attempt + 1, max_attempts, e)
                else:
                    logger.warning("tronpy get_transaction_info error (attempt %d/%d): %s", attempt + 1, max_attempts, e)

            # 2) Fallbacks: local/remote solidity and fullnode endpoints
            try:
                headers = {"Content-Type": "application/json"}
                # Local endpoints
                local_conf = self.tron_config.get_tron_client_config()
                local_sol = local_conf.get("solidity_node")
                local_full = local_conf.get("full_node")

                # Helper to check responses
                def _is_success_json(obj: dict) -> bool:
                    if not obj:
                        return False
                    if obj.get("receipt", {}).get("result") == "SUCCESS":
                        return True
                    # gettransactionbyid style
                    ret = obj.get("ret")
                    if isinstance(ret, list) and ret and isinstance(ret[0], dict):
                        if ret[0].get("contractRet") == "SUCCESS":
                            return True
                    return False

                # Local solidity gettransactioninfobyid
                if local_sol:
                    url = f"{local_sol}/walletsolidity/gettransactioninfobyid"
                    resp = requests.post(url, json={"value": txid}, headers=headers, timeout=5)
                    if resp.ok:
                        data = resp.json() or {}
                        if _is_success_json(data):
                            logger.info("%s successful via local walletsolidity/gettransactioninfobyid", operation)
                            return True
                # Local solidity gettransactionbyid (checks contractRet)
                if local_sol:
                    url = f"{local_sol}/walletsolidity/gettransactionbyid"
                    resp = requests.post(url, json={"value": txid}, headers=headers, timeout=5)
                    if resp.ok:
                        data = resp.json() or {}
                        if _is_success_json(data):
                            logger.info("%s successful via local walletsolidity/gettransactionbyid", operation)
                            return True
                # Remote solidity
                remote_sol = self.tron_config.remote_solidity_node
                if remote_sol:
                    rh = dict(headers)
                    if self.tron_config.api_key:
                        rh["TRON-PRO-API-KEY"] = self.tron_config.api_key
                    url = f"{remote_sol}/walletsolidity/gettransactioninfobyid"
                    resp = requests.post(url, json={"value": txid}, headers=rh, timeout=8)
                    if resp.ok:
                        data = resp.json() or {}
                        if _is_success_json(data):
                            logger.info("%s successful via remote walletsolidity/gettransactioninfobyid", operation)
                            return True
                    url = f"{remote_sol}/walletsolidity/gettransactionbyid"
                    resp = requests.post(url, json={"value": txid}, headers=rh, timeout=8)
                    if resp.ok:
                        data = resp.json() or {}
                        if _is_success_json(data):
                            logger.info("%s successful via remote walletsolidity/gettransactionbyid", operation)
                            return True
                # As last resort, try fullnode gettransactionbyid (may not be confirmed yet)
                if local_full:
                    url = f"{local_full}/wallet/gettransactionbyid"
                    resp = requests.post(url, json={"value": txid}, headers=headers, timeout=5)
                    if resp.ok:
                        data = resp.json() or {}
                        if _is_success_json(data):
                            logger.info("%s successful via local wallet/gettransactionbyid", operation)
                            return True
            except (requests.RequestException, ValueError) as fe:
                if attempt < 5:
                    logger.debug("Fallback tx lookup error (attempt %d/%d): %s", attempt + 1, max_attempts, fe)
                else:
                    logger.warning("Fallback tx lookup error (attempt %d/%d): %s", attempt + 1, max_attempts, fe)

            time.sleep(2)

        logger.error("%s failed or timed out: %s", operation, txid)
        return False

    def _get_account_resources(self, address: str) -> dict:
        """Return current account resources: energy/bandwidth available.
        Bandwidth combines free and paid (delegated) bandwidth.
        """
        try:
            acc = self.client.get_account_resource(address)
        except (requests.RequestException):
            acc = {}
        try:
            energy_limit = int(acc.get("EnergyLimit", 0))
            energy_used = int(acc.get("EnergyUsed", 0))
        except (TypeError, ValueError):
            energy_limit = 0
            energy_used = 0
        try:
            free_limit = int(acc.get("freeNetLimit", 0))
            free_used = int(acc.get("freeNetUsed", 0))
            paid_limit = int(acc.get("NetLimit", 0))
            paid_used = int(acc.get("NetUsed", 0))
        except (TypeError, ValueError):
            free_limit = free_used = paid_limit = paid_used = 0
        energy_avail = max(0, energy_limit - energy_used)
        bandwidth_avail = max(0, (free_limit - free_used) + (paid_limit - paid_used))
        return {"energy_available": energy_avail, "bandwidth_available": bandwidth_avail}

    def _get_incoming_delegation_summary(self, to_address: str, from_address: str) -> dict:
        """Return summary of incoming delegations to 'to_address' from 'from_address'.
        Uses /wallet/getdelegatedresourcev2. Sums energy/bandwidth balances when possible.
        """
        base = self.tron_config.get_tron_client_config().get("full_node")
        headers = {"Content-Type": "application/json"}
        energy_sum = 0
        bw_sum = 0
        count_from_owner = 0
        try:
            resp = requests.post(
                f"{base}/wallet/getdelegatedresourcev2",
                json={"toAddress": to_address, "visible": True},
                headers=headers,
                timeout=5,
            )
            if not resp.ok:
                return {"energy": 0, "bandwidth": 0, "count": 0}
            try:
                data = resp.json() or {}
            except ValueError:
                return {"energy": 0, "bandwidth": 0, "count": 0}
            items = data.get("delegatedResource") or data.get("delegated_resource") or []
            for it in items:
                src = it.get("fromAddress") or it.get("from_address") or it.get("from")
                if src != from_address:
                    continue
                count_from_owner += 1
                # Model A: resource+balance
                resource = it.get("resource")
                if resource in ("ENERGY", "BANDWIDTH"):
                    try:
                        bal = int(it.get("balance", 0) or 0)
                    except (TypeError, ValueError):
                        bal = 0
                    if resource == "ENERGY":
                        energy_sum += bal
                    else:
                        bw_sum += bal
                # Model B: frozen_balance_for_energy/bandwidth
                try:
                    fe = int(it.get("frozen_balance_for_energy", 0) or 0)
                    fb = int(it.get("frozen_balance_for_bandwidth", 0) or 0)
                    energy_sum += fe
                    bw_sum += fb
                except (TypeError, ValueError):
                    pass
        except requests.RequestException:
            return {"energy": 0, "bandwidth": 0, "count": 0}
        return {"energy": energy_sum, "bandwidth": bw_sum, "count": count_from_owner}

    def _ensure_minimum_resources_for_usdt(self, owner_addr: str, invoice_address: str, signing_pk: PrivateKey) -> bool:
        """Ensure invoice address has enough ENERGY and BANDWIDTH to send 1 USDT transfer.
        Top up only if current available resources are below per-transfer estimates.
        """
        try:
            res = self._get_account_resources(invoice_address)
            cur_energy = int(res.get("energy_available", 0))
            cur_bw = int(res.get("bandwidth_available", 0))
            need_energy = max(0, int(self.tron_config.usdt_energy_per_transfer_estimate))
            need_bw = max(0, int(self.tron_config.usdt_bandwidth_per_transfer_estimate))

            # If already sufficient, nothing to do
            if cur_energy >= need_energy and cur_bw >= need_bw:
                logger.info("[gas_station] Resources already sufficient for USDT transfer at %s (E=%d, BW=%d)", invoice_address, cur_energy, cur_bw)
                return True

            # Build dynamic targets equal to max(current, required)
            target_energy = max(cur_energy, need_energy)
            target_bw = max(cur_bw, need_bw)

            return self._delegate_resources(
                owner_addr,
                invoice_address,
                signing_pk,
                target_energy_units=target_energy,
                target_bandwidth_units=target_bw,
            )
        except (requests.RequestException, ValueError, RuntimeError) as e:
            logger.error("[gas_station] Failed ensuring minimum resources for USDT at %s: %s", invoice_address, e)
            return False

    def _delegate_resources(self, owner_addr: str, invoice_address: str, signing_pk: PrivateKey,
                            target_energy_units: int | None = None,
                            target_bandwidth_units: int | None = None) -> bool:
        """Delegate ENERGY and BANDWIDTH up to configured or provided targets in as few txs as possible.
        Compute required TRX for the missing units using heuristic unit-per-TRX estimates
        and send a single delegation per resource, bounded by caps. Fallback to two-step
        if residue remains due to estimate error.
        """
        try:
            cfg = self.tron_config
            cap_energy_trx = max(0.0, cfg.max_energy_delegation_trx_per_invoice)
            cap_bw_trx = max(0.0, cfg.max_bandwidth_delegation_trx_per_invoice)

            # Resolve dynamic targets
            tgt_energy = int(target_energy_units) if target_energy_units is not None else int(cfg.target_energy_units)
            tgt_bw = int(target_bandwidth_units) if target_bandwidth_units is not None else int(cfg.target_bandwidth_units)

            # Helper to perform a single delegation tx for a given resource
            def delegate_once(resource: str, target_units: int, cap_trx: float, units_per_trx: int) -> bool:
                res_key = "energy_available" if resource == "ENERGY" else "bandwidth_available"
                before = self._get_account_resources(invoice_address)
                current = int(before.get(res_key, 0))
                # Also capture incoming delegation summary from owner
                prev_summary = self._get_incoming_delegation_summary(invoice_address, owner_addr)
                prev_e = prev_summary.get("energy", 0)
                prev_b = prev_summary.get("bandwidth", 0)
                prev_c = prev_summary.get("count", 0)

                missing = max(0, target_units - current)
                if missing <= 0:
                    logger.info("[gas_station] %s target met for %s (current=%d >= target=%d)", resource, invoice_address, current, target_units)
                    return True

                # Compute needed TRX using estimate and clamp to caps and min constraints
                if units_per_trx <= 0:
                    needed_trx = 1.0
                else:
                    needed_trx = missing / float(units_per_trx)
                needed_trx *= 1.05  # headroom
                if resource == "BANDWIDTH" and needed_trx < 1.0:
                    needed_trx = 1.0
                needed_trx = min(needed_trx, cap_trx)
                amount_sun = int(max(1_000_000, round(needed_trx, 6) * 1_000_000))

                logger.info(
                    "[gas_station] Single-shot delegating %s %.6f TRX (raw %d) to %s (missing %d units, est %d/unit)",
                    resource, amount_sun / 1_000_000, amount_sun, invoice_address, missing, units_per_trx,
                )
                tx = (
                    self.client.trx.delegate_resource(
                        owner=owner_addr,
                        receiver=invoice_address,
                        balance=amount_sun,
                        resource=resource,
                    )
                    .build()
                    .sign(signing_pk)
                )
                result = tx.broadcast()
                txid = result.get("txid")

                # Prefer observing effect: resources or incoming delegation entries from owner
                for _ in range(12):  # up to ~24s
                    time.sleep(2)
                    after = self._get_account_resources(invoice_address)
                    new = int(after.get(res_key, 0))
                    if new > current:
                        logger.info("[gas_station] %s delegation observed on-chain: %d -> %d units", resource, current, new)
                        break
                    # Check incoming delegation registry change
                    cur_summary = self._get_incoming_delegation_summary(invoice_address, owner_addr)
                    cur_e = cur_summary.get("energy", 0)
                    cur_b = cur_summary.get("bandwidth", 0)
                    cur_c = cur_summary.get("count", 0)
                    if (cur_c > prev_c) or (cur_e > prev_e) or (cur_b > prev_b):
                        logger.info("[gas_station] %s delegation detected via delegatedresourcev2 (owner->invoice)", resource)
                        break
                else:
                    if not txid or not self._wait_for_transaction(txid, f"{resource} delegation"):
                        return False

                # If still below target due to conservative estimate, do one small top-up within cap
                after = self._get_account_resources(invoice_address)
                new = int(after.get(res_key, 0))
                remaining = max(0, target_units - new)
                if remaining > 0 and cap_trx > 0:
                    if units_per_trx <= 0:
                        extra_trx = 1.0
                    else:
                        extra_trx = max(1.0 if resource == "BANDWIDTH" else 0.5, remaining / float(units_per_trx))
                    extra_trx *= 1.05
                    total_trx_used = amount_sun / 1_000_000
                    extra_trx = min(extra_trx, max(0.0, cap_trx - total_trx_used))
                    if extra_trx > 0.0:
                        extra_sun = int(round(extra_trx, 6) * 1_000_000)
                        logger.info(
                            "[gas_station] Top-up delegating %s %.6f TRX (raw %d) to %s (remaining %d units)",
                            resource, extra_sun / 1_000_000, extra_sun, invoice_address, remaining,
                        )
                        tx2 = (
                            self.client.trx.delegate_resource(
                                owner=owner_addr,
                                receiver=invoice_address,
                                balance=extra_sun,
                                resource=resource,
                            )
                            .build()
                            .sign(signing_pk)
                        )
                        res2 = tx2.broadcast()
                        txid2 = res2.get("txid")
                        for _ in range(10):
                            time.sleep(2)
                            after2 = self._get_account_resources(invoice_address)
                            new2 = int(after2.get(res_key, 0))
                            if new2 > new:
                                logger.info("[gas_station] %s top-up observed on-chain: %d -> %d units", resource, new, new2)
                                break
                        else:
                            if not txid2 or not self._wait_for_transaction(txid2, f"{resource} delegation top-up"):
                                return False
                return True

            # ENERGY single-shot
            if cfg.target_energy_units > 0 and cap_energy_trx > 0:
                if not delegate_once(
                    resource="ENERGY",
                    target_units=tgt_energy,
                    cap_trx=cap_energy_trx,
                    units_per_trx=cfg.energy_units_per_trx_estimate,
                ):
                    return False

            # BANDWIDTH single-shot
            if cfg.target_bandwidth_units > 0 and cap_bw_trx > 0:
                if not delegate_once(
                    resource="BANDWIDTH",
                    target_units=tgt_bw,
                    cap_trx=cap_bw_trx,
                    units_per_trx=cfg.bandwidth_units_per_trx_estimate,
                ):
                    return False

            return True
        except (requests.RequestException, ValueError, RuntimeError) as e:
            logger.error("[gas_station] Resource delegation failed for %s: %s", invoice_address, e)
            return False

# Global gas station manager instance
gas_station = GasStationManager()

# Legacy functions for backward compatibility

def prepare_for_sweep(invoice_address: str) -> bool:
    """Legacy function for backward compatibility"""
    return gas_station.prepare_for_sweep(invoice_address)


def auto_activate_on_usdt_receive(invoice_address: str) -> bool:
    """If address is not yet activated, prepare it for sweep; otherwise no-op.
    Returns True if address is active or activation+delegation completed.
    """
    try:
        acc = gas_station.client.get_account(invoice_address)
        if acc:
            return True
    except (requests.RequestException, ValueError, RuntimeError):
        # Treat lookup failure as not activated; will try to activate
        pass
    return prepare_for_sweep(invoice_address)


def get_or_create_tron_deposit_address(db, seller_id: int, deposit_type: str = "TRX", xpub: str = None, account: int = None) -> str:
    """Return existing seller deposit address or create one if missing.
    For now, use the gas wallet address as a shared deposit address if none exists.
    """
    try:
        wal = get_seller_wallet(db, seller_id=seller_id, deposit_type=deposit_type)
        if wal and wal.address:
            return wal.address
    except SQLAlchemyError:
        wal = None
    # Fallback: use gas wallet address as deposit address
    try:
        gas_addr = gas_station.get_gas_wallet_address()
    except (ValueError, RuntimeError):
        gas_addr = ""
    try:
        # Ensure a record exists
        created = create_seller_wallet(
            db,
            seller_id=seller_id,
            address=gas_addr,
            derivation_path="",
            deposit_type=deposit_type,
            xpub=xpub or "",
            account=account or 0,
        )
        return created.address
    except SQLAlchemyError:
        return gas_addr


def calculate_trx_needed(seller) -> float:
    """Heuristic recommendation for TRX deposit amount for gas operations."""
    try:
        cfg = config.tron
        credited = 0.0
        try:
            credited = float(getattr(seller, 'gas_deposit_balance', 0) or 0.0)
        except (TypeError, ValueError):
            credited = 0.0
        # Recommend enough for one activation and initial ENERGY/BW staking with some headroom,
        # scaled up if credited balance is low
        base = (cfg.auto_activation_amount * 2.0) + cfg.energy_delegation_amount + cfg.bandwidth_delegation_amount + 2.0
        if credited < base / 2:
            rec = base * 1.5
        else:
            rec = base
        return round(float(rec), 2)
    except (ValueError, RuntimeError):  # As a last resort, return a sensible default
        return 50.0
