### Run tests

To run all tests from the project root, use:

```sh
PYTHONPATH=src pytest -q
```

To run a specific test file, for example `test_hd_wallet.py`:

```sh
PYTHONPATH=src pytest tests/test_hd_wallet.py
```

**Note:**  

- All imports in tests should use the `core.` prefix (e.g., `from core.crypto.hd_wallet_service import ...`).
- All mocks/patches should use the same `core.` prefix (e.g., `@patch("core.crypto.hd_wallet_service.Bip44")`).

Additional:

- Some integration-like paths rely on environment defaults (e.g., TRON_LOCAL_NODE_ENABLED, fallback nodes). Tests are written to avoid network dependency; keep PYTHONPATH set to `src` to resolve in-repo modules.
- The Free Gas flow is user-interactive in the bot and isn’t unit-tested directly; core gas station logic is covered in `test_gas_station.py`.
