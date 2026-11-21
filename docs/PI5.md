# AXIOM0 Living City — Raspberry Pi 5 Edition

One command turns a Raspberry Pi 5 into a self-contained AXIOM0 appliance. It runs the
local AI model (Ollama), the AXIOM0 dashboard and API, and the signed ledger. Nothing
leaves the box and nothing listens on the network.

```bash
sudo bash deploy/pi5/install.sh
```

The installer detects how much RAM the board has, picks a matching profile and model,
installs and tunes Ollama, downloads and preloads the model, starts AXIOM0 as a
sandboxed service, and finishes with a health report.

---

## 1. What you need

| Part | Recommendation | Why |
|---|---|---|
| Board | **Raspberry Pi 5, 8 GB** (16 GB also great; 4 GB works with a smaller model) | RAM decides which model fits |
| Cooling | **Official Active Cooler** (or a case with a fan) | AI work runs all 4 cores flat out; a bare Pi 5 throttles at 85 °C |
| Power | **Official 27 W USB-C supply** (5 V / 5 A) | Phone chargers cause under-voltage and slowdowns |
| Storage | **NVMe SSD on the M.2 HAT+** (or a USB 3 SSD); 64 GB+ | Models load 3–5× faster than from an SD card |
| OS | **Raspberry Pi OS Lite (64-bit)**, Bookworm or newer | The installer requires a 64-bit OS |

An SD card works, just with slower model loading. Use `--models-dir /mnt/nvme/ollama`
to keep models on an SSD when the OS boots from SD.

## 2. Install

On the Pi, from the repository folder:

```bash
sudo bash deploy/pi5/install.sh                  # auto profile from RAM
sudo bash deploy/pi5/install.sh --dry-run        # preview every step, change nothing
```

Useful options:

| Option | Effect |
|---|---|
| `--profile pi5-4gb\|pi5-8gb\|pi5-16gb` | Override the RAM-based profile |
| `--model qwen2.5:7b` | Use a different model (16 GB boards: better answers, about half the speed) |
| `--admin howard` | AXIOM0 operator label (default: the account that ran sudo) |
| `--models-dir PATH` | Store Ollama models on an SSD |
| `--ollama-version 0.x.y` | Pin the Ollama version |
| `--performance-governor` | Hold the CPU at full clock (only with active cooling) |
| `--skip-model` | Install everything now, download the model later |
| `--enable-anchors` | Daily signed ledger anchor, published from `/var/lib/axiom0-anchors` (see `ANCHORING.md`) |

The installer is safe to re-run. It keeps your keys and ledger, backs up the previous
config, and regenerates the tuning to match the profile you choose.

## 3. Profiles

| | pi5-4gb | pi5-8gb (recommended) | pi5-16gb |
|---|---|---|---|
| Model | `llama3.2:1b` | `llama3.2:3b` | `llama3.2:3b` (or `--model qwen2.5:7b`) |
| Source excerpts per answer | 3 | 4 | 6 |
| Context window | 3,072 | 4,096 | 6,144 |
| Max answer length | 384 tokens | 512 | 640 |
| Answer timeout | 300 s | 420 s | 600 s |
| Model stays loaded | 15 min idle | 30 min idle | always |
| Compressed swap (zram) | yes | only if < 6 GB | no |

**Rough answer times** for one cited AXIOM0 answer with the model already loaded, on
an actively cooled Pi 5: about 30–60 s on 4 GB/1B and about 1.5–3 min on 8 GB/3B.
These are estimates. Run the speed test (section 5) to measure your own board; it also
warns if the timeout is too tight.

### Why the settings look like this

- **The prompt is the slow part.** A Pi 5 reads prompt text roughly 5–7× slower than it
  writes answers, and each source excerpt adds about 430 tokens. Fewer excerpts
  (`AXIOM0_LLM_SOURCES`) is the biggest speed lever.
- **The context window is set explicitly** (`AXIOM0_NUM_CTX`). Otherwise Ollama's
  default could silently cut source excerpts off the end of the prompt.
- **4 threads, 1 request at a time, 1 model in memory.** The Pi 5 has 4 cores and
  shares RAM with the system, so running requests in parallel only makes each slower.
- **Flash attention and an 8-bit KV cache** roughly halve the memory the context uses,
  with negligible quality loss.
- **Keep-alive plus warmup.** The model is preloaded at boot and kept in memory, so the
  first question doesn't wait for a model load.
- **The dashboard gets CPU priority** over Ollama, so the web page stays responsive
  while an answer is being generated.
- **The timeout was raised.** v0.6 gave up after 90 s, which is too short for a Pi.
  Timeouts now have their own error message that names the setting to change.

## 4. Using it

```bash
# Files to ingest go in the inbox (your home folder is private to you)
cp examples/SIMULATED_charter.md /srv/axiom0-inbox/
axiom0 ingest /srv/axiom0-inbox/SIMULATED_charter.md
axiom0 ask "What does the charter say about public records?" --llm
axiom0 --json status
```

`axiom0` runs as the sandboxed `axiom0` service account with the Pi configuration loaded.

**Dashboard from another computer:** AXIOM0 listens only on the Pi itself. Tunnel in over SSH:

```bash
ssh -L 8765:127.0.0.1:8765 pi@<pi-address>
# then open http://127.0.0.1:8765 on your computer
```

The API key is in `/etc/axiom0/secrets.env` (`sudo cat` it).

## 5. Health and speed

```bash
sudo /opt/axiom0/deploy/pi5/axiom0-pi5-doctor.sh   # board, power, heat, storage, Ollama, AXIOM0, ledger
sudo /opt/axiom0/deploy/pi5/axiom0-pi5-bench.sh    # tokens/s and an estimated AXIOM0 answer time
```

The doctor flags under-voltage, throttling, missing cooling, SD-card storage, a missing
model, and any service listening beyond localhost.

## 6. Changing settings

Edit `/etc/axiom0/axiom0.env`, then `sudo systemctl restart axiom0`. Every value is
optional, and leaving one unset keeps the desktop v0.6 behaviour.

| Setting | Meaning |
|---|---|
| `AXIOM0_MODEL` | Ollama model name (pull it first: `sudo ollama pull NAME`) |
| `AXIOM0_LLM_SOURCES` | Source excerpts sent to the model, 1–6 |
| `AXIOM0_NUM_CTX` | Context window in tokens |
| `AXIOM0_NUM_THREAD` | CPU threads |
| `AXIOM0_NUM_PREDICT` | Maximum answer length in tokens |
| `AXIOM0_LLM_TIMEOUT` | Seconds to wait for an answer |
| `AXIOM0_KEEP_ALIVE` | How long the model stays loaded: `30m`, `2h`, `-1` (always) |

Ollama's own tuning lives in `/etc/systemd/system/ollama.service.d/10-axiom0-pi5.conf`.
Invalid values are rejected with a clear error rather than silently ignored.

### Accountability features (v0.7)

```bash
axiom0 reviewer-add "Daliah West"     # personal reviewer key, shown once
axiom0 backup /media/usb/axiom0       # then store the archive encrypted and offline
sudo systemctl start axiom0-anchor    # one anchor now (needs --enable-anchors + ANCHORING.md setup)
```

The optional 3·6·9 Intention Lab is off by default. To turn it on for a personal install,
set `AXIOM0_ENABLE_SYMBOLIC=1` in `/etc/axiom0/axiom0.env` and restart.

### Measure grounding on this Pi

```bash
sudo -u axiom0 env $(grep -v '^#' /etc/axiom0/axiom0.env | xargs) \
  /opt/axiom0/.venv/bin/python /opt/axiom0/tools/eval_grounding.py --out /tmp/axiom0-eval
```

This runs 12 fixed questions (including three that the sources cannot answer) against the
installed model with the Pi's tuning, and writes a report showing citation accuracy,
refusals and timing.

## 7. Where things live

| Path | Contents |
|---|---|
| `/opt/axiom0` | Program and its Python environment (read-only to the service) |
| `/var/lib/axiom0` | Ledger, identity key, database (owner-only, `700`) |
| `/etc/axiom0/axiom0.env` | Settings (profile + overrides) |
| `/etc/axiom0/secrets.env` | Service and reviewer keys |
| `/srv/axiom0-inbox` | Drop files here to ingest them |
| `/var/lib/axiom0-anchors` | Signed anchor receipts (public by design) |
| `/usr/local/bin/axiom0` | Command-line wrapper |

## 8. Uninstall

```bash
sudo bash /opt/axiom0/deploy/pi5/uninstall.sh                  # keeps ledger, keys, Ollama
sudo bash /opt/axiom0/deploy/pi5/uninstall.sh --purge          # also deletes ledger and keys (asks first)
sudo bash /opt/axiom0/deploy/pi5/uninstall.sh --remove-ollama  # also removes Ollama and all models
```

## 9. Limits

This is the same **local pilot** as v0.6: not a certified production system, and not an
official City of Kansas City, Missouri system. Model drafts are labelled
`unverified_model_draft` and need human review. Verification so far (section 10) used
stand-ins for Ollama and systemd on an x86 machine. The first run on real Pi 5 hardware
should record its doctor and speed-test results in `docs/VERIFICATION.md`.

## 10. Verification of this edition

- 40 automated tests (27 from v0.6, plus 13 covering the tuning settings, end-to-end
  delivery of those settings to a stand-in Ollama, timeout messages, and fail-closed
  validation).
- All shell scripts pass `shellcheck`.
- A full non-dry install, re-install (8 GB → 4 GB profile), ingest, `ask --llm`, doctor,
  speed test and uninstall were run on Linux, with stand-ins for Ollama and `systemctl`.
  That run confirmed the service account and permissions, the config and kept keys, the
  sandboxed service command, the localhost dashboard, the warmup, the profile settings
  arriving in the model request, and ledger verification after the re-install.
- **Not yet done:** a run on physical Pi 5 hardware with real Ollama and a downloaded
  model, and live temperature and throttling measurements.
