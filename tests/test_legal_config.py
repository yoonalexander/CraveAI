from dataclasses import replace

from backend.config import Config
from backend import legal_config


def test_finalized_legal_identity_is_complete_and_publication_ready():
    settings = Config(
        OPERATOR_LEGAL_NAME=legal_config.OPERATOR_LEGAL_NAME,
        OPERATOR_ADDRESS=legal_config.OPERATOR_ADDRESS,
        GOVERNING_LAW=legal_config.GOVERNING_LAW,
        SUPPORT_EMAIL=legal_config.SUPPORT_EMAIL,
        PRIVACY_EMAIL=legal_config.PRIVACY_EMAIL,
        TERMS_VERSION=legal_config.TERMS_VERSION,
        PRIVACY_VERSION=legal_config.PRIVACY_VERSION,
        POLICY_EFFECTIVE_DATE=legal_config.POLICY_EFFECTIVE_DATE,
    )

    assert settings.OPERATOR_LEGAL_NAME == "Alexander Yoon"
    assert settings.OPERATOR_ADDRESS == "5 London St\nToronto, ON M6G 1M8\nCanada"
    assert settings.GOVERNING_LAW == (
        "The laws of the Province of Ontario and the federal laws of Canada "
        "applicable therein."
    )
    assert settings.SUPPORT_EMAIL == "craveai.support@gmail.com"
    assert settings.PRIVACY_EMAIL == "craveai.support@gmail.com"
    assert settings.legal_publication_issues() == ()


def test_legal_publication_guard_still_rejects_real_placeholders():
    settings = Config()
    invalid = replace(
        settings,
        OPERATOR_ADDRESS="[OPERATOR ADDRESS]",
        SUPPORT_EMAIL="support@example.com",
    )

    assert invalid.legal_publication_issues() == (
        "OPERATOR_ADDRESS",
        "SUPPORT_EMAIL",
    )
