#!/usr/bin/env bash
set -euo pipefail

# Always run from repo root so relative paths (a4-app/...) work the same locally and in Azure
cd "$(dirname "$0")"

# Make Python output unbuffered for real-time logs in Azure
export PYTHONUNBUFFERED=1

# ---- Dependencies ----
# Install Python packages. The --no-input and --exists-action i flags reduce interactive prompts.
if [ -f requirements.txt ]; then
  pip install --no-input --exists-action i -r requirements.txt
else
  echo "requirements.txt not found at repo root"
  exit 1
fi

# Install Playwright browsers (chromium only). If already installed, do nothing.
# --with-deps ensures required OS packages are pulled in by Playwright’s installer on Azure.
python -m playwright install chromium || true

# ---- Run workload ----
# Execute your Playwright-driven script. Adjust the path only if your file moves.
exec python app.py