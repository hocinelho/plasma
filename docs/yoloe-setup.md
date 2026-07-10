# YOLOE setup — open-vocabulary recognition ("pen", not "toothbrush")

The default detector only knows 80 COCO classes — it physically cannot say
"pen". YOLOE lets you bake **your own object list** into a model that runs in
real time on CPU via onnxruntime (already installed with Plasma).

⚠️ Licensing note: YOLOE weights + the `ultralytics` exporter are **AGPL-3.0**
(unlike the rest of Plasma's Apache/MIT stack). Fine for personal, private
use; don't redistribute Plasma bundled with the model. The exporter is only
needed on the machine that does the export — Plasma itself never imports
`ultralytics`.

## Step 1 — export the model (on any PC WITH internet, not necessarily this one)

```bash
pip install ultralytics
python - <<'EOF'
from ultralytics import YOLOE

model = YOLOE("yoloe-11s-seg.pt")           # ~small; use 11m for more accuracy

# YOUR object list — edit freely. Short, concrete nouns work best.
names = [
    "person", "face", "hand",
    "pen", "computer mouse", "keyboard", "laptop", "phone", "headphones",
    "bottle", "red bull can", "coffee mug", "glass",
    "keys", "wallet", "glasses", "watch", "remote control",
    "book", "notebook", "chair", "plant", "toothbrush",
]
model.set_classes(names, model.get_text_pe(names))   # bake the vocabulary in
model.export(format="onnx", imgsz=640)               # -> yoloe-11s-seg.onnx
EOF
```

First run downloads the weights (~30 MB for 11s) plus the text encoder. The
result is a single `.onnx` file (~30–90 MB) with your class names embedded in
its metadata.

## Step 2 — copy it to the Plasma machine

Copy `yoloe-11s-seg.onnx` (USB stick is fine) to:

```
<plasma>/.plasma/models/yoloe.onnx
```

(or any path — then set `YOLO_ONNX_MODEL=<path>` in `.env`).

## Step 3 — switch Plasma to it

`.env`:

```ini
VISION_BACKEND=yolo_onnx
```

Restart. The startup log shows either
`Detector backend: YOLO-ONNX (...)  YOLO ONNX ready: 23 classes ['person', ...]`
or a clear warning + automatic fallback to the old mediapipe detector (Plasma
never breaks if the file is missing).

## Step 4 — verify

Open the UI → 👁 Watch me → 🎯 Track objects. Hold up the pen: the box should
say **pen**, and the Red Bull can **red bull can**.

## Changing the vocabulary

The class list is fixed at export time. To add an object, re-run Step 1 with
the new list and replace the `.onnx`. (`YOLO_ONNX_CLASSES` in `.env` only
*renames* classes — it cannot add ones the export doesn't know.)

## Tuning

```ini
# .env                       default
VISION_SCORE_THRESHOLD=0.5   # snapshot confidence floor
TRACK_CONF=0.35              # live-feed confidence floor
YOLO_ONNX_IOU=0.45           # NMS overlap threshold
YOLO_ONNX_IMGSZ=640          # inference size (matches export; auto-read from metadata)
```

If live tracking feels heavy on CPU, lower `TRACK_FPS` (e.g. 8) or export the
smaller `yoloe-11s` variant instead of `11m`.
