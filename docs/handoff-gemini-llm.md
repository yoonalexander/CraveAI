# Handoff: Gemini LLM provider

Date: 2026-11-09 · Branch: `main` · Status: implemented, all 174 backend tests passing

## What this covers

Two pieces of work, both now on `main`:

1. **Map/chat UX** (commit `aad35f3`): anchored recommendation replies (chat no longer
   jumps to the bottom), compact filters above the map column, and inline chat photo
   arrows for browsing photos without opening the gallery.
2. **Gemini LLM provider** (this handoff): the backend language model can run on
   Gemini's free tier through its OpenAI-compatible endpoint, with OpenAI kept as a
   selectable fallback. No new SDK dependency; both providers are driven through the
   OpenAI SDK.

## What changed for Gemini

- `backend/services/llm.py` (new): provider resolution, client options, model
  defaults, and per-provider completion parameters in one place.
- `backend/config.py`: adds `LLM_PROVIDER` (`auto`/`openai`/`gemini`),
  `GEMINI_API_KEY`, and `GEMINI_BASE_URL`. `MODEL_NAME` now defaults blank and
  resolves per provider (`gpt-5-nano` for OpenAI, `gemini-3.8-flash` for Gemini).
- `LLM_PROVIDER=auto` uses Gemini only when `GEMINI_API_KEY` is set and
  `OPENAI_API_KEY` is absent. Explicit `gemini` wins when both keys exist.
- Gemini requests send `max_tokens` and omit OpenAI-only `store`/`verbosity`.
- Migrated to the provider helper: intent extraction
  (`backend/services/craving_intent.py`), evidence ranking
  (`backend/services/evidence_ranker.py`), menu-label classification
  (`backend/services/filter_enrichment.py`), news discovery
  (`backend/services/discovery.py`), and voice transcription
  (`backend/routers/audio.py` — Gemini inline audio for webm/m4a/mp3/wav/ogg,
  Whisper still used on the OpenAI path).
- Docs and tooling: `.env.example`, `README.md`, `scripts/evaluate_filter_labels.py`.
- Tests: `tests/test_llm_provider.py` (new; provider resolution, request shape,
  config validation, Gemini inline-audio transcription) and `tests/conftest.py`
  forces `LLM_PROVIDER=openai` so the suite stays deterministic.

## To enable Gemini

Local `.env` or the backend host (Render):

```env
LLM_PROVIDER=gemini
GEMINI_API_KEY=<key from https://aistudio.google.com/apikey>
# optional; blank resolves to gemini-3.8-flash
MODEL_NAME=
```

`OPENAI_API_KEY` can stay set. Note: while it is set, `auto` keeps using OpenAI, so
`LLM_PROVIDER=gemini` is what actually switches providers.

## Verification status

- Full backend suite: 174 passed (run with Python 3.11, openai 2.54.0).
- No live Gemini call has been made yet — there was no key available when this was
  built. The compatibility surface was checked against current Google docs
  (structured outputs, `reasoning_effort`, inline audio incl. WebM, `max_tokens`).
- Smoke test after enabling: one chat request and one voice note; check backend logs
  if either fails.

## Caveats and follow-ups

- Gemini free tier has per-project RPM/RPD/TPM limits; view them in Google AI
  Studio. Free-tier content may be used to improve Google products.
- If `FILTER_LABEL_MODEL` / `DISCOVERY_MODEL` are set, they must exist on the active
  provider.
- Google Places billing and the `/api/places/photo` 429 rate limits are unaffected
  by this switch.
- If Gemini is ever unavailable, chat falls back to lexical intent/ranking and menu
  labels are marked `unavailable`; voice returns 502 `transcription_unavailable`.
