# Inter

CraveAI serves the unmodified Inter 4.1 variable fonts locally. Normal and italic
faces both use the application's single Inter family and support weights
100–900. Only the normal face is preloaded; italic loads when needed.

Upstream: https://rsms.me/inter/download/

Font files:

- https://rsms.me/inter/font-files/InterVariable.woff2?v=4.1
- https://rsms.me/inter/font-files/InterVariable-Italic.woff2?v=4.1

The fonts are distributed under the SIL Open Font License 1.1. The upstream
copyright notice and complete license are included in LICENSE.txt, downloaded
from https://raw.githubusercontent.com/rsms/inter/v4.1/LICENSE.txt.

The shared CSS token is `--font-family-sans`. The preload and
`font-display: optional` allow Inter to render immediately when available while
retaining the consistent system sans-serif fallback for a slow or failed font
request, without switching families later in that page view.
