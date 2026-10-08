#!/usr/bin/env bash
# Set up PAWS on a Raspberry Pi running Raspberry Pi OS (Bookworm or newer).
# Run from anywhere:  ./scripts/install.sh
set -euo pipefail
cd "$(dirname "$0")/.."

echo "==> Installing system packages"
sudo apt-get update
# The camera, GPIO and OpenCV libraries are best taken from apt on a Pi.
sudo apt-get install -y \
    python3-venv python3-pip \
    python3-picamera2 python3-opencv python3-numpy \
    python3-gpiozero python3-lgpio

echo "==> Creating virtual environment (.venv)"
# --system-site-packages lets the venv see the apt packages above.
python3 -m venv --system-site-packages .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -e .

echo "==> Downloading the dog detection model"
.venv/bin/python -m paws download-model || echo "    Model download failed. Retry later with: python -m paws download-model"

cat <<'EOF'

Done. Next steps:
  1. Edit config.yaml so the pin numbers match your wiring (see docs/WIRING.md).
  2. Put the robot on blocks and run:   .venv/bin/python -m paws hwtest
  3. Start the robot:                   .venv/bin/python -m paws serve
  4. To start on every boot:            ./scripts/install_service.sh
EOF
