# Issue #25: food illustrations for cuisine discovery

Implementation for [issue #25](https://github.com/yoonalexander/CraveAI/issues/25). This is a frontend change; no migrations, new dependencies or environment settings are needed.

## Behavior and artwork

Home and Discovery share a horizontally scrollable cuisine row with all 18 existing cuisine choices, plus Any cuisine. Each choice pairs a readable name with an original SVG dish illustration. Clicking a selected cuisine deselects it; Any cuisine clears only cuisine. The existing filter state and evidence rules still determine the map and restaurant collection. Functional state updates preserve rapid toggles and other selected filters. Choices are disabled during an area search, then re-enabled with results.

Selected choices have a checkmark as well as a green background and border. Hover, keyboard focus and disabled appearances stay distinct. Touch targets are at least 44px tall; 28px artwork keeps its size on narrow screens. The row scrolls within the toolbar, with a visible exploration hint and a scrollbar where the browser provides one. Every SVG is decorative (`aria-hidden`, `focusable=false`); the cuisine name is the accessible button label. Inter and the existing green palette remain in use, with explicit light/dark styles for the new controls and tags. No motion is introduced.

The advanced selector shows the currently drafted cuisine's icon while retaining a native, explicitly labelled select. Restaurant cards on Home, Discovery and Likes reuse 20px icons beside their first supported cuisine label, falling back to the existing first tag when no label is available. Label source details remain available. Unknown labels keep their text and use a neutral plate illustration; icons do not infer cuisine, a dish's availability or dietary suitability. Discovery's empty state uses the same neutral illustration and retains its guidance.

The set uses food rather than flags or caricatures: a burger, grilled skewers, dumpling, croissant, salad, curry, pasta, sushi, rice bowl, mezze, olives, taco, paella, noodles and soup. Related cuisines intentionally share some dish drawings. Each is a scanning cue alongside its text, not a claim that one dish represents an entire cuisine. All drawings were authored directly for CraveAI in `CuisineIcon.tsx`; no third-party artwork, image fonts, remote assets or licence attribution is required.

Screenshot review also exposed an inherited layout problem in Discovery and Likes: the vertical card's photo container retained the horizontal card's `min-height: 100%`, which could push details below the clipped card. Vertical cards now size the photo container to its contents so names, source links and cuisine tags remain inside the card, including with contributor credits.

## Verification

- Frontend suite: 113 tests passed, covering every catalog icon, normalized labels, neutral fallback, decorative semantics, cuisine tag sources and rapid shared-state toggles.
- Playwright: 60 checks passed across desktop, 390px touch and 320px touch, in both themes. Twelve new checks cover loading, selection/deselection, hover, keyboard focus, advanced selector synchronization, far-end scroll choices, empty results, source links and card geometry. The card clipping check failed before the sizing correction. Existing chat progress, filter and photo checks also pass; the nine photo checks were then extended and passed again with explicit bounds checks for names, cuisine tags and contributor credits in Discovery and Likes.
- Lint and production build passed. TypeScript still reports the same six pre-existing errors, with no new errors.
- Desktop/mobile screenshots were inspected. Browser checks use controlled restaurant/provider fixtures; live Google/OpenAI requests and the hosted release have not been verified.
