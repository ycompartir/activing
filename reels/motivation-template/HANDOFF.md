# Handoff: next MotivationDeeply reels (for the next Claude session)

Start sessions for this channel on the **motivationdeeply** cloud environment. It allows Pixabay, Openverse (+ Wikimedia and Flickr), YouTube and package registries. The Pixabay key is in the env var `PIXABAY_API_KEY`. Never print it or commit it.

## Who and how
- Owner runs two channels: @keepmesignedin (tech tutorials, `reels/template/`) and **@motivationdeeply** (this template).
- All on-screen text, captions and metadata are in **US English**. The owner writes in Spanish and has asked for **explanations in Spanish (castellano)**.
- The approved format is `motivegen.py` (no anime): 29s = hook 3.5s + 3 items × 7.5s + CTA 3s. B&W cinematic scenes, logo on top, handwritten caps (Architects Daughter), one red key word (`*WORD*`), author in spaced caps, piano/pad music + SFX, no voiceover.
- Deliver per reel: `reel.mp4`, `cover.png`, `post.txt`, `youtube.txt`. Send them to the user with **distinct names** (e.g. `motivationdeeply-<topic>.mp4`, `post-motivationdeeply-<topic>.txt`). Commit and push to the working branch.

## Next task
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
