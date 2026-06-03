"""Config for the Matters newsletter (digest) bot.

This is a STANDALONE project, separate from the repost-bot. It READS article data
from one Matters environment and WRITES a single digest draft to another (which
may be the same). It does not scrape external sites.

READ vs WRITE
-------------
The bot reads hottest/pinned articles from a SOURCE environment and creates the
draft in a DESTINATION environment. These can differ — the key use case:

    Read the PRODUCTION site's hot articles, but post the draft to the ICU TEST
    site so the team (who can access icu) can review it together.

Env vars (all optional; sensible production defaults):
    MATTERS_READ_ENDPOINT   data source GraphQL     default server.matters.news
    MATTERS_WRITE_ENDPOINT  draft destination + the account that logs in
                                                     default = read endpoint
    MATTERS_SITE            base URL for article LINKS (where the articles live)
                                                     default https://matters.town
    MATTERS_GRAPHQL_ENDPOINT  back-compat: sets BOTH read & write if the two
                                                     specific vars are unset

Environments:
    Production : https://server.matters.news/graphql  +  https://matters.town
    Test (icu) : https://server.matters.icu/graphql   +  https://matters.icu
                 (separate database & accounts; register a test account there)

The "read prod, write icu" setup:
    MATTERS_WRITE_ENDPOINT=https://server.matters.icu/graphql
    (leave READ/SITE at defaults so links still point to real matters.town articles)
"""
import os
from urllib.parse import urlparse

_PROD_API = "https://server.matters.news/graphql"

# Back-compat single-endpoint var sets both read & write unless overridden.
_single = os.environ.get("MATTERS_GRAPHQL_ENDPOINT", _PROD_API)
MATTERS_READ_ENDPOINT = os.environ.get("MATTERS_READ_ENDPOINT", _single)
MATTERS_WRITE_ENDPOINT = os.environ.get("MATTERS_WRITE_ENDPOINT", _single)

# Article links point to where the source articles actually live (the read site).
MATTERS_SITE = os.environ.get("MATTERS_SITE", "https://matters.town")

# Only these API hosts are allowed for read OR write. Prevents a typo from
# sending account credentials to an unknown host. (Pattern borrowed from
# mashbean/Your-Agent-for-Matters.)
ALLOWED_API_HOSTS = {
    "server.matters.news",   # production
    "server.matters.town",   # production (alias)
    "server.matters.icu",    # test / staging
}

# Credentials — these belong to the WRITE (destination) environment. For an icu
# write target, use a SEPARATE account registered on matters.icu.
MATTERS_EMAIL = os.environ.get("MATTERS_EMAIL", "")
MATTERS_PASSWORD = os.environ.get("MATTERS_PASSWORD", "")

DRY_RUN = os.environ.get("DRY_RUN", "").lower() in ("1", "true", "yes")

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
)


def _host(url: str) -> str:
    return (urlparse(url).hostname or "").lower()


def validate_endpoints() -> None:
    """Abort if either endpoint host is not on the allowlist."""
    for label, url in (("read", MATTERS_READ_ENDPOINT), ("write", MATTERS_WRITE_ENDPOINT)):
        if _host(url) not in ALLOWED_API_HOSTS:
            raise SystemExit(
                f"Refusing to run: {label} host {_host(url)!r} ({url}) is not in the "
                f"allowlist {sorted(ALLOWED_API_HOSTS)}."
            )


def env_label(url: str) -> str:
    return "TEST(icu)" if _host(url).endswith(".icu") else "PROD"
