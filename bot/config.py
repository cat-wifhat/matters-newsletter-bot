"""Config for the Matters newsletter (digest) bot.

This is a STANDALONE project, separate from the repost-bot. It only reads
Matters' public GraphQL API and writes one digest draft; it does not scrape any
external sites.
"""
import os

MATTERS_API = "https://server.matters.news/graphql"

# Credentials for the dedicated newsletter account. The GitHub workflow maps the
# repo secrets DIGEST_MATTERS_EMAIL / DIGEST_MATTERS_PASSWORD onto these names.
MATTERS_EMAIL = os.environ.get("MATTERS_EMAIL", "")
MATTERS_PASSWORD = os.environ.get("MATTERS_PASSWORD", "")

DRY_RUN = os.environ.get("DRY_RUN", "").lower() in ("1", "true", "yes")

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
)
