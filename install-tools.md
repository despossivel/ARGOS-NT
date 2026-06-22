# ARGOS-NT Tool Installation Guide

This guide focuses on pip-based installation whenever possible.

## 1. Prerequisites

- Python 3.10+
- pip updated
- optional: `pipx` for isolated CLI installs

Recommended:

```bash
python3 -m pip install --upgrade pip
python3 -m pip install --user pipx
python3 -m pipx ensurepath
```

## 2. Core Tools (Base Scan)

Install:

```bash
pipx install holehe
pipx install sherlock-project
pipx install leaker
```

Alternative with pip:

```bash
pip install --user holehe sherlock-project leaker
```

## 3. Email Enrichment

Install:

```bash
pipx install h8mail
pipx install ghunt
```

Alternative:

```bash
pip install --user h8mail ghunt
```

## 4. Username Enrichment

Install:

```bash
pipx install socialscan
pipx install maigret
```

For `toutatis`, installation method may vary by maintained release.

Try pip first:

```bash
pip install --user toutatis
```

If unavailable on PyPI, install from the tool's official repository.

## 5. Phone Enrichment

Try pip installs:

```bash
pip install --user ignorant
pip install --user whatspy
```

If package names are not available on PyPI, install from source repositories and expose binaries in PATH.

## 6. Dork/Recon Add-ons

Try pip installs:

```bash
pip install --user google-dorks
# pip install --user dork-cli
pip install --user s3scanner
```



```bash 
sudo nano /usr/local/bin/pagodo
````

```bash 
#!/bin/bash
# Ativa o ambiente virtual do pagodo, roda o script passando todos os argumentos ($@) e depois desativa.
source /Users/SEU_USUARIO/caminho/ate/o/pagodo/venv/bin/activate
python3 /Users/SEU_USUARIO/caminho/ate/o/pagodo/pagodo.py "$@"
deactivate
```

```bash 
sudo chmod +x /usr/local/bin/pagodo
```

```bash 
pagodo --help
```

Some names may differ by package author. If pip cannot find them, install from source and ensure executable names match what ARGOS-NT checks in startup.

## 7. Verify Installation

Run ARGOS startup checks:

```bash
argos-menu
```

The boot sequence shows `OK`, `WARN`, and `ERR` for each tool and provider/service dependency.

You can also test commands directly:

```bash
command -v holehe
command -v sherlock
command -v leaker
command -v ghunt
command -v maigret
command -v ignorant
command -v whatspy
```

## 8. Notes About Optional Tools

- Missing optional tools do not stop the pipeline.
- Missing required/core tools can block startup.
- Full scan includes more optional tools than base scan.

## 9. Keep PATH Consistent

If tools were installed with `--user` or `pipx`, make sure your shell PATH includes user binaries.

Common paths on macOS:

- `~/.local/bin`
- `~/Library/Python/<version>/bin`

Reload shell after installation:

```bash
exec "$SHELL"
```

