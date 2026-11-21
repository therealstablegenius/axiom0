#!/usr/bin/env bash
# AXIOM0 Raspberry Pi 5 health check. Read-only. Run with sudo for the full report.
#   sudo /opt/axiom0/deploy/pi5/axiom0-pi5-doctor.sh
set -uo pipefail
ETC=/etc/axiom0
FAILS=0 WARNS=0
g=$'\e[32m' y=$'\e[33m' r=$'\e[31m' o=$'\e[0m'
[[ -t 1 ]] || { g="" y="" r="" o=""; }
pass() { printf '  %sPASS%s  %s\n' "$g" "$o" "$*"; }
warn() { printf '  %sWARN%s  %s\n' "$y" "$o" "$*"; WARNS=$((WARNS+1)); }
fail() { printf '  %sFAIL%s  %s\n' "$r" "$o" "$*"; FAILS=$((FAILS+1)); }
head_() { printf '\n%s\n' "$*"; }
env_get() { [[ -r $1 ]] && sed -n "s/^$2=//p" "$1" | tail -n1; }

MODEL=$(env_get "$ETC/axiom0.env" AXIOM0_MODEL); MODEL=${MODEL:-llama3.2:3b}
PROFILE=$(env_get "$ETC/axiom0.env" PI5_PROFILE)

head_ "Hardware"
BOARD=$( { tr -d '\0' </proc/device-tree/model; } 2>/dev/null || echo unknown)
[[ $BOARD == *"Raspberry Pi 5"* || $BOARD == *"Compute Module 5"* ]] && pass "$BOARD" || warn "Board: $BOARD (profiles are tuned for the Pi 5)"
[[ $(uname -m) == aarch64 ]] && pass "64-bit OS (aarch64), kernel $(uname -r), page size $(getconf PAGESIZE)" || fail "Not a 64-bit OS: $(uname -m)"
MEM_MB=$(awk '/^MemTotal:/{print int($2/1024)}' /proc/meminfo)
AVAIL_MB=$(awk '/^MemAvailable:/{print int($2/1024)}' /proc/meminfo)
pass "RAM ${MEM_MB} MB total, ${AVAIL_MB} MB available${PROFILE:+ (profile $PROFILE)}"
if swapon --show=NAME --noheadings 2>/dev/null | grep -q zram; then pass "zram swap active"
elif (( MEM_MB < 6000 )); then warn "No zram swap on a low-RAM board (re-run the installer)"
else SW=$(swapon --show=NAME,SIZE --noheadings 2>/dev/null | tr -s ' \n' ' ' | sed 's/ *$//'); pass "Swap: ${SW:-none (fine with this much RAM)}"; fi

head_ "Thermals and power"
if [[ -r /sys/class/thermal/thermal_zone0/temp ]]; then
  T=$(( $(cat /sys/class/thermal/thermal_zone0/temp) / 1000 ))
  if (( T >= 80 )); then fail "CPU ${T}°C (throttles at 85°C)"; elif (( T >= 70 )); then warn "CPU ${T}°C (warm)"; else pass "CPU ${T}°C"; fi
fi
if cat /sys/class/hwmon/*/name 2>/dev/null | grep -q pwmfan; then pass "Fan detected (Active Cooler or case fan)"
else warn "No fan detected — long answers will throttle the CPU without cooling"; fi
if command -v vcgencmd >/dev/null 2>&1; then
  HEX=$(vcgencmd get_throttled 2>/dev/null | cut -d= -f2)
  if [[ -n $HEX ]]; then
    V=$((HEX))
    (( V & 0x1 ))     && fail "Under-voltage NOW — use the official 27 W (5 V/5 A) USB-C supply"
    (( V & 0x4 ))     && fail "CPU is throttled NOW"
    (( V & 0x10000 )) && warn "Under-voltage has occurred since boot"
    (( V & 0x40000 )) && warn "Throttling has occurred since boot"
    (( V == 0 ))      && pass "No under-voltage or throttling since boot"
  fi
  GOV=$(cat /sys/devices/system/cpu/cpufreq/policy0/scaling_governor 2>/dev/null || echo ?)
  pass "CPU governor: $GOV, clock $(( $(vcgencmd measure_clock arm | cut -d= -f2) / 1000000 )) MHz"
fi

head_ "Storage"
ROOT_DEV=$(findmnt -no SOURCE / 2>/dev/null)
case $ROOT_DEV in
  /dev/nvme*) pass "Root on NVMe ($ROOT_DEV)" ;;
  /dev/sd*)   pass "Root on USB drive ($ROOT_DEV)" ;;
  /dev/mmcblk*) warn "Root on SD card ($ROOT_DEV) — model loading is slower; NVMe recommended" ;;
  *) pass "Root on $ROOT_DEV" ;;
esac
MD=$(systemctl show ollama -p Environment 2>/dev/null | grep -o 'OLLAMA_MODELS=[^ ]*' | cut -d= -f2)
MD=${MD:-/usr/share/ollama/.ollama/models}
FREE=$(df -Pk "$MD" 2>/dev/null | awk 'NR==2{print int($4/1048576)}')
[[ -n $FREE ]] && { (( FREE >= 3 )) && pass "Model store $MD: ${FREE} GB free" || warn "Model store $MD: only ${FREE} GB free"; }

head_ "Ollama"
if systemctl is-active --quiet ollama; then pass "ollama.service running"; else fail "ollama.service not running (sudo systemctl start ollama)"; fi
if VER=$(curl -fsS -m 3 http://127.0.0.1:11434/api/version 2>/dev/null); then
  pass "API answering on 127.0.0.1:11434 $VER"
  TAGS=$(curl -fsS -m 5 http://127.0.0.1:11434/api/tags 2>/dev/null)
  if python3 -c 'import json,sys; m=sys.argv[1]; n=[x["name"] for x in json.loads(sys.argv[2])["models"]]; sys.exit(0 if m in n or m+":latest" in n else 1)' "$MODEL" "$TAGS" 2>/dev/null
  then pass "Model $MODEL is downloaded"; else fail "Model $MODEL missing (sudo ollama pull $MODEL)"; fi
  PS=$(curl -fsS -m 5 http://127.0.0.1:11434/api/ps 2>/dev/null)
  python3 -c 'import json,sys; sys.exit(0 if json.loads(sys.argv[1]).get("models") else 1)' "$PS" 2>/dev/null \
    && pass "Model loaded in memory (fast first answer)" || warn "Model not loaded yet (first answer adds load time)"
else
  fail "Ollama API not answering on 127.0.0.1:11434"
fi
if command -v ss >/dev/null 2>&1; then
  if ss -ltnH 'sport = :11434' 2>/dev/null | awk '{print $4}' | grep -vqE '^(127\.0\.0\.1|\[::1\]):11434$'; then
    fail "Ollama is listening on a non-local address — check OLLAMA_HOST"
  else pass "Ollama bound to localhost only"; fi
fi
[[ -f /etc/systemd/system/ollama.service.d/10-axiom0-pi5.conf ]] && pass "Pi 5 tuning drop-in present" || warn "Pi 5 tuning drop-in missing (re-run the installer)"

head_ "AXIOM0"
if systemctl is-active --quiet axiom0; then pass "axiom0.service running"; else fail "axiom0.service not running (journalctl -u axiom0 -n 50)"; fi
if curl -fsS -m 3 http://127.0.0.1:8765/health >/dev/null 2>&1; then pass "Dashboard/API answering on 127.0.0.1:8765"; else fail "Nothing answering on 127.0.0.1:8765"; fi
if command -v ss >/dev/null 2>&1 && ss -ltnH 'sport = :8765' 2>/dev/null | awk '{print $4}' | grep -vqE '^(127\.0\.0\.1|\[::1\]):8765$'; then
  fail "AXIOM0 is listening on a non-local address"
fi
if [[ $EUID -eq 0 && -x /usr/local/bin/axiom0 ]]; then
  if OUT=$(/usr/local/bin/axiom0 --json verify 2>&1); then pass "Signed ledger verifies"; else fail "Ledger verification failed: ${OUT:0:200}"; fi
else
  warn "Run with sudo to verify the signed ledger"
fi

printf '\n%d failure(s), %d warning(s).\n' "$FAILS" "$WARNS"
exit $(( FAILS > 0 ))
