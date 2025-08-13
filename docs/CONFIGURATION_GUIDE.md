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

#### Dynamic BANDWIDTH Yield

The service attempts to read chain parameters (totalNetLimit/totalNetWeight) from your node to compute the current BANDWIDTH units per 1 TRX automatically. If these parameters are unavailable, it falls back to the environment estimate `BANDWIDTH_UNITS_PER_TRX_ESTIMATE`.

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

#### Targets and Estimates

Set targets so a single USDT TRC20 transfer succeeds reliably:

```env
TARGET_ENERGY_UNITS=90000
TARGET_BANDWIDTH_UNITS=1000
ENERGY_UNITS_PER_TRX_ESTIMATE=300
BANDWIDTH_UNITS_PER_TRX_ESTIMATE=1500
USDT_ENERGY_PER_TRANSFER_ESTIMATE=14650
USDT_BANDWIDTH_PER_TRANSFER_ESTIMATE=345
DELEGATION_SAFETY_MULTIPLIER=1.1
MIN_DELEGATE_TRX=1.0
GAS_ACCOUNT_ACTIVATION_MODE=transfer
```

#### Control Signer for Delegations (Advanced, Safer)

To prevent your main gas wallet from being able to move TRX during routine operations, configure a separate control key that can only delegate resources. TRX transfers (activation) will continue to use the main key.

```env
# Control signer (choose either raw key or mnemonic+path)
GAS_WALLET_CONTROL_PRIVATE_KEY=hex-privkey
# or
GAS_WALLET_CONTROL_MNEMONIC="seed words..."
GAS_WALLET_CONTROL_PATH="m/44'/195'/1'/0/0"

# TRON account-permission id (Active Permission) bound to the control key
GAS_WALLET_CONTROL_PERMISSION_ID=2

# Allow fallback to owner signer for delegations if control signer fails (set false for strict separation)
GAS_CONTROL_FALLBACK_TO_OWNER=true
```

Steps to configure on TRON account:

1. Create an Active Permission and add the control public key to it.
2. Restrict allowed operations to freezing/delegation with receiver where possible.
3. Note the permission id and set `GAS_WALLET_CONTROL_PERMISSION_ID` in your `.env`.

Behavior:

- Delegations (ENERGY/BANDWIDTH) are signed with the control key using the given permission id.
- If fallback is disabled and control signing fails, delegations are skipped.
- If fallback is enabled, the system falls back to the owner signer for resilience (less strict).

#### Configuration Warnings and Health

On startup, the service evaluates your environment and emits warnings when activation mode and signer configuration may cause failures. You can see them in:

- Telegram command: /gasstation — a "Configuration warnings" section is appended.
- API: GET /v1/gasstation/status returns a warnings array and node info.

Common warnings and their fixes:

- "Ownerless mode without control signer": Either set GAS_WALLET_CONTROL_PRIVATE_KEY (with limited permissions) or provide owner keys.
- "Activation mode=transfer: no owner key, no ACTIVATION_WALLET_PRIVATE_KEY, no control signer": Provide any one of these, or activation will fail.
- "Activation mode=transfer with ownerless control": Control signer must include the "Transfer TRX" operation or set ACTIVATION_WALLET_PRIVATE_KEY for activation transfers.
- "Activation mode=create_account: neither owner nor control signer": Add at least one signer capable of activation.
- "create_account not supported by client": Your tronpy/client lacks create_account builder. Either allow Transfer TRX on control or set ACTIVATION_WALLET_PRIVATE_KEY, or switch GAS_ACCOUNT_ACTIVATION_MODE=transfer.

Tip: You can keep your server ownerless by disabling Transfer TRX on the control signer and providing a small ACTIVATION_WALLET_PRIVATE_KEY that only funds new accounts with tiny TRX.

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
TARGET_ENERGY_UNITS=90000
TARGET_BANDWIDTH_UNITS=1000
ENERGY_UNITS_PER_TRX_ESTIMATE=300
BANDWIDTH_UNITS_PER_TRX_ESTIMATE=1500
USDT_ENERGY_PER_TRANSFER_ESTIMATE=14650
USDT_BANDWIDTH_PER_TRANSFER_ESTIMATE=345
```

### Production Setup (Mainnet)

```env
TRON_NETWORK=mainnet
TRON_LOCAL_NODE_ENABLED=true
GAS_STATION_TYPE=single
DEBUG=false
LOG_LEVEL=INFO
TARGET_ENERGY_UNITS=90000
TARGET_BANDWIDTH_UNITS=1000
ENERGY_UNITS_PER_TRX_ESTIMATE=300
BANDWIDTH_UNITS_PER_TRX_ESTIMATE=1500
USDT_ENERGY_PER_TRANSFER_ESTIMATE=14650
USDT_BANDWIDTH_PER_TRANSFER_ESTIMATE=345
```

## Security Best Practices

1. **Never commit `.env` files** to version control
2. **Use strong private keys** for mainnet
3. **Limit admin access** to trusted users only
4. **Use HTTPS** for all webhook URLs
5. **Monitor gas station wallet** balance regularly
6. **Keep local nodes** on private networks
7. **Regularly backup** your database
8. **Enable local pre-commit hooks** to block secrets and large files: see `.hooks-README.md`

## Testing Your Configuration

```bash
# Test network connections
python scripts/test_network_nodes.py

# Validate all settings
python scripts/validate_config.py

# Switch networks easily
./scripts/switch_network.sh testnet
./scripts/switch_network.sh mainnet

# Optional: enable the local pre-commit hook
chmod +x .git-hooks/pre-commit
git config core.hooksPath .git-hooks
```

## Troubleshooting

### Common Issues

1. **"Connection refused"**: Check if TRON nodes are running
2. **"Invalid private key"**: Ensure 64-character hex format
3. **"Bot token invalid"**: Verify token from @BotFather
4. **"Database locked"**: Stop all PortoAPI processes
5. **"Insufficient balance"**: Add TRX to gas station wallet
6. **"Delegation/activation timed out"**: Nodes can be slow; the system continues after resource effects are visible. Severity is reduced to WARNING in logs.
7. **"Energy shown as 0 right after delegation"**: Different endpoints may lag; the system reads from multiple views and uses the maximum observed. Recheck after a short delay.

### Getting Help

- Check logs: `tail -f logs/portoapi.log`
- Test configuration: `python scripts/validate_config.py`
- Network status: `python scripts/test_network_nodes.py`

For additional support, check the project documentation or create an issue.
