#!/usr/bin/env bash
set -euo pipefail
cd ~/ptvi-bot/repo/bot
# managed-identity login (for Key Vault read + storage deploy)
az login --identity --only-show-errors >/dev/null
export MicrosoftAppId="119b0d4b-3785-4631-860b-e30696ab299c"
export MicrosoftAppType="SingleTenant"
export MicrosoftAppTenantId="9b861f04-0916-485b-af37-b28a7fa65dc1"
export MicrosoftAppPassword="$(az keyvault secret show --vault-name kv-ptvi-webbot-poc --name bot-app-password --query value -o tsv)"
export PTVI_REQUESTS_ROOT="$HOME/ptvi-bot/requests"
# PoC: allowlist by env until the PTVI-Website-COMMs group exists (task #5). Empty => bot denies all.
export PTVI_COMMS_ALLOWLIST="${PTVI_COMMS_ALLOWLIST:-}"
exec ~/ptvi-bot/venv/bin/python3 app.py
