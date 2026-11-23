#!/usr/bin/env sh
# Compare Lumina v7 avec ta version précédente. Usage : sh scripts/compare_with_v6.sh ~/assistant_pwa
# (Seul le dossier fourni est lu ; rien n'est modifié.)
set -eu
[ $# -eq 1 ] || { echo "usage: $0 /chemin/vers/ancien/dossier"; exit 2; }
cd "$(dirname "$0")/.."
diff -ruN --exclude='.git' --exclude='node_modules' --exclude='*.db*' --exclude='*.backup*' --exclude='__pycache__' \
  --exclude='build' --exclude='.gradle' --exclude='*.png' --exclude='*.zip' --exclude='.env*' "$1" . | less -R
