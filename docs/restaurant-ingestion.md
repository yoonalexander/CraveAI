# Restaurant database ingestion

Use a single bulk pass over saved public datasets to add map-ready restaurants to the existing Supabase `catalog_restaurants` table. A restaurant needs a source ID, a public name, a street address, and coordinates. Keep the unit when the source provides one. Menus, prices, ratings, hours, and websites are optional.

## What we imported

On November 23, 2026, we took the 2,076 remaining candidates from the original Toronto and Mississauga queue and resolved them in one pass against the saved city exports and existing map listings.

| Final pass | Toronto | Mississauga | Total |
| --- | ---: | ---: | ---: |
| Added to Supabase | 882 | 284 | 1,166 |
| Outside restaurant scope | 98 | 4 | 102 |
| Skipped for unclear eligibility or location | 717 | 91 | 808 |

We published the new IDs as an additive batch and confirmed that all 1,166 rows matched the staged data. The live table reached **10,111 active listings**. It grew by about **0.25 MB** to **2.28 MB**, including indexes. The original 3,386-candidate queue closed with 2,255 additions across all batches and zero pending entries. These counts describe the supplied queue and city exports. [Candidate review](municipal-candidate-review.md) · [Admissions manifest](../data/gta-municipal-admissions.json) · [Disposition ledger](../data/gta-municipal-dispositions.csv)

## Admission rules

| Situation | Decision |
| --- | --- |
| Toronto city record | Add when an active food licence and a passing or conditionally passing DineSafe inspection within the previous year agree on the name and premises. Use the recorded restaurant or takeout type, or the food-service licence and endorsements, to establish public restaurant use. |
| Mississauga city record | Add when the city's food-service directory identifies an eligible venue and the name, street, unit, and coordinates agree with the source record. The 2025 directory establishes the venue as of the survey. Record that source context and skip entries with known conflicts. |
| Existing branch match | Keep the existing listing and its ID. Use the normalized name, street, unit, and nearby coordinates together. Preserve distinct businesses in separate units at the same address. |
| Closed, cancelled, or outside scope | Skip. Examples include wholesalers, private cafeterias, and retail-only shops. |
| Missing location, unclear venue type, conflicting unit, or uncertain duplicate | Close as skipped for this batch. Reopen the candidate only if a later source supplies new evidence that resolves the specific conflict. |

Use the saved city exports and existing map data. The ingestion budget for Google Places calls, reviews, and paid search is **zero**. A Google Maps match, a menu, or an operator website is optional and never holds up a batch. Store source dates and preserve null or empty fields where information is missing.

## Publish and stop

1. **Stage the full batch in one pass.** Load the saved exports and the existing active listing IDs. Apply the admission rules, assign every candidate a final outcome, and save the proposed additions and the disposition ledger. Use the existing source IDs for repeatable imports.
2. **Publish only new IDs.** Generate the additive SQL with `python -m scripts.municipal_catalog_publication --staged <manifest>`, using a manifest that includes the prior admissions. The publication plan checks the hosted ID set before writing. If it differs from the expected baseline, reconcile the two sets before applying the batch. [Publication script](../scripts/municipal_catalog_publication.py)
3. **Verify once at batch level.** Run the verification query from the same plan, confirm the expected added rows and final active ID set, and record the receipt with `--staging-ledger` and `--receipt`. Report the number added for each city, the number skipped, the live total, and table size including indexes.
4. **Close the batch.** Skip row-by-row searches, repeated agent reviews, and optional enrichment during ingestion. Fix a failed import or a broken bulk input, then rerun the affected batch. Unresolved individual records stay skipped until genuinely new evidence arrives. There is no target to admit 100% of the source rows.
