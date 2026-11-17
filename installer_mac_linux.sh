#!/usr/bin/env bash
set -e
cd "$(dirname "$0")"
echo "=== Installation de J.A.R.V.I.S. ==="
if [[ "$(uname)" == "Darwin" ]]; then
  command -v brew >/dev/null || { echo "Installe Homebrew d'abord : https://brew.sh"; exit 1; }
  brew install portaudio
else
  echo "Installation des dépendances audio (mot de passe administrateur demandé)…"
  sudo apt-get update && sudo apt-get install -y portaudio19-dev python3-venv python3-dev espeak-ng
fi
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
[ -f .env ] || cp .env.example .env
echo
echo "Installation terminée. Ouvre le fichier .env, colle ta clé API, puis lance : ./lancer_mac_linux.sh"
