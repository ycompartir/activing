# MotivationDeeply reel template

Makes a vertical 1080×1920, 30fps reel in the **@motivationdeeply** style:
- Moody black-and-white scenes, generated in code (no stock footage).
- The MotivationDeeply logo at the top.
- Handwritten capitals (Architects Daughter) with **one key word in red** (`#D44545`, sampled from the logo's brush stroke).
- The author's name in spaced capitals, and a red brush stroke under each label.
- Piano and ambient pad music with reverb, plus sound effects: thunder synced to lightning, a whoosh into each scene, a deep boom on each label and a bell on the logo. No voiceover.

Structure: **hook 3.5s + 7.5s per item + CTA 3s** (3 items = 29s). You can change the timing with `"pace": {"hook": 3.5, "item": 7.5, "cta": 3}`.

## Make a reel

```bash
python3 reels/motivation-template/motivegen.py reels/<folder>/reel.json --stills   # preview frames
python3 reels/motivation-template/motivegen.py reels/<folder>/reel.json            # video
python3 reels/motivation-template/motivegen.py reels/<folder>/reel.json --meta     # cover.png, post.txt, youtube.txt only
```

Each render writes `reel.mp4` (capped at about 10 Mbps, roughly 25 MB), plus `cover.png`, `post.txt` and `youtube.txt`.

## reel.json

```jsonc
{
  "output": "reel.mp4",
  "label": "RULE",                                  // items are labelled "RULE I", "RULE II"…
  "hook":  { "scene": "storm", "flashes": [0.35, 2.15],   // lightning (and thunder) times
             "kicker": "READ THIS ON A HARD DAY",
             "text": "3 STOIC RULES FOR *HARD* DAYS" },    // *word* = red
  "items": [
    { "scene": "night_sea", "text": "WE SUFFER MORE OFTEN IN *IMAGINATION* THAN IN REALITY.", "author": "SENECA" },
    { "scene": "fog_mountains", "label": "OPTIONAL CUSTOM LABEL", "text": "…", "author": "…" }
  ],
  "cta":   { "scene": {"name": "light_break", "start": 0.75},
             "text": "SAVE THIS FOR THE DAY YOU *NEED* IT.", "follow": "FOLLOW @MOTIVATIONDEEPLY" },
  "post":    { "caption": "…", "hashtags": ["…"] },
  "youtube": { "title": "…", "alt_titles": [], "description": "…", "tags": [], "hashtags": [], "category": "People & Blogs", "pinned_comment": "…" }
}
```

## Scenes

| `scene` | Look |
|---|---|
| `storm` | Dark, drifting storm clouds over a black sea, with lightning on the right edge (thunder in the audio) |
| `night_sea` | Night sky with stars, a low moon and a shimmering moonlight path on the water |
| `fog_mountains` | Layered mountain ridges in fog, with a lone figure standing on the nearest peak |
| `light_break` | Sun breaking through clouds behind mountains, with light rays. `start` (0–1) sets how open the sky is |

Write all text in CAPITALS to match the channel's style. A long quote shrinks to fit automatically.
