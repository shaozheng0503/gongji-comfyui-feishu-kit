# Contributing

Thanks for your interest in contributing.

## How to contribute

1. Fork this repository.
2. Create a branch:
   - `feature/<short-name>` for new features
   - `fix/<short-name>` for bug fixes
3. Make focused changes and keep commits small.
4. Update docs when behavior changes (`README.md`, `SKILL.md`, `PLAYBOOK.md`).
5. Open a Pull Request with:
   - What changed
   - Why it changed
   - How to test

## Local setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

## Coding guidelines

- Keep scripts compatible with Python 3.9+.
- Prefer clear, explicit variable names.
- Avoid hardcoding secrets; use environment variables.
- For network calls, include retries where appropriate.

## Documentation guidelines

- Keep command examples copy-pastable.
- Mention required permissions for Feishu APIs.
- Keep default parameters synchronized across:
  - `SKILL.md`
  - `PLAYBOOK.md`
  - `README.md`

## Security

- Never commit real credentials (`.env`, tokens, secrets).
- Remove sensitive data from logs/screenshots before sharing.
