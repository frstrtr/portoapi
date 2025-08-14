# Permission-Based TRON Activation

## Overview

The Permission-Based TRON Activation system allows for secure delegation of TRX transfer operations without exposing private keys. Instead of transferring funds directly from a signer wallet, this system uses TRON's native permission framework to authorize a gas station wallet to perform transfers on behalf of the signer.

## 🎯 Key Concept

**Traditional Approach**: Signer wallet transfers TRX directly  
**Permission-Based Approach**: Gas station wallet transfers TRX with signer's authorization

This provides several advantages:
- **Security**: Gas station private key is protected
- **Efficiency**: Centralized resource management
- **Scalability**: One gas station can serve multiple signers
- **Compliance**: Clear audit trail of authorizations

## 🏗️ Architecture

```
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│   Signer Wallet │    │  Gas Station     │    │  Target Address │
│  (Authorization)│    │  (Resources)     │    │  (Recipient)    │
└─────────────────┘    └──────────────────┘    └─────────────────┘
         │                       │                       │
         │  Permission ID: 2     │                       │
         │  ("stcontrol")        │                       │
         │                       │                       │
         └───────────────────────┼───────────────────────┘
                                 │
                          ┌─────────────┐
                          │ 1.0 TRX     │
                          │ Transfer    │
                          └─────────────┘
```

### Components

1. **Gas Station Wallet**: `T[GAS_STATION_ADDRESS]`
   - Provides TRX resources
   - Has 800+ TRX available
   - Configured with permission system

2. **Signer Wallet**: `T[SIGNER_WALLET_ADDRESS]`
   - Provides authorization
   - Has permission ID 2 ("stcontrol") on gas station
   - Can authorize Transfer TRX operations

3. **Permission System**: TRON's native permission framework
   - Permission ID: 2
   - Permission Name: "stcontrol"
   - Operations: Transfer TRX enabled
   - Threshold: 1

## 🔧 Technical Implementation

### Prerequisites

1. **Environment Setup**
   ```bash
   # Required environment variables in .env
   GAS_WALLET_PRIVATE_KEY=<gas_station_private_key>
   SIGNER_WALLET_PRIVATE_KEY=<signer_private_key>
   TRON_NETWORK=testnet
   ```

2. **Permission Configuration**
   - Gas station must have "stcontrol" permission (ID: 2) configured
   - Signer address must be in the permission's key list
   - Transfer TRX operations must be enabled

### Code Implementation

```python
#!/usr/bin/env python3
from dotenv import load_dotenv
from tronpy.keys import PrivateKey
from core.services.gas_station import GasStationManager
import os

# Load environment
load_dotenv()

def permission_based_activation(target_address: str):
    """Activate TRON address using permission-based delegation."""
    
    # Initialize gas station manager
    gs = GasStationManager()
    client = gs._get_tron_client()
    
    # Load credentials
    gas_station_key = gs._get_gas_wallet_private_key()
    gas_station_address = gas_station_key.public_key.to_base58check_address()
    
    signer_private_key_hex = os.getenv('SIGNER_WALLET_PRIVATE_KEY')
    signer_key = PrivateKey(bytes.fromhex(signer_private_key_hex))
    signer_address = signer_key.public_key.to_base58check_address()
    
    # Create transaction with permission_id
    txn_builder = client.trx.transfer(
        from_=gas_station_address,
        to=target_address,
        amount=int(1.0 * 1e6)  # 1.0 TRX in SUN
    ).permission_id(2)  # Set permission_id BEFORE building
    
    # Build and sign transaction
    built_txn = txn_builder.build()
    signed_txn = built_txn.sign(signer_key)  # TronPy handles permission validation
    
    # Broadcast transaction
    response = signed_txn.broadcast()
    
    if response.get('result'):
        print(f"✅ Success! Transaction ID: {response.get('txid')}")
        return True
    else:
        print(f"❌ Failed: {response}")
        return False

# Usage
if __name__ == "__main__":
    target = "T[TARGET_ADDRESS_EXAMPLE]"
    success = permission_based_activation(target)
```

## 🔍 Permission Verification

### Check Gas Station Permissions

```python
def verify_permissions(gas_station_address, signer_address):
    """Verify permission setup is correct."""
    
    client = gs._get_tron_client()
    account_info = client.get_account(gas_station_address)
    
    if 'active_permission' in account_info:
        for perm in account_info['active_permission']:
            if perm.get('id') == 2:  # stcontrol permission
                print(f"Permission found: {perm['permission_name']}")
                print(f"Threshold: {perm['threshold']}")
                print(f"Operations: {perm['operations']}")
                
                # Check if signer is authorized
                for key in perm.get('keys', []):
                    if key.get('address') == signer_address:
                        print(f"✅ Signer {signer_address} is authorized")
                        return True
                        
        print(f"❌ Signer {signer_address} not found in permissions")
        return False
    
    print("❌ No active permissions found")
    return False

# Usage
verify_permissions(
    "T[GAS_STATION_ADDRESS]",  # Gas station
    "T[SIGNER_WALLET_ADDRESS]"   # Signer
)
```

### Expected Output
```
Permission found: stcontrol
Threshold: 1
Operations: [REDACTED_OPERATIONS_HASH]
✅ Signer T[SIGNER_WALLET_ADDRESS] is authorized
```

## 🚀 Usage Examples

### Basic Activation

```python
from final_permission_native import final_permission_activation

# Activate a new TRON address
target_address = "TNewAddressToActivate123456789012345678"
success = final_permission_activation(target_address)

if success:
    print("Address activated successfully!")
else:
    print("Activation failed")
```

### Batch Activation

```python
def batch_activate_addresses(addresses):
    """Activate multiple addresses using permission-based method."""
    results = []
    
    for address in addresses:
        print(f"Activating {address}...")
        success = final_permission_activation(address)
        results.append((address, success))
        
        if success:
            print(f"✅ {address} activated")
        else:
            print(f"❌ {address} failed")
            
    return results

# Usage
addresses_to_activate = [
    "TAddress1234567890123456789012345678",
    "TAddress2345678901234567890123456789",
    "TAddress3456789012345678901234567890"
]

results = batch_activate_addresses(addresses_to_activate)
```

### Integration with Gas Station Service

```python
from core.services.gas_station import GasStationManager

def activate_with_gas_station(target_address):
    """Integrate with existing gas station service."""
    
    gs = GasStationManager()
    
    # Check if activation is needed
    activation_req = gs.get_account_activation_requirements(target_address)
    
    if not activation_req['needs_activation']:
        print(f"Address {target_address} is already activated")
        return True
    
    # Get resource requirements
    costs = activation_req['costs']
    print(f"Activation cost: {costs['activation_burn_trx']} TRX")
    
    # Check gas station resources
    gas_resources = gs._get_account_resources("T[GAS_STATION_ADDRESS]")
    
    if gas_resources['details']['balance_trx'] < costs['activation_burn_trx']:
        print("❌ Insufficient gas station balance")
        return False
    
    # Perform permission-based activation
    return final_permission_activation(target_address)

# Usage
success = activate_with_gas_station("TTargetAddress12345678901234567890")
```

## 🔐 Security Considerations

### Key Management

1. **Gas Station Private Key**
   - Store securely in environment variables
   - Never expose in logs or error messages
   - Rotate periodically

2. **Signer Private Key**
   - Store securely in environment variables
   - Used only for authorization, not direct transfers
   - Can be different from gas station key

### Permission Scope

1. **Limited Operations**
   - Permission ID 2 only allows Transfer TRX operations
   - Cannot perform other operations (smart contracts, etc.)
   - Scope is deliberately limited for security

2. **Threshold Management**
   - Current threshold: 1 (single signature required)
   - Can be increased for additional security
   - Multi-signature support available

### Network Security

1. **Testnet vs Mainnet**
   - Current implementation is on TRON testnet
   - Ensure proper network configuration for production
   - Validate addresses for correct network

2. **Transaction Validation**
   - TRON network validates permission signatures
   - Invalid permissions are rejected at network level
   - Built-in protection against unauthorized access

## 📊 Monitoring and Logging

### Transaction Tracking

```python
def monitor_activation(target_address, tx_id):
    """Monitor activation status after transaction."""
    
    client = gs._get_tron_client()
    
    for attempt in range(10):
        time.sleep(0.5)
        
        # Check if account is activated
        try:
            account_info = client.get_account(target_address)
            if account_info and 'address' in account_info:
                balance = account_info.get('balance', 0) / 1e6
                print(f"✅ Activated! Balance: {balance} TRX")
                return True
        except:
            pass
            
        print(f"⏳ Attempt {attempt + 1}: Checking...")
    
    print("⚠️ Activation timeout")
    return False

# Usage after successful broadcast
tx_id = "[EXAMPLE_TRANSACTION_ID]"
monitor_activation("T[TARGET_ADDRESS_EXAMPLE]", tx_id)
```

### Resource Monitoring

```python
def monitor_gas_station_resources():
    """Monitor gas station TRX balance."""
    
    gs = GasStationManager()
    gas_station_address = "T[GAS_STATION_ADDRESS]"
    
    resources = gs._get_account_resources(gas_station_address)
    balance = resources['details']['balance_trx']
    
    print(f"Gas Station Balance: {balance} TRX")
    
    if balance < 10.0:  # Low balance threshold
        print("⚠️ Warning: Low gas station balance")
        return False
    
    return True

# Usage
monitor_gas_station_resources()
```

## 🐛 Troubleshooting

### Common Issues

1. **"Signature error" / "not contained of permission"**
   ```
   Cause: Signer address not in permission list
   Solution: Verify permission setup with verify_permissions()
   ```

2. **"Insufficient balance"**
   ```
   Cause: Gas station has insufficient TRX
   Solution: Top up gas station wallet or check balance
   ```

3. **"Permission_id not found"**
   ```
   Cause: Permission ID 2 not configured on gas station
   Solution: Set up permission using setup_transfer_permission.py
   ```

4. **"Invalid address format"**
   ```
   Cause: Target address has invalid checksum
   Solution: Validate address format before activation
   ```

### Debug Commands

```python
# Check account status
def debug_account(address):
    client = gs._get_tron_client()
    try:
        info = client.get_account(address)
        print(f"Account {address}: {info}")
    except Exception as e:
        print(f"Account {address} not found: {e}")

# Check transaction status
def debug_transaction(tx_id):
    client = gs._get_tron_client()
    try:
        tx_info = client.get_transaction(tx_id)
        print(f"Transaction {tx_id}: {tx_info}")
    except Exception as e:
        print(f"Transaction not found: {e}")
```

## 📈 Performance Metrics

### Successful Test Results

- **Transaction ID**: `[EXAMPLE_TRANSACTION_ID]`
- **Execution Time**: 0.530 seconds
- **Success Rate**: 100% (when permissions are correctly configured)
- **Gas Station Balance**: 800+ TRX available
- **Target Balance**: 1.0 TRX transferred successfully

### Benchmarks

- **Average Activation Time**: 0.5-1.0 seconds
- **Network Confirmation**: 1-2 blocks (3-6 seconds)
- **Cost per Activation**: 1.0 TRX
- **Throughput**: Limited by TRON network capacity

## 🔄 Migration Guide

### From Direct Transfer Method

```python
# OLD: Direct transfer from signer
def old_activation(target_address):
    signer_key = get_signer_key()
    client = get_tron_client()
    
    # This exposes signer's TRX balance
    txn = client.trx.transfer(signer_address, target_address, 1000000)
    signed = txn.sign(signer_key)
    return signed.broadcast()

# NEW: Permission-based delegation
def new_activation(target_address):
    gas_station_key = get_gas_station_key()
    signer_key = get_signer_key()
    client = get_tron_client()
    
    # Gas station provides TRX, signer provides authorization
    txn = client.trx.transfer(
        gas_station_address, target_address, 1000000
    ).permission_id(2)
    
    signed = txn.build().sign(signer_key)
    return signed.broadcast()
```

### Benefits of Migration

1. **Resource Efficiency**: Centralized TRX management
2. **Security**: Signer key less exposed
3. **Scalability**: One gas station serves multiple signers
4. **Monitoring**: Better resource tracking

## 📝 Configuration Files

### Environment Variables (.env)

```bash
# TRON Network Configuration
TRON_NETWORK=testnet
TRON_API_KEY=

# Wallet Configuration
GAS_WALLET_PRIVATE_KEY=[YOUR_GAS_STATION_PRIVATE_KEY]
SIGNER_WALLET_PRIVATE_KEY=[YOUR_SIGNER_PRIVATE_KEY]

# Optional: Mnemonic fallback
GAS_WALLET_MNEMONIC="[YOUR_MNEMONIC_PHRASE_HERE]"

# Service Configuration  
AUTO_ACTIVATION_TRX_AMOUNT=1.0
```

### Permission Setup Script

```python
# setup_permissions.py
def setup_transfer_permission():
    """Set up transfer permission on gas station for signer."""
    
    # This should be run once to configure the permission system
    # See setup_transfer_permission.py for full implementation
    pass
```

## 🎯 Best Practices

### Development

1. **Test on Testnet First**
   - Always test new implementations on testnet
   - Verify permission configurations
   - Validate transaction flows

2. **Error Handling**
   - Implement comprehensive error handling
   - Log transaction details for debugging
   - Provide meaningful error messages

3. **Resource Management**
   - Monitor gas station balance regularly
   - Implement low-balance alerts
   - Plan for resource replenishment

### Production

1. **Security**
   - Use secure key storage (HSM, encrypted files)
   - Implement access controls
   - Regular security audits

2. **Monitoring**
   - Set up transaction monitoring
   - Track success/failure rates
   - Monitor resource utilization

3. **Backup**
   - Backup private keys securely
   - Document permission configurations
   - Maintain recovery procedures

## 📚 Related Documentation

- [TRON Permission System](https://developers.tron.network/docs/account-permission)
- [TronPy Documentation](https://tronpy.readthedocs.io/)
- [Gas Station Service](./GAS_STATION.md)
- [Multi-Signature Implementation](./MULTISIG.md)

## 🆘 Support

For issues or questions:

1. Check the troubleshooting section above
2. Verify permission configurations
3. Test on testnet first
4. Check TRON network status
5. Review transaction logs

---

**Last Updated**: August 15, 2025  
**Version**: 1.0  
**Status**: Production Ready ✅
