# TRON Resource Calculation System Documentation

## Overview

This documentation explains the comprehensive resource calculation system implemented in `dry_run_prepare_for_sweep()` function for TRON USDT operations.

## System Architecture

The system orchestrates three types of wallets to execute USDT transfers efficiently:

**Signer Wallet** → Signs transactions, provides authorization  
**Gas Wallet** → Provides TRX for costs, freezes for delegation  
**Destination** → Receives resources and activation (if needed)

## Core Calculation Process

### 1. Address Analysis
Determines if destination address exists and needs activation:
- Fresh addresses require 1.0 TRX (testnet) or 1.5 TRX (mainnet) activation
- Existing addresses analyzed for current resource state

### 2. Smart Contract Simulation
Calculates precise energy requirements using live contract simulation:
- Direct simulation for existing addresses
- Proxy simulation via gas wallet for fresh addresses
- Realistic energy usage (typically 1,000-2,000 for USDT transfers)

### 3. Live Network Parameter Fetching
Retrieves current resource yields from TRON network:
- Energy yield: typically 60-80 energy per TRX
- Bandwidth yield: network-specific with testnet adjustments
- Real-time parameters ensure accurate cost calculations

### 4. Resource-to-TRX Conversion
Converts resource needs to TRX freezing requirements:
- Energy delegation cost = energy_needed / energy_per_trx * 1.05
- Bandwidth delegation cost = bandwidth_needed / bandwidth_per_trx * 1.05
- Safety margins prevent insufficient resource errors

### 5. Wallet Capability Analysis
Validates both wallets can support the operation:
- Signer wallet: Must have ~540 bandwidth for transaction signing
- Gas wallet: Must have sufficient TRX for activation + delegation costs

## Key Understanding: TRX Delegation Mechanics

**Critical Point**: TRON delegation uses TRX freezing, NOT burning.

**Frozen TRX:**
- Remains in wallet but becomes locked/unavailable
- Can be unfrozen after minimum 3-day delegation period
- Wallet retains ownership throughout delegation

**Cost Structure:**
- TRX Sent: Leaves wallet permanently (activation only)
- TRX Frozen: Locked in wallet temporarily (delegation)
- Total Impact: Immediate balance unavailability

## Network-Specific Considerations

**Testnet:**
- Activation cost: 1.0 TRX
- Bandwidth yield adjustments (often unrealistic low values)
- Adjusted to 200 bandwidth/TRX for reasonable calculations

**Mainnet:**
- Activation cost: 1.5 TRX
- Live network parameters used directly
- Higher resource costs but more stable yields

## Implementation Example

For a fresh address requiring USDT transfer capability:

**Input:** Fresh address, 1.0 USDT amount  
**Analysis:** Address doesn't exist → activation needed  
**Simulation:** 1,817 energy via smart contract simulation  
**Parameters:** 76.28 energy/TRX, 200 bandwidth/TRX (testnet)  
**Costs:**
- Activation: 1.000 TRX (sent to address)
- Energy delegation: ~94 TRX (frozen in gas wallet)
- Total impact: ~95 TRX

**Result:** Operation feasible if gas wallet has sufficient balance

## Key Benefits

1. **Precision**: Smart contract simulation provides realistic energy estimates
2. **Adaptability**: Live network parameters ensure current accuracy
3. **Transparency**: Clear breakdown of sent vs frozen TRX costs
4. **Reliability**: Comprehensive validation prevents operation failures
5. **Efficiency**: Proper wallet orchestration minimizes resource waste

## Configuration

**Safety Margins:**
- Energy: 5% additional
- Bandwidth: 5% additional
- Fresh addresses: 20% penalty for simulation uncertainty

**Network Settings:**
- Testnet activation: 1.0 TRX
- Mainnet activation: 1.5 TRX
- Delegation lock period: 3 days minimum

This system enables confident operational planning with accurate resource predictions and proper cost understanding for TRON USDT operations.
