"""Finalized, non-secret legal identity used by CraveAI.

Runtime environment variables may override these values, but keeping the
finalized defaults together prevents legal pages and launch validation from
drifting when the API is run without a deployment-specific override.
"""

OPERATOR_LEGAL_NAME = "Alexander Yoon"
OPERATOR_ADDRESS = "5 London St\nToronto, ON M6G 1M8\nCanada"
GOVERNING_LAW = (
    "The laws of the Province of Ontario and the federal laws of Canada "
    "applicable therein."
)
SUPPORT_EMAIL = "craveai.support@gmail.com"
PRIVACY_EMAIL = "craveai.support@gmail.com"
TERMS_VERSION = "2026-08-14"
PRIVACY_VERSION = "2026-08-14"
POLICY_EFFECTIVE_DATE = "2026-08-14"
