#!/usr/bin/env python3
"""
Test script for PortoAPI TRON network nodes
Tests both mainnet (192.168.86.20) and nile testnet (192.168.86.154) nodes
"""

import requests
import json
import time
from datetime import datetime
from dotenv import load_dotenv
import os
import sys

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'src'))

load_dotenv()

# Network configurations
NETWORKS = {
    "mainnet": {
        "name": "Mainnet",
        "full_node": "http://192.168.86.20:8090",
        "solidity_node": "http://192.168.86.20:8091",
        "remote_fallback": "https://api.trongrid.io"
    },
    "nile": {
        "name": "Nile Testnet", 
        "full_node": "http://192.168.86.154:8090",
        "solidity_node": "http://192.168.86.154:8091",
        "remote_fallback": "https://nile.trongrid.io"
    }
}

def test_endpoint(endpoint, endpoint_name, timeout=10):
    """Test a single TRON endpoint"""
    try:
        start_time = time.time()
        
        response = requests.post(
            f"{endpoint}/wallet/getnowblock",
            timeout=timeout
        )
        
        end_time = time.time()
        latency = round((end_time - start_time) * 1000, 2)
        
        if response.status_code == 200:
            block_data = response.json()
            block_header = block_data.get('block_header', {})
            raw_data = block_header.get('raw_data', {})
            block_height = raw_data.get('number', 0)
            block_time = raw_data.get('timestamp', 0)
            
            # Convert timestamp to readable format
            if block_time > 0:
                block_datetime = datetime.fromtimestamp(block_time / 1000)
                time_str = block_datetime.strftime("%Y-%m-%d %H:%M:%S")
            else:
                time_str = "Unknown"
            
            print(f"✅ {endpoint_name}")
            print(f"   Block Height: {block_height:,}")
            print(f"   Block Time: {time_str}")
            print(f"   Latency: {latency}ms")
            return True, block_height, latency
            
        else:
            print(f"❌ {endpoint_name}: HTTP {response.status_code}")
            return False, 0, 0
            
    except requests.exceptions.ConnectionError:
        print(f"❌ {endpoint_name}: Connection refused (node not running)")
        return False, 0, 0
    except requests.exceptions.Timeout:
        print(f"❌ {endpoint_name}: Timeout ({timeout}s)")
        return False, 0, 0
    except Exception as e:
        print(f"❌ {endpoint_name}: {str(e)}")
        return False, 0, 0

def test_network(network_key, network_config):
    """Test all endpoints for a specific network"""
    print(f"\n🌐 Testing {network_config['name']} Network")
    print("=" * 50)
    
    # Test local nodes
    full_success, full_height, full_latency = test_endpoint(
        network_config['full_node'], 
        f"Local Full Node ({network_config['full_node']})"
    )
    
    solidity_success, solidity_height, solidity_latency = test_endpoint(
        network_config['solidity_node'],
        f"Local Solidity Node ({network_config['solidity_node']})"
    )
    
    # Test remote fallback
    remote_success, remote_height, remote_latency = test_endpoint(
        network_config['remote_fallback'],
        f"Remote Fallback ({network_config['remote_fallback']})"
    )
    
    # Summary
    print(f"\n📊 {network_config['name']} Summary:")
    
    if full_success and solidity_success:
        sync_diff = abs(full_height - solidity_height)
        if sync_diff <= 5:
            print(f"✅ Local nodes synchronized (diff: {sync_diff} blocks)")
        else:
            print(f"⚠️ Local nodes sync difference: {sync_diff} blocks")
    
    if full_success:
        print(f"🚀 Local Full Node: Operational ({full_latency}ms)")
    else:
        print(f"❌ Local Full Node: Failed")
    
    if solidity_success:
        print(f"🔍 Local Solidity Node: Operational ({solidity_latency}ms)")
    else:
        print(f"❌ Local Solidity Node: Failed")
    
    if remote_success:
        print(f"🌍 Remote Fallback: Available ({remote_latency}ms)")
    else:
        print(f"❌ Remote Fallback: Failed")
    
    return {
        "network": network_key,
        "local_available": full_success,  # Full Node is primary requirement
        "remote_available": remote_success,
        "full_node_height": full_height,
        "latency": full_latency if full_success else None,
        "solidity_available": solidity_success
    }

def test_current_config():
    """Test the currently configured network"""
    current_network = os.getenv("TRON_NETWORK", "testnet").lower()
    local_enabled = os.getenv("TRON_LOCAL_NODE_ENABLED", "true").lower() == "true"
    
    print(f"\n⚙️ Current PortoAPI Configuration")
    print("=" * 50)
    print(f"Active Network: {current_network.upper()}")
    print(f"Local Node Enabled: {local_enabled}")
    
    if current_network == "mainnet":
        current_endpoints = {
            "full_node": os.getenv("TRON_MAINNET_LOCAL_FULL_NODE", "http://192.168.86.20:8090"),
            "solidity_node": os.getenv("TRON_MAINNET_LOCAL_SOLIDITY_NODE", "http://192.168.86.20:8091")
        }
    else:
        current_endpoints = {
            "full_node": os.getenv("TRON_TESTNET_LOCAL_FULL_NODE", "http://192.168.86.154:8090"),
            "solidity_node": os.getenv("TRON_TESTNET_LOCAL_SOLIDITY_NODE", "http://192.168.86.154:8091")
        }
    
    print(f"Full Node: {current_endpoints['full_node']}")
    print(f"Solidity Node: {current_endpoints['solidity_node']}")
    
    if local_enabled:
        # Test current configuration
        full_ok, _, full_lat = test_endpoint(current_endpoints['full_node'], "Configured Full Node")
        sol_ok, _, sol_lat = test_endpoint(current_endpoints['solidity_node'], "Configured Solidity Node")
        
        if full_ok and sol_ok:
            print(f"\n✅ PortoAPI will use LOCAL nodes (avg latency: {(full_lat + sol_lat)/2:.1f}ms)")
        else:
            print(f"\n⚠️ PortoAPI will FALLBACK to remote APIs")
    else:
        print(f"\n🌍 PortoAPI configured to use REMOTE APIs only")

def main():
    print("🔍 PortoAPI TRON Network Test Suite")
    print(f"⏰ Test Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    results = []
    
    # Test all networks
    for network_key, network_config in NETWORKS.items():
        result = test_network(network_key, network_config)
        results.append(result)
    
    # Test current configuration
    test_current_config()
    
    # Final recommendations
    print(f"\n💡 Recommendations")
    print("=" * 50)
    
    nile_result = next((r for r in results if r["network"] == "nile"), None)
    mainnet_result = next((r for r in results if r["network"] == "mainnet"), None)
    
    if nile_result and nile_result["local_available"]:
        latency_ms = nile_result["latency"]
        print(f"✅ Nile testnet local Full Node ready for development ({latency_ms:.1f}ms)")
        if not nile_result.get("solidity_available", False):
            print("ℹ️ Solidity Node not available - some queries will use remote fallback")
        print("   Recommended: Use local Nile node for fast development")
    else:
        print("⚠️ Nile testnet local nodes not available - check node status")
    
    if mainnet_result and mainnet_result["local_available"]:
        latency_ms = mainnet_result["latency"]
        print(f"✅ Mainnet local Full Node ready for production ({latency_ms:.1f}ms)")
        if not mainnet_result.get("solidity_available", False):
            print("ℹ️ Solidity Node not available - some queries will use remote fallback")
    else:
        print("⚠️ Mainnet local nodes not available - will use remote APIs")
    
    print("\n📝 Next Steps:")
    print("1. Set TRON_NETWORK=testnet in .env for development")
    print("2. Get test TRX from Nile faucet: https://nileex.io/join/getJoinPage")
    print("3. Configure GAS_WALLET_PRIVATE_KEY with a Nile testnet wallet")
    print("4. Test staking functionality on Nile testnet")

if __name__ == "__main__":
    main()
