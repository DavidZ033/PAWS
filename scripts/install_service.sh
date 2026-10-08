#!/usr/bin/env bash
# Make PAWS start automatically when the Pi boots.
# Run from anywhere:  ./scripts/install_service.sh
set -euo pipefail
cd "$(dirname "$0")/.."

DIR="$(pwd)"
USER_NAME="$(whoami)"

sed -e "s|__DIR__|${DIR}|g" -e "s|__USER__|${USER_NAME}|g" scripts/paws.service \
    | sudo tee /etc/systemd/system/paws.service > /dev/null

sudo systemctl daemon-reload
sudo systemctl enable --now paws.service

cat <<'EOF'
PAWS is running and will start on every boot.

  sudo systemctl status paws      is it running?
  journalctl -u paws -f           live log
  sudo systemctl restart paws     after editing config.yaml
  sudo systemctl stop paws        stop it (needed before "paws hwtest")
EOF
