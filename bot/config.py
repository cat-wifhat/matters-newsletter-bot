"""Config for the Matters newsletter (digest) bot.

This is a STANDALONE project, separate from the repost-bot. It only reads
Matters' public GraphQL API and writes one digest draft; it does not scrape any
external sites.

ENVIRONMENTS
------------
Production (default):
    MATTERS_GRAPHQL_ENDPOINT = https://server.matters.news/graphql
    MATTERS_SITE             = https://matters.town
Test / staging (Matters' sandbox — separate database & accounts):
    MATTERS_GRAPHQL_ENDPOINT = https://server.matters.icu/graphql
    MATTERS_SITE             = https://matters.icu

Switch environments by setting those two env vars — no code change. The endpoint
host is checked against an allowlist (below) so a typo/wrong host can't silently
send your account credentials somewhere unexpected.
"""
import os
from urllib.parse import urlparse

# Endpoint + public site are env-configurable; default to PRODUCTION.
MATTERS_API = os.environ.get(
    "MATTERS_GRAPHQL_ENDPOINT", "https://server.matters.news/graphql"
)
MATTERS_SITE = os.environ.get("MATTERS_SITE", "https://matters.town")

# Only these API hosts are allowed. Prevents accidentally logging in / posting
# against an unknown host. (Pattern borrowed from mashbean/Your-Agent-for-Matters.)
ALLOWED_API_HOSTS = {
    "server.matters.news",   # production
    "server.matters.town",   # production (alias)
    "server.matters.icu",    # test / staging
}

# Credentials. The GitHub workflow maps the repo secrets DIGEST_MATTERS_EMAIL /
# DIGEST_MATTERS_PASSWORD onto these names. For the test env, use a SEPARATE
# account registered on matters.icu (production accounts do not exist there).
MATTERS_EMAIL = os.environ.get("MATTERS_EMAIL", "")
MATTERS_PASSWORD = os.environ.get("MATTERS_PASSWORD", "")

DRY_RUN = os.environ.get("DRY_RUN", "").lower() in ("1", "true", "yes")

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
)


def validate_endpoint() -> None:
    """Abort if MATTERS_API points at a host not on the allowlist."""
    host = (urlparse(MATTERS_API).hostname or "").lower()
    if host not in ALLOWED_API_HOSTS:
        raise SystemExit(
            f"Refusing to run: API host {host!r} ({MATTERS_API}) is not in the "
            f"allowlist {sorted(ALLOWED_API_HOSTS)}. Check MATTERS_GRAPHQL_ENDPOINT."
        )


def is_test_env() -> bool:
    return (urlparse(MATTERS_API).hostname or "").endswith(".icu")
