#!/usr/bin/env python3
"""
PortoAPI Startup Script
Demonstrates how to start different components with the new configuration system.
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import argparse
import asyncio
from src.core.config import config

def start_bot():
    """Start the Telegram bot"""
    print(f"Starting Telegram bot on {config.tron.network} network...")
    from src.bot.main_bot import main
    asyncio.run(main())

def start_api():
    """Start the FastAPI server"""
    print(f"Starting API server on {config.api.host}:{config.api.port}...")
    import uvicorn
    from src.api.v1.main import app
    
    uvicorn.run(
        app,
        host=config.api.host,
        port=config.api.port,
        reload=config.api.debug
    )

def start_keeper():
    """Start the keeper bot"""
    print(f"Starting keeper bot for {config.tron.network} network...")
    from src.services.keeper_bot import main
    main()

def validate():
    """Validate configuration"""
    print("Validating configuration...")
    try:
        from scripts.validate_config import main as validate_main
        return validate_main()
    except SystemExit as e:
        return e.code
    except Exception as e:
        print(f"Validation error: {e}")
        return 1

def main():
    parser = argparse.ArgumentParser(description="PortoAPI Service Manager")
    parser.add_argument(
        "service",
        choices=["bot", "api", "keeper", "validate", "all"],
        help="Service to start"
    )
    parser.add_argument(
        "--network",
        choices=["mainnet", "testnet"],
        help="Override TRON network (default from config)"
    )
    
    args = parser.parse_args()
    
    # Override network if specified
    if args.network:
        config.tron.network = args.network
        print(f"Network override: {args.network}")
    
    print(f"🚀 PortoAPI Service Manager")
    print(f"Network: {config.tron.network}")
    print(f"Gas Station: {config.tron.gas_station_type}")
    if config.tron.local_node_enabled:
        print(f"Local Node: {config.tron.local_full_node}")
    else:
        print("Local Node: Disabled (using remote APIs)")
    print("-" * 40)
    
    try:
        if args.service == "validate":
            return validate()
        elif args.service == "bot":
            start_bot()
        elif args.service == "api":
            start_api()
        elif args.service == "keeper":
            start_keeper()
        elif args.service == "all":
            print("Starting all services is not implemented yet.")
            print("Please start each service in separate terminals:")
            print("  python scripts/start.py bot")
            print("  python scripts/start.py api")
            print("  python scripts/start.py keeper")
            return 1
    except KeyboardInterrupt:
        print("\nService stopped by user.")
        return 0
    except Exception as e:
        print(f"Error starting service: {e}")
        return 1

if __name__ == "__main__":
    sys.exit(main())
