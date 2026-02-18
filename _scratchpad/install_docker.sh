#!/usr/bin/env bash
set -euo pipefail

echo "[INFO] Installing Docker prerequisites..."
apt-get update -y
apt-get install -y ca-certificates curl gnupg lsb-release

echo "[INFO] Setting up Docker apt repository..."
install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | gpg --batch --yes --dearmor -o /etc/apt/keyrings/docker.gpg
chmod a+r /etc/apt/keyrings/docker.gpg

codename="$(. /etc/os-release && echo "$VERSION_CODENAME")"
arch="$(dpkg --print-architecture)"
echo "deb [arch=${arch} signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu ${codename} stable" > /etc/apt/sources.list.d/docker.list

echo "[INFO] Installing Docker Engine and Compose plugin..."
apt-get update -y
apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

echo "[INFO] Enabling Docker service..."
systemctl enable docker
systemctl start docker

echo "[OK] Docker installation completed."

