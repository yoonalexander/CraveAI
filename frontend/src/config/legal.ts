export const LEGAL_CONFIG = {
  operatorName: "Alexander Yoon",
  operatorAddress: "5 London St\nToronto, ON M6G 1M8\nCanada",
  governingLaw:
    "The laws of the Province of Ontario and the federal laws of Canada applicable therein.",
  supportEmail: "craveai.support@gmail.com",
  privacyEmail: "craveai.support@gmail.com",
  termsVersion: "2026-08-14",
  privacyVersion: "2026-08-14",
  effectiveDate: "2026-08-14",
  effectiveDateLabel: "August 14, 2026",
} as const;

export const LEGAL_REVISION_FALLBACK = [
  {
    terms_version: LEGAL_CONFIG.termsVersion,
    privacy_version: LEGAL_CONFIG.privacyVersion,
    effective_date: LEGAL_CONFIG.effectiveDate,
    summary:
      "Application-specific Terms and Privacy Policy finalized from the implemented CraveAI data flows.",
  },
  {
    terms_version: "2026-08-13",
    privacy_version: "2026-08-13",
    effective_date: "2026-08-13",
    summary: "Pre-publication technical draft; replaced before legal publication.",
  },
] as const;
