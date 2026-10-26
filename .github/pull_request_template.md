## What and why

## Checks

- [ ] `uv run pytest -q` passes
- [ ] `uv run mypy --strict jobgent` passes
- [ ] `cd frontend && npm run build` passes (if the frontend changed)
- [ ] New behaviour has a test; no test reaches the network
- [ ] No personal data or keys in the diff
