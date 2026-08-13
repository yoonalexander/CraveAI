# CraveAI recommendation engine overhaul

Status: implemented and verified  
Implementation date: 2026-08-13  
Scope: craving interpretation, restaurant retrieval, menu evidence, ranking,
explanations, API response data, frontend presentation, tests, and evaluation

## 1. Executive summary

CraveAI's original recommendation path selected restaurants from sparse
restaurant-level metadata and asked one language-model call to both rank the
candidates and explain them. It did not have menu data, menu embeddings, a
vector store, dish-level retrieval, an evidence gate, or a deterministic
relevance score. As a result, plausible-sounding restaurants could be returned
when different parts of the craving were satisfied by unrelated dishes—or not
supported at all.

The new implementation is an evidence-grounded, dish-oriented pipeline. It:

1. extracts independently scoreable craving constraints;
2. preserves linguistic strength and exclusions;
3. retrieves nearby restaurants with dish-oriented Google Places searches;
4. gathers bounded evidence from public official menu/order pages;
5. restricts the model to mapping supplied evidence to supplied constraints;
6. calculates scores and confidence deterministically;
7. rejects incomplete, incoherent, or insufficiently evidenced matches;
8. constructs explanations only from selected evidence; and
9. returns zero to three results instead of forcing three.

The key architectural change is one of authority: the language model can help
interpret text and classify evidence, but it no longer has authority to invent
restaurant facts, choose arbitrary scores, or write unconstrained
recommendation justifications.

## 2. Why this work was necessary

The motivating query was:

> im craving something spicy, maybe like a soup

The previous UI returned:

1. The Franklin House
2. Brasas Churrasqueira Rotisserie & Grill
3. Axia Restaurant

Manual inspection showed three different relevance patterns:

| Restaurant | Spicy evidence | Soup evidence | Coherent spicy-soup evidence | Assessment |
| --- | --- | --- | --- | --- |
| Axia | Strong | Strong | Yes—Tom Yum and related items | Good recommendation |
| Franklin House | Some spicy pub food | Non-spicy soup | No | Poor recommendation |
| Brasas | Piri-piri chicken | Little or no soup evidence | No | Poor recommendation |

The old generated wording for Brasas suggested “spicy sides or brothy soups.”
That statement was not derived from a retrieved menu fact. It was a plausible
continuation produced to justify a selection the model had already made.

## 3. Previous implementation: exact information boundary

### 3.1 Control flow

The old runtime flow was conceptually:

```text
browser nearby pool
    -> lightly select candidates
    -> send restaurant metadata and craving to one model call
    -> model selects up to three place IDs
    -> same model writes reasons
    -> merge model choices into source place objects
    -> on timeout/error, use rating/review fallback
```

Despite the `rag_pipeline.py` name and the old architecture document, the
runtime was not retrieval-augmented generation in the usual sense.

### 3.2 Data available to ranking

The model generally received:

- place ID;
- restaurant name;
- Google rating;
- review count;
- address;
- latitude/longitude; and
- up to three broad place tags.

It generally did not receive:

- restaurant menus;
- menu items;
- dish descriptions;
- source URLs for food claims;
- menu freshness information;
- embeddings;
- vector similarity results;
- structured user constraints;
- required versus preferred strength;
- dish-level overlap evidence; or
- an independently computed relevance score.

### 3.3 What was not actually implemented

The previous documentation described LangChain, Chroma/FAISS, cuisine
embeddings, and a stored cuisine vector collection. Repository inspection found
no production vector database, no embedded menu corpus, and no menu-item
retriever. The documentation was a proposed design rather than a description of
the running application.

This distinction matters because adding or tuning an embedding weight could not
fix the incident: there was no embedding stage to tune.

### 3.4 Ranking and fallback behavior

The language model performed an uncalibrated, one-shot selection. There was no
auditable restaurant score behind the displayed ordering. If ranking failed or
timed out, the fallback prioritized Google rating and review count and still
returned up to three candidates.

That design violated the product requirement that an irrelevant 4.8-star
restaurant should lose to a relevant 4.3-star restaurant.

## 4. Root-cause analysis

The failure came from several interacting causes rather than one bad prompt.

### 4.1 Sparse restaurant-level evidence

The system reasoned about restaurants as broad entities. A pub can have one
spicy wing item and one French onion soup, but that does not imply it serves a
spicy soup. Restaurant-level aggregation erased the relationship between food
characteristics and individual dishes.

### 4.2 No explicit constraint model

`spicy` and `maybe like a soup` were passed as prose. The system had no durable
representation that said:

```text
spicy: include, taste, strong
soup: include, dish type, preferred
```

The model could silently ignore the softened soup preference or treat both
words as loose semantic hints.

### 4.3 No same-item coherence check

The system did not distinguish:

- one dish that is both spicy and soup-like;
- two unrelated dishes that separately cover the words; and
- a restaurant associated with only one requested characteristic.

This was the central Franklin House failure.

### 4.4 Explanation generation had too much authority

The same model that selected candidates also wrote the reasons. With no
evidence IDs or source restrictions, it could generate restaurant-appropriate
possibilities rather than verified facts.

### 4.5 Forced result count

The pipeline treated three suggestions as a presentation requirement rather
than a maximum. Low-confidence slots were filled even when the candidate pool
did not contain three defensible matches.

### 4.6 Popularity could compensate for irrelevance

Rating and review count were available and reliable-looking, while food evidence
was absent. The most concrete features in the prompt therefore described
popularity rather than craving satisfaction.

### 4.7 Documentation drift obscured the real problem

The stale vector-search design made it easy to assume the application already
had semantic dish retrieval. The first corrective action was to document the
runtime truth.

## 5. Design goals and non-goals

### 5.1 Goals

- Generalize beyond the spicy-soup example.
- Interpret hard requirements, strong requests, soft preferences, and
  exclusions separately.
- Rank using evidence about actual food wherever possible.
- Prevent a model from inventing dishes or unsupported explanations.
- Prefer one excellent result over three weak results.
- Keep rating and popularity subordinate to food relevance.
- Degrade safely during provider timeouts and partial outages.
- Make ranking behavior testable without live provider calls.
- Expose enough response structure for users and developers to audit a result.

### 5.2 Non-goals in this iteration

- Building a long-lived web-scale menu crawler.
- Persisting Google Places data or scraped menu content.
- Adding a vector database without a reliable menu corpus.
- Claiming medical-grade allergy or dietary verification.
- Training a learned reranker without relevance labels.
- Optimizing solely for the number of recommendations returned.

## 6. New end-to-end architecture

```text
POST /api/chat
      |
      v
validate query, location, candidate hints, quota, and request limits
      |
      v
extract_craving_intent
  - Pydantic Structured Output
  - normalized strengths and exclusions
  - bounded candidate dishes and search queries
      |
      v
retrieve_candidate_restaurants
  - Google Places Text Search (New)
  - strict restaurant type
  - geographic rectangle
  - query-specific provider evidence
  - place-ID merge and candidate cap
      |
      v
enrich_candidates_with_menu_evidence
  - official website from Places
  - explicit menu/order links
  - JSON-LD MenuItem/Product extraction
  - visible menu-page evidence fallback
  - SSRF and resource bounds
      |
      v
assess_candidate_evidence
  - model maps known evidence IDs to known constraint IDs
  - deterministic lexical links are merged
  - unknown IDs are rejected
      |
      v
rank_evidence_candidates
  - required/strong gates
  - exclusion handling
  - weighted coverage
  - same-item coherence
  - deterministic score and confidence
  - minimum score threshold
      |
      v
grounded response
  - 0-3 restaurants
  - matching dishes/preferences
  - confidence and score
  - evidence labels and URLs
  - deterministic explanation
```

The entire orchestration is bounded by `CHAT_PIPELINE_TIMEOUT_SECONDS`, which
defaults to 20 seconds.

## 7. Structured craving intent

### 7.1 Schema

`backend/services/recommendation_models.py` defines the shared contract:

```text
CravingIntent
  summary: string
  constraints: IntentConstraint[]
  candidate_dishes: string[]
  search_queries: SearchQuerySpec[]

IntentConstraint
  id: c1, c2, ...
  dimension: taste | texture | temperature | cuisine | dish_type |
             ingredient | diet | health | price | meal | other
  value: normalized user characteristic
  polarity: include | exclude
  strength: required | strong | preferred | weak
```

Limits are deliberate:

- at most 10 constraints;
- at most 10 candidate-dish expansions; and
- at most 4 search queries.

### 7.2 Strength semantics

| Strength | Typical language | Weight | Gate |
| --- | --- | ---: | --- |
| Required | must, need, only, allergy/diet requirement | 4 | Needs evidence quality >= 0.8 |
| Strong | direct unqualified craving | 3 | Needs evidence quality >= 0.5 |
| Preferred | maybe, preferably, ideally, something like | 2 | Affects weighted coverage |
| Weak | tentative contextual signal | 1 | Small ranking effect |

Explicit `not`, `no`, `without`, and `except` language becomes exclusion
polarity. Strong or required conflicting evidence is removed from use for that
candidate.

### 7.3 Model authority and deterministic repair

OpenAI Structured Outputs parses directly into the Pydantic schema. The raw
model output is not trusted as executable input. `normalize_intent`:

- renumbers IDs;
- deduplicates constraints and queries;
- removes empty or excessive values;
- drops inferred soft traits not grounded in the user's words;
- corrects `maybe`/`preferably` to preferred;
- corrects ordinary direct requests misclassified as required;
- rejects invalid query-to-constraint IDs; and
- rebuilds bounded search queries when necessary.

If the model is unavailable, `fallback_intent` conservatively recognizes a
bounded vocabulary of common tastes, textures, temperatures, dishes,
ingredients, diets, health goals, and price requests. It retains hard/soft and
negative language when possible.

### 7.4 Example

Input:

```text
im craving something spicy, maybe like a soup
```

Normalized intent:

```json
{
  "constraints": [
    {
      "id": "c1",
      "dimension": "taste",
      "value": "spicy",
      "polarity": "include",
      "strength": "strong"
    },
    {
      "id": "c2",
      "dimension": "dish_type",
      "value": "soup",
      "polarity": "include",
      "strength": "preferred"
    }
  ],
  "search_queries": [
    {"text": "spicy soup", "constraint_ids": ["c1", "c2"]},
    {"text": "hot and sour soup", "constraint_ids": ["c1", "c2"]}
  ]
}
```

Candidate dishes are query expansions only. They never become restaurant facts.

## 8. Dish-oriented restaurant retrieval

### 8.1 Provider request

`backend/services/restaurant_retrieval.py` uses Google Places Text Search (New)
for each bounded query. Requests use:

- `includedType=restaurant`;
- strict type filtering;
- a location rectangle derived from the requested radius;
- at most 10 results per query; and
- a field mask limited to identity, address, location, rating/count, types,
  price level, website, Google Maps URL, and business status.

Closed places are discarded. Results are deduplicated by place ID and capped at
12 candidates for downstream work.

### 8.2 Query evidence

When Google returns a restaurant for a dish-oriented query, CraveAI creates a
`provider_query` evidence item:

```text
quality: 0.55
label: exact search query
declared_constraint_ids: constraints represented by that query
retrieval_rank: position in the query result
source_url: Google Maps URL when present
```

This proves only that the provider matched the restaurant to the query. It does
not prove that a specific dish is currently listed.

### 8.3 Merge behavior

Candidates returned by several queries accumulate retrieval evidence and
reciprocal-rank-style retrieval scores. Query rank outranks restaurant rating
during candidate selection. Rating and review count break ties after retrieval
relevance.

The current browser session may supply up to 20 candidate places. Only explicit
cuisine, dish, or dietary tags that overlap the intent become low-quality
`restaurant_tag` evidence with quality `0.35`. Browser data cannot specify
final evidence, scores, or reasons.

If Text Search produces no merged candidates, a bounded legacy provider search
is attempted. It is not the previous rating-based recommendation fallback:
final evidence and scoring gates still apply.

## 9. Official menu evidence

### 9.1 Source selection

For the first ten candidates that have an official website, CraveAI:

1. fetches the official website supplied by Google Places;
2. recognizes when the starting URL itself is a menu/order page;
3. selects at most two explicit menu/order links; and
4. extracts evidence only from the starting menu context or followed
   menu/order pages.

Generic homepage prose is not treated as menu evidence. This avoids converting
testimonials, marketing copy, or navigation fragments into dishes.

### 9.2 Structured extraction

The HTML parser extracts schema.org JSON-LD objects whose `@type` is
`MenuItem` or `Product`. Names and descriptions are kept together, deduplicated,
and lexically filtered against constraint, candidate-dish, and search-query
terms.

Structured official menu items receive quality `1.0`.

### 9.3 Visible menu-page fallback

When structured items are unavailable, short visible blocks from an explicit
menu/order page may become `official_website` evidence. They receive quality
`0.8`. Adjacent text nodes are not fused, because combining neighboring menu
lines can manufacture a nonexistent dish.

### 9.4 Resource and network protections

Menu retrieval is intentionally bounded:

| Boundary | Value |
| --- | ---: |
| Candidate websites | 10 |
| Menu/order links per website | 2 |
| Selected structured items per candidate | 14 |
| Concurrent site fetches | 5 |
| Fetch timeout | 5 seconds |
| Maximum response body | 1.5 MB |
| Redirects | 3 |
| Allowed schemes | HTTP, HTTPS |
| Allowed ports | 80, 443 |

Every starting URL and redirect is validated. Credential-bearing URLs,
localhost, loopback, private, link-local, reserved, multicast, and unspecified
addresses are rejected after DNS resolution. Only HTML/XHTML responses are
accepted. The fetcher does not execute JavaScript, parse PDFs, authenticate, or
bypass access controls.

### 9.5 Persistence policy

Fetched menu evidence is request-scoped and is not persisted. Google Places
content is also not used to create a durable menu cache. A production-scale
corpus should come from merchant-supplied or licensed structured feeds with
explicit freshness and storage rights.

## 10. Evidence assessment

### 10.1 Restricted model task

`backend/services/evidence_ranker.py` supplies the model with:

- known constraint IDs;
- known place IDs; and
- up to ten known evidence items per candidate.

The only permitted output connects a known evidence ID to known constraint IDs
with `supports` or `violates` stance. The model cannot output:

- restaurants;
- menu items;
- new evidence IDs;
- new constraint IDs;
- scores;
- confidence;
- ranking order; or
- explanation text.

Candidate and website content is explicitly treated as untrusted reference
data, not instructions.

### 10.2 Validation and fallback

All returned IDs are checked against the supplied sets. Unknown place,
evidence, and constraint IDs are discarded. Deterministic lexical evidence
links are merged with semantic links, ensuring that literal matches do not
disappear because of model variance.

If the assessment call fails or reaches its 10.5-second cap, scoring continues
with lexical assessments. A model outage therefore reduces semantic recall but
does not authorize ungrounded output.

## 11. Deterministic scoring

### 11.1 Constraint weights

```text
required  = 4
strong    = 3
preferred = 2
weak      = 1
```

For each inclusion constraint, satisfaction is the maximum quality of any
usable supporting evidence item.

### 11.2 Hard evidence gates

Before a numeric score is accepted:

1. every required inclusion must have satisfaction >= `0.8`;
2. every strong inclusion must have satisfaction >= `0.5`;
3. at least 70% of the weighted inclusion constraints must have satisfaction
   >= `0.5`; and
4. when multiple inclusion constraints exist, one coherent evidence item must
   cover at least 70% of their total weight.

The last rule prevents cross-dish aggregation. Additional combo markers—such as
`bento`, `combo`, `platter`, `served with`, and `comes with`—cause multi-trait
support to be rejected unless the traits are present together in the item name.

### 11.3 Coverage

```text
total_weight = sum(weight(constraint))

coverage = sum(
    weight(constraint) * satisfaction(constraint)
) / total_weight
```

### 11.4 Joint coverage

For each evidence item:

```text
supported_weight_ratio =
    sum(weight(coherently supported constraint)) / total_weight

item_joint_coverage = supported_weight_ratio * evidence_quality
```

`joint_coverage` is the maximum over usable evidence items.

### 11.5 Retrieval relevance

The best provider-query rank contributes:

```text
retrieval_relevance = 1 / (1 + 0.18 * (rank - 1))
```

This signal helps distinguish candidates found near the top of a relevant dish
query, but provider rank is still weaker than official food evidence.

### 11.6 Final score

```text
food_relevance = 0.60 * coverage
               + 0.30 * joint_coverage
               + 0.10 * retrieval_relevance

rating_quality = clamp((rating - 3.0) / 2.0, 0.0, 1.0)

overall_score = 0.82 * food_relevance
              + 0.13 * evidence_strength
              + 0.05 * rating_quality
```

`evidence_strength` is the strongest usable supporting evidence quality. Scores
below `0.58` are rejected. Eligible results are sorted by score, with rating
only as a final tie-breaker, and truncated to a maximum of three.

There is no minimum result count.

## 12. Confidence and explanation generation

### 12.1 Confidence

Current output uses `high` or `medium` confidence:

- `high`: every required/strong constraint has structured official-menu
  support and a coherent structured menu item covers at least 80% of weighted
  inclusion constraints;
- `medium`: the candidate passes relevance gates but support includes visible
  official-site text, provider query evidence, or weaker coherence.

Confidence is deliberately separate from match score. A candidate can have a
good semantic match but only medium confidence because its current menu was not
available as structured data.

### 12.2 Display evidence

Evidence is ordered using constraint weight, evidence quality, evidence kind,
and literal dish-name matches. Short official-site item names may appear in
`matching_dishes`; prose descriptions do not.

### 12.3 Explanations

Explanation text is deterministic. It can state:

- `Official menu evidence: <selected item names>. Matches <preferences>.`
- `Official-site menu evidence mentions <selected label>.`
- `Google Maps matched this restaurant to <query>. Menu not verified.`

If one preference is supported only by provider retrieval while another has
official evidence, the reason explicitly marks the provider-only portion as
unverified. The model never writes the final prose.

## 13. Failure semantics

| Failure | Behavior |
| --- | --- |
| Intent model failure | Use conservative local intent parser |
| One Places query fails | Continue with other query results |
| All Text Search queries empty | Attempt bounded legacy provider retrieval |
| Official menu unavailable | Retain weaker provider/tag evidence; confidence remains limited |
| Evidence assessment failure | Use deterministic lexical links |
| No candidate passes evidence gates | Return zero recommendations |
| Total pipeline timeout | Return zero recommendations with a transparent retry/relaxation message |
| Unexpected pipeline exception | Return zero recommendations; never invoke rating filler |

Stage logs record timings and counts without logging chat content or menu bodies.

## 14. API and frontend changes

### 14.1 Recommendation response

Each recommendation can now include:

```json
{
  "restaurant": "represented by name/place_id fields",
  "match_score": 0.91,
  "confidence": "high",
  "matching_dishes": ["Tom Yum Noodle Soup"],
  "matched_preferences": ["spicy", "soup"],
  "unmatched_preferences": [],
  "evidence": [
    {
      "type": "official_menu",
      "label": "Tom Yum Noodle Soup",
      "source_url": "https://restaurant.example/menu"
    }
  ],
  "reason": "Official menu evidence: Tom Yum Noodle Soup. Matches spicy, soup."
}
```

The top-level response also exposes the normalized intent used during ranking.
This is useful for debugging phrases such as `maybe`, `must`, and `not`.

### 14.2 Frontend presentation

`frontend/src/components/ChatPanel.tsx` displays:

- strong/relevant match state;
- match percentage;
- matched and unmatched preference chips;
- named matching dishes;
- grounded reason text; and
- evidence source links.

The frontend does not infer evidence or transform provider matches into menu
claims. It renders the backend's typed result.

## 15. Security and trust boundaries

The overhaul introduced outbound requests to official restaurant sites, so the
implementation treats URL handling as a security boundary.

Controls include:

- server-derived official website URLs from Google Places;
- HTTP(S)-only requests on ports 80/443;
- per-hop DNS and address validation;
- manual redirect validation;
- content-type and byte limits;
- bounded concurrency and page count;
- no scripts, browser automation, credentials, or access-control bypass;
- untrusted-content instructions in the evidence prompt; and
- validated model IDs before scoring.

Important residual boundary: the current fetcher does not consult `robots.txt`
or negotiate source-specific reuse terms. Before broad crawling or persistence,
CraveAI should move to direct merchant integrations or licensed menu feeds and
complete a source-policy review.

## 16. Evaluation framework

### 16.1 Dataset

`evaluation/craving_cases.json` contains 20 human-authored cases:

1. spicy, maybe soup;
2. crispy but not heavy;
3. creamy and spicy;
4. refreshing and healthy;
5. beef, preferably noodles;
6. cheesy and comforting;
7. cold dessert, not ice cream;
8. super spicy;
9. soup;
10. maybe sushi, but warm;
11. high protein and cheap;
12. sweet and salty;
13. Korean, not fried;
14. vegan comfort food;
15. halal and grilled, not fried;
16. gluten-free pizza;
17. savory vegetarian breakfast;
18. light citrus seafood;
19. crunchy chocolate dessert; and
20. Mexican, high protein, low carb.

Each case defines structured constraints and two coherent positive dishes. The
runner generates:

- two relevant candidates with one coherent matching dish each;
- an aggregate trap whose separate dishes cover different constraints;
- a popular partial match; and
- a highly rated irrelevant candidate.

### 16.2 Comparison method

The old side is a deterministic proxy for the previous information boundary:
restaurant-level aggregate traits plus rating, no menu evidence, and three
forced results. It is not a replay of nondeterministic historical model output.

The new side invokes the production constraint/evidence scorer with labeled
dish evidence. Intent and evidence labels are human-authored, isolating the
scoring and evidence-gating layer from live provider variability.

Run:

```powershell
python scripts\evaluate_recommendations.py --json
```

### 16.3 Results

| Metric | Previous proxy | Evidence-grounded scorer | Change |
| --- | ---: | ---: | ---: |
| Precision@3 | 0.4333 | 0.6667 | +0.2334 |
| Recall@3 | 0.6500 | 1.0000 | +0.3500 |
| NDCG@3 | 0.4307 | 1.0000 | +0.5693 |
| Constraint satisfaction | 0.4333 | 1.0000 | +0.5667 |
| Unsupported-claim rate | 0.5667 | 0.0000 | -0.5667 |
| Menu-evidence coverage | 0.0000 | 1.0000 | +1.0000 |
| Strong matching-item rate | 0.4333 | 1.0000 | +0.5667 |
| Mean results returned | 3.0000 | 2.0000 | -1.0000 intentionally |

Precision@3 tops out at `2/3` in this fixture because exactly two candidates are
labeled relevant and the new engine intentionally leaves the third slot empty.

### 16.4 What the benchmark proves

It provides reproducible evidence that the production scorer:

- ranks coherent dish matches before aggregate traps;
- does not let rating compensate for poor relevance;
- rejects unsupported filler; and
- returns fewer results when the labeled candidate set contains fewer strong
  matches.

### 16.5 What the benchmark does not prove

It does not measure:

- live Google Places recall;
- official menu parsing coverage across geographies;
- end-to-end intent-model accuracy;
- restaurant closure or item availability;
- menu freshness;
- user satisfaction, saves, clicks, or conversion;
- result diversity;
- distance/price preference calibration; or
- production latency under provider load.

These limitations are intentionally stated in the script output and top-level
documentation.

## 17. Regression result

### 17.1 Before

For the screenshot query, the old system displayed:

1. The Franklin House
2. Brasas Churrasqueira Rotisserie & Grill
3. Axia Restaurant

The first two lacked coherent spicy-soup evidence.

### 17.2 Current live result

A final live run near Streetsville returned:

| Rank | Restaurant | Score | Confidence | Selected official evidence |
| ---: | --- | ---: | --- | --- |
| 1 | Dear Saigon Mississauga | 0.790 | Medium | Hue's Style Spicy Beef Noodle Soup |
| 2 | Shi Miaodao (Ten Seconds) Yunnan Rice Noodle | 0.769 | Medium | Szechuan Mala Spicy Rice Noodle Soup; Szechuan Mala Spicy Beef Flank Rice Noodle Soup |
| 3 | Fortune Dragon Chinese Restaurant | 0.764 | Medium | Spicy/tangy soup description and Hot & Sour Soup menu evidence |

Franklin House and Brasas were absent.

Another live run ranked Axia first at `0.941`, high confidence, based on
structured official menu evidence for Tom Yum Noodle Soup. The differing pools
illustrate a remaining reality: Google result ordering, model query expansion,
site availability, and network timing can change live candidates. Both runs
remained evidence-grounded and excluded the known poor matches.

In a separate fixed-intent snapshot for this query, 5 of 12 retrieved candidates
produced usable official menu/site evidence, or 41.7%. This is a one-query
diagnostic—not a general menu-coverage claim.

## 18. Test coverage and verification

New recommendation-specific regressions cover:

- `maybe` versus direct versus required preference strength;
- exclusions in the local parser;
- JSON-LD menu extraction;
- prevention of adjacent menu-line fusion;
- localhost/private-network URL rejection;
- multi-query place deduplication and evidence retention;
- Axia versus Franklin/Brasas same-dish behavior;
- rejection of provider-only evidence for required constraints;
- explicit unverified wording for provider-only results;
- combo/bento cross-component rejection;
- official-site menu names in `matching_dishes`;
- dish-level exclusion behavior;
- rejection of unknown evidence IDs; and
- zero-result timeout behavior instead of rating fallback.

Final verification on the implementation tree:

| Check | Result |
| --- | --- |
| Backend pytest | 48 passed |
| Frontend Vitest | 37 passed across 11 files |
| Frontend ESLint | Passed with zero warnings allowed |
| Frontend production build | Passed |
| Python compilation | Passed |
| Controlled recommendation evaluation | Passed, 20 cases |
| Synthetic API framework benchmark | About 81 ms average for 3 local requests |

The synthetic latency benchmark replaces recommendation provider work with a
short stub. It measures API/middleware/serialization overhead, not live
end-to-end recommendation latency.

## 19. File-level change inventory

### 19.1 New backend modules

| File | Purpose |
| --- | --- |
| `backend/services/recommendation_models.py` | Typed intent, evidence, and assessment contracts |
| `backend/services/craving_intent.py` | Structured extraction, normalization, and local fallback |
| `backend/services/restaurant_retrieval.py` | Text Search retrieval, evidence creation, deduplication, and candidate cap |
| `backend/services/menu_evidence.py` | Safe official-site fetching and menu extraction |
| `backend/services/evidence_ranker.py` | Validated evidence mapping, deterministic scoring, confidence, explanations |

### 19.2 Reworked backend modules

| File | Change |
| --- | --- |
| `backend/services/rag_pipeline.py` | Replaced one-shot ranking with staged orchestration and fail-closed result behavior |
| `backend/routers/chat.py` | Added intent, score, confidence, dish, preference, and evidence response fields |
| `backend/requirements.txt` | Removed unused LangChain dependency and pinned OpenAI SDK 2.x support |

### 19.3 Frontend changes

| File | Change |
| --- | --- |
| `frontend/src/api/chat.ts` | Added typed recommendation evidence fields |
| `frontend/src/components/ChatPanel.tsx` | Added match/confidence state, dishes, preferences, and evidence links |
| `frontend/src/index.css` | Added supporting result styles |

### 19.4 Evaluation and tests

| File | Purpose |
| --- | --- |
| `evaluation/craving_cases.json` | Twenty-case labeled dataset |
| `scripts/evaluate_recommendations.py` | Metrics and controlled before/after runner |
| `tests/test_recommendation_quality.py` | Intent, retrieval, evidence, security, and ranking regressions |
| `tests/test_recommendation_evaluation.py` | Dataset and metric gates |
| `tests/test_chat_pipeline.py` | Updated chat orchestration fixtures; removed obsolete LangChain shims |
| `scripts/benchmark_latency.py` | Updated isolated benchmark without obsolete recommendation dependencies |

### 19.5 Documentation

| File | Change |
| --- | --- |
| `README.md` | Rewritten as the current contributor and operator entry point |
| `docs/technical_design.md` | Replaced fictional vector architecture with the running design |
| `docs/PRD.md` | Marked as historical where it describes unimplemented LangChain/vector plans |
| `docs/recommendation_engine_overhaul.md` | This detailed implementation and change record |

## 20. Operational considerations

### 20.1 Cost and latency

One recommendation can involve:

- one intent-model request;
- two to four parallel Places Text Search requests;
- up to ten official sites, with at most two menu/order links each; and
- one evidence-assessment model request.

The stages are bounded and parallelized where practical, but the menu and model
calls make this materially more expensive than the old one-shot path. Accuracy
was the primary objective. Production telemetry should measure per-stage
latency, evidence coverage, provider cost, and zero-result rate before raising
the current caps.

### 20.2 No durable menu cache

Not caching avoids stale evidence and policy risks, but repeats work across
similar requests. The preferred future optimization is a licensed structured
menu source rather than an indiscriminate scrape cache.

### 20.3 Zero-result behavior

A higher zero-result rate can be a sign that evidence gates are working, not
necessarily a regression. It should be evaluated alongside:

- verified dish coverage;
- user reformulation rate;
- saves/clicks per returned result;
- unsupported-claim audits; and
- geographic/provider coverage.

## 21. Remaining limitations

### Data availability

- Google Places has useful place metadata and query relevance but no universal
  full-menu field.
- Official menu pages vary widely in markup and availability.
- JavaScript-only apps, PDFs, anti-bot systems, expired links, and slow sites can
  leave a candidate without verified evidence.
- Menu presence does not guarantee current item availability.

### Retrieval and ranking

- Provider-only query evidence can still be noisy; it is clearly labeled and
  cannot satisfy required positive constraints.
- Distance is bounded geographically but not explicitly calibrated in the final
  score.
- Price evidence is limited and does not yet compare actual dish prices.
- No diversity objective prevents several similar restaurants from occupying
  all available slots.
- Intent and semantic evidence calls can vary, although their outputs are
  bounded and deterministic gates retain final authority.

### Dietary safety

- Official menu wording is not enough to guarantee allergen handling,
  certification, kitchen separation, or cross-contamination safety.
- CraveAI must not be represented as a medical or allergy-safety system.

### Evaluation

- Twenty synthetic cases are useful for regression but too small for a product
  quality estimate.
- The set does not contain geographically sampled real restaurants.
- There are no inter-annotator agreement measurements or real behavioral
  labels yet.

### Source policy

- Public official pages are fetched ephemerally, but broad production crawling
  still requires a robots/terms review or direct data agreements.

## 22. Further improvements ranked by expected impact

### 1. Licensed or merchant-supplied structured menus

Expected impact: very high.

Store stable restaurant and item IDs, item names/descriptions, prices, dietary
metadata, availability, and freshness timestamps. This improves both retrieval
recall and evidence confidence while reducing live website latency and policy
risk.

### 2. Live, human-adjudicated evaluation

Expected impact: very high.

Sample real cravings, geographies, and candidate pools. Have multiple reviewers
judge dish relevance, constraint satisfaction, evidence validity, and ranking.
Track retrieval recall separately from ranking precision.

### 3. Hybrid dish retrieval after a reliable corpus exists

Expected impact: high.

Add lexical BM25 plus dense embeddings over individual menu items and structured
metadata. Evaluate the hybrid retriever against the current Places-query path.
Do not embed restaurant names/tags and call that dish retrieval.

### 4. Learned reranking and score calibration

Expected impact: high after labels exist.

Train or calibrate a compact cross-encoder/reranker using human relevance data.
Retain hard constraint and evidence gates outside the learned score.

### 5. Distance, price, availability, and diversity objectives

Expected impact: medium-high.

Add calibrated distance decay, dish-price evidence, open-now/availability
signals, and explicit result diversification after food relevance has passed.

### 6. Opt-in personalization

Expected impact: medium.

Use prior likes, dislikes, price sensitivity, travel tolerance, and cuisine
preferences only after current hard constraints are satisfied. Personalization
must not override dietary requirements or explicit exclusions.

### 7. Evidence freshness and source observability

Expected impact: medium.

Record request-scoped freshness timestamps, parser success categories, source
types, and geographic coverage metrics without retaining prohibited provider
content or chat text.

## 23. Acceptance criteria achieved

- The current pipeline has been traced and the prior failure explained.
- The stale vector-database description has been corrected.
- Intent is structured and strength-aware.
- Retrieval is dish-oriented and location-bounded.
- Official menu evidence is attempted for nearby candidates.
- Required/strong preferences and exclusions affect eligibility.
- Multi-part cravings require coherent dish evidence.
- Ratings cannot compensate for poor food relevance.
- Explanations cannot introduce unknown dishes or unsupported characteristics.
- Results below the confidence threshold are omitted rather than backfilled.
- The spicy-soup regression excludes Franklin House and Brasas in live testing.
- A reproducible 20-case evaluation and quality regression suite exists.
- API and frontend expose evidence, dishes, matched preferences, confidence, and
  score.
- Limitations and next improvements are documented without overstating the
  controlled benchmark.
