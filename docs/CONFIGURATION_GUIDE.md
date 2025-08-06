# PortoAPI Configuration Guide

This guide explains how to configure PortoAPI using the `.env` file.

## Quick Setup

1. **Copy the template**:
   ```bash
   cp .env.example .env
   ```

2. **Configure your values** using this guide

3. **Validate configuration**:
   ```bash
   python scripts/validate_config.py
   ```

## Configuration Sections

### 🤖 Telegram Bot Configuration

```env
TELEGRAM_BOT_TOKEN=1234567890:ABCDEFghijklmnopqrstuvwxyz123456789
TELEGRAM_BOT_NAME=your_bot_username
TELEGRAM_BOT_ID=1234567890
BOT_WEBHOOK_URL=https://yourdomain.com/webhook/telegram
BOT_SECRET_TOKEN=your_secure_webhook_secret_token
```

**How to get these values:**

1. **Bot Token**: Message [@BotFather](https://t.me/botfather) on Telegram
   - Send `/newbot`
   - Follow instructions to create your bot
   - Copy the token (format: `1234567890:ABCDEFghijklmnopqrstuvwxyz123456789`)

2. **Bot Name**: The username you chose (without @)

3. **Bot ID**: Extract from token (numbers before the colon)

4. **Webhook URL**: Your public domain where PortoAPI is hosted
   - Example: `https://yourdomain.com/webhook/telegram`
   - Must be HTTPS for production

5. **Secret Token**: Generate a random secure string
   - Example: `openssl rand -hex 32`

### 🌐 API Configuration

```env
API_HOST=0.0.0.0
API_PORT=8000
API_DEBUG=false
API_BASE_URL=https://yourdomain.com/api/v1
SETUP_URL_BASE=https://yourdomain.com:8000
```

- **API_HOST**: Use `0.0.0.0` to accept connections from any IP, or `127.0.0.1` for local only
- **API_PORT**: Port for the FastAPI server (default: 8000)
- **API_DEBUG**: Set to `true` for development, `false` for production
- **API_BASE_URL**: Public URL where your API is accessible
- **SETUP_URL_BASE**: URL for the setup interface

### 💾 Database Configuration

```env
DATABASE_URL=sqlite:///./data/database.sqlite3
DATABASE_ECHO=false
```

- **DATABASE_URL**: SQLite database file path (relative to project root)
- **DATABASE_ECHO**: Set to `true` to log all SQL queries (development only)

### ⚡ TRON Network Configuration

#### Network Selection
```env
TRON_NETWORK=testnet
TRON_API_KEY=your_trongrid_api_key_here
```

- **TRON_NETWORK**: `testnet` for development, `mainnet` for production
- **TRON_API_KEY**: Optional TronGrid API key for better rate limits
  - Get from: [TronGrid Console](https://www.trongrid.io/)

#### Local TRON Nodes (Recommended)
```env
TRON_LOCAL_NODE_ENABLED=true

# Mainnet Local Node
TRON_MAINNET_LOCAL_FULL_NODE=http://your_mainnet_ip:8090
TRON_MAINNET_LOCAL_SOLIDITY_NODE=http://your_mainnet_ip:8091
TRON_MAINNET_LOCAL_EVENT_SERVER=http://your_mainnet_ip:8092
TRON_MAINNET_LOCAL_GRPC_ENDPOINT=your_mainnet_ip:50051

# Testnet Local Node
TRON_TESTNET_LOCAL_FULL_NODE=http://your_testnet_ip:8090
TRON_TESTNET_LOCAL_SOLIDITY_NODE=http://your_testnet_ip:8091
TRON_TESTNET_LOCAL_EVENT_SERVER=http://your_testnet_ip:8092
TRON_TESTNET_LOCAL_GRPC_ENDPOINT=your_testnet_ip:50051
```

**Replace placeholders:**
- `your_mainnet_ip`: IP address of your mainnet TRON node
- `your_testnet_ip`: IP address of your testnet TRON node

**If you don't have local nodes:**
- Set `TRON_LOCAL_NODE_ENABLED=false`
- The system will use remote APIs automatically

### 🔐 Gas Station Configuration

The Gas Station manages TRX for activating new addresses and delegating resources.

#### Single Wallet Mode (Recommended)
```env
GAS_STATION_TYPE=single
GAS_WALLET_PRIVATE_KEY=your_private_key_64_characters_hex
GAS_WALLET_MNEMONIC=your twelve word mnemonic phrase for gas station wallet
```

**How to get these values:**

1. **For Testnet Development**:
   ```bash
   # Generate test wallet
   python scripts/generate_test_wallet.py
   
   # Get test TRX from faucet
   # Visit: https://nileex.io/join/getJoinPage
   ```

2. **For Mainnet Production**:
   - Use a secure wallet with sufficient TRX
   - Private key format: 64 character hexadecimal string
   - Mnemonic: 12 or 24 word BIP39 phrase

#### Resource Amounts
```env
AUTO_ACTIVATION_TRX_AMOUNT=1.0
ENERGY_DELEGATION_TRX_AMOUNT=1.0
BANDWIDTH_DELEGATION_TRX_AMOUNT=0.5
```

**Recommended values:**
- **Testnet**: 1.0, 1.0, 0.5 TRX (lower costs)
- **Mainnet**: 1.5, 2.0, 1.0 TRX (production amounts)

#### Multisig Mode (Advanced)
```env
GAS_STATION_TYPE=multisig
MULTISIG_CONTRACT_ADDRESS=TYourMultiSigContractAddress123456789
MULTISIG_REQUIRED_SIGNATURES=2
MULTISIG_OWNER_KEYS=private_key_1,private_key_2,private_key_3
```

Only use if you have a deployed multisig contract.

### 👑 Admin Configuration

```env
ADMIN_IDS=123456789,987654321
```

**How to get Telegram User IDs:**
1. Message [@userinfobot](https://t.me/userinfobot) on Telegram
2. Copy your numeric user ID
3. Add multiple IDs separated by commas

### 📊 Monitoring & Logging

```env
LOG_LEVEL=INFO
LOG_FILE=logs/portoapi.log
KEEPER_CHECK_INTERVAL=30
KEEPER_ENABLED=true
```

- **LOG_LEVEL**: `DEBUG`, `INFO`, `WARNING`, `ERROR`
- **LOG_FILE**: Path to log file (directory must exist)
- **KEEPER_CHECK_INTERVAL**: Seconds between invoice checks
- **KEEPER_ENABLED**: Set to `false` to disable automatic payment monitoring

### 🔧 Development Settings

```env
DEBUG=false
DATABASE_ECHO=false
```

Set both to `true` for development mode with verbose logging.

## Example Configurations

### Development Setup (Testnet)
```env
TRON_NETWORK=testnet
TRON_LOCAL_NODE_ENABLED=true
GAS_STATION_TYPE=single
DEBUG=true
LOG_LEVEL=DEBUG
```

### Production Setup (Mainnet)
```env
TRON_NETWORK=mainnet
TRON_LOCAL_NODE_ENABLED=true
GAS_STATION_TYPE=single
DEBUG=false
LOG_LEVEL=INFO
```

## Security Best Practices

1. **Never commit `.env` files** to version control
2. **Use strong private keys** for mainnet
3. **Limit admin access** to trusted users only
4. **Use HTTPS** for all webhook URLs
5. **Monitor gas station wallet** balance regularly
6. **Keep local nodes** on private networks
7. **Regularly backup** your database

## Testing Your Configuration

```bash
# Test network connections
python scripts/test_network_nodes.py

# Validate all settings
python scripts/validate_config.py

# Switch networks easily
./scripts/switch_network.sh testnet
./scripts/switch_network.sh mainnet
```

## Troubleshooting

### Common Issues

1. **"Connection refused"**: Check if TRON nodes are running
2. **"Invalid private key"**: Ensure 64-character hex format
3. **"Bot token invalid"**: Verify token from @BotFather
4. **"Database locked"**: Stop all PortoAPI processes
5. **"Insufficient balance"**: Add TRX to gas station wallet

### Getting Help

- Check logs: `tail -f logs/portoapi.log`
- Test configuration: `python scripts/validate_config.py`
- Network status: `python scripts/test_network_nodes.py`

For additional support, check the project documentation or create an issue.
