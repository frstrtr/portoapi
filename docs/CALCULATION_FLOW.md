# TRON Resource Calculation Flow

## Executive Summary

The `comprehensive_resource_calculation_and_cost_estimation()` function calculates precise resource requirements and costs for TRON USDT operations using modern techniques:

- **Smart contract simulation** for realistic energy estimation
- **Live network parameters** for accurate TRX-to-resource yields  
- **Proper delegation mechanics** understanding (freeze vs burn)
- **Comprehensive wallet orchestration** between signer and gas wallets

## Calculation Flow Diagram

```
Input: destination_address, amount_usdt
    ↓
┌─────────────────────────────────────┐
│ 1. Address Analysis                 │
│ • check_address_existence()         │
│ • analyze_current_resources()       │
│ • determine_usdt_holder_status()    │
└─────────────────────────────────────┘
    ↓
┌─────────────────────────────────────┐
│ 2. Smart Contract Simulation       │
│ • simulate_usdt_transfer()          │
│ • use_gas_wallet_as_proxy()         │
│ • get_realistic_energy_usage()     │
└─────────────────────────────────────┘
    ↓
┌─────────────────────────────────────┐
│ 3. Live Network Parameters         │
│ • fetch_current_yields()            │
│ • apply_network_adjustments()       │
│ • calculate_trx_freezing_costs()    │
└─────────────────────────────────────┘
    ↓
┌─────────────────────────────────────┐
│ 4. Wallet Analysis                 │
│ • check_signer_bandwidth()          │
│ • verify_gas_wallet_balance()       │
│ • assess_operation_feasibility()    │
└─────────────────────────────────────┘
    ↓
Output: Complete resource & cost analysis
```

## Key Formulas

### Energy Calculation
```python
# Smart contract simulation (primary)
energy_needed = simulate_usdt_transfer_and_get_energy_cost(address, usdt_contract, amount)

# Fallback estimation based on address analysis and network
# Values from config: USDT_ENERGY_PER_TRANSFER_ESTIMATE (default: 14,650)
# But implementation uses different values based on recipient type:
energy_needed = 65_000 if is_new_usdt_holder else 32_000  # Network-agnostic TRON values

# NOTES ON ENERGY VALUES:
# - 65,000: New USDT holders (fresh addresses, contract state initialization required)
# - 32,000: Existing USDT holders (addresses with USDT history, lower energy)
# - Threshold: 50,000 energy divides categories (< 50k = existing, ≥ 50k = new)
# - Source: Empirical TRON network observations, same for testnet/mainnet
# - Detection: Smart contract simulation determines actual category
# - Override: Implementation dynamically chooses 32k/65k, ignoring config default

# Convert energy to TRX freezing requirement
energy_trx = (energy_needed / get_current_energy_yield_per_trx()) * 1.05  # 5% safety margin
```

### Bandwidth Calculation
```python
# Calculate exact transaction size and bandwidth requirement
bandwidth_needed = calculate_transaction_size_in_bytes(address, usdt_contract, amount)

# Convert bandwidth to TRX freezing requirement
bandwidth_trx = (bandwidth_needed / get_current_bandwidth_yield_per_trx()) * 1.05
```

### Total Cost Structure
```python
activation_cost = get_network_activation_cost()  # 1.0 TRX testnet, 1.5 TRX mainnet
delegation_cost = energy_trx + bandwidth_trx  # TRX frozen in gas wallet for delegation
total_impact = activation_cost + delegation_cost  # Total balance unavailability
```

## Wallet Orchestration

### Role Distribution
- **Signer Wallet**: Signs transactions, authorizes delegation (needs ~540 bandwidth)
- **Gas Wallet**: Provides TRX, freezes for delegation, pays activation
- **Destination**: Receives activation TRX and delegated resources

### Transaction Sequence
1. send_activation_trx_to_fresh_address(gas_wallet, destination) // if address doesn't exist
2. freeze_trx_and_delegate_energy(gas_wallet, destination, energy_amount)
3. freeze_trx_and_delegate_bandwidth(gas_wallet, destination, bandwidth_amount) // if needed
4. authorize_all_operations_via_permission(signer_wallet, gas_wallet, permission_id_2)

## Network Awareness

### Live Parameter Fetching
```python
# Fetch current network resource yields from blockchain
energy_per_trx = fetch_sun_per_energy_from_network() / 1_000_000  # Convert SUN to TRX
bandwidth_per_trx = fetch_sun_per_bandwidth_from_network() / 1_000_000

# Apply testnet reality adjustments
if detect_network_is_testnet() and bandwidth_per_trx < 50:
    bandwidth_per_trx = 200  # Use reasonable testnet value
```

### Network-Specific Settings
- **Testnet**: 1.0 TRX activation, bandwidth yield adjustments
- **Mainnet**: 1.5 TRX activation, live parameter usage

## Example Calculation

For fresh address `TRjSYTUmXJByV1vDeWTrqXCRECnqDquatH`:

### Input
- Destination: Fresh address (doesn't exist)
- Amount: 1.0 USDT transfer

### Calculation Steps
1. **Address Analysis**: check_if_address_exists() → determine_activation_required()
2. **Smart Simulation**: simulate_contract_call_via_proxy() → get_realistic_energy_usage()
3. **Network Parameters**: fetch_live_yields() → apply_network_adjustments()
4. **Resource Requirements**: calculate_total_energy_and_bandwidth_needs()
5. **Cost Calculation**:
   - Activation: get_network_activation_cost() (sent)
   - Energy delegation: convert_energy_to_trx_freeze_amount() (frozen)  
   - Bandwidth delegation: convert_bandwidth_to_trx_freeze_amount() (frozen)
   - **Total impact**: sum_all_trx_costs()

### Result
```
✅ Operation Feasible
💰 Total Cost: 94.832 TRX (1.0 sent + 93.832 frozen)
⚡ Energy: 6,817 needed (realistic simulation)
📶 Bandwidth: 337 needed (precise calculation)
🔐 Signer: Sufficient bandwidth for signing
⛽ Gas Wallet: Sufficient balance (7,897 TRX available)
```

## Critical Understanding: Delegation Mechanics

### TRX Freezing (Not Burning)
- **Frozen TRX**: Remains in wallet but locked/unavailable
- **Duration**: Minimum 3-day lock period
- **Reversible**: Can be unfrozen after delegation expires
- **Ownership**: Wallet retains ownership throughout

### Cost Impact Analysis
```
TRX Sent (leaves wallet): 1.000 TRX      ← Permanent transfer
TRX Frozen (locked in wallet): 93.832 TRX ← Temporary lock
Total Balance Impact: 94.832 TRX          ← Immediate unavailability
```

## Implementation Benefits

1. **Accurate Estimates**: Smart contract simulation provides realistic energy usage
2. **Network Adaptive**: Live parameters ensure current yield calculations
3. **Cost Transparency**: Clear breakdown of sent vs frozen TRX
4. **Feasibility Checking**: Validates wallet capabilities before operations
5. **Fresh Address Support**: Proxy simulation handles non-existent addresses

This comprehensive calculation system enables confident operational planning with precise resource requirements and cost predictions for TRON USDT operations.

## Energy Estimation System Notes

### Energy Value Sources and Logic

**Primary Method: Smart Contract Simulation**
- Uses `estimate_usdt_energy_precise()` for real-time energy calculation
- Simulates actual USDT transfer calls to get precise energy usage
- Typically returns 1,000-2,000 energy for realistic operations

**Fallback Method: Category-Based Estimation**
When simulation fails, the system uses empirical TRON network observations:

| Recipient Type | Energy Needed | Source | Network |
|----------------|---------------|---------|---------|
| New USDT Holder | 65,000 | Contract state initialization | Both testnet/mainnet |
| Existing USDT Holder | 32,000 | Account update only | Both testnet/mainnet |

**Detection Logic:**
```python
# From gas_station.py implementation
recipient_has_usdt = energy_used < 50000 if energy_used > 0 else None
```
- **Threshold**: 50,000 energy divides categories
- **< 50,000**: Existing USDT holder (lower energy needs)
- **≥ 50,000**: New USDT holder (contract initialization required)

**Configuration vs Implementation:**
- **Config Default**: `USDT_ENERGY_PER_TRANSFER_ESTIMATE=14650`
- **Implementation Override**: Dynamically chooses 32,000 or 65,000
- **Reason**: Category-based estimation more accurate than single static value

**Network Relationship:**
- **Energy costs**: Network-agnostic (same for testnet/mainnet)
- **Smart contract mechanics**: Determined by TRON protocol, not network type
- **Only activation varies**: 1.0 TRX (testnet) vs 1.5 TRX (mainnet)

**Fresh Address Handling:**
- Fresh addresses assumed to be new USDT holders
- Uses gas wallet proxy simulation with 20% penalty
- Defaults to 65,000 energy category if simulation unavailable
