# Загрузка конфигурации из .env

import os
from dotenv import load_dotenv
import logging

logger = logging.getLogger(__name__)

# Load environment variables from .env file
load_dotenv()

class TronConfig:
    """Configuration for TRON blockchain interaction"""
    
    def __init__(self):
        # Network Configuration
        self.network = os.getenv("TRON_NETWORK", "testnet")  # mainnet or testnet
        self.api_key = os.getenv("TRON_API_KEY", "")
        
        # Local node configuration (preferred if available)
        self.local_node_enabled = os.getenv("TRON_LOCAL_NODE_ENABLED", "true").lower() == "true"
        
        # Network-specific local nodes
        if self.network == "mainnet":
            self.local_full_node = os.getenv("TRON_MAINNET_LOCAL_FULL_NODE", "http://192.168.86.20:8090")
            self.local_solidity_node = os.getenv("TRON_MAINNET_LOCAL_SOLIDITY_NODE", "http://192.168.86.20:8091")
            self.local_event_server = os.getenv("TRON_MAINNET_LOCAL_EVENT_SERVER", "http://192.168.86.20:8092")
            self.local_grpc_endpoint = os.getenv("TRON_MAINNET_LOCAL_GRPC_ENDPOINT", "192.168.86.20:50051")
        else:  # testnet/nile
            self.local_full_node = os.getenv("TRON_TESTNET_LOCAL_FULL_NODE", "http://192.168.86.154:8090")
            self.local_solidity_node = os.getenv("TRON_TESTNET_LOCAL_SOLIDITY_NODE", "http://192.168.86.154:8091")
            self.local_event_server = os.getenv("TRON_TESTNET_LOCAL_EVENT_SERVER", "http://192.168.86.154:8092")
            self.local_grpc_endpoint = os.getenv("TRON_TESTNET_LOCAL_GRPC_ENDPOINT", "192.168.86.154:50051")
        
        # Remote endpoints (fallback)
        if self.network == "mainnet":
            self.remote_full_node = os.getenv("TRON_REMOTE_MAINNET_FULL_NODE", "https://api.trongrid.io")
            self.remote_solidity_node = os.getenv("TRON_REMOTE_MAINNET_SOLIDITY_NODE", "https://api.trongrid.io")
            self.remote_event_server = os.getenv("TRON_REMOTE_MAINNET_EVENT_SERVER", "https://api.trongrid.io")
            self.usdt_contract = os.getenv("TRON_MAINNET_USDT_CONTRACT", "TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t")
        else:  # testnet
            self.remote_full_node = os.getenv("TRON_REMOTE_TESTNET_FULL_NODE", "https://nile.trongrid.io")
            self.remote_solidity_node = os.getenv("TRON_REMOTE_TESTNET_SOLIDITY_NODE", "https://nile.trongrid.io")
            self.remote_event_server = os.getenv("TRON_REMOTE_TESTNET_EVENT_SERVER", "https://nile.trongrid.io")
            self.usdt_contract = os.getenv("TRON_TESTNET_USDT_CONTRACT", "TXYZopYRdj2D9XRtbG411XZZ3kM5VkAeBf")
        
        # Gas Station Configuration
        self.gas_station_type = os.getenv("GAS_STATION_TYPE", "single")  # single or multisig
        
        # Single wallet gas station
        self.gas_wallet_private_key = os.getenv("GAS_WALLET_PRIVATE_KEY", "")
        self.gas_wallet_mnemonic = os.getenv("GAS_WALLET_MNEMONIC", "")
        
        # Multisig gas station
        self.multisig_contract_address = os.getenv("MULTISIG_CONTRACT_ADDRESS", "")
        self.multisig_required_signatures = int(os.getenv("MULTISIG_REQUIRED_SIGNATURES", "2"))
        self.multisig_owner_keys = self._parse_multisig_keys()
        
        # Resource delegation settings (network-specific)
        if self.network == "testnet":
            # Lower amounts for testnet
            self.auto_activation_amount = float(os.getenv("AUTO_ACTIVATION_TRX_AMOUNT", "1.0"))
            self.energy_delegation_amount = float(os.getenv("ENERGY_DELEGATION_TRX_AMOUNT", "1.0"))
            self.bandwidth_delegation_amount = float(os.getenv("BANDWIDTH_DELEGATION_TRX_AMOUNT", "0.5"))
        else:
            # Production amounts for mainnet
            self.auto_activation_amount = float(os.getenv("AUTO_ACTIVATION_TRX_AMOUNT", "1.5"))
            self.energy_delegation_amount = float(os.getenv("ENERGY_DELEGATION_TRX_AMOUNT", "2.0"))
            self.bandwidth_delegation_amount = float(os.getenv("BANDWIDTH_DELEGATION_TRX_AMOUNT", "1.0"))
        
        # Validation
        self._validate_config()
    
    def _parse_multisig_keys(self) -> list:
        """Parse multisig owner private keys from environment"""
        keys_str = os.getenv("MULTISIG_OWNER_KEYS", "")
        if not keys_str:
            return []
        return [key.strip() for key in keys_str.split(",") if key.strip()]
    
    def _validate_config(self):
        """Validate configuration settings"""
        if self.network not in ["mainnet", "testnet"]:
            raise ValueError(f"Invalid TRON_NETWORK: {self.network}. Must be 'mainnet' or 'testnet'")
        
        if self.gas_station_type == "single":
            if not self.gas_wallet_private_key and not self.gas_wallet_mnemonic:
                logger.warning("No gas wallet credentials provided for single wallet mode")
        elif self.gas_station_type == "multisig":
            if not self.multisig_contract_address:
                raise ValueError("MULTISIG_CONTRACT_ADDRESS required for multisig mode")
            if len(self.multisig_owner_keys) < self.multisig_required_signatures:
                raise ValueError(f"Not enough multisig owner keys. Required: {self.multisig_required_signatures}, Provided: {len(self.multisig_owner_keys)}")
        else:
            raise ValueError(f"Invalid GAS_STATION_TYPE: {self.gas_station_type}. Must be 'single' or 'multisig'")
    
    def get_tron_client_config(self) -> dict:
        """Get configuration for TronPy client, preferring local node if available"""
        if self.local_node_enabled:
            client_config = {
                "full_node": self.local_full_node,
                "solidity_node": self.local_solidity_node,
                "event_server": self.local_event_server,
                "node_type": "local"
            }
        else:
            client_config = {
                "full_node": self.remote_full_node,
                "solidity_node": self.remote_solidity_node,
                "event_server": self.remote_event_server,
                "node_type": "remote"
            }
        
        # Add API key for remote connections
        if not self.local_node_enabled and self.api_key:
            client_config["api_key"] = self.api_key
            
        return client_config
    
    def test_local_node_connection(self) -> bool:
        """Test if local TRON node is accessible"""
        if not self.local_node_enabled:
            return False
            
        try:
            import requests
            response = requests.get(f"{self.local_full_node}/wallet/getnowblock", timeout=5)
            return response.status_code == 200
        except Exception:
            return False
    
    def get_fallback_client_config(self) -> dict:
        """Get fallback configuration when local node fails"""
        client_config = {
            "full_node": self.remote_full_node,
            "solidity_node": self.remote_solidity_node,
            "event_server": self.remote_event_server,
            "node_type": "remote_fallback"
        }
        
        if self.api_key:
            client_config["api_key"] = self.api_key
            
        return client_config

class DatabaseConfig:
    """Database configuration"""
    
    def __init__(self):
        self.database_url = os.getenv("DATABASE_URL", "sqlite:///./data/database.sqlite3")
        self.echo_sql = os.getenv("DATABASE_ECHO", "false").lower() == "true"

class BotConfig:
    """Telegram bot configuration"""
    
    def __init__(self):
        self.token = os.getenv("TELEGRAM_BOT_TOKEN", "")
        self.webhook_url = os.getenv("BOT_WEBHOOK_URL", "")
        self.secret_token = os.getenv("BOT_SECRET_TOKEN", "")
        
        if not self.token:
            raise ValueError("TELEGRAM_BOT_TOKEN is required")

class APIConfig:
    """API configuration"""
    
    def __init__(self):
        self.host = os.getenv("API_HOST", "0.0.0.0")
        self.port = int(os.getenv("API_PORT", "8000"))
        self.debug = os.getenv("API_DEBUG", "false").lower() == "true"
        self.base_url = os.getenv("API_BASE_URL", f"http://localhost:{self.port}")

class Config:
    """Main configuration class"""
    
    def __init__(self):
        self.tron = TronConfig()
        self.database = DatabaseConfig()
        self.bot = BotConfig()
        self.api = APIConfig()
        
        # Logging
        self.log_level = os.getenv("LOG_LEVEL", "INFO").upper()
        self.log_file = os.getenv("LOG_FILE", "portoapi.log")

# Global config instance
config = Config()

def load_config() -> Config:
    """Load and return configuration"""
    return config
