# Local TRON Node Configuration

This document explains how to configure PortoAPI to use a local TRON node for improved performance and reduced dependency on external APIs.

## Overview

PortoAPI supports both local and remote TRON node configurations with automatic fallback. When a local node is available, the system will prefer it for blockchain operations, falling back to remote APIs (TronGrid/TronScan) when the local node is unavailable.

## Benefits of Local Node

- **Improved Performance**: Direct connection eliminates network latency to external APIs
- **Better Reliability**: Reduced dependency on external service availability
- **Enhanced Privacy**: Blockchain queries don't leave your network
- **Cost Efficiency**: No API rate limits or costs for high-volume operations

## Configuration

### Environment Variables

Add these variables to your `.env` file:

```bash
# Local TRON Node Configuration
TRON_LOCAL_NODE_ENABLED=true
TRON_LOCAL_FULL_NODE=http://127.0.0.1:8090
TRON_LOCAL_SOLIDITY_NODE=http://127.0.0.1:8091
TRON_LOCAL_EVENT_SERVER=http://127.0.0.1:8092

# Connection Settings
TRON_LOCAL_TIMEOUT=10
TRON_LOCAL_MAX_RETRIES=3

# Fallback Remote Endpoints (used when local node fails)
TRON_REMOTE_FULL_NODE=https://api.trongrid.io
TRON_REMOTE_SOLIDITY_NODE=https://api.trongrid.io
TRON_REMOTE_EVENT_SERVER=https://api.trongrid.io
```

### Network-Specific Configuration

#### Multi-Node Setup (Recommended)

For development with dedicated nodes:

**Nile Testnet Node** (Development):
```bash
TRON_NETWORK=testnet
TRON_LOCAL_NODE_ENABLED=true

# Your Nile testnet node
TRON_TESTNET_LOCAL_FULL_NODE=http://192.168.86.154:8090
TRON_TESTNET_LOCAL_SOLIDITY_NODE=http://192.168.86.154:8091
TRON_TESTNET_LOCAL_EVENT_SERVER=http://192.168.86.154:8092

# Remote fallback
TRON_REMOTE_TESTNET_FULL_NODE=https://nile.trongrid.io
TRON_REMOTE_TESTNET_SOLIDITY_NODE=https://nile.trongrid.io
```

**Mainnet Node** (Production):
```bash
TRON_NETWORK=mainnet
TRON_LOCAL_NODE_ENABLED=true

# Your mainnet node
TRON_MAINNET_LOCAL_FULL_NODE=http://192.168.86.20:8090
TRON_MAINNET_LOCAL_SOLIDITY_NODE=http://192.168.86.20:8091
TRON_MAINNET_LOCAL_EVENT_SERVER=http://192.168.86.20:8092

# Remote fallback
TRON_REMOTE_MAINNET_FULL_NODE=https://api.trongrid.io
TRON_REMOTE_MAINNET_SOLIDITY_NODE=https://api.trongrid.io
```

#### Single-Node Setup (Alternative)

For **Testnet** (Nile):
```bash
TRON_NETWORK=testnet
TRON_LOCAL_FULL_NODE=http://127.0.0.1:16667
TRON_LOCAL_SOLIDITY_NODE=http://127.0.0.1:16668
TRON_REMOTE_FULL_NODE=https://nile.trongrid.io
TRON_REMOTE_SOLIDITY_NODE=https://nile.trongrid.io
```

For **Mainnet**:
```bash
TRON_NETWORK=mainnet
TRON_LOCAL_FULL_NODE=http://127.0.0.1:8090
TRON_LOCAL_SOLIDITY_NODE=http://127.0.0.1:8091
TRON_REMOTE_FULL_NODE=https://api.trongrid.io
TRON_REMOTE_SOLIDITY_NODE=https://api.trongrid.io
```

## Setting Up a Local TRON Node

### Your Current Setup

You have two TRON nodes running in your network:

- **Mainnet Node**: `192.168.86.20` (Production ready)
- **Nile Testnet Node**: `192.168.86.154` (Development ready)

### Quick Start for Your Setup

1. **Test your nodes**:
   ```bash
   python scripts/test_network_nodes.py
   ```

2. **Generate development wallet**:
   ```bash
   python scripts/generate_test_wallet.py
   ```

3. **Configure for development**:
   ```bash
   # Copy generated config
   cp .env.development .env
   
   # Or manually set network
   echo "TRON_NETWORK=testnet" >> .env
   ```

4. **Get test TRX**:
   - Visit [Nile Faucet](https://nileex.io/join/getJoinPage)
   - Send TRX to your generated wallet address

5. **Start development**:
   ```bash
   python scripts/start.py validate
   python scripts/start.py bot
   ```

### Option 1: Docker (Recommended)

Create a `docker-compose.yml` for TRON node:

```yaml
version: '3.8'
services:
  tron-node:
    image: tronprotocol/java-tron:latest
    container_name: tron-node
    ports:
      - "8090:8090"    # Full Node HTTP
      - "8091:8091"    # Solidity Node HTTP
      - "18888:18888"  # Full Node gRPC
      - "50051:50051"  # Solidity Node gRPC
    volumes:
      - tron-data:/java-tron/output-directory
    environment:
      - JAVA_OPTS=-Xmx4g
    command: |
      sh -c "
        wget -O /java-tron/main_net_config.conf https://raw.githubusercontent.com/tronprotocol/tron-deployment/master/main_net_config.conf &&
        java -jar /java-tron/FullNode.jar -c /java-tron/main_net_config.conf
      "

volumes:
  tron-data:
```

Start the node:
```bash
docker-compose up -d tron-node
```

### Option 2: Manual Installation

1. Download TRON FullNode from [TRON releases](https://github.com/tronprotocol/java-tron/releases)
2. Download the appropriate config file:
   - Mainnet: `main_net_config.conf`
   - Testnet: `test_net_config.conf`
3. Start the node:
   ```bash
   java -Xmx4g -jar FullNode.jar -c main_net_config.conf
   ```

### Node Synchronization

- **Initial Sync**: Can take several hours to days depending on network and hardware
- **Storage Requirements**: 
  - Mainnet: ~500GB+ (growing)
  - Testnet: ~50GB+ (growing)
- **Hardware Requirements**: 4GB+ RAM, SSD recommended

## Health Monitoring

PortoAPI automatically monitors local node health and switches to remote APIs when needed.

### Connection Test

Check if your local node is working:

```bash
# Test Full Node
curl http://127.0.0.1:8090/wallet/getnowblock

# Test Solidity Node  
curl http://127.0.0.1:8091/walletsolidity/getnowblock
```

### Using Validation Script

Run the configuration validator to test connections:

```bash
python scripts/validate_config.py
```

This will test:
- Local node connectivity
- Remote API fallback
- Network configuration
- Latest block retrieval

## Troubleshooting

### Common Issues

1. **Connection Refused**
   - Check if TRON node is running: `docker ps` or process status
   - Verify ports are open: `netstat -tlnp | grep :8090`
   - Check firewall settings

2. **Node Not Synchronized**
   - Check sync status: `curl http://127.0.0.1:8090/wallet/getnodeinfo`
   - Wait for synchronization to complete
   - System will automatically fall back to remote APIs

3. **High Resource Usage**
   - Increase JVM heap size: `-Xmx8g`
   - Use SSD for faster sync
   - Monitor disk space

4. **Network Issues**
   - Check node logs for connectivity issues
   - Verify internet connection for sync
   - Consider using fast sync if available

### Log Analysis

Check PortoAPI logs for connection status:

```bash
# Check gas station logs
grep "TRON.*node" logs/portoapi.log

# Check connection health
grep "Connection.*health" logs/portoapi.log
```

### Performance Optimization

1. **SSD Storage**: Use SSD for TRON data directory
2. **Memory**: Allocate sufficient JVM heap (4-8GB)
3. **Network**: Ensure stable internet for synchronization
4. **Monitoring**: Set up monitoring for node health

## Integration Details

### Gas Station Service

The Gas Station automatically:
- Tests local node connectivity on startup
- Performs health checks every operation
- Falls back to remote APIs on failure
- Reconnects to local node when available

### Configuration Priority

1. **Local Node** (if enabled and healthy)
2. **Remote APIs** (fallback)
3. **Error Handling** (operation retry with exponential backoff)

### Performance Metrics

The system tracks:
- Connection latency
- Success/failure rates
- Fallback frequency
- Node synchronization status

## Security Considerations

- **Local Network**: Keep node on private network
- **Firewall**: Restrict external access to node ports
- **Updates**: Keep TRON node software updated
- **Monitoring**: Monitor for unusual activity

## Future Enhancements

- Load balancing between multiple local nodes
- Advanced health metrics and alerting
- Automatic node management and restart
- Integration with TRON node clustering

For additional support, check the [TRON documentation](https://developers.tron.network/) or PortoAPI issues.
