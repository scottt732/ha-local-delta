# Local Delta Faucet — agent guide

Home Assistant custom integration in `custom_components/local_delta/`, Python 3.14, uv.

```bash
uv sync
uv run ruff check . && uv run ruff format --check .
uv run mypy
uv run pytest
```

Rules that are easy to break:

- **Never build a faucet command with `json.dumps` or `tojson`.** The faucet matches text
  literally and needs a space after the colon. `protocol.dispense_payload` is the only
  place commands are built; `test_dispense_payload_keeps_the_space_the_faucet_requires`
  pins it.
- `protocol.py` holds the wire format and stays free of Home Assistant runtime so it can
  be tested alone.
- `manifest.json` is the version of record; release-please bumps it. `pyproject.toml`
  stays at `0.0.0`.
- Use US English in user-facing text: milliliters, liters.
- Do not commit a real faucet MAC. Tests use `60A423000001`.
