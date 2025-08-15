# TRON Resource Calculation - Implementation Guide

## Quick Reference

### Core Function
```python
dry_run_prepare_for_sweep(destination_address, amount_usdt)
```

### Key Calculations

1. **Energy Estimation**: Smart contract simulation → TRX freezing cost
2. **Bandwidth Estimation**: Transaction size → TRX freezing cost  
3. **Activation Cost**: Network-specific TRX transfer (1.0 testnet, 1.5 mainnet)
4. **Wallet Orchestration**: Signer signs, Gas wallet pays

## Implementation Steps

### Step 1: Analyze Destination Address

```python
# Check if address exists and get current state
address_exists = tron_client.is_address(destination_address)
current_resources = get_account_resources(destination_address) if address_exists else {}
```

### Step 2: Smart Contract Simulation

```python
if address_exists:
    # Direct simulation
    energy_needed = estimate_usdt_energy_precise(
        from_address=destination_address,
        to_address="TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t",  # USDT
        amount_usdt=amount_usdt
    )
else:
    # Proxy simulation via gas wallet
    energy_needed = estimate_usdt_energy_precise(
        from_address=gas_wallet_address,
        to_address="TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t",
        amount_usdt=amount_usdt
    ) * 1.2  # 20% penalty for fresh address
```

### Step 3: Live Network Parameters

```python
def get_resource_yields():
    """Get current energy/bandwidth yields per TRX"""
    params = tron_client.get_chain_parameters()
    
    energy_fee = params.get('getEnergyFee', 280)  # SUN per energy
    bandwidth_fee = params.get('getBandwidthFee', 1000)  # SUN per bandwidth
    
    # Convert to per-TRX yields (1 TRX = 1,000,000 SUN)
    energy_per_trx = 1_000_000 / energy_fee
    bandwidth_per_trx = 1_000_000 / bandwidth_fee
    
    # Testnet adjustment for unrealistic bandwidth yields
    if network_type == 'testnet' and bandwidth_per_trx < 50:
        bandwidth_per_trx = 200
    
    return energy_per_trx, bandwidth_per_trx
```

### Step 4: Calculate Delegation Costs

```python
def calculate_trx_freezing_costs(energy_needed, bandwidth_needed):
    """Calculate TRX to freeze for resource delegation"""
    energy_per_trx, bandwidth_per_trx = get_resource_yields()
    
    # Apply safety margins
    energy_trx = (energy_needed / energy_per_trx) * 1.05
    bandwidth_trx = (bandwidth_needed / bandwidth_per_trx) * 1.05
    
    return {
        'energy_delegation_frozen_trx': energy_trx,
        'bandwidth_delegation_frozen_trx': bandwidth_trx,
        'total_trx_frozen': energy_trx + bandwidth_trx
    }
```

### Step 5: Wallet Analysis

```python
def analyze_wallets(activation_cost, delegation_costs):
    """Analyze signer and gas wallet capabilities"""
    
    # Signer wallet analysis
    signer_resources = get_account_resources(signer_address)
    signer_bandwidth_ok = signer_resources.get('bandwidth', 0) >= 540  # ~2-3 TXs
    
    # Gas wallet analysis  
    gas_resources = get_account_resources(gas_wallet_address)
    total_cost = activation_cost + delegation_costs['total_trx_frozen']
    gas_balance_ok = gas_resources.get('balance_trx', 0) >= total_cost
    
    return {
        'signer_sufficient_bandwidth': signer_bandwidth_ok,
        'gas_wallet_sufficient_balance': gas_balance_ok,
        'total_trx_sent': activation_cost,  # Leaves wallet
        'total_trx_frozen': delegation_costs['total_trx_frozen'],  # Locked in wallet
        'total_balance_impact': total_cost
    }
```

## Key Concepts

### Delegation Mechanics
- **TRX Freezing**: TRX stays in wallet but becomes locked
- **Not Burning**: Frozen TRX can be unfrozen later
- **Duration**: Minimum 3-day lock period

### Wallet Roles
- **Signer**: Authorizes operations, needs bandwidth for signing
- **Gas Wallet**: Provides TRX, freezes for delegation, pays activation
- **Destination**: Receives activation TRX and delegated resources

### Cost Structure
```
Total Operation Cost = Activation TRX (sent) + Delegation TRX (frozen)
```

### Network Differences
- **Testnet**: 1.0 TRX activation, adjusted bandwidth yields
- **Mainnet**: 1.5 TRX activation, live network parameters

## Testing Example

```python
# Test with fresh address
result = dry_run_prepare_for_sweep("TRjSYTUmXJByV1vDeWTrqXCRECnqDquatH", 1.0)

# Expected results:
assert result['activation_needed'] == True
assert result['energy_needed'] > 1000  # Smart contract simulation
assert result['total_trx_sent'] == 1.0  # Testnet activation
assert result['total_trx_frozen'] > 50  # Delegation costs
assert result['feasible'] == True  # If wallets have sufficient resources
```

## Common Issues

1. **Low Bandwidth Yields on Testnet**: Use 200/TRX adjustment
2. **Fresh Address Simulation**: Use gas wallet as proxy with penalty
3. **Insufficient Signer Bandwidth**: Need ~540 points for 2-3 TXs
4. **Gas Wallet Balance**: Must cover activation + delegation costs
5. **Network Parameter Fetch Failure**: Use config fallbacks

## Configuration

```python
NETWORK_CONFIG = {
    'testnet': {
        'activation_cost': 1.0,
        'bandwidth_yield_min': 200,
        'energy_safety_margin': 1.05
    },
    'mainnet': {
        'activation_cost': 1.5,
        'bandwidth_yield_min': 50,
        'energy_safety_margin': 1.05
    }
}
```

This implementation provides accurate resource estimation and cost calculation for TRON operations using modern smart contract simulation and proper delegation mechanics understanding.
