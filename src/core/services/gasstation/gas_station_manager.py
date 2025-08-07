"""
Gas Station Manager
Provides high-level interface for gas station operations
"""

import logging
from typing import Dict, Optional, Tuple
from .gas_station_service import GasStationService
from src.core.config import config

logger = logging.getLogger(__name__)


class GasStationManager:
    """
    High-level manager for gas station operations
    Integrates with PortoAPI configuration and provides business logic
    """
    
    def __init__(self, tron_config=None):
        """Initialize with PortoAPI configuration"""
        self.config = tron_config or config.tron
        self.gas_station = GasStationService(self.config)
        
        logger.info(f"Gas Station Manager initialized for {self.config.network}")
    
    def get_gas_wallet_address(self) -> str:
        """Get the gas station wallet address"""
        return self.gas_station.address
    
    def check_operational_status(self) -> Dict:
        """Check if gas station is operational"""
        status = self.gas_station.get_status()
        
        # Add business logic checks
        warnings = []
        errors = []
        
        # Check balance
        if status['balance'] < 10:
            errors.append("Critical: Low TRX balance for activations")
        elif status['balance'] < 50:
            warnings.append("Warning: Low TRX balance, consider refilling")
        
        # Check daily capacity
        daily_capacity = status['capacity']['daily_usdt_transactions']
        if daily_capacity < 10:
            errors.append("Critical: Very low daily transaction capacity")
        elif daily_capacity < 100:
            warnings.append("Warning: Low daily transaction capacity")
        
        # Check resource efficiency
        if status['efficiency']['energy'] < 80:
            warnings.append("Energy staking efficiency below 80%")
        
        if status['efficiency']['bandwidth'] < 80:
            warnings.append("Bandwidth staking efficiency below 80%")
        
        operational = len(errors) == 0
        
        return {
            'operational': operational,
            'status': status,
            'warnings': warnings,
            'errors': errors,
            'summary': {
                'can_activate_accounts': status['capacity']['account_activations'],
                'daily_tx_capacity': daily_capacity,
                'total_resources': status['total_staked']
            }
        }
    
    def activate_new_user(self, user_address: str) -> Tuple[bool, Optional[str], str]:
        """Activate a new user account"""
        try:
            # Check if we can afford activation
            status = self.check_operational_status()
            if not status['operational']:
                error_msg = "Gas station not operational: " + "; ".join(status['errors'])
                return False, None, error_msg
            
            if status['summary']['can_activate_accounts'] < 1:
                return False, None, "Insufficient balance for account activation"
            
            # Perform activation
            success, txid = self.gas_station.activate_account(user_address)
            
            if success:
                logger.info(f"User account activated: {user_address}")
                return True, txid, "Account activated successfully"
            else:
                return False, None, "Account activation failed"
                
        except Exception as e:
            logger.error(f"User activation failed: {e}")
            return False, None, f"Activation error: {str(e)}"
    
    def setup_seller(self, seller_address: str) -> Tuple[bool, Dict[str, str], str]:
        """Complete seller setup with activation and resource delegation"""
        try:
            # Check operational status
            status = self.check_operational_status()
            if not status['operational']:
                error_msg = "Gas station not operational: " + "; ".join(status['errors'])
                return False, {}, error_msg
            
            # Check if we have enough resources
            if status['summary']['can_activate_accounts'] < 1:
                return False, {}, "Insufficient balance for seller activation"
            
            if status['summary']['daily_tx_capacity'] < 50:
                return False, {}, "Insufficient resources for seller operations"
            
            # Setup seller account
            success, transactions = self.gas_station.setup_seller_account(seller_address)
            
            if success:
                logger.info(f"Seller account setup completed: {seller_address}")
                return True, transactions, "Seller account setup completed"
            else:
                return False, {}, "Seller setup failed"
                
        except Exception as e:
            logger.error(f"Seller setup failed: {e}")
            return False, {}, f"Setup error: {str(e)}"
    
    def can_process_invoice(self, estimated_transactions: int = 1) -> Tuple[bool, str]:
        """Check if gas station can process invoice transactions"""
        try:
            can_process, msg = self.gas_station.can_process_usdt_transactions(estimated_transactions)
            return can_process, msg
        except Exception as e:
            logger.error(f"Invoice processing check failed: {e}")
            return False, f"Check failed: {str(e)}"
    
    def get_resource_summary(self) -> Dict:
        """Get summary of gas station resources for monitoring"""
        try:
            status = self.gas_station.get_status()
            
            return {
                'address': status['address'],
                'network': status['network'],
                'balance_trx': status['balance'],
                'staked_trx': status['total_staked'],
                'daily_capacity': {
                    'usdt_transactions': status['capacity']['daily_usdt_transactions'],
                    'account_activations': status['capacity']['account_activations']
                },
                'current_resources': {
                    'energy_available': status['resources']['energy']['available'],
                    'bandwidth_available': status['resources']['bandwidth']['available']
                },
                'efficiency': status['efficiency'],
                'last_updated': 'now'  # Could add timestamp
            }
        except Exception as e:
            logger.error(f"Resource summary failed: {e}")
            return {}
    
    def perform_maintenance(self) -> Dict:
        """Perform routine maintenance operations"""
        maintenance_results = {
            'rebalancing_performed': False,
            'actions_taken': [],
            'recommendations': []
        }
        
        try:
            # Check if auto-rebalancing is needed
            rebalanced = self.gas_station.auto_rebalance()
            maintenance_results['rebalancing_performed'] = rebalanced
            
            if rebalanced:
                maintenance_results['actions_taken'].append("Auto-rebalanced resources")
            
            # Get current status for recommendations
            status = self.check_operational_status()
            
            if status['warnings']:
                maintenance_results['recommendations'].extend(status['warnings'])
            
            if status['errors']:
                maintenance_results['recommendations'].extend(status['errors'])
            
            logger.info(f"Maintenance completed: {maintenance_results}")
            
        except Exception as e:
            logger.error(f"Maintenance failed: {e}")
            maintenance_results['error'] = str(e)
        
        return maintenance_results