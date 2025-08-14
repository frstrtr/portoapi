# TRON Gas-Free System Documentation

## Overview

The TRON Gas-Free System enables free USDT transfers by automatically providing the necessary energy and bandwidth resources to user addresses. The system uses an estimation-based approach that adapts to different network conditions (mainnet/testnet) and employs permission-based transactions for secure resource delegation.

## Table of Contents

1. [System Architecture](#system-architecture)
2. [Energy and Bandwidth Calculation](#energy-and-bandwidth-calculation)
3. [Network Type Adaptation](#network-type-adaptation)
4. [Permission-Based Signer System](#permission-based-signer-system)
5. [Transaction Construction and Broadcasting](#transaction-construction-and-broadcasting)
6. [Success Verification](#success-verification)
7. [API Reference](#api-reference)
8. [Configuration](#configuration)
9. [Troubleshooting](#troubleshooting)

---

## System Architecture

### Core Components

1. **GasStationManager**: Main orchestrator for gas-free operations
2. **Estimation Engine**: Calculates precise resource requirements
3. **Permission System**: Manages secure resource delegation
4. **Verification Engine**: Confirms successful resource allocation

### Workflow

```
User Address → Estimation → Activation (if needed) → Resource Delegation → Verification
```

---

## Energy and Bandwidth Calculation

### Energy Calculation Formula

The system uses a sophisticated estimation approach rather than fixed values:

#### 1. Simulation-Based Estimation

```python
# Primary method: Real-time simulation
simulation_result = simulate_usdt_transfer(target_address)
base_energy = simulation_result.energy_used  # Typically 1,817 for existing USDT holders

# Apply safety margin
required_energy = int(base_energy * 1.15)  # 15% safety buffer

# Apply reasonable minimum
if base_energy > 0:
    final_energy = max(required_energy, base_energy + 5000)  # Simulation + 5k buffer
else:
    # Fallback for failed simulation
    fallback_energy = 25000  # Network-appropriate default
    final_energy = max(required_energy, fallback_energy)
```

#### 2. TRX to Energy Conversion

```python
# Energy yield per TRX (August 2025 ratio)
energy_per_trx = 2.38  # Based on: 100B total daily energy / 42B frozen TRX

# Calculate TRX needed for delegation
trx_needed = max(1, int(required_energy / energy_per_trx))

# Example: 6,817 energy / 2.38 = 2,864 TRX
```

### Bandwidth Calculation

#### 1. Bandwidth Requirements

```python
# Simulation-based bandwidth calculation
base_bandwidth = simulation_result.bandwidth_used  # Typically 270

# Apply safety margin
required_bandwidth = int(base_bandwidth * 1.25)  # 25% safety buffer

# Minimum threshold
final_bandwidth = max(required_bandwidth, 350)  # Minimum for transactions
```

#### 2. Activation Bonus

```python
# New addresses get free bandwidth upon activation
activation_bandwidth_bonus = 600  # TRON network standard

# Total available bandwidth after activation
total_bandwidth = current_bandwidth + activation_bandwidth_bonus
```

### Mathematical Formulas

#### Energy Requirements by Recipient Type

| Recipient Type | Typical Energy | Calculation | TRX Required |
|---------------|----------------|-------------|--------------|
| Existing USDT holder | ~32,000 | 32,000 / 2.38 | ~13,445 TRX |
| New USDT recipient | ~65,000 | 65,000 / 2.38 | ~27,310 TRX |
| Simulation-based | 1,817 + 5,000 | 6,817 / 2.38 | ~2,864 TRX |

#### Network Resource Parameters

```python
# Global network parameters (retrieved dynamically)
total_energy_limit = get_network_parameter("TotalEnergyLimit")
total_energy_weight = get_network_parameter("TotalEnergyWeight")

# Calculate daily energy per TRX
daily_energy_per_trx = total_energy_limit / total_energy_weight

# Fallback to documented ratio if unavailable
if daily_energy_per_trx <= 0:
    daily_energy_per_trx = 2.38  # August 2025 mainnet ratio
```

---

## Network Type Adaptation

### Mainnet vs Testnet Differences

#### 1. Energy Yield Variations

```python
# Network-specific energy yields
mainnet_energy_per_trx = 2.38  # Stable production ratio
testnet_energy_per_trx = 76.28  # Higher in test environments

# System automatically detects and adapts
def get_network_energy_yield():
    params = get_global_resource_parameters()
    network_yield = params.get("dailyEnergyPerTrx", 2.38)
    
    # Use documented ratio for consistency
    delegation_yield = 2.38  # Always use production values for delegation
    return delegation_yield
```

#### 2. Network Parameter Detection

```python
# Automatic network detection
def detect_network_type():
    try:
        # Query network parameters
        params = client.get_network_parameters()
        
        # Testnet typically has different energy/bandwidth limits
        if params.get("TotalEnergyLimit", 0) < 1000000000:
            return "testnet"
        else:
            return "mainnet"
    except:
        return "unknown"
```

#### 3. Adaptive Fallbacks

```python
# Network-appropriate fallbacks
fallback_values = {
    "mainnet": {
        "energy_per_transfer": 32000,
        "energy_per_trx": 2.38,
        "bandwidth_per_trx": 1500
    },
    "testnet": {
        "energy_per_transfer": 25000,  # Lower for testing
        "energy_per_trx": 2.38,       # Use consistent values
        "bandwidth_per_trx": 1500
    }
}
```

---

## Permission-Based Signer System

### Architecture

The system uses a multi-key architecture for secure resource delegation:

```
Gas Wallet (Resource Provider) → Signer (Authorization) → Target Address (Recipient)
```

### Key Roles

#### 1. Gas Wallet
- **Purpose**: Provides TRX resources for energy/bandwidth delegation
- **Address**: `THpjvxomBhvZUodJ3FHFY1szQxAidxejy8`
- **Resources**: Maintains pool of TRX for delegation operations
- **Permissions**: Cannot initiate transactions directly

#### 2. Signer Wallet
- **Purpose**: Authorizes transactions on behalf of gas wallet
- **Key Source**: `SIGNER_WALLET_PRIVATE_KEY` environment variable
- **Address**: `TXb8AYmGgPRuXovkm1wsVwKfAvrbrHQ1Lo`
- **Permissions**: Permission ID 2 access to gas wallet

#### 3. Permission System

```python
# Permission configuration on gas wallet
{
    "owner_permission": {
        "permission_name": "owner",
        "threshold": 1,
        "keys": [{"address": "gas_wallet_address", "weight": 1}]
    },
    "active_permissions": [
        {
            "id": 2,
            "permission_name": "active",
            "threshold": 1,
            "operations": "7fff1fc0037e0000000000000000000000000000000000000000000000000000",
            "keys": [{"address": "signer_address", "weight": 1}]
        }
    ]
}
```

### Security Model

#### 1. Separation of Concerns
```python
# Gas wallet: Holds resources, cannot initiate transactions
gas_wallet_private_key = None  # Not available to system

# Signer: Can authorize transactions, no direct resource access
signer_private_key = os.getenv('SIGNER_WALLET_PRIVATE_KEY')
```

#### 2. Permission Scope
```python
# Operations allowed for Permission ID 2
allowed_operations = [
    "TransferContract",           # TRX transfers
    "FreezeBalanceV2Contract",    # Resource freezing
    "DelegateResourceContract",   # Resource delegation
    "UnDelegateResourceContract"  # Resource reclamation
]
```

---

## Transaction Construction and Broadcasting

### Activation Transaction

#### 1. Transaction Structure

```python
def create_activation_transaction(target_address):
    # Build transfer transaction (1 TRX to activate address)
    txn_builder = client.trx.transfer(
        from_=gas_wallet_address,
        to=target_address,
        amount=1_000_000  # 1 TRX in SUN
    ).permission_id(2)  # Use Permission ID 2
    
    return txn_builder
```

#### 2. Permission Injection

```python
# Permission ID injection
transaction = base_transaction.permission_id(2)

# This modifies the transaction to use specific permission:
# - References gas wallet as resource owner
# - Uses signer for authorization
# - Enables delegation without gas wallet private key
```

#### 3. Signing Process

```python
def sign_with_signer(transaction):
    # Get signer private key
    signer_key = os.getenv('SIGNER_WALLET_PRIVATE_KEY')
    private_key = PrivateKey(bytes.fromhex(signer_key))
    
    # Build and sign transaction
    built_txn = transaction.build()
    signed_txn = built_txn.sign(private_key)
    
    return signed_txn
```

### Resource Delegation Transaction

#### 1. Energy Delegation

```python
def delegate_energy(target_address, energy_amount):
    # Calculate TRX needed
    trx_amount = max(1, int(energy_amount / 2.38))
    
    # Build delegation transaction
    txn_builder = client.trx.delegate_resource(
        owner=gas_wallet_address,        # Resource provider
        receiver=target_address,         # Resource recipient
        balance=trx_amount * 1_000_000,  # Amount in SUN
        resource='ENERGY'                # Resource type
    ).permission_id(2)                   # Signer authorization
    
    return txn_builder
```

#### 2. Bandwidth Delegation

```python
def delegate_bandwidth(target_address, bandwidth_amount):
    # Calculate TRX needed
    trx_amount = max(1, int(bandwidth_amount / 1500))
    
    # Build delegation transaction
    txn_builder = client.trx.delegate_resource(
        owner=gas_wallet_address,        # Resource provider
        receiver=target_address,         # Resource recipient
        balance=trx_amount * 1_000_000,  # Amount in SUN
        resource='BANDWIDTH'             # Resource type
    ).permission_id(2)                   # Signer authorization
    
    return txn_builder
```

### Broadcasting Process

#### 1. Transaction Broadcasting

```python
def broadcast_transaction(signed_transaction):
    try:
        # Submit to TRON network
        response = signed_transaction.broadcast()
        
        # Validate response
        if response.get('result'):
            transaction_id = response.get('txid')
            logger.info(f"Transaction successful: {transaction_id}")
            return True, transaction_id
        else:
            logger.error(f"Transaction failed: {response}")
            return False, None
            
    except Exception as e:
        logger.error(f"Broadcast error: {e}")
        return False, None
```

#### 2. Network Submission

```python
# Transaction flow
Local Node → TRON Network → Block Confirmation → Resource Update
     ↓              ↓              ↓                    ↓
  Build Txn    Submit Txn    Mine Block        Update Balances
```

---

## Success Verification

### Fast Verification System

#### 1. Resource Monitoring

```python
def verify_delegation_fast(target_address, resource_type, expected_amount):
    """
    Fast verification using 0.5s intervals (5 seconds total)
    Matches activation check pattern for consistency
    """
    max_attempts = 10  # 10 attempts × 0.5s = 5 seconds
    interval = 0.5     # 500ms between checks
    
    # Get baseline resources
    baseline = get_account_resources(target_address)
    baseline_amount = baseline.get(f'{resource_type}_available', 0)
    
    for attempt in range(max_attempts):
        # Check current resources
        current = get_account_resources(target_address)
        current_amount = current.get(f'{resource_type}_available', 0)
        
        # Calculate increase
        increase = current_amount - baseline_amount
        
        # Success if any positive increase detected
        if increase > 0:
            logger.info(f"Delegation verified: {resource_type} increased by {increase}")
            return True
            
        # Wait before next attempt
        if attempt < max_attempts - 1:
            time.sleep(interval)
    
    return False  # Timeout after 5 seconds
```

#### 2. Success Criteria

```python
# Verification success conditions
def check_preparation_success(target_address, required_energy, required_bandwidth):
    resources = get_account_resources(target_address)
    current_energy = resources.get('energy_available', 0)
    current_bandwidth = resources.get('bandwidth_available', 0)
    
    # Success criteria
    energy_sufficient = current_energy >= required_energy * 0.9    # 90% threshold
    bandwidth_sufficient = current_bandwidth >= required_bandwidth * 0.9
    address_activated = check_address_exists(target_address)
    
    return energy_sufficient and bandwidth_sufficient and address_activated
```

### Verification Phases

#### 1. Immediate Verification (0-5 seconds)
```python
# Fast check for immediate resource reflection
immediate_success = verify_delegation_fast(address, "energy", expected_energy)
```

#### 2. Final Verification (5+ seconds)
```python
# Comprehensive check after all operations
final_resources = get_account_resources(target_address)
final_success = check_preparation_success(target_address, required_energy, required_bandwidth)
```

#### 3. USDT Readiness Check
```python
def check_usdt_readiness(target_address):
    resources = get_account_resources(target_address)
    
    # USDT transfer requirements
    min_energy = 15000      # Conservative minimum
    min_bandwidth = 300     # Basic transaction needs
    
    energy_ready = resources.get('energy_available', 0) >= min_energy
    bandwidth_ready = resources.get('bandwidth_available', 0) >= min_bandwidth
    activated = check_address_exists(target_address)
    
    return energy_ready and bandwidth_ready and activated
```

---

## API Reference

### Main Functions

#### `intelligent_prepare_address_for_usdt(target_address)`

Comprehensive preparation function that handles activation and resource delegation.

**Parameters:**
- `target_address` (str): TRON address to prepare for USDT transfers

**Returns:**
```python
{
    "success": bool,
    "strategy": str,  # "complete_preparation", "activation_only", etc.
    "execution_time": float,
    "details": {
        "required_energy": int,
        "required_bandwidth": int,
        "current_resources": dict,
        "simulation_data": dict
    },
    "delegation_details": {
        "success": bool,
        "method": "permission_based_delegation",
        "execution_time": float,
        "details": {
            "delegations": [
                {
                    "type": "energy",
                    "amount": int,
                    "trx_delegated": int,
                    "success": bool,
                    "transaction_id": str
                }
            ]
        }
    }
}
```

#### `simulate_usdt_transfer(from_address, to_address=None, amount_usdt=1.0)`

Simulates a USDT transfer to determine precise resource requirements.

**Parameters:**
- `from_address` (str): Sender address
- `to_address` (str, optional): Recipient address
- `amount_usdt` (float): USDT amount to simulate

**Returns:**
```python
{
    "energy_used": int,      # Energy required
    "bandwidth_used": int,   # Bandwidth required
    "success": bool,
    "simulation_time": float
}
```

#### `delegate_resources_with_permission(target_address, energy_amount=None, bandwidth_amount=None)`

Direct resource delegation using permission-based system.

**Parameters:**
- `target_address` (str): Address to receive resources
- `energy_amount` (int, optional): Energy units to delegate
- `bandwidth_amount` (int, optional): Bandwidth units to delegate

**Returns:**
```python
{
    "success": bool,
    "method": "permission_based_delegation",
    "execution_time": float,
    "details": {
        "delegations": list,
        "successful_count": int,
        "total_count": int
    }
}
```

---

## Configuration

### Environment Variables

```bash
# Required: Signer wallet private key
SIGNER_WALLET_PRIVATE_KEY=your_signer_private_key_hex

# Optional: Gas wallet address (if not derived)
GAS_WALLET_ADDRESS=THpjvxomBhvZUodJ3FHFY1szQxAidxejy8

# Optional: Network configuration
TRON_NODE_URL=http://192.168.86.154:8090
TRON_NETWORK_TYPE=mainnet  # or testnet

# Optional: Estimation overrides
USDT_ENERGY_PER_TRANSFER_ESTIMATE=25000
ENERGY_UNITS_PER_TRX_ESTIMATE=2.38
BANDWIDTH_UNITS_PER_TRX_ESTIMATE=1500
```

### Gas Station Configuration

```python
# Gas wallet setup requirements
gas_wallet_setup = {
    "minimum_trx_balance": 100,     # Minimum TRX for operations
    "minimum_energy": 1000000,      # Minimum energy reserve
    "minimum_bandwidth": 10000,     # Minimum bandwidth reserve
    
    "permissions": {
        "active_permission_id": 2,
        "signer_address": "TXb8AYmGgPRuXovkm1wsVwKfAvrbrHQ1Lo",
        "allowed_operations": [
            "TransferContract",
            "DelegateResourceContract",
            "FreezeBalanceV2Contract"
        ]
    }
}
```

### Network Adaptation Settings

```python
# Automatic network detection and adaptation
network_settings = {
    "energy_calculation": {
        "use_simulation": True,        # Prefer simulation over fixed values
        "simulation_fallback": 25000,  # Fallback if simulation fails
        "safety_margin": 1.15,         # 15% safety buffer
        "minimum_buffer": 5000         # Minimum additional buffer
    },
    
    "delegation_calculation": {
        "energy_per_trx": 2.38,        # Use documented mainnet ratio
        "bandwidth_per_trx": 1500,     # Conservative bandwidth estimate
        "minimum_trx": 1               # Minimum delegation amount
    },
    
    "verification": {
        "fast_check_attempts": 10,     # 5 seconds total
        "check_interval": 0.5,         # 500ms between attempts
        "success_threshold": 0.9       # 90% of required resources
    }
}
```

---

## Troubleshooting

### Common Issues

#### 1. "No signer available" Error
```python
# Cause: Missing SIGNER_WALLET_PRIVATE_KEY environment variable
# Solution: Set the environment variable
export SIGNER_WALLET_PRIVATE_KEY=your_private_key_here
```

#### 2. Permission Denied
```python
# Cause: Signer doesn't have Permission ID 2 access to gas wallet
# Solution: Verify permission configuration on gas wallet
```

#### 3. Insufficient Gas Station Resources
```python
# Cause: Gas wallet doesn't have enough TRX/energy/bandwidth
# Solution: Top up gas wallet resources
```

#### 4. Verification Timeout
```python
# Cause: Network congestion or delegation not reflected quickly
# Note: Address likely received resources despite timeout
# Solution: Manual verification after timeout
```

### Debugging Tools

#### 1. Resource Verification

```python
def debug_address_status(address):
    resources = gas_station._get_account_resources(address)
    activated = gas_station._check_address_exists(address)
    
    print(f"Address: {address}")
    print(f"Activated: {activated}")
    print(f"Energy: {resources.get('energy_available', 0):,}")
    print(f"Bandwidth: {resources.get('bandwidth_available', 0):,}")
    print(f"USDT Ready: {check_usdt_readiness(address)}")
```

#### 2. Network Parameter Check

```python
def debug_network_parameters():
    params = gas_station.get_global_resource_parameters()
    
    print(f"Network Energy per TRX: {params.get('dailyEnergyPerTrx', 'N/A')}")
    print(f"Network Bandwidth per TRX: {params.get('dailyBandwidthPerTrx', 'N/A')}")
    print(f"Total Energy Limit: {params.get('totalEnergyLimit', 'N/A'):,}")
    print(f"Total Energy Weight: {params.get('totalEnergyWeightSun', 'N/A'):,}")
```

#### 3. Simulation Testing

```python
def debug_simulation(address):
    try:
        sim = gas_station.simulate_usdt_transfer(address)
        print(f"Simulation Success: {sim.get('success', False)}")
        print(f"Energy Needed: {sim.get('energy_used', 0):,}")
        print(f"Bandwidth Needed: {sim.get('bandwidth_used', 0):,}")
    except Exception as e:
        print(f"Simulation Failed: {e}")
```

### Performance Optimization

#### 1. Batch Operations
```python
# For multiple addresses, use batch preparation
addresses = ["addr1", "addr2", "addr3"]
results = []

for address in addresses:
    result = gas_station.intelligent_prepare_address_for_usdt(address)
    results.append(result)
    
    # Add delay to avoid rate limiting
    time.sleep(1)
```

#### 2. Resource Monitoring
```python
# Monitor gas station resources
def monitor_gas_station():
    resources = gas_station._get_account_resources(gas_wallet_address)
    
    if resources.get('energy_available', 0) < 500000:
        alert("Gas station energy low")
    
    if resources.get('bandwidth_available', 0) < 5000:
        alert("Gas station bandwidth low")
```

---

## Best Practices

### 1. Resource Management
- Monitor gas station resources regularly
- Maintain minimum TRX balance for operations
- Use simulation-based estimation when possible

### 2. Security
- Store signer private key securely
- Rotate signer keys periodically
- Monitor permission usage

### 3. Performance
- Use fast verification for time-sensitive operations
- Implement retry logic for network issues
- Cache simulation results when appropriate

### 4. Monitoring
- Log all delegation transactions
- Track success rates
- Monitor resource consumption patterns

---

## Conclusion

The TRON Gas-Free System provides a robust, estimation-based approach to automatic resource provisioning for USDT transfers. By using real-time simulation, permission-based security, and network-adaptive calculations, the system efficiently allocates just the right amount of resources while maintaining security and reliability across different network conditions.

The system's key advantages:
- **Estimation-based**: Adapts to actual requirements vs fixed values
- **Network-agnostic**: Works across mainnet/testnet environments
- **Secure**: Permission-based authorization without exposing gas wallet keys
- **Efficient**: Precise resource allocation avoiding waste
- **Fast**: Quick verification and resource provisioning

This documentation covers the complete implementation details, from mathematical formulas to API usage, providing everything needed to understand, deploy, and maintain the gas-free system.
