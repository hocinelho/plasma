# Characters

Drop a `.glb` in this folder and it appears in the picker on the main page.
No code change. The list is read from disk by `/api/avatar/models`.

**Every character plays every move.** The Mixamo clips in `../animations/` are
retargeted onto whichever skeleton is loaded, so swapping the face never costs
you the motion set.

## What a model needs

| Requirement | If it's missing |
|---|---|
| **ARKit / Oculus viseme blend shapes** | she loads, but her mouth never moves |
| **Mixamo-compatible rig** (`mixamorig` bones) | she loads and talks, but cannot walk, wave or dance |
| glTF binary (`.glb`) | won't load at all — `.obj` and `.fbx` are not accepted here |

## Free characters that already satisfy all of it

The [TalkingHead](https://github.com/met4citizen/TalkingHead) repo (MIT) ships
five sample characters, one from each avatar service:

```bash
git clone --depth 1 https://github.com/met4citizen/TalkingHead
cp TalkingHead/avatars/*.glb frontend/avatars/
```

| File | Source | Size | Licence |
|---|---|---|---|
| `brunette.glb` | Ready Player Me | 4.6 MB | CC BY-NC 4.0 — **non-commercial** |
| `avaturn.glb` | [Avaturn](https://avaturn.me) | 14 MB | non-commercial |
| `avatarsdk.glb` | [Avatar SDK / MetaPerson](https://avatarsdk.com) | 12 MB | non-commercial, logo on the shirt |
| `vroid.glb` | [VRoid Studio](https://vroid.com/en/studio) | 2.3 MB | permissive; anime style |
| `mpfb.glb` | [MPFB / MakeHuman](https://static.makehumancommunity.org/mpfb.html) | 36 MB | **CC0 — free for anything** |

Only `brunette.glb` is committed. The others are deliberately left out: this
repository is public, and four of the five are licensed for non-commercial use
only. Fetch the ones you want with the command above.

**`mpfb.glb` is the only unrestricted one.** If Plasma ever becomes anything
other than a personal project, that is the character to build on.

### Making your own

- [Avaturn](https://avaturn.me) — photo → realistic avatar, works as a drop-in
- [Avatar SDK / MetaPerson](https://avatarsdk.com) — has a *cartoon* style
- [VRoid Studio](https://vroid.com/en/studio) — free, anime; needs a
  [VRM → glTF conversion](https://github.com/met4citizen/TalkingHead/blob/main/blender/VRoid/VROID.md)
- [Microsoft RocketBox](https://github.com/microsoft/Microsoft-Rocketbox) —
  **MIT**, a whole library with ARKit shapes already, but the models must be
  re-rigged through Mixamo first
- Ready Player Me is **gone** — Netflix shut the creator down in January 2026.
  Existing exports still work.

## Labels

`avatars.json` beside these files gives the picker readable names, a body type
(`F`/`M`, which only selects built-in pose variants), and a note shown on
hover. It is entirely optional — an unlisted `.glb` is named after its file.
