# TRON Gas-Free System - Quick Reference

## 🚀 How It Works

The gas-free system automatically provides energy and bandwidth to user addresses for free USDT transfers using:

1. **Estimation-Based Calculation**: Real-time simulation determines exact resource needs
2. **Permission-Based Security**: Signer authorizes gas wallet transactions without exposing keys
3. **Network Adaptation**: Adjusts to mainnet/testnet differences automatically
4. **Fast Verification**: 5-second confirmation using 0.5s intervals

## 🧮 Key Formulas

### Energy Calculation
```
Simulation Energy: ~1,817 (for existing USDT holders)
Safety Buffer: simulation_result + 5,000
TRX Required: energy_needed / 2.38
Example: 6,817 energy ÷ 2.38 = 2,864 TRX
```

### Network Ratios (August 2025)
- **Energy per TRX**: 2.38 (100B daily energy / 42B frozen TRX)
- **Bandwidth per TRX**: 1,500 (conservative estimate)
- **Activation Bonus**: 600 bandwidth (automatic)

## 🔐 Security Architecture

```
Gas Wallet (Resources) → Signer (Authorization) → Target Address (Recipient)
```

- **Gas Wallet**: Holds TRX, cannot initiate transactions
- **Signer**: Authorizes with Permission ID 2, no direct resources
- **Separation**: No gas wallet private key on server

## ⚡ Quick API Usage

```python
# Initialize
gas_station = GasStationManager()

# Prepare address for USDT
result = gas_station.intelligent_prepare_address_for_usdt("TYourAddressHere")

# Check result
if result['success']:
    print(f"Address ready! Strategy: {result['strategy']}")
    print(f"Time: {result['execution_time']:.3f}s")
```

## 🎯 Success Criteria

Address is ready when:
- ✅ **Activated**: Address exists on TRON network
- ✅ **Energy**: ≥15,000 units (conservative minimum)
- ✅ **Bandwidth**: ≥300 units (transaction minimum)

## 🔧 Configuration

```bash
# Required
export SIGNER_WALLET_PRIVATE_KEY=your_hex_key

# Optional
export GAS_WALLET_ADDRESS=THpjvxomBhvZUodJ3FHFY1szQxAidxejy8
export TRON_NODE_URL=http://192.168.86.154:8090
```

## 📊 Performance Metrics

- **Typical Energy**: 6,817 units (simulation-based)
- **Typical TRX**: 2,864 TRX (efficient allocation)
- **Execution Time**: ~5 seconds (including verification)
- **Success Rate**: >95% (with proper configuration)

## 🐛 Common Issues

| Issue | Cause | Solution |
|-------|-------|----------|
| "No signer available" | Missing env var | Set `SIGNER_WALLET_PRIVATE_KEY` |
| Permission denied | Signer lacks access | Verify Permission ID 2 setup |
| Verification timeout | Network delay | Resources likely allocated despite timeout |
| Insufficient resources | Gas wallet low | Top up gas wallet TRX/energy |

## 📈 Resource Requirements by Type

| Recipient Type | Energy Needed | TRX Required | Use Case |
|---------------|---------------|--------------|----------|
| Existing USDT | ~6,817 | ~2,864 | Regular users |
| New USDT | ~65,000 | ~27,310 | First-time recipients |
| Minimal | ~32,000 | ~13,445 | Conservative fallback |

## 🔍 Quick Verification

```python
# Check if address is ready
def verify_ready(address):
    resources = gas_station._get_account_resources(address)
    activated = gas_station._check_address_exists(address)
    
    energy_ok = resources.get('energy_available', 0) >= 15000
    bandwidth_ok = resources.get('bandwidth_available', 0) >= 300
    
    return activated and energy_ok and bandwidth_ok
```

For complete details, see [GASFREE_SYSTEM_DOCUMENTATION.md](./GASFREE_SYSTEM_DOCUMENTATION.md)
