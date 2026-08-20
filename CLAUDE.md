# DJ Bot — Project Rules for Claude

## HARD RULE: Keep token/compute usage as cheap as possible without sacrificing quality

Default to the leanest approach that still gets a correct, thorough result:
- Prefer direct tool calls (Bash/Read/Grep/WebSearch) over spawning subagents or
  multi-agent workflows for anything one agent can do inline.
- Never reach for the multi-agent `deep-research` skill or `Workflow` tool for
  research that a few targeted `WebSearch`/`WebFetch` calls can answer.
- Reuse existing code/tests/infrastructure instead of rebuilding — check what
  already exists before writing something new.
- Don't re-read files or re-run checks already covered earlier in the same task.

**This is not a license to cut corners.** When something is safety- or
correctness-critical (security/privacy audits, the audio quality gate,
anything the user says to verify "100%" or "multiple passes"), do the full,
thorough job — cheapness never overrides correctness. The goal is to cut
*wasted* spend (redundant agents, unnecessary fan-out, re-deriving known
facts), not to skip real verification.

## HARD RULE: Always use Lou's photos as character references — no exceptions

For ANY story pipeline, image generation, or character reference sheet in this project:

**Character reference images are ALWAYS Lou's personal photos:**
- `/Users/louislapat/Desktop/vibe/djbot/lou photos/IMG_1667.jpeg`
- `/Users/louislapat/Desktop/vibe/djbot/lou photos/IMG_2012.jpg`

**Never:**
- Generate synthetic character references via FLUX
- Use the story_test7 ref sheet (`output/story_test7/ref_sheet/`)
- Use any other placeholder character

**Always:**
- Use both photos as the character refs injected into Gemini chat
- Describe the character as he appears in those photos
- Inject them on scene 0, re-inject every 6 scenes

This applies to every story script: `run_new_stories.py`, `run_vending_machine.py`, and any future story pipeline.

---

## HARD RULE: No phones in story scenes — ever

Phones cannot be rendered correctly by any current model and always break the story:
- Phone screens render as blank white or unreadable generic text
- Asking Gemini for a "hand holding a phone" CU generates a face too (character context bleeds in)
- A phone call implies an off-screen conversation partner the audience can never see or hear
- Phones are the #1 "lazy modern shortcut" in AI film — they short-circuit physical storytelling

**Replace every phone beat with a physical prop that does the same emotional work:**
- "He calls to share the news" → he holds a photograph of the person inside
- "He checks his phone" → he looks at his watch, or reaches into his pocket and pauses
- "She texts him" → she leaves a note, or a door is ajar, or a light is on that wasn't
- "He gets a call" → someone appears in a doorway, or a door opens

This rule applies to every scene in every story script. If a phone appears in a scene description, the description is wrong. Rewrite it.

**Why this rule exists (root cause of the June 2026 waiting room failure):** The "waiting room phone call" scene was described as a CU OBJECT of a hand holding a phone. Gemini's chat context had character refs loaded, so it included Lou's face in the shot — exactly the opposite of what was needed. Additionally, phone screen text was unreadable. The beat was rewritten as "The Photo" — a hand holding a photograph of the person inside — which required no screen text and worked immediately.

---

## HARD RULE: Every secondary character who appears in 3+ scenes needs a FLUX reference image

The same outfit drift problem that affects the main character affects ALL recurring characters. A kid in a soccer jersey will change colors. A woman in a restaurant will change outfits. A doctor will change scrubs.

**For any character who appears in 3 or more scenes:**
1. Write a `CHAR_<NAME>_DESCRIPTION` constant (frozen, never paraphrased)
2. Generate a `ref_<name>.jpg` via FLUX before Gemini scenes run
3. Inject the ref in EVERY scene that character appears in (not just cut-aways — every scene)
4. For cut-away scenes showing that character, inject THEIR ref instead of the main character refs

**Detection:** In `generate_scenes()`, check if a scene is a cut-away AND contains the secondary character's name/description. If yes, inject that character's ref, not Lou's refs.

**This applies to:** soccer kids, parents, doctors, bystanders, romantic partners — anyone who appears in more than 2 scenes.

---

## Story beats — three rules about what must be on screen

**1. Dramatic action must be visible in frame — no implied inciting incidents.**
If the story starts with aftermath (a scrape, a missed ferry, someone already gone), add a scene showing the moment it happened. The inciting incident is the most important scene; it can't happen off-screen.

**2. Every story needs a "then what" beat after the emotional climax.**
The Kuleshov landing is not the ending — it's the setup for one more scene showing what the character does with what they just learned/felt. If the character just stands there, it's not a story beat, it's a pause. They must DO something: leave something behind, walk somewhere, sit down, turn away. Active, not passive.

**3. Light-dark contrast — don't hold one emotional register for the whole story.**
Stories that build through dark dread need a beat in fresh light after. Stories that build through urgency need a quiet beat after the goal is reached. The contrast is what makes the climax land. A man on the bleachers alone after a mile-long sprint reads completely differently than the same face mid-run.

These rules apply to every story script. Check all three before generating.

---

## Story development — figure out the story first, Lou second

When brainstorming or developing a new story — premises, structure, beats, twists, props — **do not think about Lou or what Lou would do.** Figure out what makes a compelling story first. Lou's character gets adapted in afterward.

Thinking about Lou's character during story development constrains the premise before it's found. A story built around "what would Lou do" starts from the wrong end. A story built around "what is the most compelling version of this situation" can always have Lou stepped into it later.

This applies to: brainstorming sessions, second-beat development, twist construction, any conversation where we're figuring out story structure before writing code.

---

## Story structure — hero's journey compressed to 5-7 scenes

Every story needs a character with a **real problem to solve** — not just an emotion to feel. The problem must require brains, brawn, luck, OR timing. If the character just has to show up and decide, it's a mood piece, not a story.

**The compressed hero's journey (5-7 scenes):**
1. **Ordinary world + problem visible** (scene 1) — the audience immediately understands what the character needs and why they can't easily get it
2. **First attempt / the obstacle** (scene 2-3) — he tries; something pushes back or closes a window
3. **The cut-away** (scene 3-4) — show what he doesn't know; the audience now has more information than he does (Hitchcock's bomb under the table)
4. **Active problem-solving** (scene 4-5) — he uses brains, brawn, luck, or timing to bridge the gap
5. **The ordeal** (scene 5-6) — one image that is the hardest thing he does; real cost, real chance of failure
6. **Resolution** (scene 6-7) — succeed or fail, but changed

**The cut-away is the dramatic irony engine.** It puts two things in the audience's head at once: what he's experiencing AND what's happening somewhere else without him knowing. The gap between those two things IS the emotion.

**The Buster Keaton model (confirmed reference for wordless active problem-solving):**
- The problem is always physical and visible — never internal
- He tries, fails, finds a creative alternative, tries again
- "Brains" reads visually as: character looks at problem → looks at available resources → executes a non-obvious solution
- The sequence look-at-problem → look-at-resource → look-at-problem-again → execute communicates intelligence without words
- Success or failure is always visible in the frame — the wall falls around him or on him

**Two forces required.** A mood has one force (something sad happened). A story has two forces in tension (he needs X / something prevents X). Name both forces before writing scenes. If you can only name one, redesign.

---

## Story audit — cross-story similarity check

Run this before generating any story. Two stories are too similar if they share the same combination of (setting type) + (who he's going to) + (obstacle type).

**Audit dimensions:**
- **Setting type:** indoor-institutional / outdoor-urban / vehicle / private space / transit
- **Who:** parent / child / romantic partner / stranger / self
- **Obstacle:** physical barrier / time / money / moral choice / information gap / emotional courage
- **Cut-away shows:** person waiting unaware / person in danger / normal life continuing / consequence he doesn't see yet
- **Active element:** brains / brawn / timing / luck / moral choice

**Flag if:**
- Any two stories share the same setting + obstacle + who combination → too similar, redesign one
- Any character spends more than one scene standing outside something looking in → same story structure, redesign
- The cut-away shows "person waiting unaware" in more than two stories → the stories blur together
- More than two stories resolve via timing alone → overused mechanism
- The character does not actively DO something (use brains/brawn/luck/timing) → mood piece, not story

---

## Cut-away scenes — how to implement in Gemini chat

Cut-away scenes show secondary characters in different locations. Gemini's stateful chat will try to insert the main character if refs are present. Prevent this:

1. In the scene `note`, use `"CUT AWAY — WIDE"` or `"CUT AWAY — CU"` as the note string
2. In the scene `description`, begin with: `"IMPORTANT — DIFFERENT LOCATION. No main character in frame."`
3. In `generate_scenes()`, detect cut-away scenes by checking `'CUT AWAY' in scene['note'].upper()` and send without character refs:
```python
is_cutaway = 'CUT AWAY' in scene.get('note', '').upper()
if is_cutaway:
    parts = [scene['description']]  # No char refs — different person
else:
    parts = ref_parts + [f"Same character... {scene['description']}"]
```

---

## HARD RULE: Wardrobe, hair, and face must stay consistent in ALL shots — including action shots

The #1 failure mode in action and running shots: the model treats dynamic scenes as a fresh generation and defaults to generic athletic or casual clothing. The outfit re-injection in the chat prompt is not enough — the wardrobe description must also appear INSIDE the scene description itself for every shot where the character is visible.

**This applies to every shot type equally:**
- Wide shots ✓
- CU face shots ✓
- Wide action / running shots ✓ ← most commonly missed
- Establishing shots ✓
- Kuleshov shots ✓

**Does NOT apply to:**
- POV shots (character not visible by definition)
- CU object / hands-only shots (character not visible)
- FLUX montage shots with silhouetted figures

**Rule:** If the character's body is visible in the frame, the scene description must contain the outfit keywords verbatim. Not in the chat wrapper — in the description string itself.

```python
# WRONG — outfit only in the chat wrapper, not the scene description:
f"WIDE ACTION: {CHAR_DESCRIPTION} running full sprint into the rain. ARRI Alexa 35"

# CORRECT — outfit embedded in the scene description:
f"WIDE ACTION: {CHAR_DESCRIPTION}, {OUTFIT_DESCRIPTION}, running full sprint into the rain. ARRI Alexa 35"
```

**Why action shots fail specifically:** When a scene description implies motion (running, throwing, sprinting), the model's training distribution associates athletic/casual clothing with those actions. The chat-level outfit ref competes with this prior and often loses. Embedding the outfit description directly in the scene description overrides the motion-clothing prior at the token level.

## HARD RULE: Wardrobe must be anchored — every scene, every call

Clothing consistency is the second-biggest failure mode after face drift. Without anchoring, the model assigns random clothing each generation.

### The three required steps

**1. Generate an outfit reference image (FLUX 1.1 Pro) before every Gemini run**

Treat the outfit exactly like a prop — it needs its own FLUX ref.

```python
OUTFIT_DESCRIPTION = "charcoal grey wool overcoat, single-breasted, notched lapel, collar up, knee-length"
OUTFIT_FLUX = (
    "Full-body shot head to toe of a man, arms slightly away from body, facing camera directly. "
    "Wearing a charcoal grey wool overcoat, single-breasted, notched lapel, collar up, knee-length. "
    "Plain white background, soft diffused studio light, camera at neutral height, "
    "photorealistic, no text"
)
```

Inject the outfit ref alongside the character refs on scene 0. Re-inject it on EVERY scene call (see rule 3).

**2. Freeze OUTFIT_DESCRIPTION — copy-paste verbatim into every scene prompt**

Never paraphrase. "blazer" and "jacket" are different tokens. The outfit string is frozen the same as the character DNA block. Append it to every scene description:

```python
f"...scene content... {OUTFIT_DESCRIPTION}"
```

Order: character DNA block (including outfit) FIRST, then scene content. CLIP-L drops tokens past position 77 — don't bury the outfit after a long scene description.

**3. Re-inject character refs + outfit ref on EVERY scene call (not every 6)**

Outfit drift starts faster than face drift. The 5-image payload (2 Lou photos + 1 outfit ref + 1 prop ref + optional location ref) fits within Gemini 3.1 Flash Image limits.

```python
# Every non-scene-0 call:
parts = [
    _part_from_path(CHAR_REFS[0]),
    _part_from_path(CHAR_REFS[1]),
    _part_from_path(outfit_path),
    _part_from_path(prop_path),
    f"Same character. Same outfit: {OUTFIT_DESCRIPTION}. ...[scene description]..."
]
```

### Outfit selection — choose for consistency

Most to least consistent (confirmed by community benchmarks):
- Dark solid colors (black, charcoal, dark navy) — best; drift is invisible at dark tones
- Mid-tone solid with one named structural detail — good
- Large-scale low-contrast texture (ribbed knit) — tolerable
- Stripes — hard; alignment breaks are visible immediately
- Small-repeat patterns (plaid, houndstooth) — very hard
- Text or logos on clothing — do not use

**Default outfit for Lou's stories: dark charcoat wool overcoat, simple dark shirt underneath.** Visually distinctive, maximum consistency, appropriate for any urban/suburban setting.

### The selfie-clothing bleed problem

Lou's reference photos show him in casual selfie clothing that bleeds into generated scenes. Fix: generate the outfit ref separately (step 1) and describe the intended outfit explicitly in every prompt. The explicit outfit ref + verbatim description overrides what the model infers from the face photos.

Advanced option: FLUX VTO (`docs.bfl.ai/flux_tools/flux_vto`) for pixel-accurate outfit-on-character reference — decouples face identity from outfit identity completely.

### What realistic consistency looks like

Best-in-class: ~70-80% outfit similarity with visual refs + verbatim descriptions. Pixel-identical clothing is not achievable with any current tool. Dark solid colors and simple silhouettes keep drift invisible.

---

## AI short film — the formula that works (confirmed June 2026, The Vending Machine)

### Story engine: problem-solving, not sentiment

The story structure that works: **character has a visible external problem → tries → fails → learns → tries differently → solves or doesn't.** Every scene is a failed attempt that teaches the character something. The audience is actively rooting. This replaced the broken formula (character notices thing → does gracious act → done = no stakes, no engagement).

**The Ten (Kishōtenketsu)**: Every story needs a twist that reframes the first half. The ending must land somewhere the audience didn't predict. Test: could a viewer who only sees scenes 10-12 understand that something they thought they understood in scenes 1-3 was wrong? If yes, you have a Ten.

**Dramatic irony must be spatial** — visible in the frame, not inferred from backstory. The audience sees both sides of a physical situation. The character sees one. The irony must be established within the images themselves, not through relationship context or history the audience already knows.

**Conflict the AI can render**: not internal deliberation — external, physical, visible. The world must push back in a way the camera can show.

### Multi-prop reference system — every key object gets a FLUX ref

**Before any Gemini image generation run:**
1. Read through ALL scene descriptions
2. Identify every physical object that appears in 3+ scenes
3. Generate a FLUX reference image for EACH one
4. Inject the relevant prop refs in the scenes where that object appears

**The Vending Machine had two key props:**
- The vending machine (scenes 0, 2-6, 13-17) → `ref_machine.jpg`
- The chair (scenes 12, 13, 14) → `ref_chair.jpg`

Missing the chair ref caused two completely different chairs across three scenes. The solution prop is as important as the problem prop — always ref both.

**Before running any story pipeline:**
```bash
python story_pipeline/audit_shot_list.py story_pipeline/<script>.py
```
This catches: missing prop refs, establishing shot orientation errors, CU scenes missing eyeline direction, POV scenes missing camera facing direction, and wrong character refs.

### Eyeline match + POV structure (the Kuleshov engine)

**The rule**: CU of face looking in a direction → next shot is that character's POV from the correct angle. This is how emotion is built in a wordless sequence — the audience constructs it at the cut.

**The 180-degree line**: pick a spatial layout for the whole film and never cross it.
- Example: Machine = SCREEN-RIGHT, desk = SCREEN-LEFT
- All CU shots of character facing machine: he looks SCREEN-RIGHT
- All POV shots of the machine: camera faces RIGHT from his position
- Never flip sides mid-film

**In every CU scene description, specify:**
- Which direction the character's gaze goes off-frame (screen-left, screen-right, down)
- "DO NOT show him looking at camera"

**In every POV scene description, specify:**
- Camera is at character's position
- Camera height (eye level = how tall the character is)
- Camera facing direction (screen-right/left/down)
- "This is NOT a shot of the character — this is what they see"

**The Kuleshov shot**: the emotional climax is a held CU of the face AFTER the problem resolves, in a context-loaded environment. The face is neutral. The audience loads it with everything the situation implies. In The Vending Machine: a man alone in a hospital at night holding a chocolate bar, looking up toward the elevators. Nothing explained. Everything implied.

### Establishing shot orientation — always specify

If a character appears in the establishing shot, specify their orientation explicitly:
- "seen FROM BEHIND, walking TOWARD the vending machine screen-right" ✓
- "stands in the center of the room" ✗ → model defaults to facing camera, subject ends up behind them

Best establishing shot option: show the character FROM BEHIND walking toward the subject. Sets up geography, 180-degree line, and character direction of travel in one shot.

### Shot list audit — run before every image generation

```bash
python story_pipeline/audit_shot_list.py story_pipeline/<script>.py
```

**Catches:**
- Missing prop FLUX refs for objects appearing in 3+ scenes
- Establishing shots with character but no orientation spec
- CU scenes missing eyeline direction keywords
- POV scenes missing camera facing direction
- Wrong character refs (story_test7 instead of Lou's photos)

**Rule: 0 errors before running.** Warnings are acceptable but review them.

---

## HARD RULE: Never report a video file as working without verifying it first

Before saying any video output is ready, open, or done — always run both checks:

1. **ffprobe stream check** — confirm a video stream exists AND pixel format is `yuv420p`:
   ```bash
   ffprobe -v error -show_entries stream=codec_type,pix_fmt \
     -of default=noprint_wrappers=1:nokey=1 output.mp4
   ```
   Output must contain `video` and `yuv420p`. Any other pixel format (e.g. `yuv444p`)
   will NOT open in QuickTime. Add `-pix_fmt yuv420p` to the FFmpeg encode command.

2. **Full decode check** — confirm FFmpeg can decode every frame without errors:
   ```bash
   ffmpeg -v error -i output.mp4 -f null - 2>&1
   ```
   Must produce zero output. Any error = corrupt or unplayable file.

**Why this rule exists:** In June 2026, `p-video-animate` returned clips in `yuv444p`
(High 4:4:4 profile). The loop assembly inherited that format. The preview was reported
as "open" based only on the `open` shell command returning 0 — which is async and does
not confirm playback. The user tried to open the file and it failed. Never report a
video as working until `_verify_video()` passes.

**All FFmpeg video encode commands in this project must include:**
- `-pix_fmt yuv420p` — QuickTime / hardware decoder compatibility
- `-movflags +faststart` — moov atom at start, required for streaming/preview
- Silent audio track for preview clips (`-f lavfi -i anullsrc=...`) — some players
  refuse to open video-only files

**The `_verify_video(path)` function in `pipeline/video_builder.py` enforces all of
this automatically. Call it on every generated video file.**

## HARD RULE: Every deliverable video must have audio

Any video shown to the user or used for Twitch streaming must have audio. Never deliver a
silent video as a final output.

**For stream videos** (THE_PASSAGE_*.mp4 and equivalents): always combine with the DJ mix
before opening or reporting done:
```bash
ffmpeg -y \
  -i video.mp4 \
  -ss 30 -i output/full_mix.mp3 \
  -map 0:v -map 1:a \
  -c:v copy -c:a aac -b:a 192k \
  -shortest -movflags +faststart \
  video_MUSIC.mp4
```

**The file shown to the user must be `video_MUSIC.mp4`**, not the silent `video.mp4`.

**Why this rule exists:** In June 2026, THE_PASSAGE_V2.mp4 was delivered silently and
the user had to ask "where's the music?" twice across two separate sessions. The music
step is easy to skip when focused on video generation — this rule makes it mandatory.

## HARD RULE: Hailuo-02 outputs portrait video — always crop to fill, never pad

Hailuo-02 (`minimax/hailuo-02`) outputs video in portrait orientation (~720px wide)
even when fed 16:9 landscape input images. Using `force_original_aspect_ratio=decrease`
with padding creates black bars on left and right.

**Always use this FFmpeg filter for Hailuo-02 output:**
```
-vf 'scale=1280:720:force_original_aspect_ratio=increase,crop=1280:720'
```
This scales the portrait video up to fill 1280×720 (cropping top/bottom slightly)
instead of centering it with black bars.

**Why:** Using `decrease+pad` produces a 720px-wide portrait image centered in a
1280×720 frame with ~280px black bars on each side. Detected via `ffmpeg cropdetect`
showing `crop=720:682:280:38` on processed clips.

## Stream video — how to generate (the discovered method)

The Twitch stream visual is a seamless chain of surreal AI-generated scenes animated with
Hailuo-02 first+last frame. This produces a continuous, non-looping cinematic video.

### Image generation (FLUX 1.1 Pro)

**Model:** `black-forest-labs/flux-1.1-pro` at `width=1280, height=720` (native 16:9 — required)

**Prompt structure (confirmed working):** Full prose sentences. FLUX uses a T5-XXL encoder that
parses grammar — keyword lists reduce quality 50-75%. Describe the scene as a complete sentence.

**What makes prompts great — the confirmed formula:**
1. **Technical cinematic specificity** — name the actual gear: `ARRI Alexa 65`, `Zeiss Master Prime 50mm at T1.4`, `Kodak Vision3 500T film stock`, `Fujifilm Eterna 250D`, `Hasselblad 907X`. These are the single biggest quality driver.
2. **Weird surreal concept** — the scene must be a distinct impossible world, not just a location. Confirmed high-quality style categories:
   - `baroque noir futurism` — dark impossible baroque architecture
   - `NeonCortex architecture` — cities mapped with glowing neural networks
   - `celestial golden elegance` — divine light, ascending, god rays
   - `Echo Vista Neon` — neon cities floating in clouds
   - `liminal space` — abandoned places at wrong hours (flooded malls at 3am)
   - `biopunk` — organic-tech hybrids, fiber optics as hair
   - `analog horror` — brutalist spaces, single flickering bulb
   - surreal physics inversion (walking on underside of bridge, gravity reversed)
3. **Director references where meaningful:** Ridley Scott, Béla Tarr, Guillermo del Toro, Wes Anderson — use when they genuinely describe the look, not as decoration.
4. **Varied subjects** — don't force a human into every shot. Some scenes work better as pure environments. When there is a figure, keep them from behind / silhouetted to avoid face-consistency problems.

**Why this formula works (verified by research, June 2026):**

- **Prose sentences vs keyword lists:** FLUX uses a dual encoder — CLIP-L and T5-XXL. T5-XXL was trained on prose documents, not image tags. Comma-separated keywords are parsed as malformed English and lose relational context. A full sentence like "A lone figure stands at the end of a fog-filled corridor, backlit by a single sodium vapor lamp, shot on ARRI Alexa 65 with a Zeiss Master Prime 50mm at T1.4" lets T5-XXL correctly parse subject, spatial relationship, lighting, and equipment as a coherent scene. The 30–80 word prose sentence is BFL's own recommended sweet spot.

- **Camera/lens/film stock names:** FLUX's training data is metadata-rich photography corpora. Photographers and stock libraries embed EXIF data (camera, lens, aperture) as text. The model learned strong associations: ARRI Alexa 65 → large-sensor cinema color science; Zeiss Master Prime T1.4 → creamy background separation, high micro-contrast; Kodak Vision3 500T → warm shadow tones, tungsten balance, grain. "Professional camera" gives the model nothing to match — "ARRI Alexa 65 with Fujifilm Eterna 250D" lands in a dense region of the training distribution. This is the single biggest quality lever.

- **Style category names:** These work when the style has a subreddit, Tumblr aesthetic, or Civitai tag with hundreds of images. "Liminal space" has a massive Reddit/Pinterest corpus (r/LiminalSpace) with consistent visual vocabulary — the model learned it. "Baroque noir futurism" is compositional — model combines Baroque (chiaroscuro, gilded architecture) + noir (deep shadow, rain) + futurism (chrome, velocity). Invented compound names (like "NeonCortex") are riskier — only use if that term appears in real creative communities before FLUX's training cutoff.

- **Director references:** These are flavor, not instruction. Ridley Scott, Béla Tarr, Guillermo del Toro appear in film criticism and production design articles in training data — the model has loose visual associations (Scott → industrial environments + lens flare; Tarr → desaturated Eastern European palette, rain; del Toro → baroque creature design, amber-teal grade). But these are weak signals. Use directors for general mood priming; use equipment specs for reliable, predictable optical signatures.

**How to generate more scenes (for 65-min full mix needing ~280 images):**
- 8 confirmed style archetypes × ~10 scene concepts each = ~80 unique combos before repeating
- Each archetype has many sub-variations: liminal horror has 20+ distinct abandoned location types; physics inversion has a dozen impossible gravity scenarios; baroque noir has countless architectural sub-concepts
- Rule: no two adjacent scenes share the same archetype, subject type, or dominant color palette

**Example prompt that worked:**
> "A lone silhouette standing at the vanishing point of an infinitely long abandoned shopping mall corridor at 3am, two inches of perfectly still black water covering the floor reflecting every flickering fluorescent ceiling light, liminal space horror aesthetic, Dutch angle, Fujifilm Eterna 500 film stock, cinematic"

### Animation (Hailuo-02 first+last frame chain)

**Model:** `minimax/hailuo-02` via Replicate

**How the chain works:**
- Generate N+1 images → N clips
- Clip i: `first_frame_image=img_i`, `last_frame_image=img_{i+1}`
- Last frame of clip i == first frame of clip i+1 → seamless join
- Trim first frame from clips 1-N (it duplicates the last frame of the previous clip)
- Concat all clips → continuous video, no loops, no holds

**Duration:** Use `duration=10` (10s per clip, $0.46) for a good pace where each world has
breathing room. `duration=6` ($0.23) switches too fast. The 10s version is the canonical choice.

**Cost reference:**
- 3 minutes: 19 images ($0.76) + 18 clips at 10s ($8.28) = **~$9**
- 65-minute full mix: ~280 images ($11) + ~280 clips ($129) = **~$140**

**Submit all clips concurrently** — Replicate runs them in parallel on their GPU farm.
Each thread has retry-on-429 logic (burst limit is 5/min under $10 balance).

### Hailuo-02 prompt rules (from official knowledge base)

**Adjectival motion, not numeric:** "steady," "sweeping," "gentle," "abrupt" work. "Pan 30 degrees" or "Zoom 15%" do NOT — the model interprets visual feel, not geometry.

**The 2+1 Rule:** No more than 2 primary movements + 1 secondary quality per clip.
Success rates by complexity: single axis ~85-90%, dual ~60-70%, triple ~20-30%.
Example: `[slow dolly push in], [subtle tilt up], [cinematic]` — two axes plus one quality descriptor.

**Keep first+last frames in the same framing level:** A first frame that's a wide and a last frame that's an extreme close-up forces the model to resolve too many degrees of freedom → artifacts. Each clip should be one visual idea. Handle framing level changes via adjacent clips with matching last→first frame anchors.

**Use "85mm focal length" for dialogue/emotional close-ups** — this gets shallow DOF and the cinematic portrait look. "24mm" for wide environmental shots.

**Avoid complex fine-motor actions in prompts:** Handshakes, drinking coffee, typing → temporal "melting" artifacts 10-15% of the time. Gross motor movement (walking, turning, leaning, looking) is reliable.

**ECU on hands or objects** instead of face close-ups sidesteps the AI uncanny valley — hands tearing an envelope, fingers tracing a surface, a prop being held conveys the same emotion without extended face scrutiny.

**Shot type is controlled by the input image frame, not the prompt text.** In a first/last-frame chain, if the first frame is a wide shot, the clip will be a wide shot regardless of what the prompt says. Design shot variety at the image-generation stage (generate a close-up image for a close-up clip), not at the animation stage.

**"Close-up" often yields a medium shot in FLUX and Midjourney.** Use "extreme close-up" for a true ECU. Use "medium close-up" (chest up) vs. "medium shot" (waist up) vs. "tight portrait" (head and shoulders) to get the exact framing. Plain "close-up" lands somewhere in between.

**Kuleshov effect requires environmental consistency** between the face shot and the object/trigger shot. When face and object shots have inconsistent backgrounds or lighting (common in AI sequences), the contextual framing doesn't fire — the audience can't construct the emotional connection. Prompt both shots with matching lighting, color palette, and environment.

**Lighting consistency across clips:** Specify "key light from camera-left, 3200K" in every clip prompt. Generic "cinematic lighting" does not persist. Inconsistent lighting is what makes edits visible.

### FFmpeg rules for Hailuo-02 output

Hailuo-02 outputs portrait video regardless of input image aspect ratio. Always use
crop-to-fill, never pad:
```
-vf 'scale=1280:720:force_original_aspect_ratio=increase,crop=1280:720'
```

### Shot duration rules for AI video (AI-specific, verified from practitioners)

AI footage has different attention thresholds than live-action — cut earlier or viewers notice the synthetic quality.

| Shot type | Duration |
|---|---|
| Static medium (AI character) | Max ~4s before attention drift |
| Close-up (AI face) | 2–5s |
| Opening / transitional | 2–4s |
| Wide establishing | 4–7s |
| Dynamic camera movement | 3–5s |
| Contemplative environment | 5–8s |
| Horror / dread (uncanny = atmospheric) | 7–10s |

**Fast-slow-fast rhythm:** Group shots in triplets (e.g. 2-4-3s or 3-6-4s). One long shot per triplet creates a breath — every shot the same length feels monotone.

**Tension ramp:** If avg shot = 4s, tighten to 3s as tension builds, then 2s at peak.

**Slowdown trick:** Render at normal speed, then time-stretch to 50–70% in FFmpeg. A 4s Hailuo-02 clip becomes 6–8s with cinematic weight:
```bash
ffmpeg -i clip.mp4 -vf "setpts=1.6*PTS" -an -c:v libx264 -pix_fmt yuv420p clip_slow.mp4
```

**Hard cuts expose AI consistency failures** — use crossfades between stylistically inconsistent clips.

**Alternation rule:** Never place two visually similar images consecutively. Alternate wide/close-up, static/dynamic, populated/empty, high-energy/quiet. Violating this collapses rhythm.

**Pause before climax:** The beat immediately before the emotional peak should be a quiet or wide frame. Wide/quiet → CLIMAX (close-up) → resolution. The peak lands harder after visual rest. This is the three-beat unit around any emotional moment in a still-image sequence.

**Shot duration psychology (non-AI footage):**
- Under 3s → urgency, adrenaline
- 3–6s → natural narrative flow
- Over 10s → contemplative, heavy weight

**Close-up = climax tool.** Emotional peaks go tight (portrait or close-up), not wide. Wide shots establish context and setup. The funnel: wide (context) → medium (action) → close-up (emotional event).

### Scripts

- `output/the_passage_v2/run.py` — reference implementation (31 scenes, concurrent, crop fix)
- `pipeline/video_builder.py` — legacy p-video-animate pipeline (abandoned, kept for reference)

---

## HARD RULE: Never commit credentials to git

All secrets live in Railway environment variables or `~/.zshrc` only. **Never put any of the following in code, comments, or any tracked file:**

- Mixcloud client ID / secret / access token
- Twilio Account SID / Auth Token / phone numbers
- Railway API key or project tokens
- Any API key, password, or bearer token

If a future feature needs a new credential, add it as a Railway env var via:
```
RAILWAY_API_KEY=... railway variables set KEY=value --project dependable-nature --service djbot --environment production
```

The `.gitignore` blocks `.env`, `secrets.py`, `credentials.json`, and all `*.token` files. Do not bypass it.

## NON-NEGOTIABLE: Never corrupt the audio timeline
**These are the hardest rules. No feature, no technique, no "improvement" overrides them.**

1. **Never repeat audio.** If a section of a track plays once, it must not play again.
   Any code that appends audio from position X and then separately appends audio that
   overlaps or replays position X is a critical bug. Audit every concat in the assembly loop.

2. **Never skip audio.** A gap between where the body ends and where the blend picks up
   is a content hole. The transition must be gapless — body ends at sample N, blend A-side
   starts at sample N (or the exact equivalent position in the native-BPM version of the track).

3. **Never cut audio mid-phrase without a crossfade.** Every hard boundary (body→blend,
   blend→next body) must be either (a) a continuous read of the same audio array with no
   position jump, or (b) an equal-power crossfade with verified phase alignment.

**What caused repeats in the past:** A "preload" was added that played Butch's outro zone
(after body_end) for 3 seconds, then the pre-computed blend ALSO started from the same
position — playing the same musical content twice. User heard the repeat at 6:13 and 9:23.
Preload was removed entirely. Do not re-add any preload unless the start position is verified
to NOT overlap with the blend's A-side start.


## HARD RULE: Beat-matching correctness is the top priority — above avoiding hard-cuts (decided 2026-08-19)

**If the beats don't actually match, nothing else about a transition matters.** A
blend where the incoming and outgoing tracks' beats are audibly overlapping/
clashing is worse than no blend at all — Louis's own words: "if you don't match
the beats NOTHING matters, might as well just do the song ends with echo and
cut to other song." When there is real doubt about whether two tracks' beats
will actually lock (not just "does the numeric phase-error check pass"), the
hard-cut + echo-out fallback (see `_build_hard_cut_transition`/`_echo_out_tail`
in set_builder.py) is the CORRECT, PREFERRED choice, not a fallback to be
avoided. Never let "let's try to force a beat-matched blend anyway" win over
"this will clearly land better as a clean hard cut."

**The existing phase-error number is not proof the beats actually match — it
has a real, confirmed false-positive mode.** Case in point (2026-08-19): a
Corona → Real McCoy transition measured phase error 0.1ms (an excellent score,
comfortably under the 20ms gate) and passed the RMS-continuity check too — yet
Louis reported hearing "multiple beats overlapping" when actually listening to
it. A single-point phase-error regression over the blend window can land on a
coincidental alignment while the underlying detected tempo relationship
between the two tracks is still wrong (a classic way this happens: an
undetected octave/double-time mismatch — see the existing `_octave_match()`
correction — where the phase regression can still find *a* low-residual fit
even though the felt beat pattern is doubled or halved relative to the other
track). **Do not treat "phase error < 20ms" as equivalent to "the beats will
sound matched."** Passing the numeric gate is necessary but demonstrably not
sufficient — when in doubt, or when a user reports a transition sounds
off despite passing the gate, investigate for an octave/tempo-ratio mismatch
specifically, not just re-check the phase-error number again.

## Non-negotiable quality gate
**Every transition MUST pass both checks before presenting to the user:**

1. **Phase error < 20ms** — measured by linear regression over all beats detected in the
   blend file (`_phase_error_ms(blend_path)` in set_builder.py). This is the ONLY reliable
   method — PRE/POST file approach has ±30ms noise from beat detector startup bias.

2. **Amplitude continuity < 3.0x RMS ratio** — checked at BOTH blend-in (blend_start) and
   blend-out (blend_end) using a 2-second window. Ratio = max(pre,post)/min(pre,post).
   Threshold 3.0x accounts for normal music dynamics over 2s; anything higher is a real cut.

If either check fails → fix it. Do not show the user a transition that fails.
Never report a transition as done without running both checks.


## Full mix assembly — how it works

### Structure of a mid-set track
```
[body_start ──────────────── body_end] [blend_audio] [next body_start ────]
         stretched B at A's BPM              ~31s           stretched B' at B's BPM
```

1. **Body**: `b_s[body_start : body_end]` — stretched B, continuous from prior blend-in
2. **Blend**: pre-computed equal-power crossfade — A fades out, B fades in over 16 bars
3. **Next body**: starts at `trim + cf_len` in the NEXT transition's `samples_b_s`

The body ends at EXACTLY the position where the pre-computed blend's A-side starts.
The next body starts at EXACTLY the position where the blend's B-side ends.
No gap. No overlap. No repeat.

### Body audio rule — CRITICAL
**Always use stretched B audio (`samples_b_s`) for the body section.**

- `b_s = tr_prev["samples_b_s"]` — B stretched to A's native BPM
- Continuous with how B was introduced in the blend-in. No BPM jump at blend-end.
- `body_start = tr_prev["trim"] + tr_prev["cf_len"]` — exact position where blend-in left off
- `body_end = outro_stretched` (capped at 180s, bar-snapped)

**NEVER switch to native B audio for body** — causes BPM jump at blend-END when the
incoming track takes over at 100% volume. User hears this as a "clear cut." Tested and
confirmed bad (caused the 3:32 cut in the solomun set).

### 5ms micro-crossfade at every body→blend splice — DO NOT REMOVE
The body uses stretched audio from the PREVIOUS transition's build (e.g., Butch at 122 BPM).
The blend's A-side uses native audio loaded fresh in the NEXT transition's build (e.g., Butch
at 124 BPM). Even when BPMs match, different processing chains produce different sample values
at the exact splice point → audible click ("blip") at the transition start.

Fix: crossfade the last 5ms of body into the first 5ms of blend:
```python
micro_n = int(0.005 * sr)
t = np.linspace(0.0, 1.0, micro_n)[:, np.newaxis]
b_body[-micro_n:] = b_body[-micro_n:] * (1.0 - t) + blend_audio[:micro_n] * t
blend_audio = blend_audio[micro_n:]
```
This is inaudible as a transition (5ms) but eliminates the waveform discontinuity.
Apply at every `elif idx < len(transitions)` body→blend join.

### Body cap: 3 minutes max
- `MAX_BODY_SEC = 180` — hard cap, bar-snapped to keep beats aligned
- If capped: recompute blend with `_reblend(b_s[body_end:], tr_next["b_full"], tr_next["cf_len"])`
- If not capped: use pre-computed `tr_next["blend"]` directly (already beat-verified)

### Last track
- `last_body = tr_prev["samples_b_s"][tr_prev["trim"] + tr_prev["cf_len"]:]`
- Play to the end — no blend needed


## The BPM jump problem — solved with gradual ramp

When consecutive tracks have DIFFERENT BPMs, there is always a BPM transition somewhere.
Three approaches were tested before finding the correct solution:

| Approach | BPM jump location | User perception |
|---|---|---|
| Stretched body + pre-computed blend (no ramp) | Blend-START (A at 100%, fading out) | "Slight issue" / rhythm jump |
| Native body + pre-computed blend | Blend-END (B at 100%, just took over) | **"Clear cut"** |
| Re-stretched B-side + stretched body | Blend-END content gap (0.49s skip) | **5x amplitude discontinuity** |

**Solution: BPM ramp over the last 8 bars of body.** Before the blend starts, gradually nudge
the body's playback speed from body BPM to blend-native BPM over 8 bars (≈16 seconds).
This is exactly what a real DJ does with the pitch control on CDJs.

### How the ramp works (in set_builder.py `_bpm_ramp`)
- Split the last `RAMP_BARS=8` bars of body into `RAMP_CHUNKS=32` chunks (~0.5s each)
- Each chunk gets a linearly interpolated stretch ratio: lerp(1.0, target_ratio, t)
  - Chunk 0 (t=0.015625): 0.05% change from body BPM — inaudible
  - Chunk 31 (t=0.984375): 98.4% of the way to blend native BPM
  - Step per chunk: ~0.06 BPM for a 2-BPM jump — completely imperceptible
- `target_ratio = tr_next["period_a"] / tr_prev["period_a"]`
  - < 1.0: compress (speed up toward blend BPM)
  - > 1.0: expand (slow down toward blend BPM)
- **5ms micro-crossfade at every chunk boundary** — eliminates waveform discontinuities
  from different pyrubberband calls; 31 boundaries × 5ms = 155ms total crossfade
- pyrubberband preserves beat positions within each chunk → phase-continuous at body→blend
- Only applied when NOT capped (capped bodies use `_reblend` at body BPM, no mismatch)
- `RAMP_THRESHOLD = 0.0` — ramp fires for ALL non-capped bodies, including same-nominal-BPM
  pairs where the beat detector gives slightly different period values. Inner guard in
  `_bpm_ramp` skips the pyrubberband call when |ratio-1| < 0.0001 (true no-op).

After the ramp, the existing 5ms micro-crossfade handles sample-level discontinuity at the
body→blend boundary as before.

### Why 4 chunks (RAMP_CHUNKS=4) was not enough
With 4 chunks of ~2 seconds each:
- Each boundary is a discrete BPM jump of ~0.5 BPM for a 2-BPM transition
- 4 audible rhythm steps within the ramp zone, instead of 1 jump at the blend
- User confirmed this was still audible at 6:11 after the first ramp implementation
With 32 chunks of ~0.5 seconds each:
- Each boundary is ~0.06 BPM — well below the perceptual threshold (~0.2 BPM)
- The crossfades between chunks eliminate any waveform discontinuity at each step

### Why RAMP_THRESHOLD = 0.0 (apply to ALL transitions)
Originally set to 0.01 (1%), which caught the major 2-4 BPM jumps. But the user heard
a rhythm issue at 9:21 (Sol body at Butch's 124 BPM entering Sol→Adana blend at Sol's
native 124 BPM). Even a 0.05% BPM difference from the beat detector produces a noticeable
rhythm stutter at the body→blend boundary. Setting threshold to 0.0 ensures EVERY transition
is ramped, with the inner guard making truly same-BPM pairs a no-op.

### Which transitions get ramped (solomun set)
| Track body | Body BPM → Blend BPM | Why |
|---|---|---|
| Butch_Lale | 122→124 | KT intro at 122, Butch native at 124 |
| Innellea | 123→120 | Patrice at 123, Innellea native at 120 |
| Wassermann | 120→124 | Innellea at 120, Wassermann native at 124 |
| Sol_Amanacer | 122→120 | GuyGerber at 122, Amanacer native at 120 |
| TubeNBerger | 120→122 | Amanacer at 120, TubeNBerger native at 122 |
| TaleOfUs | 123→125 | Adriatique at 123, TaleOfUs native at 125 |


## mix_in_bars — CRITICAL, must be tuned per track

`mix_in_bars` controls WHERE in the incoming track the blend enters.
**A bad mix_in_bars is the #1 cause of audible "cut in" artifacts.**

### How to choose mix_in_bars
- **Start with 0** — most house/techno tracks have a quiet 16–32 bar intro that blends in naturally
- If the blend-in sounds abrupt ("cuts into the middle of a song"), the mix point landed loud
- If the blend-in is smooth, the quiet section is at that bar count
- Try 0 → 8 → 16 → 32 and listen

### Symptoms of wrong mix_in_bars
- User says "cut in" or "something happening" at blend-start
- User says "sounds like cutting into the middle of the song"
- High blend-in RMS ratio in the amplitude report

### Known good settings (solomun set — do NOT change without testing)
| Track | mix_in_bars | Notes |
|---|---|---|
| KT_Sorry | 16 | first track |
| Butch_Lale | 32 | quiet 32-bar intro ✓ |
| Sol_Story | 32 | ✓ |
| Adana_Everyday | 0 | 32 was loud — fixed |
| Adana_Strange | 0 | bar 32 lands at full volume (0.24 RMS) — fixed |
| Brecht | 0 | 32 was loud — fixed |
| Ame_Fiori | 0 | 32 caused "trash" transition — fixed |
| Patrice_Serpent | 32 | ✓ |
| Innellea | 32 | quiet 32-bar intro ✓ |
| Wassermann | 32 | ✓ |
| Nicone | 32 | ✓ |
| GuyGerber | 32 | quiet 32-bar intro ✓ |
| Sol_Amanacer | 32 | ✓ |
| TubeNBerger | 32 | ✓ |
| Rampa_2000 | 32 | ✓ |
| Adriatique | 32 | ✓ |
| TaleOfUs | 32 | ✓ |
| Rampa_Touch | 8 | known good |
| Ame_Rej | 32 | ✓ |
| Stimming | 140 | last track — skip into outro section |


## Crossfade settings (solomun brain)
- CF_BARS = 16 — 16 bars ≈ 31s at 122 BPM
- OUTRO_BARS = 90 default; per-track overrides via `"outro_bars"` key in TRACKS list
- SNIPPET_SEC = 15 — snippet clips export 15s before and after blend for review

## Beat detection
- Primary: `beat_this` (CPJKU, `checkpoint='final0'`, `device='cpu'`, `dbn=False`)
- Anchor cache: `downloads/library/beatgrid_cache.json`
- Startup bias fix: feed the model 2 beats of audio BEFORE the target window
- Phase measurement: blend-file linear regression over ALL detected beats (mid-half residuals)
  Formula: fit line to beat timestamps → residuals → compare mean of first half vs second half

## Output structure
- `output/<set_name>/FULL_SET.mp3` — canonical full mix
- `output/<set_name>/SET_NOTES.txt` — tracklist + auto-generated cue sheet (actual blend times)
- `output/<set_name>/<n>_A_into_B.mp3` — per-transition snippet (15s pre + blend + 15s post)
- `output/transitions/` — raw build artifacts per pair (BLEND.mp3 for phase measurement)

## Cue sheet
Auto-generated from actual `blend_start`/`blend_end` sample positions — never hardcode times.
Strip any existing `── CUE SHEET` block from the brain's SET_NOTES before appending.

## Testing — run after every code change

```bash
# Fast unit tests only (no audio files, ~2s):
python -m pytest tests/test_set_quality.py -v -m "not slow"

# Full integration test — 3-track build (~60s):
python -m pytest tests/test_set_quality.py -v -m "slow" -k "ThreeTrack"

# Full solomun 20-track test (~10 min):
python -m pytest tests/test_set_quality.py -v -m "slow" -k "Solomun"
```

**test_set_quality.py covers:**
- 10 unit tests for `_bpm_ramp`: ratio=1.0 no-op, short body guard, stable section
  unchanged, speed-up shortens output, slow-down lengthens output, energy preserved,
  length matches average ratio, and the 3 constant values (BARS=8, CHUNKS=32, THRESHOLD=0.0)
- 7 unit tests for `_band_split` / `_eq_blend` (v2): bands sum to original, bass/high capture
  correct frequencies, output shape, no clipping, bass swap verified by correlation, USE_EQ_BLEND=True
- 8 integration tests for 3-track build: exit code, files exist, 2 phase errors < 20ms,
  no RMS cuts, ramp fires for Butch, ramp BPM values correct, snippets exported
- 12 integration tests for full solomun set: all 19 phase errors, no RMS cuts, ≥6 ramps,
  cue sheet has 19 entries, 19 snippets exist, duration 60–65 min, per-transition ramp checks


## History of problems solved (read before touching assembly code)

Every item below was a real user complaint that took multiple attempts to fix.
Before changing any assembly logic, verify your change doesn't re-introduce these.

| Time | Symptom | Root Cause | Fix Applied |
|---|---|---|---|
| 3:32 | Clear cut at end of KT→Butch blend | Body used native Butch audio → BPM jump at blend-END when B took over at 100% | Reverted to stretched body (`samples_b_s`) at all times |
| 6:13, 9:23 | Audio repeat — same section played twice | Preload played `b_s[body_end : body_end+n]`, then blend replayed same position | Removed preload entirely. Do not re-add. |
| 9:19, 15:09, 18:05–18:37 | Abrupt "cut in" at blend-start | `mix_in_bars=32` landed in loud section of Adana/Brecht/Ame_Fiori | Set `mix_in_bars=0` for those tracks |
| (all blends) | Waveform click/blip at body→blend splice | Different processing chains (stretched vs native) give different sample values at exact splice | 5ms micro-crossfade at every `elif idx` body→blend boundary — DO NOT REMOVE |
| 6:10, 9:19 | 5.21× amplitude spike at blend-start | `outro_stretched` computed wrong: `outro_sample × len(b_s)/len(native_full)` ignores cue_b offset. When B-track has cue point C, b_s starts at C in native B, so correct formula is `(outro_sample - C) × stretch_ratio`. Wrong formula made body end too late (in a quiet breakdown past the real outro point); blend then jumped to loud outro_sample. Fixed by storing `cue_b` and `stretch_ratio` in the build dict and using them in assembly. |
| 6:11 | Rhythm jump at Butch blend-start | Butch body at 122 BPM, blend A-side switched to Butch native 124 BPM | BPM ramp over last 4 bars (122→124 gradual, 4 chunks) |
| 9:21 | Rhythm issue at Sol→Adana blend-start | Even same-nominal-BPM pairs have slightly different detector periods → tiny jump | Lowered RAMP_THRESHOLD to 0.0 (ALL non-capped bodies get ramped) |
| (discovery) | phase error measurement unreliable ±30ms | PRE/POST file approach has beat-detector startup bias | Switched to blend-file linear regression (±1ms accuracy) |
| (discovery) | 5x RMS discontinuity at some blend-outs | Re-stretching B-side of blend → `cf_len / restretch ≠ cf_len` → wrong body_start next track | Never re-stretch the blend's B-side; body_start = `trim + cf_len` always |
| 22:49 | "Starts matched then gets unmatched" during AmeF→Patrice blend | Capped AmeF body plays at 120 BPM; `_reblend` used `b_full` at AmeF's native 122.984 BPM → 386ms BPM drift by blend midpoint | For capped bodies with BPM mismatch (>0.1%): ramp body to native BPM, convert body_end to native coords, snap to native bar, use `samples_a[native_bar_end:]` as A-side of `_reblend`. Store `anchor_b_s` in build dict. Also fires for Adana_Everyday (124→120 BPM). |
| 19:17, 22:49 | "Off by a beat" at capped-body transitions (Brecht→AmeF, AmeF→Patrice) | `body_end` was snapped forward from `body_start` by whole bars (`body_start + N*bar_len`). `outro_stretched` can be 1–3 beats into a bar; B's trim was aligned to `outro_stretched`'s bar phase, not to body_end's bar phase → B arrives 1–3 beats off within its bar | Snap `body_end` BACKWARD from `outro_stretched` in whole-bar steps (`outro_stretched - k*bar_samples`) so body_end has the same bar phase as outro_stretched. Same for `native_bar_end` in the BPM-mismatch case. |
| (improvement) | Offset selection optimized for beat regularity only — phase drift ignored | ±1-beat search picked offset by minimum beat CV but didn't penalize BPM drift during blend | Combined score: `cv + 0.3 * min(phase_ms, 40) / 20` — keeps CV dominant, adds 0.3 CV-point penalty for 20ms phase drift. Computed inline from beats already detected. |


## What NOT to do (approaches tested and rejected)
- **Preload (B fading in before body_end):** Causes REPEAT — preload plays audio from after
  body_end, which is the same audio the blend's A-side then replays. User heard repeat at
  6:13 and 9:23. Do not re-add unless start position is provably non-overlapping.
- **Re-stretching B-side of blend** to match A's BPM → content gap at blend-out (≥5x RMS).
- **Native B body** → BPM jump at blend-END (user heard as "clear cut" at 3:32).
- **PRE/POST phase measurement** → ±30ms noise from beat detector startup bias.
- **body_start_override** → made amplitude worse (5.02x) by landing at a quieter position.
- **RAMP_THRESHOLD > 0** → misses same-nominal-BPM pairs with slight detector differences,
  leaving a rhythm stutter at those transition boundaries (user heard at 9:21).
- **Stretching Demucs stems independently (v2 research finding):** Do NOT time-stretch
  drums/bass/other stems separately with pyrubberband then re-sum. pyrubberband's phase vocoder
  introduces per-frequency-bin phase rotations that differ per stem → comb filtering at 60–120 Hz
  (exactly where kick/sub-bass overlap). The re-summed audio sounds thin and hollow. Only stretch
  the FULL mix; then apply EQ filtering on the already-stretched blend zone.
- **Drum-stem beat detection (v2 research finding):** Running beat_this on a Demucs drum stem does
  NOT improve phase accuracy. beat_this was trained on full-mix audio — feeding it an isolated drum
  stem is out-of-distribution. Our 2–8ms phase errors are already below what academic papers target.


## v2 — EQ-style per-band crossfade (branch: v2-stem-mixing)

### What it does

Instead of a uniform equal-power crossfade across all frequencies, v2 applies **Pioneer DJM-800
frequency band curves** to the blend zone. Research finding: the biggest perceptual improvement
in DJ transitions is eliminating bass clash (two kick+sub-bass signals simultaneously producing
comb filtering at 60–120 Hz).

### Signal flow

```
Full track A → time-stretch (pyrubberband) → samples_a
Full track B → time-stretch to A's BPM    → samples_b_s
Select blend zone via offset search (beat CV + phase score) [equal-power for measurement]
After offset + drift correction are locked:
  A blend zone = samples_a[outro_sample : outro_sample + n]
  B blend zone = samples_b_s[trim : trim + n]
  _band_split(A zone) → (A_bass, A_mid, A_high)   [IIR zero-phase, lossless]
  _band_split(B zone) → (B_bass, B_mid, B_high)
  A_bass * logistic_out(p) + B_bass * logistic_in(p)   ← sigmoid swap at 50 %
  A_mid  * equal_power_out(p) + B_mid  * equal_power_in(p)
  A_high * equal_power_out(p) + B_high * equal_power_in(p)
  → sum → clip to [-1, 1] → best["blend"]
```

### Key implementation facts

- **Bands:** bass = 0–200 Hz (4th-order Butterworth LPF), high = 5 kHz+ (HPF), mid = A − bass − high.
  `bass + mid + high == audio` exactly (no energy loss or overlap artifacts).
- **Bass swap:** logistic (sigmoid) centered at 50% of blend, width w=0.12 (≈3.7 s at 31 s blend ≈2 bars).
  Short enough to avoid prolonged comb filtering; not a hard cut, so no click.
- **Measurement blends** (offset loop, drift correction) still use equal-power so beat_this CV/phase
  scores are clean and unaffected by the EQ curves.
- **`_reblend`** (used for capped bodies) also uses `_eq_blend`. Falls back to equal-power when
  `USE_EQ_BLEND = False`.
- **`USE_EQ_BLEND`** flag at module level — set `False` to revert to v1 equal-power for A/B comparison.

### Files changed in v2

- `mixer/set_builder.py` — added `_band_split`, `_eq_blend`, `USE_EQ_BLEND`; updated `_reblend`;
  applied EQ blend after offset/drift selection, before export.
- `mixer/stems.py` — Demucs htdemucs wrapper, cached npz. Available for future experiments but
  NOT used in the main blend path (stretching stems independently breaks phase coherence).
- `tests/test_set_quality.py` — 7 new unit tests: band_split sums to original, bass/high capture
  correct frequencies, shape, no clipping, bass swap verified by correlation, USE_EQ_BLEND=True.

### Perceptual improvement expected

- Bass clash eliminated — one kick at a time through the blend.
- Melody (mid/high) transitions smoothly with standard equal-power.
- Phase accuracy unchanged (still measured and enforced at < 20ms).
- The "starts matched then gets unmatched" complaint may be partially masked by the EQ swap —
  phase errors above 6ms are most audible when both bass lines are simultaneously present.


## Story shorts — what works and what doesn't (discovered June 2026)

We made 5 AI short films using the formula: one character (same face), one prop, one setting,
12 scenes with eyeline match structure, one emotion arc. Two worked, three didn't.

### What worked
- **The Photo** — park bench, photograph of a woman, grief/longing → unexpected reunion
- **The Find** — beach, tin box, wonder → absurd pride (the token is worthless; he's proud anyway)

### What didn't work
- **The Recipe** — kitchen, recipe card, determination → triumph
- **The Leaf** — apartment, dying plant, tenderness → joy
- **The Train** — subway, unsent phone call, hesitation → choice (visuals were good, story unclear)

### Why — the three rules

**Rule 1: The prop must carry HISTORY, not FUNCTION.**
A photograph and an arcade token are *evidence of something that happened before the scene started.*
They do nothing. They just *were.* A recipe card is an instruction — it tells you what to DO.
A plant is alive and present. Cinematic props are objects with unexplained pasts, not tools.

**Rule 2: The emotion must be SPECIFIC and SURPRISING — not earned.**
Absurd pride over a worthless token = unexpected. You laugh because it's specific and weird.
Grief → reunion = unexpected reversal. You feel it because you didn't see it coming.
Triumph after cooking = exactly what you expected. No surprise, no feeling.
Joy at a plant surviving = visible from scene 1. No reveal, no landing.
The audience should not know what emotion they're going to feel until the last 2 scenes.

**Rule 3: The character must DISCOVER, not DO.**
Finding a photo, finding a token — the character is *changed by something external.*
Cooking, repotting — the character *does a task.* Tasks don't move an audience.
Short films without dialogue need a character who is acted upon, not acting.

### The formula that works
> Character finds an object that belongs to the past → reacts in a way we didn't predict
> → the world responds in a way we also didn't predict

### The Train — borderline case
The phone is the right kind of prop (loaded, past-connected, belongs to an unresolved story).
But "decides not to call" has no visible emotional resolution. The face can't show "I chose not to."
The train visuals are strong — the story needs a clearer ending state that reads on a face.

### For next stories
- Every story needs a *specific surprising detail* (not "a recipe card" — "a recipe in handwriting
  he doesn't recognize until the last scene")
- Every story needs an *unexpected ending* — not the outcome the setup implied
- The prop should be something you'd find at an estate sale, not something you'd buy at a store
- The emotion arc should end somewhere the audience didn't think they were going

---

## Wordless short film — craft rules (confirmed by deep research, June 2026)

These come from Kuleshov Effect research (2024 peer-reviewed fMRI study) + production testing
on five AI short films. Delete this section if we find better rules.

### The beat IS the cut

Emotion in a wordless scene is not in the face alone or the object alone — it's constructed by
the audience at the moment the two are cut together. Face → object. That juxtaposition IS the
story. Everything before is setup. What the face does after is the release.

Structure of one beat:
1. Setup — establish character and world, prime the audience
2. The cut — face meets object (or object reveals something to face)
3. Release — face reacts, world responds

A "twist" is just a second juxtaposition that reframes what the first one meant.

### What makes a prop work

The object must carry history — evidence of something that happened before the scene started.
It does nothing. It just *was.* The character's reaction to it is the story.

Props that work: photographs, old letters, a found object from someone else's life, something
that belongs to the past and does nothing useful now.

Props that fail: tools, instructions, anything that tells the character what to DO next.

### What reads on a face (use these)
- Recognition — I know what this is
- Surprise — this isn't what I expected
- Loss — something I can't get back
- Understanding something for the first time

### What doesn't read on a face (avoid these)
- Internal decisions — "I decided not to call" is invisible
- Abstract emotions — determination, tenderness, pride in general (too generic)
- Anything requiring explanation — if it needs words, it doesn't work
- Causally complex backstory — the audience can't reconstruct it from a face

### The Portrait rule (confirmed working)
The Portrait concept works because all three shots are readable without words:
face staring at painting (setup) → guard sees himself in it for the first time (the beat)
→ neither of them says anything (the release). No interior access required at any point.
This is the template: everything visible, nothing explained.

### CRITICAL: Never evaluate a story sequence without music

Evaluating still images silently will always feel flat. This is not a narrative problem — it is a neurological fact.

Baumgartner et al. (2006, Brain Research) showed that still images activate cognitive emotion processing only. Music + congruent images activates amygdala, hippocampus, insula, striatum — the circuits that produce FELT emotion. A physiological study (PMC6014633) measured music vs. silence on identical video clips: heart rate p<.01, respiration p<.001, skin conductance p<.001, pupil diameter p<.001.

**The sequence is not broken. It is incomplete.** Before judging whether a story works, set it to music and watch it. What feels flat as static images often lands with the Solomun mix underneath.

Wrong music makes things worse than silence. The music must match the emotional register of the scene.

### The 12-scene structure (face/environment ratio)

**Face-to-environment ratio: approximately 4 face shots / 8 non-face shots.** The face is scarce, therefore valuable. Sequences that stay in close-up throughout flatten.

| Scene | Shot | Purpose |
|---|---|---|
| 1 | Wide establishing | World, not character. Context before character. |
| 2 | Medium | Character in world. Action, not face. |
| 3 | Prop close-up | The object. Negative/loss valence. |
| 4 | Face close-up | First face. Neutral expression. Kuleshov now active. Hold 3-4s. |
| 5 | Aspect-to-aspect | Environment fragment. No narrative advance. Mood. |
| 6 | Wide reset | Pull back. Resets contrast for next close-up. |
| 7 | Prop (different state) | Prop changed or seen differently. |
| 8 | Face (longer hold) | Viewer is attributing deeply. Hold longer than scene 4. |
| 9 | Medium with action | Something shifts. |
| 10 | Face (apex) | Emotional climax. Maximum hold. |
| 11 | Prop insert (brief) | Object encapsulates the meaning. |
| 12 | Wide | Return to world. World unchanged. Viewer is not. |

**Prop valence rule:** The Kuleshov effect is twice as strong when the object preceding the face carries loss, absence, or negative valence (a withered flower, an empty chair, a photograph of someone absent). Props with positive valence produce a weak signal.

---

## AI short film — what actually makes them land (verified from 2025-2026 festival winners)

Research across real award-winning AI short films: Runway AI Film Festival 2026 (Grand Prix,
Gold), Reply AI Film Festival (Venice, Grand Prize), Global AI Film Award ($1M, Dubai),
AIIFF monthly winners, Shanghai SAISFF, viral Chinese AI shorts reaching hundreds of millions
of views. These are the patterns that separate the ones that moved audiences from the ones
that didn't.

### What works (confirmed across multiple winners)

**Non-human or silhouetted subjects sidestep the uncanny valley.** Live-action AI human faces
are stiff — at the Runway festival, animated/stylized entries outperformed live-action human
entries. "JAILBIRD" (Gold Award) used a chicken's POV. "Paper Phone" used restraint — the
boy's face, the shopkeeper's face — rather than constant face generation.

**Concept with emotional stakes built into the premise itself, not the craft.** "ZERO" (AIIFF
September winner): an AI named Zero wins the Nobel Prize in Literature. The premise IS the
emotion. Not "a story made with AI" — a story about something the AI existence makes possible.

**Cultural specificity beats generic sentiment.** "Paper Phone" (Kling AI, went viral in China):
a boy saves 15 RMB to buy a paper phone from a funeral goods shop to call his deceased
grandmother in the afterlife. Chaoshan funeral customs. The shopkeeper's slow realization.
Not "a boy misses his grandmother" — a very specific, culturally located gesture.

**The reveal reframes everything.** The emotional landing is when something is suddenly
understood differently. If the audience sees the ending coming, the film is "sentimental and
predictable" — that was said about the Runway Grand Prix winner even as people cried at it.
The best ones land somewhere the audience didn't know they were going.

**Restraint over spectacle.** Jury quote from "You Just Forgot" (Best Directing, Shanghai):
"restraint rather than spectacle, showing how AI can create atmosphere." Three days,
one prop, minimal generations — the best AI films are often the simplest productions.

### What fails (confirmed across multiple reviews)

**Photorealistic live-action human faces.** Owen Gleiberman (Variety) on "Dreams of Violets"
(Tribeca 2026): "the uncanny-valley problem between us and the cataclysm." Technically
photorealistic imagery the viewer knows is fake creates distance rather than connection.
Animated or stylized visuals bypass this entirely.

**Predictable emotional resolution.** If the structure is "setup → exactly the outcome the
setup implied," there is no emotional event. The audience needs to land somewhere they
didn't predict.

**Documentary-style photorealism strung together.** Gleiberman again: "like moments from a
documentary strung together... stultifying." No dramatic development. Technically impressive
visuals without a story engine.

**Too many images, too long.** The community consensus (confirmed across multiple AI filmmaker
interviews): cut the sequence in half before regenerating anything. Structure problems cannot
be solved with more images.

### The Paper Phone formula (the most studied viral AI short)
- One boy, one funeral shop, one paper phone
- The beat: the shopkeeper realizes what the boy wants — his face changes
- The release: a children's song AI-generated. Long take. Nothing explained.
- What makes it work: The prop is specific to a culture's funeral practice. The boy doesn't
  know his grandmother is gone — that's what the shopkeeper sees. The emotion is in
  the shopkeeper's face, not the boy's. Discovery, not understanding.

## AI face production rules — from 2024-2026 peer-reviewed research

These are not aesthetic preferences. They reflect how the human visual system actually processes AI faces.

### What the research says (confirmed by multiple EEG + behavioral studies)

**Smiles are the hardest expression to make land.** EEG research (Eiserbeck et al., 2023) found that AI smiles do not fire the same neural chains as real smiles — the P1/N170/EPN sequence that produces genuine emotional resonance is suppressed when the viewer suspects synthetic origin. Angry/tense expressions retain full neural impact regardless of label. **Consequence for story scenes:** schedule emotional climaxes around recognition, stillness, and loss — not happiness. A man going still is more powerful in AI than a man smiling.

**Categorization failure = maximum discomfort.** The uncanny valley is not produced by difficulty of classifying a face — it's produced by FAILURE to classify it. Faces stuck in "almost human" are the worst. **Consequence:** either be clearly, authentically human (via imperfections) OR use silhouettes/stylization. The middle zone is the dead zone.

**AI faces have passed through the uncanny valley for neutral expressions.** At 48-62% human detection accuracy (barely above chance), modern diffusion faces in neutral expressions fool most viewers. The remaining failure modes are specific: smiles, complex grief cascades, and fine eye animation.

**Eyes are the primary detection region.** Eye tracking studies show eyes attract the most fixations during authenticity evaluation. Dead/empty/doll eyes are the most cited uncanny trigger. Add "eyes glistening," "eyes sharpening," "eyes going still" — never just "sad eyes."

### The mid-action principle (single biggest authenticity lever — no technical knowledge required)

Describe the subject as mid-way through an action, not positioned. "Caught mid-" language forces the model to render interrupted motion rather than posed stillness.

| Stock/Posed (avoid) | Mid-action (use) |
|---|---|
| "a man sitting by a window" | "a man mid-turn away from the window, one hand still on the sill" |
| "a woman holding a photograph" | "a woman who has just stopped moving, photograph in both hands, arms not yet lowered" |
| "man with a sad expression" | "a man whose face has gone very still" |
| "woman smiling" | "a woman mid-laugh, head turned, caught between two expressions" |

### Micro-imperfection keywords (fight hyper-averageness)

AI faces are too symmetrical, too average. Peer-reviewed research (Dunn & Dawel 2026) confirms modern AI faces are detected via their *excessive perfection* — real faces have 10-15% asymmetry from lived experience. Add these to every character face prompt:

`natural facial asymmetry` / `visible pores` / `subtle skin texture` / `unretouched` / `natural skin imperfection` / `slight weathering`

Never add: "perfect skin," "flawless," "professional photo," "beautiful" — these push the model toward the averaged-attractive aesthetic that reads as AI.

### Three-part lighting rule

Specify all three, or the model defaults to flat safe lighting:
1. **Direction** — "from camera left," "window at 45 degrees," "overhead"
2. **Quality** — "soft diffused," "hard single source," "overcast"
3. **Color temperature** — "3200K tungsten," "5500K daylight," "warm golden hour"

Example: "soft diffused window light from the left, 5500K daylight, gentle shadow on the right side of the face"

---

## HARD RULE: Story pipeline always uses the story_test7 approach

The working pipelines are:
- `story_pipeline/run_four_stories.py` — original 4-story implementation, fully working
- `story_pipeline/run_new_stories.py` — rewritten June 2026 to use the same approach (Gemini chat + ref sheets)

Never generate story image sequences using raw FLUX 1.1 Pro without character references.

### The story_test7 approach (confirmed working)

**Reference sheets required before any scene generation:**

1. **Character references** — generate or collect 3 images of the character from DIFFERENT angles:
   - `char_front.jpg` — straight-on face
   - `char_34.jpg` — 3/4 view
   - `char_profile.jpg` — side profile
   - Do NOT use 3 frontal shots — different angles is what makes the ref sheet work
   - Store in `output/story_test7/ref_sheet/` (the existing working refs live here)

2. **Prop reference** — generate via FLUX 1.1 Pro at 1280×720:
   - `ref_prop.jpg` — the story's key prop, isolated, well-lit

3. **Location reference** — generate via FLUX 1.1 Pro:
   - `ref_location.jpg` — the setting, establishing shot

**Generation pipeline (Gemini stateful chat):**

```python
CHAR_REFS = [
    Path('output/story_test7/ref_sheet/char_front.jpg'),
    Path('output/story_test7/ref_sheet/char_34.jpg'),
    Path('output/story_test7/ref_sheet/char_profile.jpg'),
]

client = genai.Client(api_key=GEMINI_KEY)
config = types.GenerateContentConfig(response_modalities=['IMAGE', 'TEXT'])
chat = client.chats.create(model='gemini-3.1-flash-image', config=config)

# Scene 1: send all 5 reference images + description
ref_parts = [_part_from_path(p) for p in CHAR_REFS] + [
    _part_from_path(prop_path),
    _part_from_path(loc_path)
]
chat.send_message(ref_parts + [scene_1_description])

# Scenes 2-12: description only — chat remembers the references
# Re-inject character refs every 6 scenes to prevent drift
for i, scene in enumerate(scenes[1:], 1):
    if i % 6 == 0:
        parts = [_part_from_path(p) for p in CHAR_REFS] + [scene.description + "\nSame character as references. Keep exact face."]
    else:
        parts = [scene.description + "\nKeep exact character appearance. Same man, same face, same horseshoe mustache."]
    chat.send_message(parts)
```

**Why this works:** Gemini stateful chat maintains the character's visual identity across all
12 scenes because the reference images are in the chat context from scene 1. Raw FLUX generates
each image independently with no memory — faces drift completely.

**Gemini drift rule:** Re-inject the character reference images every 6 scenes. Gemini's chat
context holds up to ~8 turns of strong identity signal before drift starts. Re-injection on
turn 6 prevents compounding drift in the second half of a 12-scene sequence. See `run_new_stories.py`
for the implementation.

**Authentic emotion in FLUX prompts (from official BFL docs):** Describe HOW emotion manifests physically, not just the emotion name. Naming the emotion produces a posed, performed look.

| Weak (too generic) | Strong (physical) |
|---|---|
| `"sad"` | `"eyes glistening with unshed tears"` |
| `"happy"` | `"genuine laugh, eyes crinkled"` |
| `"tense"` | `"furrowed brow, slight jaw tension"` |
| `"pensive"` | `"gaze directed downward, lips slightly parted"` |
| `"recognition"` | `"eyes sharpening, body gone still"` |
| `"grief"` | `"face suspended between recognition and something he cannot name"` |

Add `"candid"`, `"unaware of camera"`, `"unposed"` to override FLUX's default frontal-pose bias.
Add `"visible pores"`, `"subtle asymmetry"` to fight the beauty-filter / stock-photo bias.

**FLUX Raw Mode** (`raw=True` in the API / toggle in ComfyUI): The single most effective toggle for candid photography aesthetics. Specifically designed to add natural imperfections, organic shadows, and increase subject diversity — breaks the statistical-average-attractive default. Use this for any story scene requiring emotional authenticity.

**FLUX does NOT support negative prompts natively.** BFL official docs confirm this. No `--no` equivalent. Describe only what you want; use affirmative language only.

**The bittersweet compound (AU6 + AU1):** The most cinematically effective expression for complex emotion — genuine eye smile (AU6, cheek raiser) contradicted by worried inner brow raise (AU1). Reads as someone who is happy but also grieving something. Use: `"genuine eye smile, eyes crinkling at corners, inner brow slightly raised in concern"`. This is the Duchenne-marked complex expression that reads as a real person, not a stock photo.

**What NOT to do:**
- Never use raw FLUX 1.1 Pro without character references for story sequences
- Never use 3 frontal character shots (use front + 3/4 + profile)
- Never chain from edited outputs (each generation drifts further from the original)

---

## Character consistency — production rules (June 2026)

Research confirmed across 30+ sources including official BFL documentation, arxiv papers,
and community benchmarks. Claims not backed by primary sources are flagged.

### The best tools (ranked)

**1. FLUX.1 Kontext — best for iterative story editing** (released May 29, 2025)

In-context image editing: pass a reference image + text instruction → model preserves
identity while changing the scene. No LoRA training needed.

Available on Replicate: `black-forest-labs/flux-kontext-pro` ($0.04/image)

```
Power phrases that preserve identity:
"while maintaining the same facial features"
"while preserving exact facial features, eye color, and expression"
"keeping identical [feature]"

Subject references — use NOUNS not pronouns:
WRONG: "Make her wear a coat"
RIGHT: "Change the woman with short black hair into a viking warrior while
        preserving her exact facial features, eye color, and expression"

Scene transitions:
WRONG: "Transform into a jazz club performer"  ← destroys face
RIGHT: "Change the setting to a jazz club while preserving her exact face"
```

CFG: 2–4 (lower prevents over-stylization). Denoising: 0.6–0.8.
Reset to ORIGINAL reference every 3–4 edits — drift accumulates across chained outputs.

**2. InfiniteYou (ByteDance) — highest face quality** (ICCV 2025 Highlight)

Residual injection (not cross-attention) → no face-paste artifacts.
72.8% human preference over PuLID. Lower identity loss than PuLID in paper benchmarks.
`zsxkib/infinite-you` on Replicate ($0.038/run, ~39s)

**3. PuLID-FLUX (ByteDance) — best zero-shot API option**

`bytedance/flux-pulid` or `zsxkib/flux-pulid` on Replicate ($0.020/run)
id_weight: 1.0 default (0–3 range; higher = stronger face preservation)
start_step: 4 for photorealistic, 0 for stylized/max identity

**4. FLUX.2 Pro multi-reference — our validated 5-ref approach**

Native multi-reference support (up to 10 images simultaneously).
Our 5-ref approach (char×3 angles + prop + location) is confirmed best practice.
`black-forest-labs/flux-2-pro` on Replicate

### The Character DNA block (copy-paste verbatim into every prompt)

For FLUX.1 and FLUX.2, the character description block must be:
- Written once and copy-pasted identically into every scene prompt
- NEVER paraphrased or synonymized ("blazer" and "jacket" are different tokens)
- Written as prose sentences, NOT keyword lists (FLUX T5-XXL/Mistral is prose-trained)
- Subject placed FIRST (Mistral encoder is order-sensitive — earlier tokens have stronger weight)

**Fixed attribute order (locks identity across generations):**
```
age → gender → hair (color, style, texture) → skin → distinctive marks → outfit → [VARY: action, setting, lighting]
```

**Example DNA block:**
```
A 35-year-old man with sharp cheekbones and close-set dark eyes, short black hair with
a natural wave, pale skin with a faint scar through his left eyebrow, wearing a dark grey
wool coat with the collar up, [SCENE-SPECIFIC CONTENT HERE], cinematic
```

**After writing the DNA block:** append only what changes (scene, action, lighting).
Never put the scene first and character second.

### What DOESN'T work (verified as failures)

- **Text-only prompting** — cannot reliably anchor face biometrics across independent
  generations. Each generation starts from random noise. Text captures style/silhouette
  but NOT unique facial geometry.
- **FLUX IP-Adapter (standard)** — the creators (InstantX) explicitly state it is "not for
  fine-grained character consistency." Do not use for face identity. IP-Adapter FaceID
  variants (which use InsightFace embeddings rather than CLIP/SigLIP) can work for faces —
  but the standard IP-Adapter cannot. The recommended scale for FaceID is 0.5–0.7 (official
  HuggingFace docs default: 0.5; FaceID example: 0.6). The "0.65 sweet spot" cited in some
  blogs is not in any official documentation.
- **Keyword/tag lists** — FLUX T5-XXL and Mistral were trained on prose, not image tags.
  Comma-separated keywords parse as malformed English.
- **Negative prompts** — FLUX.1 and FLUX.2 do not support negative prompts. Affirmative
  language only ("clean-shaven" not "no beard").
- **Transformation verbs** — "transform into", "make them look like" destroys facial identity.
  Use "change the setting to X while preserving her exact face."
- **Chaining from edited outputs** — drift accumulates. Always use the ORIGINAL reference
  image as input for each new scene, not the output of the previous edit.
- **The "40% identity drift reduction" and "90%+ identity preservation" claims attributed
  to BFL** — FABRICATED. These numbers appear in AI-generated search summaries and SEO
  blogs (selfielabstudio.com). They do not appear in any BFL official document, the
  Kontext technical paper (arxiv 2506.15742), or any independent benchmark. BFL's actual
  claims are qualitative (top rank on KontextBench) with no specific percentage stated.

### Character reference sheet requirements

When building new character reference sheets:
- Minimum 3 angles: front view, 3/4 view, side profile (NOT 3 frontals)
- Clean background on reference shots
- Include at least 2 different expressions
- 1024×1024 minimum resolution
- Use the reference that best shows the distinctive marks (scar, mole, etc.)

---

## Session — June 24-25 2026: Story pipeline audit + Flamingo

### What was done

**Visual audit tool improvements (`story_pipeline/audit_images.py`):**
- Fixed parser apostrophe bug: `[^"']` regex stopped at apostrophes in scene titles (e.g., "What's Left"). Fixed to `[^"]+` (double-quote only). Caused 13-scene stories to parse as 12 scenes, generating all false positives for flowers.
- Fixed sequence checker: "face CU before first object CU" was flagging setup faces. Now only flags if the KULESHOV-tagged scene appears before its first object CU trigger.
- Consecutive wides: changed from hard error to ℹ️ rhythm note — action+consequence pairs legitimately use two wides.

**Stories fixed and passing (all 5 pass visual audit):**
1. `run_bees.py` — 15/15 ✅ (was already clean; rhythm notes only)
2. `run_handoff.py` — 13/13 ✅ (Kuleshov eyeline fixed in prior session)
3. `run_umbrella.py` — 13/13 ✅ (outfit on FLUX montage shots; scene 09 eyeline; scene 11 changed to "The Cross" — profile run instead of toward-camera)
4. `run_flowers.py` — 13/13 ✅ (parser bug was causing all false positives; actual images were fine)
5. `run_flamingo.py` — NEW. 13/13 ✅. See below.

**New story: The Flamingo (`story_pipeline/run_flamingo.py`):**
- Man running encounters a pink plastic lawn flamingo that slightly encroaches his path
- He moves it → it returns. He moves it farther → it returns with a dinosaur next to it
- THE TEN: he returns to find the flamingo surrounded by a full semicircle of child's toy animals (dinosaur, lion, bear, giraffe)
- No child ever in frame — audience reads the arrangement and understands everything
- First confirmed use of **Prop Accumulation Reveal** (see STORY_SKILL.md, section 5)

**Camera-facing wide shot fix (discovered across umbrella + flamingo):**
Wide action shots where character "runs SCREEN-RIGHT" often generate character facing camera.
Fix: always add "seen FROM BEHIND AND SIDE" or "seen from the side in profile — NOT facing camera" to every wide shot where the character is running or walking.

**write_story.py — generator hardening:**
- Added explicit bans for smart glasses, AR displays, laptop screens as story elements
- These appear repeatedly because Lou's brain captures his internal world (data, analysis, technology). The generator now explicitly refuses these.

**Current state:**
- All 5 stories: 0 hard errors in visual audit, warnings only (collar down in some action shots — acceptable)
- `output/flamingo/` — 13 scenes generated, ready to animate
- Branch: `v2-stem-mixing`

---

## Session — June 21 2026: Four Stories + Solomun set rebuild

### What was done

**Story pipeline (FOUR_STORIES_INTERCUT):**
- Produced 5 AI short films: The Find, The Recipe, The Leaf, The Train, The Photo
- Added 4 ambient first/last-frame sequences (FLUX+Hailuo-02 chain) as bridges between stories
- Sequence: FIND → ambient1 → RECIPE → ambient2 → LEAF → ambient3 → TRAIN → ambient4 → THE_PHOTO
- ambient4 (TRAIN→THE_PHOTO): 8 FLUX images (nighttime subway → pre-dawn city → park bench), 8 Hailuo-02 clips at 10s, assembled to ~80s
- Key scripts: `story_pipeline/run_final.py` (ambient4 + full assembly), `story_pipeline/run_four_stories.py`, `story_pipeline/run_intercutting.py`
- `output/FINAL_STORIES_INTERCUT_V2.mp4` — the visual-only story intercut (~14.5 min)

**Story video format rule (save for next time):**
- Hard cuts between scenes look better than transitions
- Ambient first/last sequences go ONLY between complete stories, not between every scene

**Solomun set ("sorry_i_am_late") — bugs found and fixed:**

1. **First track opener replaced**: KT_Sorry (Kollektiv Turmstrasse) removed as opener — song has an unblendable outro structure. Replaced with **Adriatique - Mr. Creasy** (124 BPM, F minor / 9A Camelot). This is the same track Solomun used in his 2013 Pacha Ibiza set. Downloaded to `downloads/solomun/2dF1g2Jw33k.mp3`. Phase error: 0.3ms, RMS ratio: 1.07×.

2. **First track bar-snap fix** (`mixer/set_builder.py`, `idx==0` path): Body cap at 180s was using `body_end = min(outro_sample, 180*sr)` — not bar-aligned. Added bar-snap backward loop (same logic as mid-set capped transitions). Ensures `_reblend` A-side starts on correct beat phase.

3. **Adana_Strange `mix_in_bars` fix**: Was `32` (bar 32 = 69s into track = 0.24 RMS, full volume). Fixed to `0` (enters from quiet beginning at 0.07 RMS). Same category of bug as Adana_Everyday, Brecht, Ame_Fiori. Root cause: the "quiet 32-bar intro ✓" note was wrong.

**Current state:**
- `output/sorry_i_am_late/FULL_SET.mp3` — 116MB, 63:22 duration, all 19 transitions pass (phase <12ms, RMS <2.1×)
- `output/FINAL_STORIES_SOLOMUN_V3.mp4` — 370MB, uploaded to YouTube: https://youtu.be/xC7TrzArE0k
- Branch: `v2-stem-mixing` (3 commits ahead of origin)

**Known remaining issues to investigate if picking up:**
- YouTube thumbnail upload returns 403 (channel needs verification at youtube.com/verify)
- KT_Sorry (`fMNdGT7yAC8.mp3`) is still in `downloads/solomun/` but removed from TRACKS list — can delete or repurpose
