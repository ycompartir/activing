# Branded "N app tricks" reel template

Makes a vertical **1080×1920, 30fps** reel (H.264 + AAC) in the **keepmesignedin.com** look. Every image, animation and the soundtrack is generated in code.
You write one JSON file per reel, and the engine takes care of layout, timing, animation and music.

```
reels/
  template/
    reelgen.py        # the engine
    brand/            # Space Grotesk, Inter, JetBrains Mono (from keepmesignedin.com) + K mark
  whatsapp-tricks/reel.json     # example: chat-style screens
  gmail-tricks/reel.json        # example: menu → sheet and swipe screens
  instagram-settings/reel.json  # example: settings → toggle screens
```

## Make a new reel

1. Copy an example folder: `cp -r reels/whatsapp-tricks reels/my-new-reel`
2. Edit `reels/my-new-reel/reel.json` (schema below).
3. Preview stills first (takes about 10s). They land in `reels/my-new-reel/stills/`:

   ```bash
   python3 reels/template/reelgen.py reels/my-new-reel/reel.json --stills
   ```

4. Render the video. This writes `reels/my-new-reel/reel.mp4`:

   ```bash
   python3 reels/template/reelgen.py reels/my-new-reel/reel.json
   ```

Every run (video or stills) also writes:
- `cover.png`: the hook at full reveal, to use as the Reels or TikTok cover.
- `post.txt`: the caption plus hashtags, if the JSON has a `"post"` block.
- `youtube.txt`: YouTube Shorts title, alternative titles, description, tags, hashtags and upload settings, if the JSON has a `"youtube"` block. You'll get a warning if a field goes over YouTube's limits.

Only need the metadata? Use `--meta`. It takes a few seconds and doesn't re-render the video:

```bash
python3 reels/template/reelgen.py reels/my-new-reel/reel.json --meta
```

Requirements: Python 3 with `pillow` and `numpy`, plus `ffmpeg`.

## Timing

Hook **3s**, then **5s per trick**, then the CTA **2s**. With 3 tricks the reel is exactly **20s**. You can use 1 to 5 tricks.

## JSON schema

```jsonc
{
  "output": "reel.mp4",              // file name, written next to the JSON
  "handle": "@keepmesignedin",       // watermark (bottom right, with the K mark)
  "badge": "TRICK",                  // label on each trick: "TRICK #1", "SETTING #2", "HACK #3"...

  "app": {                           // colors of the phone mockup (light-mode screens)
    "name": "WhatsApp",
    "header": "#008069",             // top bar color
    "header_text": "#FFFFFF",        // optional, picked automatically from the header color
    "screen_bg": "#ECE5DD",          // screen background
    "bubble_out": "#D9FDD3",         // your sent messages
    "bubble_in": "#FFFFFF",          // optional
    "accent": "#25D366",             // highlights and switches when on
    "send": "#008069",               // optional, send button color
    "touch": "light"                 // finger-tap color: "light" on colored screens, "dark" on white screens
  },

  "hook": {
    "kicker": "APP TIPS · WHATSAPP", // small mono label at the top
    "number": "3",                   // optional, defaults to the number of tricks
    "line1": "WhatsApp tricks",      // big headline
    "line2": "nobody told you",      // second line, with the amber highlighter
    "teaser": "#2 will change how you take notes"   // optional curiosity line
  },

  "tricks": [
    {
      "title": "Format your texts",  // headline above the phone
      "chip": "Format",              // short name for the CTA chips "1 Format"
      "screen": { "type": "...", ... },   // see "Screen types"
      "captions": [
        ["Line 1 (cream)", "Line 2 (amber)"],   // shown before the action
        ["Line 1", "Line 2"]                     // shown after the action
      ]
    }
  ],

  "post": {                          // optional: writes post.txt next to the video
    "caption": "Caption text…",
    "hashtags": ["gmail", "techtips"]
  },

  "youtube": {                       // optional: writes youtube.txt (YouTube Shorts metadata)
    "title": "3 Gmail Tricks for a Calmer Inbox 📥 #gmail #shorts",   // max 100 chars
    "alt_titles": ["…", "…"],
    "description": "…",              // optional: auto-built from the tricks + captions if omitted
    "tags": ["gmail tricks", "…"],   // max 500 chars total (checked)
    "hashtags": ["gmail", "gmailtips", "productivity"],   // first 3 show above the title
    "category": "Howto & Style",
    "pinned_comment": "Which one are you trying first? 👇"
  },

  "cta": {
    "line1": "Which trick",
    "line2": "was new to you?",
    "prompt": "COMMENT THE NUMBER",
    "button": "Follow @keepmesignedin",
    "chips": ["Format", "Notes", "Pin"]   // optional, defaults to each trick's "chip"
  }
}
```

Message text supports WhatsApp-style formatting: `*bold*`, `_italic_`, `~strike~`, `` `mono` `` (or ```` ```mono``` ````).
Text that is too long shrinks automatically to fit.

## Screen types

| `type` | What it animates | Fields |
|---|---|---|
| `chat_send` | Typing in a chat, tapping send, then the message pops in | `contact`, `contact_sub`, `incoming` (list of messages), `type_text` (what gets typed), `sent` (how the sent message looks) |
| `search_open` | Typing in search, the list filters down, tapping the result, then items pop in on the next screen | `list_title`, `query`, `result` `[name, subtitle]`, `others` `[[name, msg, time], ...]`, `open_title`, `open_sub`, `items` (list of messages) |
| `long_press_pin` | Long-pressing a row, the toolbar appears, tapping pin, then the row slides to the top | `list_title`, `rows` `[[name, msg, time], ...]` (up to 6), `target` (index of the row to pin) |
| `menu_pick` | Tapping the 3-dot menu, picking an item, picking an option in the bottom sheet (optional), then an "Undo" pop-up confirms | `base` (`"compose"` or `"email"`), compose: `from`, `to`, `subject`, `body` (paragraphs); email: `subject`, `sender`, `time`, `body`. Then `menu` (items), `pick` (index), `sheet_title`, `sheet` `[[label, detail], ...]`, `sheet_pick`, `toast`, `toast_action` |
| `swipe_action` | An inbox list, swiping one row away to reveal the action, the gap closing, then an "Undo" pop-up | `list_title`, `section`, `rows` `[[sender, subject, snippet, time], ...]` (up to 5), `target`, `direction` (`"left"` or `"right"`), `action_label`, `action_color`, `toast`, `toast_action` |
| `settings_toggle` | A settings list, tapping a row, the detail page slides in, then a switch flips | `title`, `rows` (labels, up to 7), `tap` (index), `detail_title`, `detail_text`, `toggle_label`, `toggle_sub`, `start_on` (`true` animates the switch turning **off**) |

You can mix screen types in the same reel.

## Content checklist before posting

- Check every menu path and limit (for example "up to 3 pinned chats") in the current version of the app.
- The phone screens are stylized mockups. Don't add official app logos.
