"""
Gas Station Utilities
Helper functions for gas station operations
"""

import logging
from typing import Dict, List, Tuple
from decimal import Decimal

logger = logging.getLogger(__name__)


def calculate_transaction_costs(transaction_count: int) -> Dict[str, int]:
    """
    Calculate resource costs for USDT transactions
    
    Args:
        transaction_count: Number of USDT transactions
        
    Returns:
        Dict with energy and bandwidth costs
    """
    # Standard costs based on network analysis
    ENERGY_PER_USDT_TX = 31_895
    BANDWIDTH_PER_TX = 345
    
    return {
        'energy_needed': transaction_count * ENERGY_PER_USDT_TX,
        'bandwidth_needed': transaction_count * BANDWIDTH_PER_TX,
        'transaction_count': transaction_count
    }


def calculate_staking_efficiency(staked_amount: float, resource_limit: int, resource_type: str) -> float:
    """
    Calculate staking efficiency percentage
    
    Args:
        staked_amount: Amount of TRX staked
        resource_limit: Current resource limit
        resource_type: 'energy' or 'bandwidth'
        
    Returns:
        Efficiency percentage (0-100)
    """
    if staked_amount <= 0:
        return 0.0
    
    # Expected resource per TRX based on TRON Staking 2.0
    if resource_type.lower() == 'energy':
        expected_per_trx = 32_000  # Energy units per TRX
    elif resource_type.lower() == 'bandwidth':
        expected_per_trx = 1_000   # Bandwidth units per TRX
    else:
        raise ValueError(f"Unknown resource type: {resource_type}")
    
    expected_total = staked_amount * expected_per_trx
    
    if expected_total <= 0:
        return 0.0
    
    efficiency = (resource_limit / expected_total) * 100
    return min(efficiency, 100.0)  # Cap at 100%


def estimate_daily_operations(energy_limit: int, bandwidth_limit: int, balance: float, activation_cost: float) -> Dict:
    """
    Estimate daily operational capacity
    
    Args:
        energy_limit: Daily energy limit
        bandwidth_limit: Daily bandwidth limit  
        balance: Available TRX balance
        activation_cost: Cost per account activation
        
    Returns:
        Dict with operational estimates
    """
    costs = calculate_transaction_costs(1)
    
    # Calculate transaction capacity
    energy_tx_capacity = energy_limit // costs['energy_needed'] if energy_limit > 0 else 0
    bandwidth_tx_capacity = bandwidth_limit // costs['bandwidth_needed'] if bandwidth_limit > 0 else 0
    activation_capacity = int(balance / activation_cost) if activation_cost > 0 else 0
    
    # Find bottleneck
    daily_tx_capacity = min(energy_tx_capacity, bandwidth_tx_capacity)
    bottleneck = 'energy' if energy_tx_capacity < bandwidth_tx_capacity else 'bandwidth'
    
    return {
        'daily_usdt_transactions': daily_tx_capacity,
        'account_activations': activation_capacity,
        'bottleneck': bottleneck,
        'energy_capacity': energy_tx_capacity,
        'bandwidth_capacity': bandwidth_tx_capacity,
        'utilization': {
            'energy_per_tx': costs['energy_needed'],
            'bandwidth_per_tx': costs['bandwidth_needed']
        }
    }


def analyze_resource_needs(target_daily_transactions: int, target_activations: int, activation_cost: float) -> Dict:
    """
    Analyze resource requirements for target operations
    
    Args:
        target_daily_transactions: Target daily USDT transactions
        target_activations: Target account activations
        activation_cost: Cost per activation
        
    Returns:
        Dict with resource requirements
    """
    # Calculate transaction resource needs
    tx_costs = calculate_transaction_costs(target_daily_transactions)
    
    # Calculate staking requirements (assuming perfect efficiency)
    energy_trx_needed = tx_costs['energy_needed'] / 32_000
    bandwidth_trx_needed = tx_costs['bandwidth_needed'] / 1_000
    
    # Calculate balance needed for activations
    balance_needed = target_activations * activation_cost
    
    return {
        'requirements': {
            'energy_stake_trx': energy_trx_needed,
            'bandwidth_stake_trx': bandwidth_trx_needed,
            'balance_trx': balance_needed,
            'total_trx': energy_trx_needed + bandwidth_trx_needed + balance_needed
        },
        'targets': {
            'daily_transactions': target_daily_transactions,
            'account_activations': target_activations
        },
        'resource_breakdown': {
            'daily_energy_needed': tx_costs['energy_needed'],
            'daily_bandwidth_needed': tx_costs['bandwidth_needed']
        }
    }


def format_resource_status(resources: Dict) -> str:
    """
    Format resource status for display
    
    Args:
        resources: Resource status dict
        
    Returns:
        Formatted status string
    """
    try:
        lines = []
        lines.append(f"💰 Balance: {resources['balance']:,.2f} TRX")
        lines.append(f"🔒 Staked: {resources['total_staked']:,.0f} TRX")
        
        lines.append(f"⚡ Energy: {resources['energy']['available']:,}/{resources['energy']['limit']:,} units")
        lines.append(f"📡 Bandwidth: {resources['bandwidth']['available']:,}/{resources['bandwidth']['limit']:,} units")
        
        return "\n".join(lines)
        
    except KeyError as e:
        return f"Error formatting resources: Missing key {e}"


def validate_gas_station_config(config) -> Tuple[bool, List[str]]:
    """
    Validate gas station configuration
    
    Args:
        config: Configuration object
        
    Returns:
        Tuple of (is_valid, error_messages)
    """
    errors = []
    
    # Check private key
    if not hasattr(config, 'gas_wallet_private_key') or not config.gas_wallet_private_key:
        errors.append("Gas wallet private key not configured")
    elif len(config.gas_wallet_private_key) != 64:
        errors.append("Gas wallet private key should be 64 characters (32 bytes hex)")
    
    # Check network
    if not hasattr(config, 'network') or config.network not in ['mainnet', 'testnet']:
        errors.append("Network must be 'mainnet' or 'testnet'")
    
    # Check activation cost
    if not hasattr(config, 'auto_activation_trx_amount') or config.auto_activation_trx_amount <= 0:
        errors.append("Auto activation TRX amount must be positive")
    
    # Check USDT contracts
    if config.network == 'testnet' and not hasattr(config, 'testnet_usdt_contract'):
        errors.append("Testnet USDT contract address not configured")
    
    if config.network == 'mainnet' and not hasattr(config, 'mainnet_usdt_contract'):
        errors.append("Mainnet USDT contract address not configured")
    
    return len(errors) == 0, errors


def get_recommended_staking(current_usage: Dict, target_capacity: int) -> Dict:
    """
    Get staking recommendations based on usage patterns
    
    Args:
        current_usage: Current resource usage data
        target_capacity: Target daily transaction capacity
        
    Returns:
        Dict with staking recommendations
    """
    # Calculate what's needed for target capacity
    requirements = analyze_resource_needs(target_capacity, 0, 1.0)
    
    current_energy_stake = current_usage.get('energy', {}).get('staked', 0)
    current_bandwidth_stake = current_usage.get('bandwidth', {}).get('staked', 0)
    
    energy_gap = max(0, requirements['requirements']['energy_stake_trx'] - current_energy_stake)
    bandwidth_gap = max(0, requirements['requirements']['bandwidth_stake_trx'] - current_bandwidth_stake)
    
    recommendations = {
        'additional_staking_needed': energy_gap + bandwidth_gap > 0,
        'energy_stake_needed': energy_gap,
        'bandwidth_stake_needed': bandwidth_gap,
        'total_additional_trx': energy_gap + bandwidth_gap,
        'current_capacity': current_usage.get('daily_capacity', 0),
        'target_capacity': target_capacity
    }
    
    return recommendations