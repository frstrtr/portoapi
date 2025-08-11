# Gas Station Module

The Gas Station module provides comprehensive TRON resource management for PortoAPI's USDT operations.

## Overview

The gas station manages:

- **Energy** for USDT smart contract operations
- **Bandwidth** for transaction execution  
- **TRX** for account activation
- **Resource delegation** for users and sellers
- **Automatic rebalancing** based on usage patterns

## Architecture

```text
src/core/services/gasstation/
├── __init__.py                 # Module exports
├── gas_station_service.py      # Core TRON operations
├── gas_station_manager.py      # Business logic layer
├── gas_station_utils.py        # Utility functions
└── cli.py                      # Command-line interface
```

## Key Components

### GasStationService

Core service handling direct TRON blockchain operations:

- Resource management and monitoring
- Account activation
- Resource delegation
- Auto-rebalancing

### GasStationManager  

High-level business logic for PortoAPI integration:

- Operational status checks
- User and seller onboarding
- Invoice processing validation
- Maintenance operations

### Utilities

Helper functions for calculations and analysis:

- Transaction cost estimation
- Staking efficiency analysis
- Resource requirement planning

## Usage

### Integration with PortoAPI

```python
from src.core.config import TronConfig
from src.core.services.gasstation import GasStationManager

# Initialize
config = TronConfig()
gas_station = GasStationManager(config)

# Check status
status = gas_station.check_operational_status()

# Activate user
success, txid, msg = gas_station.activate_new_user(user_address)

# Setup seller
success, transactions, msg = gas_station.setup_seller(seller_address)

# Check capacity
can_process, msg = gas_station.can_process_invoice(10)
```

### Command Line Interface

```bash
# Check status
python -m src.core.services.gasstation.cli status

# Activate account
python -m src.core.services.gasstation.cli activate TAddress123...

# Setup seller
python -m src.core.services.gasstation.cli setup-seller TSellerAddress...

# Check capacity
python -m src.core.services.gasstation.cli capacity --transactions 100

# Perform maintenance
python -m src.core.services.gasstation.cli maintenance

# Get summary
python -m src.core.services.gasstation.cli summary --json
```

## Configuration

The gas station uses the existing PortoAPI configuration:

```env
# Gas station configuration
GAS_STATION_TYPE=single
GAS_WALLET_PRIVATE_KEY=your_private_key_here
AUTO_ACTIVATION_TRX_AMOUNT=1.0
ENERGY_DELEGATION_TRX_AMOUNT=1.0
BANDWIDTH_DELEGATION_TRX_AMOUNT=0.5

# Network and contracts
TRON_NETWORK=testnet
TRON_TESTNET_USDT_CONTRACT=TXYZopYRdj2D9XRtbG411XZZ3kM5VkAeBf
TRON_MAINNET_USDT_CONTRACT=TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t
```

## Resource Model

The gas station operates on TRON's Staking 2.0 model:

1. **Energy Stakes**: Can only delegate energy resources
2. **Bandwidth Stakes**: Can only delegate bandwidth resources  
3. **Resource Pools**: Pre-staked TRX generates daily renewable resources
4. **Efficient Operation**: Direct resource delegation instead of TRX transfers

### Typical USDT Transaction Costs (defaults)

- Energy: ~14,650 units per USDT transfer (Nile testnet baseline)
- Bandwidth: ~345 units per transaction
- Account Activation: 1.0 TRX (configurable)

Note: The module computes BANDWIDTH units/TRX dynamically from chain parameters when available and falls back to config estimates otherwise.

## Monitoring and Maintenance

The gas station provides comprehensive monitoring and resilient operations:

- **Real-time resource status**
- **Daily transaction capacity calculation**
- **Staking efficiency analysis**
- **Automatic rebalancing recommendations**
- **Operational health checks**
- **Resilient confirmations** using multiple endpoints (wallet and walletsolidity, local and remote)
- **Lag-aware resource reads**: queries multiple views and uses the maximum observed values

## Enterprise Features

- **Multi-seller support** with individual resource allocation
- **Auto-scaling** based on usage patterns
- **Fee collection framework** for revenue management
- **High-availability** with operational status monitoring
- **Resource optimization** for cost-effective operations
- **Free Gas integration**: one-click address activation and minimum resource top-up via Telegram bot (/free_gas)

## Security

- **Private key management** through configuration
- **Transaction validation** before execution
- **Resource limit checks** to prevent over-delegation
- **Error handling** with detailed logging
- **Network isolation** (testnet vs mainnet)

The gas station module provides enterprise-grade TRON resource management optimized for high-volume USDT operations while maintaining security and operational efficiency.
