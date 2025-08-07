#!/usr/bin/env python3
"""
Gas Station CLI Tool
Command-line interface for gas station management
"""

import sys
import argparse
import json
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from src.core.config import TronConfig
from src.core.services.gasstation import GasStationManager, format_resource_status


def status_command(args):
    """Show gas station status"""
    try:
        config = TronConfig()
        manager = GasStationManager(config)
        
        status = manager.check_operational_status()
        
        print("🏭 GAS STATION STATUS")
        print("=" * 50)
        print(format_resource_status(status['status']['resources']))
        print()
        
        print("📊 CAPACITY")
        print(f"   Daily USDT Transactions: {status['summary']['daily_tx_capacity']:,}")
        print(f"   Account Activations: {status['summary']['can_activate_accounts']:,}")
        print()
        
        print("🔍 OPERATIONAL STATUS")
        print(f"   Status: {'✅ OPERATIONAL' if status['operational'] else '❌ NOT OPERATIONAL'}")
        
        if status['warnings']:
            print("⚠️  WARNINGS:")
            for warning in status['warnings']:
                print(f"   • {warning}")
        
        if status['errors']:
            print("❌ ERRORS:")
            for error in status['errors']:
                print(f"   • {error}")
        
        if args.json:
            print("\n" + json.dumps(status, indent=2, default=str))
            
    except Exception as e:
        print(f"❌ Error: {e}")
        sys.exit(1)


def activate_command(args):
    """Activate an account"""
    try:
        config = TronConfig()
        manager = GasStationManager(config)
        
        print(f"🔄 Activating account: {args.address}")
        
        success, txid, message = manager.activate_new_user(args.address)
        
        if success:
            print(f"✅ {message}")
            print(f"   Transaction ID: {txid}")
        else:
            print(f"❌ {message}")
            sys.exit(1)
            
    except Exception as e:
        print(f"❌ Error: {e}")
        sys.exit(1)


def setup_seller_command(args):
    """Setup a seller account"""
    try:
        config = TronConfig()
        manager = GasStationManager(config)
        
        print(f"🔄 Setting up seller account: {args.address}")
        
        success, transactions, message = manager.setup_seller(args.address)
        
        if success:
            print(f"✅ {message}")
            for tx_type, txid in transactions.items():
                print(f"   {tx_type.title()}: {txid}")
        else:
            print(f"❌ {message}")
            sys.exit(1)
            
    except Exception as e:
        print(f"❌ Error: {e}")
        sys.exit(1)


def capacity_command(args):
    """Check transaction capacity"""
    try:
        config = TronConfig()
        manager = GasStationManager(config)
        
        can_process, message = manager.can_process_invoice(args.transactions)
        
        print(f"🔍 Checking capacity for {args.transactions} transactions")
        print(f"   Result: {'✅' if can_process else '❌'} {message}")
        
        if not can_process:
            sys.exit(1)
            
    except Exception as e:
        print(f"❌ Error: {e}")
        sys.exit(1)


def maintenance_command(args):
    """Perform maintenance"""
    try:
        config = TronConfig()
        manager = GasStationManager(config)
        
        print("🔧 Performing maintenance...")
        
        results = manager.perform_maintenance()
        
        if results.get('error'):
            print(f"❌ Maintenance failed: {results['error']}")
            sys.exit(1)
        
        print("✅ Maintenance completed")
        
        if results['rebalancing_performed']:
            print("   🔄 Auto-rebalancing performed")
        
        if results['actions_taken']:
            print("   Actions taken:")
            for action in results['actions_taken']:
                print(f"     • {action}")
        
        if results['recommendations']:
            print("   📋 Recommendations:")
            for rec in results['recommendations']:
                print(f"     • {rec}")
        
        if args.json:
            print("\n" + json.dumps(results, indent=2, default=str))
            
    except Exception as e:
        print(f"❌ Error: {e}")
        sys.exit(1)


def summary_command(args):
    """Show resource summary"""
    try:
        config = TronConfig()
        manager = GasStationManager(config)
        
        summary = manager.get_resource_summary()
        
        if args.json:
            print(json.dumps(summary, indent=2, default=str))
        else:
            print("📊 RESOURCE SUMMARY")
            print("=" * 50)
            print(f"Address: {summary['address']}")
            print(f"Network: {summary['network']}")
            print(f"Balance: {summary['balance_trx']:,.2f} TRX")
            print(f"Staked: {summary['staked_trx']:,.0f} TRX")
            print()
            print("Daily Capacity:")
            print(f"  USDT Transactions: {summary['daily_capacity']['usdt_transactions']:,}")
            print(f"  Account Activations: {summary['daily_capacity']['account_activations']:,}")
            
    except Exception as e:
        print(f"❌ Error: {e}")
        sys.exit(1)


def main():
    """Main CLI entry point"""
    parser = argparse.ArgumentParser(description='Gas Station Management CLI')
    parser.add_argument('--json', action='store_true', help='Output JSON format')
    
    subparsers = parser.add_subparsers(dest='command', help='Available commands')
    
    # Status command
    status_parser = subparsers.add_parser('status', help='Show gas station status')
    status_parser.set_defaults(func=status_command)
    
    # Activate command
    activate_parser = subparsers.add_parser('activate', help='Activate an account')
    activate_parser.add_argument('address', help='TRON address to activate')
    activate_parser.set_defaults(func=activate_command)
    
    # Setup seller command
    seller_parser = subparsers.add_parser('setup-seller', help='Setup seller account')
    seller_parser.add_argument('address', help='Seller TRON address')
    seller_parser.set_defaults(func=setup_seller_command)
    
    # Capacity command
    capacity_parser = subparsers.add_parser('capacity', help='Check transaction capacity')
    capacity_parser.add_argument('--transactions', type=int, default=10, help='Number of transactions to check')
    capacity_parser.set_defaults(func=capacity_command)
    
    # Maintenance command
    maintenance_parser = subparsers.add_parser('maintenance', help='Perform maintenance')
    maintenance_parser.set_defaults(func=maintenance_command)
    
    # Summary command
    summary_parser = subparsers.add_parser('summary', help='Show resource summary')
    summary_parser.set_defaults(func=summary_command)
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        sys.exit(1)
    
    args.func(args)


if __name__ == '__main__':
    main()