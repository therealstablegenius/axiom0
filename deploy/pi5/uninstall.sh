#!/usr/bin/env bash
# Remove the AXIOM0 Raspberry Pi 5 install.
#   sudo bash uninstall.sh                 remove services, program and command; KEEP data, config, Ollama
#   sudo bash uninstall.sh --purge         also delete /var/lib/axiom0 (ledger!), /etc/axiom0 and the inbox
#   sudo bash uninstall.sh --remove-ollama also remove Ollama, its tuning and ALL downloaded models
set -euo pipefail
PURGE=no RM_OLLAMA=no
for a in "$@"; do
  case $a in --purge) PURGE=yes ;; --remove-ollama) RM_OLLAMA=yes ;; *) echo "Unknown option $a" >&2; exit 2 ;; esac
done
[[ $EUID -eq 0 ]] || { echo "Run with sudo" >&2; exit 1; }

for u in axiom0 axiom0-warmup axiom0-cpu-performance; do
  systemctl disable --now "$u.service" 2>/dev/null || true
  rm -f "/etc/systemd/system/$u.service"
done
rm -rf /opt/axiom0
rm -f /usr/local/bin/axiom0
rm -f /etc/systemd/system/ollama.service.d/10-axiom0-pi5.conf
systemctl daemon-reload
systemctl restart ollama 2>/dev/null || true
echo "Removed AXIOM0 program, services and Pi 5 Ollama tuning."

if [[ $PURGE == yes ]]; then
  read -r -p "Delete the AXIOM0 ledger and keys in /var/lib/axiom0 and /etc/axiom0? This cannot be undone. Type DELETE: " ok
  if [[ $ok == DELETE ]]; then
    rm -rf /var/lib/axiom0 /etc/axiom0 /srv/axiom0-inbox
    userdel axiom0 2>/dev/null || true
    echo "Data, config and service account deleted."
  else
    echo "Kept data and config."
  fi
else
  echo "Kept /var/lib/axiom0 (ledger) and /etc/axiom0 (config and keys)."
fi

if [[ $RM_OLLAMA == yes ]]; then
  systemctl disable --now ollama 2>/dev/null || true
  rm -f /etc/systemd/system/ollama.service /usr/local/bin/ollama /usr/bin/ollama
  rm -rf /usr/local/lib/ollama /usr/lib/ollama /usr/share/ollama /etc/systemd/system/ollama.service.d
  userdel ollama 2>/dev/null || true
  groupdel ollama 2>/dev/null || true
  systemctl daemon-reload
  echo "Ollama and its models removed."
fi
