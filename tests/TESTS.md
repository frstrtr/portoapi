### Run tests

To run all tests from the project root, use:

```sh
PYTHONPATH=src pytest
```

To run a specific test file, for example `test_hd_wallet.py`:

```sh
PYTHONPATH=src pytest tests/test_hd_wallet.py
```

**Note:**  
- All imports in tests should use the `core.` prefix (e.g., `from core.crypto.hd_wallet_service import ...`).
- All mocks/patches should use the same `core.` prefix (e.g., `@patch("core.crypto.hd_wallet_service.Bip44")`).
