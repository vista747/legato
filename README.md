# legato

A terminal-first Last.fm client.

## Install
Recommended (CLI UX): `pipx install legato`

Dev:
```bash
python -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install -e .
```

## First-time setup
```bash
legato setup
```

## Output
Simple, non-boxed text. Hyperlinks are emitted using Rich (OSC 8) where supported.
