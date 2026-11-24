# Handoff: next MotivationDeeply reels (for the next Claude session)

Start sessions for this channel on the **motivationdeeply** cloud environment. It allows Pixabay, Openverse (+ Wikimedia and Flickr), YouTube and package registries. The Pixabay key is in the env var `PIXABAY_API_KEY`. Never print it or commit it.

## Who and how
- Owner runs two channels: @keepmesignedin (tech tutorials, `reels/template/`) and **@motivationdeeply** (this template).
- All on-screen text, captions and metadata are in **US English**. The owner writes in Spanish and has asked for **explanations in Spanish (castellano)**.
- The approved format is `motivegen.py` (no anime): 29s = hook 3.5s + 3 items × 7.5s + CTA 3s. B&W cinematic scenes, logo on top, handwritten caps (Architects Daughter), one red key word (`*WORD*`), author in spaced caps, piano/pad music + SFX, no voiceover.
- Deliver per reel: `reel.mp4`, `cover.png`, `post.txt`, `youtube.txt`. Send them to the user with **distinct names** (e.g. `motivationdeeply-<topic>.mp4`, `post-motivationdeeply-<topic>.txt`). Commit and push to the working branch.

## Roles (decided by the owner, Nov 2026)
- **Claude is producer and director.** The owner trusts Claude's judgment: choose topics, quotes, backgrounds, grading and pacing yourself, review your own stills critically, fix what doesn't work, and deliver finished reels. Don't stop for approval of backgrounds or test frames.
- The owner acts as **advisor and, for some reels, scriptwriter**. When the owner provides a script or notes, follow them; otherwise the reels should "work on their own".
- Still explain what you did in Spanish at the end, briefly, with the deliverables.

## Font (decided by the owner, Nov 2026)
- The owner's own font in Canva is **FF Providence Sans** (commercial, can't be extracted from Canva). For our reels they chose the free lookalike **Patrick Hand** (regular, not SC). It is the default in `motivegen.py`; older reels pin `"font": "architects-daughter"`.

## Done (Nov 2026)
- `stock` scenes (Pixabay video/photo, Openverse fallback) are in `motivegen.py` and documented in the README.
- The 4 reels below were rendered with stock backgrounds on the items (hook storm and CTA light break kept as the channel signature) and delivered.
- Direction notes learned: skip clip intros where the subject is cut off (`start`), dim bright skies and light sources behind the text (`level` 0.6–0.8), move bright spots out of the text area with `focus`, and check that the red key word stays readable.
- Ideas for next reels: vary the hook too (e.g. a stock rain clip with no thunder), and avoid reusing clip ids already in other reel.json files.

## Previous task (done)
The 4 reels are drafted with text in their `reel.json` files (quotes checked; "MS. DEEPLY" = the channel's own lines, as the channel already does):
1. `reels/motivation-stop-doing/`: 3 things to stop doing if you want to grow
2. `reels/motivation-success-truths/`: 3 truths nobody tells you about success
3. `reels/motivation-marcus-overthinkers/`: 3 lessons from Marcus Aurelius for overthinkers
4. `reels/motivation-feel-behind/`: 3 quotes for when you feel behind in life

To do:
1. **Add stock backgrounds to `motivegen.py`:** a new scene type `{"name": "stock", "query": "...", "kind": "video"|"photo", "id": <pixabay id, optional>}`.
   - Search the Pixabay API (`https://pixabay.com/api/videos/` and `https://pixabay.com/api/`, key as a URL param), prefer vertical or calm clips, and cache the downloads under `reels/motivation-template/cache/` (gitignored).
   - Convert to B&W (slightly cool or warm tint like the existing scenes), cover-crop to 1080×1920, slow zoom, loop video clips. Keep the existing vignette, text band and grain.
   - Fallback: Openverse CC0/PDM photos (`https://api.openverse.org/v1/images/?q=...&license=cc0,pdm`, no key).
   - Record the chosen asset ids and URLs in `reel.json` so renders are reproducible.
2. Choose fitting backgrounds per item (e.g. rain on a window, an empty road at dawn, a candle in the dark, ocean waves, a forest path in fog, a city at night), and vary them across the 4 reels.
3. Add `post` and `youtube` blocks to each `reel.json` (see `reels/motivation-stoic-rules/reel.json` for tone, hashtags and the Facebook link), render, check stills, and deliver.

Licensing: the Pixabay Content License and CC0 allow free commercial use without attribution. Don't redistribute clips as standalone files.
