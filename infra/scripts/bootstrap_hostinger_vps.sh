#!/usr/bin/env bash
# Bootstrap a fresh Ubuntu VPS for AI Job Hunter hosting.
#
# Installs:
#   - Basic OS/admin packages
#   - UFW + fail2ban
#   - Docker Engine + Compose plugin from Docker's official apt repository
#   - K3s single-node Kubernetes using its default containerd runtime
#   - Helm
#
# Usage:
#   sudo bash infra/scripts/bootstrap_hostinger_vps.sh
#
# Optional env:
#   INSTALL_K3S_EXEC_EXTRA="--tls-san your.domain.com" sudo -E bash infra/scripts/bootstrap_hostinger_vps.sh

set -euo pipefail

if [[ "${EUID}" -ne 0 ]]; then
  echo "Run this script as root, for example: sudo bash $0" >&2
  exit 1
fi

export DEBIAN_FRONTEND=noninteractive

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"; }
die() { echo "ERROR: $*" >&2; exit 1; }

require_ubuntu() {
  if [[ ! -r /etc/os-release ]]; then
    die "/etc/os-release not found; this script expects Ubuntu."
  fi

  # shellcheck disable=SC1091
  . /etc/os-release
  if [[ "${ID:-}" != "ubuntu" ]]; then
    die "Unsupported OS '${PRETTY_NAME:-unknown}'. This script expects Ubuntu."
  fi

  log "Detected ${PRETTY_NAME}"
}

install_basic_packages() {
  log "Updating apt metadata and installing base packages..."
  apt-get update
  apt-get install -y \
    apt-transport-https \
    ca-certificates \
    curl \
    dnsutils \
    fail2ban \
    git \
    gnupg \
    htop \
    jq \
    lsb-release \
    make \
    nano \
    net-tools \
    software-properties-common \
    tar \
    ufw \
    unzip \
    vim \
    wget
}

configure_sysctl() {
  log "Configuring kernel networking settings for Kubernetes..."
  cat >/etc/modules-load.d/k3s.conf <<'EOF'
br_netfilter
overlay
EOF
  modprobe br_netfilter || true
  modprobe overlay || true

  cat >/etc/sysctl.d/99-k3s.conf <<'EOF'
net.bridge.bridge-nf-call-iptables=1
net.bridge.bridge-nf-call-ip6tables=1
net.ipv4.ip_forward=1
EOF
  sysctl --system >/dev/null
}

disable_swap() {
  log "Disabling swap for Kubernetes compatibility..."
  swapoff -a || true
  if grep -qE '^[^#].*\sswap\s' /etc/fstab; then
    cp /etc/fstab "/etc/fstab.backup.$(date +%Y%m%d%H%M%S)"
    sed -i.bak -E '/^[^#].*\sswap\s/s/^/# /' /etc/fstab
  fi
}

configure_firewall() {
  log "Configuring UFW firewall rules..."
  ufw allow OpenSSH >/dev/null || true
  ufw allow 80/tcp >/dev/null || true
  ufw allow 443/tcp >/dev/null || true
  ufw allow 6443/tcp >/dev/null || true
  ufw --force enable >/dev/null
  systemctl enable --now fail2ban >/dev/null
}

install_docker() {
  if command -v docker >/dev/null 2>&1; then
    log "Docker already installed; ensuring service is enabled..."
  else
    log "Installing Docker Engine from Docker's official apt repository..."
    install -m 0755 -d /etc/apt/keyrings
    curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
    chmod a+r /etc/apt/keyrings/docker.asc

    # shellcheck disable=SC1091
    . /etc/os-release
    echo \
      "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu ${VERSION_CODENAME} stable" \
      >/etc/apt/sources.list.d/docker.list

    apt-get update
    apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
  fi

  mkdir -p /etc/docker
  cat >/etc/docker/daemon.json <<'EOF'
{
  "log-driver": "json-file",
  "log-opts": {
    "max-size": "50m",
    "max-file": "3"
  }
}
EOF

  systemctl daemon-reload
  systemctl enable --now docker
  docker version >/dev/null
  docker compose version >/dev/null
}

install_k3s() {
  if command -v k3s >/dev/null 2>&1; then
    log "K3s already installed; ensuring service is enabled..."
    systemctl enable --now k3s
  else
    log "Installing K3s with the default containerd runtime..."
    curl -sfL https://get.k3s.io | \
      INSTALL_K3S_EXEC="--write-kubeconfig-mode 644 ${INSTALL_K3S_EXEC_EXTRA:-}" sh -
  fi

  mkdir -p /root/.kube
  cp /etc/rancher/k3s/k3s.yaml /root/.kube/config
  chmod 600 /root/.kube/config

  if ! command -v kubectl >/dev/null 2>&1; then
    ln -sf /usr/local/bin/k3s /usr/local/bin/kubectl
  fi

  log "Waiting for K3s node to become Ready..."
  kubectl wait --for=condition=Ready node --all --timeout=180s
}

install_helm() {
  if command -v helm >/dev/null 2>&1; then
    log "Helm already installed."
    return
  fi

  log "Installing Helm..."
  curl -fsSL https://raw.githubusercontent.com/helm/helm/main/scripts/get-helm-3 | bash
}

print_summary() {
  log "Bootstrap complete. Current status:"
  echo ""
  hostnamectl || true
  echo ""
  docker --version
  docker compose version
  k3s --version | head -1
  helm version --short || true
  echo ""
  kubectl get nodes -o wide
  echo ""
  kubectl get pods --all-namespaces
  echo ""
  ufw status verbose
}

main() {
  require_ubuntu
  install_basic_packages
  configure_sysctl
  disable_swap
  configure_firewall
  install_docker
  install_k3s
  install_helm
  print_summary
}

main "$@"
