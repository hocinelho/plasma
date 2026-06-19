# locate-anything — external dependency

Open-vocabulary object detection via [locate-anything.cpp](https://github.com/mudler/locate-anything.cpp)
(NVIDIA LocateAnything-3B on ggml). Lets Plasma find ANY object by description:
"find my keys", "where is my phone", "Wo ist mein Schlüssel".

This folder holds the compiled binary and model only — the source stays external.

---

## One-time setup (Windows)

### 1. Build the CLI

Open **Developer PowerShell for VS 2022** (requires Visual Studio with "Desktop development with C++"):

```powershell
cd C:\Users\<you>\PycharmProjects
git clone --recursive https://github.com/mudler/locate-anything.cpp
cd locate-anything.cpp
cmake -B build -DLA_BUILD_CLI=ON
cmake --build build --config Release -j
```

### 2. Copy the binary here

```powershell
copy "C:\Users\<you>\PycharmProjects\locate-anything.cpp\build\examples\cli\Release\locate-anything-cli.exe" `
     "C:\Users\<you>\PycharmProjects\plasma\external\locate-anything\bin\locate-anything-cli.exe"
```

### 3. Download the model here

```powershell
hf download mudler/locate-anything.cpp-gguf locate-anything-q8_0.gguf `
    --local-dir "C:\Users\<you>\PycharmProjects\plasma\external\locate-anything\models"
```

Or with SSL bypass (corporate networks):
```powershell
$env:HF_HUB_DISABLE_SSL_VERIFY = "1"
hf download mudler/locate-anything.cpp-gguf locate-anything-q8_0.gguf `
    --local-dir "C:\Users\<you>\PycharmProjects\plasma\external\locate-anything\models"
```

Or use curl:
```powershell
curl.exe -L -k -o "external\locate-anything\models\locate-anything-q8_0.gguf" `
    "https://huggingface.co/mudler/locate-anything.cpp-gguf/resolve/main/locate-anything-q8_0.gguf"
```

---

## One-time setup (Linux / Proxmox LXC)

```bash
apt install -y git cmake build-essential
git clone --recursive https://github.com/mudler/locate-anything.cpp /tmp/la
cd /tmp/la && cmake -B build -DLA_BUILD_CLI=ON && cmake --build build -j$(nproc)
cp /tmp/la/build/examples/cli/locate-anything-cli external/locate-anything/bin/
pip install huggingface_hub
python3 -c "from huggingface_hub import hf_hub_download; \
    hf_hub_download('mudler/locate-anything.cpp-gguf', 'locate-anything-q8_0.gguf', \
    local_dir='external/locate-anything/models')"
```

---

## .env configuration

```
# Local — binary + model in this folder
LOCATE_ANYTHING_BIN=external/locate-anything/bin/locate-anything-cli.exe
LOCATE_ANYTHING_MODEL=external/locate-anything/models/locate-anything-q8_0.gguf
LOCATE_ANYTHING_THREADS=20   # set to (your_cores - 2)

# OR — remote server (run tools/locate_server.py on a GPU machine)
# LOCATE_ANYTHING_SERVER_URL=http://192.168.1.50:8765
```

---

## Available model sizes

| File | Size | Notes |
|------|------|-------|
| `locate-anything-q8_0.gguf` | ~6.3 GB | recommended — fast, near-identical quality |
| `locate-anything-q6_k.gguf` | ~5.5 GB | |
| `locate-anything-q4_k.gguf` | ~4.7 GB | smallest — use on low-RAM machines |
