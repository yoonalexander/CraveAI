# CraveAI launch video

- `brag.mp4`: 20.000 seconds, 1920×1080, 30 fps, H.264/AAC, stereo audio, fast-start playback.
- `brag-fixed.mp4`: the corrected render under a fresh filename for playback without an old preview cache.
- `brag.jpg`: settled opening poster, also baked into frame zero of the video.
- `share-copy.txt`: ready-to-post caption and product link.
- `brag-plan.md`: story, pacing, sources and creative direction.
- `work/`: editable HyperFrames composition, source builder, original soundtrack, stills and verification logs.

The film follows a specific craving through chat, menu evidence, and a nearby destination. The pin, Inter font files, original styles and React components come directly from CraveAI. `ChatPanel` and `MapRestaurantList` are server-rendered from the repository; presentation framing is tailored for video. Restaurant/menu data is illustrative and visibly labeled; the map is an illustrative backdrop. No provider requests were used to generate recommendations, images or music.

The soundtrack is an original, locally synthesized 96 BPM composition with warm chords, plucks, restrained percussion, and tonal cues in the same key. It contains no external music samples or voiceover.

To rebuild, run these commands from `work/`:

```powershell
node build.mjs
python music.py
npm.cmd run check
npx.cmd --yes hyperframes@0.8.106 render . --output launch-render.mp4 --fps 30 --quality delivery --workers 1 --low-memory-mode --strict
.\finalize.ps1
python review.py
python jitter-check.py
```

FFmpeg and FFprobe must be on PATH for the render command. `finalize.ps1` records the installed local encoder path. The builder reuses the repository's installed frontend packages. All project changes for this deliverable are contained in `brag-output/`.

Validation: runtime and motion checks passed; 70/70 sampled text checks passed contrast validation; all scenes and transitions were reviewed as stills. Lint warnings concern repeated use of the original logo and keeping five scenes in one editable composition. The small full-frame translation during scene entrances intentionally extends the scene wrapper beyond its clipping boundary. Final metadata, a full decode check, audio measurements, and decoded frame previews are retained under `work/`.

The jitter repair gives every delayed scene/element an initially hidden state, so it appears only when its entrance runs. The opening holds its settled pose so the baked poster does not jump into another position on frame one. `work/jitter-check.py` inspects decoded frames around all four cuts and the opening. `jitter-before.json` reproduces the previous flashes; `jitter-verification.json` records the corrected result. The previous video is retained as `work/pre-fix.mp4`.
