# CraveAI recommendation engine

Last updated: 2026-08-13

This document describes the recommendation engine that is actually implemented.
It replaces the earlier design document, which described LangChain, Chroma/FAISS,
and cuisine embeddings that were not present in the runtime.

## Product invariant

A recommendation is eligible only when CraveAI has attributable evidence that it
satisfies the important parts of the craving. Returning fewer than three results
is expected when the evidence is weak. Star rating is a tie-breaker, not a
substitute for food relevance.

## Previous runtime and failure analysis

Before this change, `rag_pipeline.py` received a top-rated nearby restaurant pool
from the legacy Google Nearby Search endpoint. For an unconstrained chat query it
usually passed the whole pool to one GPT-5-nano call. The model saw only the
restaurant name, rating, review count, address, coordinates, and at most three
generic tags. It did not receive menus, menu items, review evidence, embeddings,
or a dish-level index.

The same model selected up to three restaurants and wrote the explanations. A
rating/review-count fallback also forced three results when the model call failed.
There was no structured intent, constraint strength, hard exclusion, dish-level
retrieval, evidence threshold, same-dish overlap check, or independent reranker.

That information boundary explains the `spicy, maybe like a soup` failure:

- Franklin House could look plausible as a pub with soup and spicy items, but no
  evidence established one coherent spicy-soup dish.
- Brasas could look relevant because of spicy Portuguese chicken, while the soup
  preference was effectively ignored.
- Axia happened to be a good choice, but the old system did not know about its
  actual Tom Yum and other spicy soup items when it selected it.
- Phrases such as `may pair with spicy sides or brothy soups` were generated from
  plausibility. They were not linked to a retrieved menu fact.

The old module name said `RAG`, and the old design claimed a vector store, but the
runtime had neither a retrieval corpus nor retrieval-augmented generation.

## Current pipeline

```text
user craving + location
    -> structured intent (constraints, strengths, exclusions, query expansions)
    -> Google Places Text Search for 2-4 dish-oriented queries
    -> merge and cap nearby restaurant candidates
    -> fetch public official menu/order pages on demand
    -> extract structured JSON-LD menu items and bounded visible menu evidence
    -> classify which evidence supports which known constraints
    -> deterministic constraint, coherence, and evidence scoring
    -> evidence threshold and exclusion gate
    -> return 0-3 restaurants with dishes, scores, confidence, and sources
```

### 1. Structured craving intent

`backend/services/craving_intent.py` uses OpenAI Structured Outputs with Pydantic
models. Each constraint has a category and a strength:

| Strength | Typical language | Scoring behavior |
| --- | --- | --- |
| required | must, need, allergy, no/without | Must have high-quality supporting evidence; exclusions reject conflicts |
| strong | direct craving such as `spicy` | Must have at least medium-quality support |
| preferred | maybe, preferably | Important but can be unmatched if the total match remains coherent |
| weak | soft contextual signal | Small ranking contribution |

Categories cover cuisine, dish type, ingredient, taste, texture, temperature,
diet, health goal, price, meal type, other traits, and exclusion polarity. A conservative
local parser is used when the model is unavailable. It does not invent implied
traits such as `brothy` unless the user actually supplies them.

### 2. Dish-oriented candidate retrieval

`backend/services/restaurant_retrieval.py` issues 2-4 bounded Google Places Text
Search (New) queries such as `spicy soup restaurant` and candidate dish queries.
Queries are constrained to a rectangle around the user and to restaurant place
types. Results are merged by place ID with a reciprocal-rank-style retrieval
signal. The candidate set is capped at 12.

Provider query matches are evidence, but only medium-strength evidence. They are
never represented as verified menu items. Legacy Nearby Search is a best-effort
fallback and candidates without attributable relevance evidence are skipped.

### 3. Official menu evidence

`backend/services/menu_evidence.py` visits the official website supplied by the
place result for at most ten candidates. It follows at most two explicit menu or
order links and extracts:

- schema.org `MenuItem` or `Product` JSON-LD;
- visible text from pages whose URL or link is explicitly menu/order related.

Fetching is bounded by concurrency, time, response size, content type, redirect
count, and page count. Every redirect is DNS-resolved and rejects credentials,
non-HTTP(S) schemes, nonstandard ports, localhost, and private/link-local IPs.
Menu content is ephemeral per request and is not persisted.

Structured exact items are stronger than visible menu-page text, which is
stronger than a provider query match. Cuisine-level inference alone is not enough
to pass the recommendation gate.

### 4. Evidence classification and deterministic ranking

`backend/services/evidence_ranker.py` lets the model perform one bounded task: map
known evidence IDs to known constraint IDs. It cannot add restaurants, dishes,
scores, explanations, or evidence. Deterministic lexical mappings are merged with
the model output so an exact literal match cannot be lost to model variability.
Unknown IDs are discarded. A timeout falls back to lexical mappings.

The deterministic restaurant score is:

```text
overall = 0.82 * food relevance
        + 0.13 * evidence strength
        + 0.05 * rating quality
```

Food relevance is based on weighted constraint coverage, evidence quality,
retrieval rank, and same-item coherence. Constraint weights are 4/3/2/1 for
required/strong/preferred/weak. A candidate needs at least 70% weighted coverage.
When a craving has multiple positive constraints, at least one evidence item must
cover 70% of their weighted importance. This prevents separate `spicy wings` and
`French onion soup` items from masquerading as a spicy soup match.

Required positive constraints need official-menu-quality evidence. Strong
constraints need at least medium-quality evidence. Required exclusions reject a
candidate when its evidence conflicts. The final threshold is 0.58 and at most
three restaurants are returned; no popularity fallback fills empty slots.

### 5. Grounded response contract

`POST /api/chat` returns these fields for each result:

```json
{
  "name": "Example Restaurant",
  "match_score": 0.91,
  "confidence": "high",
  "matching_dishes": ["Example spicy soup"],
  "matched_preferences": ["spicy", "soup"],
  "unmatched_preferences": [],
  "evidence": [
    {
      "type": "official_menu",
      "label": "Example spicy soup",
      "source_url": "https://restaurant.example/menu"
    }
  ],
  "reason": "Its official menu lists Example spicy soup, supporting spicy and soup."
}
```

Explanations are templates assembled only from selected evidence. Provider-only
support is labeled as an unverified Google Maps match and receives medium
confidence; it is never phrased as a verified menu fact.

## Evaluation

`evaluation/craving_cases.json` contains 20 human-labeled, synthetic cases across
taste, texture, temperature, cuisine, dish type, ingredients, diet, exclusions,
health goals, price, and simultaneous constraints. Each case includes two
coherent dish-level matches plus deliberately misleading aggregate or partial
matches. Run it with:

```powershell
python scripts\evaluate_recommendations.py --json
```

Results as of 2026-08-13:

| Metric | Previous information-boundary proxy | Evidence-grounded scorer |
| --- | ---: | ---: |
| Precision@3 | 0.4333 | 0.6667 |
| Recall@3 | 0.6500 | 1.0000 |
| NDCG@3 | 0.4307 | 1.0000 |
| Constraint satisfaction | 0.4333 | 1.0000 |
| Unsupported-claim rate | 0.5667 | 0.0000 |
| Menu-evidence coverage | 0.0000 | 1.0000 |
| Results with a strong matching item | 0.4333 | 1.0000 |
| Mean results returned | 3.0000 | 2.0000 |

This is a deterministic scorer regression, not an estimate of live production
quality. It isolates ranking and evidence gating under controlled labels. It does
not measure changing Google coverage, official-site parsability, end-to-end intent
model variance, closed restaurants, or live menu freshness. Those require a
separately judged, geographically representative online evaluation.

## Data-source boundaries and policy

Google Places supplies place identity, location, types, rating, website, and
query relevance, but it does not expose a general full-menu field. Google content
is kept request-scoped rather than placed in a durable menu cache. Official menu
pages are used only for user-initiated evidence lookup and are not persisted.

In a 2026-08-13 Streetsville snapshot for the spicy-soup regression, 5 of the 12
retrieved candidates (41.7%) yielded usable official menu/site evidence. This is
a one-query diagnostic, not a production coverage estimate; geography, query,
site technology, and transient availability materially change the denominator.

Before broad production crawling, review each source's terms and robots policy or
prefer direct merchant/licensed menu feeds. The current fetcher does not execute
JavaScript, parse PDFs, or bypass access controls.

## Known limitations

- Official menu coverage is uneven. JavaScript-only menus, PDF menus, bot
  protection, timeouts, and changed links can reduce evidence coverage.
- Text Search is query-sensitive and provider-only matches can still be noisy.
  They remain explicitly unverified and cannot satisfy required constraints.
- Intent extraction and semantic evidence classification are model calls and can
  vary, although deterministic parsing, lexical evidence, and thresholds limit
  their authority.
- Menu pages change and an item can be unavailable even when currently listed.
- On-demand website lookup adds latency; work is capped to keep a request bounded.
- The controlled 20-case set is too small to represent production traffic and
  currently has no click, conversion, distance-preference, or diversity labels.
- There is intentionally no embedding/vector layer: without a reliable,
  permissioned dish corpus, embeddings would index weak restaurant metadata and
  reproduce the original plausibility problem.

## Further improvements, ordered by expected impact

1. Ingest licensed or merchant-supplied structured menus with item IDs,
   availability, prices, dietary metadata, and freshness timestamps.
2. Build a geographically representative adjudicated set from real cravings and
   measure live retrieval recall, menu coverage, false positives, latency, and
   downstream saves/clicks.
3. Once a reliable menu corpus exists, add hybrid BM25 + dense dish retrieval and
   evaluate it against the current query retrieval rather than assuming a win.
4. Train or calibrate a compact cross-encoder/reranker from human judgments after
   enough labels exist.
5. Add explicit distance/price calibration and opt-in personalization without
   allowing either to override required food constraints.

## Relevant implementation files

- `backend/services/craving_intent.py`
- `backend/services/restaurant_retrieval.py`
- `backend/services/menu_evidence.py`
- `backend/services/evidence_ranker.py`
- `backend/services/rag_pipeline.py`
- `backend/services/recommendation_models.py`
- `evaluation/craving_cases.json`
- `scripts/evaluate_recommendations.py`
- `tests/test_recommendation_quality.py`
- `tests/test_recommendation_evaluation.py`
