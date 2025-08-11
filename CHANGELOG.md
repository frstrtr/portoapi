# Changelog

All notable changes to this project will be documented in this file.

## [Unreleased]

### Added

- ⛽ Free Gas bot flow (/free_gas): one-click address activation and minimal resource top-up (limit 3 per seller).
- Dynamic BANDWIDTH yield estimation from chain parameters with safe fallback to config.
- Multi-endpoint resource reads (local full/solidity and remote solidity) with max-value selection to mitigate view lag.
- Resilient transaction confirmation probing across endpoints with reduced false-positive errors.
- Local pre-commit hook (.git-hooks/pre-commit) to block secrets and large files.

### Changed

- Gas station acceptance logic for BANDWIDTH lag: treat ≥1 TRX delegation as sufficient when math guarantees coverage.
- Activation heuristic: proceed when account appears activated (balance/freeNet) even if tx confirmation times out.
- Logging: downgrade expected activation/delegation timeouts to WARNING; quieter aiogram dispatcher logs.
- Bot: improved post-state reporting after delegation; added slight delay and multi-view fetch.
- Bot: fixed Free Gas usage counter to display correctly (used_now).

### Docs

- README: new features overview, Free Gas section, TRON client behavior, pre-commit instructions, targets/estimates.
- docs/CONFIGURATION_GUIDE.md: dynamic bandwidth yield, targets/estimates, pre-commit hook, troubleshooting entries.
- src/core/services/gasstation/README.MD: dynamic BW note, resilience items, Free Gas reference.
- tests/TESTS.md updates and notes.

