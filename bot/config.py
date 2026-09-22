"""
Bot configuration — all from environment, secrets never hardcoded.

On the VM, APP_PASSWORD is pulled from Key Vault (secret `bot-app-password`) at start-up by
run.sh / the systemd unit; here we only read the already-exported env vars. Nothing sensitive
lands in this file or in the repo.
"""
import os


class Config:
    # --- Bot Framework identity (single-tenant, matches the Azure Bot registration) ---
    APP_ID = os.environ.get("MicrosoftAppId", "")
    APP_PASSWORD = os.environ.get("MicrosoftAppPassword", "")
    APP_TYPE = os.environ.get("MicrosoftAppType", "SingleTenant")
    APP_TENANTID = os.environ.get("MicrosoftAppTenantId", "9b861f04-0916-485b-af37-b28a7fa65dc1")

    # --- HTTP listener ---
    HOST = os.environ.get("BOT_HOST", "0.0.0.0")
    PORT = int(os.environ.get("BOT_PORT", "3978"))

    # --- Access control (Layer 2) ---
    # AAD security group whose members are the authorised COMMs guests. Membership is checked
    # via Graph on every message. Empty => dev/PoC "allow-list by env" fallback (see auth.py).
    COMMS_GROUP_ID = os.environ.get("PTVI_COMMS_GROUP_ID", "")
    # Comma-separated AAD object IDs allowed when COMMS_GROUP_ID is unset (PoC bootstrap only).
    COMMS_ALLOWLIST = [x.strip() for x in os.environ.get("PTVI_COMMS_ALLOWLIST", "").split(",") if x.strip()]

    # --- Request source ---
    # Where request folders are fetched from. For the PoC this can be a local path on the VM;
    # in production it's the SharePoint library read via Graph. See requests.py.
    REQUESTS_ROOT = os.environ.get("PTVI_REQUESTS_ROOT", os.path.expanduser("~/ptvi-bot/requests"))
