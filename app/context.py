"""Request-scoped credential storage.

Three ContextVars, one per credential header. The middleware sets them at
the start of a request and resets them in `finally`, so concurrent requests
from different tenants never observe each other's values (SOP S3.3, AC11).

These must never be read from anywhere except inside an active request
(i.e. after the middleware has set them) and never written to by anything
other than the middleware.
"""

from contextvars import ContextVar

paypal_client_id: ContextVar[str | None] = ContextVar("paypal_client_id", default=None)
paypal_client_secret: ContextVar[str | None] = ContextVar("paypal_client_secret", default=None)
paypal_environment: ContextVar[str | None] = ContextVar("paypal_environment", default=None)


def current_credentials() -> tuple[str, str, str]:
    """Read the three credential context vars for the in-flight request.

    Raises RuntimeError if called outside a request the middleware has
    populated -- that is a programming error, not a tenant-facing one, so
    it is not mapped to the structured error envelope.
    """
    client_id = paypal_client_id.get()
    client_secret = paypal_client_secret.get()
    environment = paypal_environment.get()
    if not client_id or not client_secret or not environment:
        raise RuntimeError(
            "paypal credentials not set on the current request context; "
            "the credential middleware must run before any tool executes"
        )
    return client_id, client_secret, environment
