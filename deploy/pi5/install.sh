#!/usr/bin/env bash
# AXIOM0 Living City — Raspberry Pi 5 edition installer.
#
# Installs, on Raspberry Pi OS (64-bit, Bookworm or newer):
#   * AXIOM0 into /opt/axiom0 (own Python venv), data in /var/lib/axiom0, config in /etc/axiom0
#   * Ollama (official installer), tuned for the Pi 5 by a systemd drop-in, localhost only
#   * the model chosen by a RAM profile (4 GB / 8 GB / 16 GB), pulled and preloaded
#   * systemd services: axiom0 (dashboard/API on 127.0.0.1:8765) and axiom0-warmup
#   * optional: zram compressed swap (low-RAM boards), CPU "performance" governor
#
# Usage:  sudo bash deploy/pi5/install.sh [options]
#   --profile pi5-4gb|pi5-8gb|pi5-16gb   override the RAM-based choice
#   --model NAME                          override the profile's model (e.g. qwen2.5:7b)
#   --admin NAME                          AXIOM0 operator label (default: the sudo user)
#   --models-dir PATH                     store Ollama models here (e.g. on an NVMe drive)
#   --ollama-version X.Y.Z                pin the Ollama version
#   --performance-governor                keep CPU at full clock (needs active cooling)
#   --skip-ollama                         do not install/configure Ollama
#   --skip-model                          do not download the model now
#   --enable-anchors                      daily signed ledger anchor, published from /var/lib/axiom0-anchors
#                                         (make that folder a git clone of a public repo; see docs/ANCHORING.md)
#   --force                               continue on a board that is not a Pi 5
#   --dry-run                             print every action, change nothing
#   -h | --help
#
# Nothing is exposed to the network: AXIOM0 and Ollama both listen on 127.0.0.1 only.
set -euo pipefail

SRC_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PI5_DIR="$SRC_ROOT/deploy/pi5"
APP=/opt/axiom0
DATA=/var/lib/axiom0
ETC=/etc/axiom0
INBOX=/srv/axiom0-inbox
SVC_USER=axiom0

PROFILE="" MODEL_OVERRIDE="" ADMIN="${SUDO_USER:-}" MODELS_DIR="" OLLAMA_VERSION_PIN=""
GOVERNOR=no SKIP_OLLAMA=no SKIP_MODEL=no FORCE=no DRY_RUN=no ANCHORS=no
ANCHOR_DIR=/var/lib/axiom0-anchors

# ---------------------------------------------------------------- helpers
c_ok=$'\e[32m' c_warn=$'\e[33m' c_err=$'\e[31m' c_dim=$'\e[2m' c_off=$'\e[0m'
[[ -t 1 ]] || { c_ok="" c_warn="" c_err="" c_dim="" c_off=""; }
step() { printf '\n%s==>%s %s\n' "$c_ok" "$c_off" "$*"; }
info() { printf '    %s\n' "$*"; }
warn() { printf '    %sWARNING:%s %s\n' "$c_warn" "$c_off" "$*"; }
die()  { printf '%sERROR:%s %s\n' "$c_err" "$c_off" "$*" >&2; exit 1; }

# run CMD...  — execute, or just print it in --dry-run mode
run() {
  if [[ $DRY_RUN == yes ]]; then printf '    %s[dry-run]%s %s\n' "$c_dim" "$c_off" "$*"; return 0; fi
  "$@"
}

# put_file PATH MODE OWNER:GROUP  < content  — write atomically
put_file() {
  local path=$1 mode=$2 owner=$3 tmp
  if [[ $DRY_RUN == yes ]]; then
    printf '    %s[dry-run] write %s (%s %s):%s\n' "$c_dim" "$path" "$mode" "$owner" "$c_off"
    sed 's/^/      | /'
    return 0
  fi
  tmp="$(mktemp "$(dirname "$path")/.axiom0.XXXXXX")"
  cat >"$tmp"
  chmod "$mode" "$tmp"; chown "$owner" "$tmp"
  mv -f "$tmp" "$path"
}

# env_get FILE KEY — read KEY=value from a plain env file (no shell evaluation)
env_get() { sed -n "s/^$2=//p" "$1" | tail -n1; }

as_svc() { run runuser -u "$SVC_USER" -- "$@"; }

# ---------------------------------------------------------------- arguments
while [[ $# -gt 0 ]]; do
  case $1 in
    --profile) PROFILE=${2:?}; shift 2 ;;
    --model) MODEL_OVERRIDE=${2:?}; shift 2 ;;
    --admin) ADMIN=${2:?}; shift 2 ;;
    --models-dir) MODELS_DIR=${2:?}; shift 2 ;;
    --ollama-version) OLLAMA_VERSION_PIN=${2:?}; shift 2 ;;
    --performance-governor) GOVERNOR=yes; shift ;;
    --skip-ollama) SKIP_OLLAMA=yes; shift ;;
    --skip-model) SKIP_MODEL=yes; shift ;;
    --enable-anchors) ANCHORS=yes; shift ;;
    --force) FORCE=yes; shift ;;
    --dry-run) DRY_RUN=yes; shift ;;
    -h|--help) sed -n '2,29p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) die "Unknown option: $1 (see --help)" ;;
  esac
done

[[ -n $MODEL_OVERRIDE && ! $MODEL_OVERRIDE =~ ^[A-Za-z0-9._:/-]+$ ]] && die "Invalid model name: $MODEL_OVERRIDE"
[[ -n $OLLAMA_VERSION_PIN && ! $OLLAMA_VERSION_PIN =~ ^[0-9]+\.[0-9]+\.[0-9]+(-rc[0-9]+)?$ ]] && die "Invalid --ollama-version"
ADMIN=${ADMIN:-howard}
[[ $ADMIN =~ ^[A-Za-z0-9._-]{1,64}$ ]] || die "Invalid --admin label: $ADMIN"

# ---------------------------------------------------------------- 1. preflight
step "Checking this machine"
if [[ $DRY_RUN != yes && $EUID -ne 0 ]]; then die "Run with sudo:  sudo bash $0"; fi

ARCH=$(uname -m)
[[ $ARCH == aarch64 ]] || { [[ $FORCE == yes || $DRY_RUN == yes ]] && warn "Architecture is $ARCH, not aarch64 (64-bit OS required on the Pi)" || die "64-bit Raspberry Pi OS (aarch64) required; found $ARCH"; }

BOARD=$( { tr -d '\0' </proc/device-tree/model; } 2>/dev/null || echo "unknown")
info "Board: $BOARD"
if [[ $BOARD != *"Raspberry Pi 5"* && $BOARD != *"Compute Module 5"* ]]; then
  [[ $FORCE == yes || $DRY_RUN == yes ]] && warn "Not a Raspberry Pi 5 — profiles are tuned for the Pi 5's 4-core Cortex-A76" \
    || die "This installer is tuned for the Raspberry Pi 5. Use --force to continue anyway."
fi

if [[ -r /etc/os-release ]]; then
  # shellcheck disable=SC1091
  . /etc/os-release
  info "OS: ${PRETTY_NAME:-unknown}"
  case ${VERSION_CODENAME:-} in bookworm|trixie|forky) ;; *) warn "Tested on Raspberry Pi OS Bookworm/Trixie; ${VERSION_CODENAME:-unknown} may need adjustments" ;; esac
fi

MEM_KB=$(awk '/^MemTotal:/{print $2}' /proc/meminfo)
MEM_GB=$(( (MEM_KB + 524288) / 1048576 ))
info "RAM: ${MEM_GB} GB"

if [[ -z $PROFILE ]]; then
  if   (( MEM_KB < 6000000 ));  then PROFILE=pi5-4gb
  elif (( MEM_KB < 12000000 )); then PROFILE=pi5-8gb
  else PROFILE=pi5-16gb; fi
fi
PROFILE_FILE="$PI5_DIR/profiles/$PROFILE.env"
[[ -f $PROFILE_FILE ]] || die "No such profile: $PROFILE"
(( MEM_KB < 3000000 )) && warn "2 GB board: the 1B model will fit only with zram swap; expect slow answers."
MODEL=${MODEL_OVERRIDE:-$(env_get "$PROFILE_FILE" AXIOM0_MODEL)}
info "Profile: $PROFILE   Model: $MODEL"

python3 - <<'PY' || die "Python 3.11 or newer is required"
import sys
raise SystemExit(0 if sys.version_info >= (3, 11) else 1)
PY
info "Python: $(python3 -V 2>&1)"

FREE_GB=$(df -Pk / | awk 'NR==2{print int($4/1048576)}')
TARGET_FS=${MODELS_DIR:-/}
[[ -n $MODELS_DIR ]] && FREE_GB=$(df -Pk "$MODELS_DIR" 2>/dev/null | awk 'NR==2{print int($4/1048576)}' || echo 0)
info "Free space for models ($TARGET_FS): ${FREE_GB} GB"
(( FREE_GB >= 6 )) || warn "Less than 6 GB free; Ollama plus a 3B model needs about 4 GB."

ROOT_DEV=$(findmnt -no SOURCE / 2>/dev/null || true)
if [[ $ROOT_DEV == /dev/mmcblk* && -z $MODELS_DIR ]]; then
  warn "Running from an SD card. Models load 3-5x faster from NVMe/USB SSD (see --models-dir)."
fi

# ---------------------------------------------------------------- 2. packages
step "Installing system packages"
run apt-get update -qq
run env DEBIAN_FRONTEND=noninteractive apt-get install -y -qq python3-venv python3-pip curl ca-certificates zstd tar

# ---------------------------------------------------------------- 3. user & folders
step "Creating the axiom0 service account and folders"
if ! id "$SVC_USER" >/dev/null 2>&1; then
  run useradd --system --home-dir "$DATA" --no-create-home --shell /usr/sbin/nologin "$SVC_USER"
fi
run install -d -m 0755 -o root -g root "$APP"
run install -d -m 0700 -o "$SVC_USER" -g "$SVC_USER" "$DATA"
run install -d -m 0750 -o root -g "$SVC_USER" "$ETC"
# Drop files here so the service account can read them (your home folder is private).
run install -d -m 2770 -o "$SVC_USER" -g "$SVC_USER" "$INBOX"
run install -d -m 0755 -o "$SVC_USER" -g "$SVC_USER" "$ANCHOR_DIR"   # receipts are public by design
if [[ -n ${SUDO_USER:-} && $SUDO_USER != root ]]; then
  run usermod -aG "$SVC_USER" "$SUDO_USER"
  info "$SUDO_USER added to the $SVC_USER group (log out and back in for it to apply)."
fi

# ---------------------------------------------------------------- 4. AXIOM0 code + venv
step "Installing AXIOM0 into $APP"
if [[ $DRY_RUN == yes ]]; then
  run "copy $SRC_ROOT -> $APP (excluding .git .venv axiom0_data caches)"
else
  find "$APP" -mindepth 1 -maxdepth 1 ! -name .venv -exec rm -rf {} +
  tar -C "$SRC_ROOT" --exclude=./.git --exclude=./.venv --exclude=./axiom0_data \
      --exclude='__pycache__' --exclude='.pytest_cache' --exclude='*.egg-info' --exclude=./build \
      -cf - . | tar -C "$APP" --no-same-owner -xmf -
  chown -R root:root "$APP"
  chmod -R go-w "$APP"
  chmod 0755 "$APP"/deploy/pi5/*.sh
fi
[[ -x $APP/.venv/bin/python ]] || run python3 -m venv "$APP/.venv"
run "$APP/.venv/bin/python" -m pip install -q --upgrade pip
run "$APP/.venv/bin/python" -m pip install -q "$APP"

# ---------------------------------------------------------------- 5. config + secrets
step "Writing configuration to $ETC"
ENV_FILE="$ETC/axiom0.env"
{
  echo "# Generated by deploy/pi5/install.sh from profile $PROFILE on $(date -Is)"
  echo "# Edit freely, then: sudo systemctl restart axiom0"
  grep -v '^AXIOM0_MODEL=' "$PROFILE_FILE"
  echo "AXIOM0_MODEL=$MODEL"
  echo "AXIOM0_DATA_DIR=$DATA"
  echo "AXIOM0_LOCAL_ACTOR=$ADMIN"
  echo "AXIOM0_ANCHOR_DIR=$ANCHOR_DIR"
  echo "# Optional personal 3-6-9 Intention Lab / symbolic scoring (off for municipal use):"
  echo "AXIOM0_ENABLE_SYMBOLIC=0"
} >"/tmp/axiom0-env.$$"
if [[ -f $ENV_FILE && $DRY_RUN != yes ]]; then
  cp -a "$ENV_FILE" "$ENV_FILE.bak.$(date +%Y%m%d%H%M%S)"
  info "Previous config backed up next to $ENV_FILE"
fi
put_file "$ENV_FILE" 0640 "root:$SVC_USER" <"/tmp/axiom0-env.$$"
rm -f "/tmp/axiom0-env.$$"

SECRETS="$ETC/secrets.env"
if [[ -f $SECRETS ]]; then
  info "Keeping existing service and reviewer keys"
else
  if [[ $DRY_RUN == yes ]]; then gen() { echo '<random-64-characters>'; }
  else gen() { python3 -c 'import secrets; print(secrets.token_urlsafe(48))'; }; fi
  printf 'AXIOM0_API_KEY=%s\nAXIOM0_REVIEWER_KEY=%s\nAXIOM0_REVIEWER_ID=local_reviewer\n' "$(gen)" "$(gen)" \
    | put_file "$SECRETS" 0640 "root:$SVC_USER"
  info "Generated new service and reviewer keys in $SECRETS"
fi

# Command-line wrapper: runs AXIOM0 as the service account with the Pi config loaded.
put_file /usr/local/bin/axiom0 0755 root:root <<EOF
#!/usr/bin/env bash
# AXIOM0 (Raspberry Pi 5 edition) — runs as the '$SVC_USER' account with $ETC config.
# Files you ingest must be readable by that account: copy them to $INBOX first.
set -euo pipefail
if [[ \$(id -un) != $SVC_USER ]]; then
  # Turn relative file arguments into absolute paths before switching account and folder.
  args=()
  for a in "\$@"; do
    if [[ \$a != /* && \$a != -* && -e \$a ]]; then a="\$PWD/\$a"; fi
    args+=("\$a")
  done
  exec sudo -u $SVC_USER -- "\$0" "\${args[@]}"
fi
set -a
. $ETC/axiom0.env
. $ETC/secrets.env
set +a
cd $DATA
exec $APP/.venv/bin/python -P -m axiom0 --data-dir $DATA "\$@"
EOF

step "Initialising the AXIOM0 ledger (admin: $ADMIN)"
[[ $DRY_RUN == yes ]] && info "[dry-run] axiom0 --data-dir $DATA init --admin $ADMIN  (as $SVC_USER)"
INIT_OUT=$(as_svc env AXIOM0_LOCAL_ACTOR="$ADMIN" "$APP/.venv/bin/python" -m axiom0 --data-dir "$DATA" init --admin "$ADMIN" 2>&1) \
  || { grep -q 'already configured' <<<"$INIT_OUT" && warn "An admin is already enrolled; keeping it." || die "init failed: $INIT_OUT"; }

# ---------------------------------------------------------------- 6. Ollama
if [[ $SKIP_OLLAMA == no ]]; then
  step "Installing Ollama"
  if command -v ollama >/dev/null 2>&1 && [[ -z $OLLAMA_VERSION_PIN ]]; then
    info "Ollama already installed: $(ollama --version 2>/dev/null | tail -n1)"
  else
    if [[ $DRY_RUN == yes ]]; then
      run "curl -fsSL https://ollama.com/install.sh -o /tmp/ollama-install.sh && OLLAMA_VERSION=${OLLAMA_VERSION_PIN:-latest} sh /tmp/ollama-install.sh"
    else
      curl -fsSL https://ollama.com/install.sh -o /tmp/ollama-install.sh
      info "Downloaded official installer (sha256 $(sha256sum /tmp/ollama-install.sh | cut -c1-16)…)"
      OLLAMA_VERSION="$OLLAMA_VERSION_PIN" sh /tmp/ollama-install.sh
      rm -f /tmp/ollama-install.sh
    fi
  fi

  step "Tuning Ollama for the Raspberry Pi 5"
  if [[ -n $MODELS_DIR ]]; then
    run install -d -m 0755 "$MODELS_DIR"
    id ollama >/dev/null 2>&1 && run chown -R ollama:ollama "$MODELS_DIR"
  fi
  run install -d -m 0755 /etc/systemd/system/ollama.service.d
  {
    echo "# Written by AXIOM0 deploy/pi5/install.sh (profile $PROFILE). Re-run the installer to regenerate."
    echo "[Service]"
    echo "# Localhost only: AXIOM0 refuses any other endpoint, and nothing else should reach the model."
    echo "Environment=OLLAMA_HOST=127.0.0.1:11434"
    echo "# One request at a time and one model in memory: the Pi has 4 cores and shared RAM."
    echo "Environment=OLLAMA_NUM_PARALLEL=1"
    echo "Environment=OLLAMA_MAX_LOADED_MODELS=1"
    echo "Environment=OLLAMA_MAX_QUEUE=16"
    echo "Environment=OLLAMA_KEEP_ALIVE=$(env_get "$PROFILE_FILE" PI5_OLLAMA_KEEP_ALIVE)"
    echo "Environment=OLLAMA_CONTEXT_LENGTH=$(env_get "$PROFILE_FILE" PI5_OLLAMA_CONTEXT_LENGTH)"
    echo "# Flash attention + 8-bit KV cache roughly halve context memory with negligible quality loss."
    echo "Environment=OLLAMA_FLASH_ATTENTION=$(env_get "$PROFILE_FILE" PI5_OLLAMA_FLASH_ATTENTION)"
    echo "Environment=OLLAMA_KV_CACHE_TYPE=$(env_get "$PROFILE_FILE" PI5_OLLAMA_KV_CACHE_TYPE)"
    [[ -n $MODELS_DIR ]] && echo "Environment=OLLAMA_MODELS=$MODELS_DIR"
    echo "# Yield to the AXIOM0 dashboard when both are busy."
    echo "CPUWeight=80"
    echo "Restart=always"
    echo "RestartSec=3"
  } | put_file /etc/systemd/system/ollama.service.d/10-axiom0-pi5.conf 0644 root:root
  run systemctl daemon-reload
  run systemctl enable --now ollama
  run systemctl restart ollama

  if [[ $DRY_RUN != yes ]]; then
    for _ in $(seq 1 60); do curl -fsS -m 2 http://127.0.0.1:11434/api/version >/dev/null 2>&1 && break; sleep 1; done
    curl -fsS -m 2 http://127.0.0.1:11434/api/version >/dev/null || die "Ollama did not start; see: journalctl -u ollama -n 50"
    info "Ollama is up: $(curl -fsS http://127.0.0.1:11434/api/version)"
  fi

  if [[ $SKIP_MODEL == no ]]; then
    step "Downloading model $MODEL (one time; 1-5 GB)"
    run ollama pull "$MODEL"
  else
    info "Skipping model download. Later: ollama pull $MODEL"
  fi
fi

# ---------------------------------------------------------------- 7. system tuning
step "System tuning"
ZRAM_WANT=$(env_get "$PROFILE_FILE" PI5_ZRAM)
if [[ $ZRAM_WANT == auto ]]; then (( MEM_KB < 6000000 )) && ZRAM_WANT=yes || ZRAM_WANT=no; fi
if [[ $ZRAM_WANT == yes ]]; then
  if swapon --show=NAME --noheadings 2>/dev/null | grep -q zram; then
    info "zram swap already active (left unchanged)"
  else
    run env DEBIAN_FRONTEND=noninteractive apt-get install -y -qq zram-tools
    printf 'ALGO=zstd\nPERCENT=50\nPRIORITY=100\n' | put_file /etc/default/zramswap 0644 root:root
    run systemctl restart zramswap
    info "zram swap enabled (zstd, 50% of RAM)"
  fi
else
  info "zram: not needed for this profile"
fi

if [[ $GOVERNOR == yes ]]; then
  put_file /etc/systemd/system/axiom0-cpu-performance.service 0644 root:root <<'EOF'
[Unit]
Description=Hold Raspberry Pi 5 CPU at full clock for AXIOM0/Ollama (needs active cooling)

[Service]
Type=oneshot
RemainAfterExit=yes
ExecStart=/bin/sh -c 'for g in /sys/devices/system/cpu/cpufreq/policy*/scaling_governor; do echo performance > "$g"; done'
ExecStop=/bin/sh -c 'for g in /sys/devices/system/cpu/cpufreq/policy*/scaling_governor; do echo ondemand > "$g"; done'

[Install]
WantedBy=multi-user.target
EOF
  run systemctl daemon-reload
  run systemctl enable --now axiom0-cpu-performance.service
  info "CPU governor: performance"
else
  info "CPU governor: unchanged (add --performance-governor if you have the Active Cooler)"
fi

if ! cat /sys/class/hwmon/*/name 2>/dev/null | grep -q pwmfan; then
  warn "No fan detected. Sustained AI work will throttle a bare Pi 5 at 85°C — fit the Active Cooler."
fi

# ---------------------------------------------------------------- 8. services
step "Installing and starting services"
run install -m 0644 "$PI5_DIR/systemd/axiom0.service" /etc/systemd/system/axiom0.service
run install -m 0644 "$PI5_DIR/systemd/axiom0-warmup.service" /etc/systemd/system/axiom0-warmup.service
run install -m 0644 "$PI5_DIR/systemd/axiom0-anchor.service" /etc/systemd/system/axiom0-anchor.service
run install -m 0644 "$PI5_DIR/systemd/axiom0-anchor.timer" /etc/systemd/system/axiom0-anchor.timer
run systemctl daemon-reload
run systemctl enable axiom0.service
run systemctl restart axiom0.service
if [[ $SKIP_OLLAMA == no && $SKIP_MODEL == no ]]; then
  run systemctl enable axiom0-warmup.service
  run systemctl start axiom0-warmup.service || warn "Model warmup failed; the first question will load it instead."
fi

if [[ $ANCHORS == yes ]]; then
  run systemctl enable --now axiom0-anchor.timer
  info "Daily ledger anchors: on (receipts in $ANCHOR_DIR). Make it a git clone with a remote to publish them."
else
  info "Daily ledger anchors: off (re-run with --enable-anchors; see docs/ANCHORING.md)"
fi

if [[ $DRY_RUN != yes ]]; then
  for _ in $(seq 1 30); do curl -fsS -m 2 http://127.0.0.1:8765/health >/dev/null 2>&1 && break; sleep 1; done
fi

# ---------------------------------------------------------------- 9. report
step "Health check"
if [[ $DRY_RUN == yes ]]; then
  run "$APP/deploy/pi5/axiom0-pi5-doctor.sh"
else
  "$APP/deploy/pi5/axiom0-pi5-doctor.sh" || true
fi

cat <<EOF

${c_ok}AXIOM0 Living City — Raspberry Pi 5 edition is installed.${c_off}

  Dashboard   http://127.0.0.1:8765  (on the Pi)
              From another computer:  ssh -L 8765:127.0.0.1:8765 ${SUDO_USER:-pi}@<pi-address>
              then open http://127.0.0.1:8765 there.
  API key     sudo cat $SECRETS
  Try it      cp $APP/examples/SIMULATED_charter.md $INBOX/
              axiom0 ingest $INBOX/SIMULATED_charter.md
              axiom0 ask "What does the charter say about public records?" --llm
  Health      sudo $APP/deploy/pi5/axiom0-pi5-doctor.sh
  Speed test  sudo $APP/deploy/pi5/axiom0-pi5-bench.sh
  Settings    $ENV_FILE   (then: sudo systemctl restart axiom0)
EOF
