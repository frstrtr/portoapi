"""
Gas Station Module for PortoAPI
Comprehensive TRON resource management for USDT operations
"""

from .gas_station_service import GasStationService
from .gas_station_manager import GasStationManager
from .gas_station_utils import (
    calculate_transaction_costs,
    calculate_staking_efficiency,
    estimate_daily_operations,
    analyze_resource_needs,
    format_resource_status,
    validate_gas_station_config,
    get_recommended_staking
)

__all__ = [
    'GasStationService',
    'GasStationManager', 
    'calculate_transaction_costs',
    'calculate_staking_efficiency',
    'estimate_daily_operations',
    'analyze_resource_needs',
    'format_resource_status',
    'validate_gas_station_config',
    'get_recommended_staking'
]

# Version info
__version__ = '1.0.0'
__author__ = 'PortoAPI Team'
__description__ = 'TRON Gas Station for USDT operations and resource management'