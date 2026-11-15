#!/usr/bin/env bash
# Measure how fast this Pi runs the AXIOM0 model, with the same settings AXIOM0 uses.
#   sudo /opt/axiom0/deploy/pi5/axiom0-pi5-bench.sh [MODEL]
# Reports: model load time, prompt reading speed, answer writing speed, temperature,
# and an estimate of a typical AXIOM0 cited answer time for the current profile.
set -euo pipefail
ENV=/etc/axiom0/axiom0.env
env_get() { [[ -r $ENV ]] && sed -n "s/^$1=//p" "$ENV" | tail -n1 || true; }
MODEL=${1:-$(env_get AXIOM0_MODEL)}; MODEL=${MODEL:-llama3.2:3b}
CTX=$(env_get AXIOM0_NUM_CTX); CTX=${CTX:-4096}
THR=$(env_get AXIOM0_NUM_THREAD); THR=${THR:-4}
SRC=$(env_get AXIOM0_LLM_SOURCES); SRC=${SRC:-6}
TIMEOUT=$(env_get AXIOM0_LLM_TIMEOUT); TIMEOUT=${TIMEOUT:-90}
[[ $MODEL =~ ^[A-Za-z0-9._:/-]+$ ]] || { echo "invalid model name" >&2; exit 2; }

temp() { [[ -r /sys/class/thermal/thermal_zone0/temp ]] && echo "$(( $(cat /sys/class/thermal/thermal_zone0/temp) / 1000 ))°C" || echo "n/a"; }

curl -fsS -m 3 http://127.0.0.1:11434/api/version >/dev/null || { echo "Ollama is not running." >&2; exit 1; }
echo "Benchmarking $MODEL  (num_ctx=$CTX, threads=$THR)  start temp $(temp)"
echo "Unloading model first so load time is measured…"
curl -fsS -m 30 http://127.0.0.1:11434/api/generate -d "{\"model\":\"$MODEL\",\"keep_alive\":0}" >/dev/null || true
sleep 2

# A prompt about the size of one AXIOM0 source excerpt (~450 tokens), asking for ~200 tokens.
python3 - "$MODEL" "$CTX" "$THR" "$SRC" "$TIMEOUT" <<'PY'
import json, sys, time, urllib.request
model, ctx, thr, sources, timeout = sys.argv[1], int(sys.argv[2]), int(sys.argv[3]), int(sys.argv[4]), int(sys.argv[5])
excerpt = ("Section 2-13. Council Chambers. The City Clerk shall maintain the reservation calendar for the "
           "Council Chambers. Requests must be submitted in writing and are approved in the order received, "
           "subject to Council and committee meetings, which take precedence. Public records relating to "
           "reservations are open under the Missouri Sunshine Law. ") * 5
prompt = ("Using only this excerpt, explain in about 150 words who approves Council Chambers "
          "reservations and in what order.\n\n" + excerpt)
body = json.dumps({"model": model, "prompt": prompt, "stream": False, "keep_alive": "5m",
                   "options": {"temperature": 0, "num_ctx": ctx, "num_thread": thr, "num_predict": 220}}).encode()
req = urllib.request.Request("http://127.0.0.1:11434/api/generate", data=body,
                             headers={"Content-Type": "application/json"})
t0 = time.time()
with urllib.request.urlopen(req, timeout=900) as r:
    d = json.loads(r.read())
wall = time.time() - t0
ns = 1e9
load = d.get("load_duration", 0) / ns
pc, pd = d.get("prompt_eval_count", 0), d.get("prompt_eval_duration", 1) / ns
ec, ed = d.get("eval_count", 0), d.get("eval_duration", 1) / ns
pp, tg = pc / pd if pd else 0, ec / ed if ed else 0
print(f"  Model load:        {load:6.1f} s")
print(f"  Prompt reading:    {pp:6.1f} tokens/s  ({pc} tokens in {pd:.1f} s)")
print(f"  Answer writing:    {tg:6.1f} tokens/s  ({ec} tokens in {ed:.1f} s)")
print(f"  Total wall time:   {wall:6.1f} s")
# Typical AXIOM0 ask: ~450 system tokens + ~430 per excerpt, ~250-token JSON answer.
est_prompt = 450 + 430 * sources
est = (est_prompt / pp if pp else 0) + (250 / tg if tg else 0)
print(f"\n  Estimated AXIOM0 cited answer with {sources} excerpts (model already loaded): ~{est:.0f} s")
print(f"  Configured timeout (AXIOM0_LLM_TIMEOUT): {timeout} s", end="")
if est > timeout * 0.8:
    print("  <-- too tight: raise AXIOM0_LLM_TIMEOUT or lower AXIOM0_LLM_SOURCES")
else:
    print("  (OK)")
PY
echo "  End temp: $(temp)"
if command -v vcgencmd >/dev/null 2>&1; then
  V=$(( $(vcgencmd get_throttled | cut -d= -f2) ))
  (( V & 0x40000 )) && echo "  NOTE: the CPU has throttled since boot — results are lower than the Pi can do with better cooling."
fi
exit 0
