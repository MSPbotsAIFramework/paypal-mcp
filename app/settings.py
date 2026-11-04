"""Non-credential runtime configuration.

Credentials are never read here -- they arrive per request as HTTP headers
(see app/middleware.py) and must never be stored in process configuration
or environment variables (SOP S3.1).
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Process-wide, non-secret configuration.

    extra="ignore" is required: the runtime environment injects variables
    this project does not declare, and strict parsing would crash on boot
    (SOP S1.2).
    """

    model_config = SettingsConfigDict(extra="ignore")

    mcp_http_host: str = "0.0.0.0"
    mcp_http_port: int = 8080

    # Overridable for testing against PayPal's sandbox vs. live host; the
    # per-request X-Paypal-Environment header is the actual selector (see
    # app/paypal_client.py), this is only an escape hatch for local dev.
    paypal_sandbox_base_url: str = "https://api-m.sandbox.paypal.com"
    paypal_live_base_url: str = "https://api-m.paypal.com"

    connect_timeout_seconds: float = 5.0
    read_timeout_seconds: float = 30.0
    max_retries: int = 3


settings = Settings()
