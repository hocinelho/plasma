# Avatar animations (Mixamo FBX)

Drop Mixamo animation files here. They're served at `/animations/<file>.fbx`
and played on the 3D avatar with TalkingHead's `playAnimation()`.

## Downloading from Mixamo — exact settings

Go to [mixamo.com](https://www.mixamo.com) (free Adobe account), pick an
animation, then in the **Download** dialog set:

| Setting | Value | Why |
|---|---|---|
| **Format** | `FBX Binary (.fbx)` | The loader is an `FBXLoader` — glTF/Collada won't load. |
| **Skin** | **Without Skin** | We only want the motion; our own avatar supplies the body. Much smaller files. |
| **Frames per Second** | `30` | See the fps note below — 60 works too, it is just bigger. |
| **Keyframe Reduction** | `none` | Keeps the motion smooth. |

The character you preview it on does **not** matter when downloading
*Without Skin* — only the skeleton motion is exported, and every Mixamo rig
uses the same bone names.

## Is 60 fps better?

No, not usually. Mixamo's mocap is authored around 30 fps; exporting at 60
resamples it and interpolates the in-between frames — you get twice the
keyframes and roughly twice the file size, but no motion detail that was not
captured in the first place.

three.js interpolates between keyframes anyway and renders at the display's
refresh rate, so 30 fps keyframes already play back perfectly smoothly at
60 Hz+. Use 60 only for genuinely fast motion (a punch, a fast spin) where
30 samples per second can miss the peak of the movement. Both load fine.

## Why the settings matter

The player renames every animation track from `mixamorigHips.position` to
`Hips.position` and scales positions by `0.01` (Mixamo rigs are scale 100,
the avatar is scale 1). That only works with a genuine Mixamo FBX export —
which is why the format and the "Without Skin" option are not optional.

## Clips are auto-discovered

Any `.fbx` in this folder is picked up automatically and served at
`/animations/<name>.fbx` — no Python change needed to make it playable.
Filenames must be lowercase letters, digits and hyphens (`idle-breathe.fbx`);
anything else is ignored, because the name goes straight into a URL.

You only need to touch `backend/skills/avatar_move.py` to give a clip a
**voice command** and a spoken reply.

**Idle motion:** clips named `idle-*.fbx` are used as ambient movement — she
plays one at random now and then while standing idle, so she doesn't freeze
between conversations. Drop in `idle-breathe.fbx`, `idle-look-around.fbx`
and so on and it starts working immediately.

## Installed clips

`walking`, `start-walking`, `jump`, `waving`, `talking`, `arguing`,
`disappointed`, `secret`, `yelling`.

After adding a file, register the name in `backend/modules/avatar_state.py`
(`KNOWN_ANIMATIONS`) and `backend/skills/avatar_move.py` (`ANIMATIONS` +
`ANIMATION_KEYWORDS`), or nothing will trigger it.

## Naming

Use short, lowercase, descriptive filenames — they become part of the URL
and are what voice commands map to:

```
dance.fbx
wave.fbx
thinking.fbx
idle.fbx
```

## Size

Keep files reasonably small (a few MB). *Without Skin* exports are usually
well under 1 MB; a *With Skin* export can be 10–20 MB and also drags in a
character mesh we don't use.
