#!/bin/bash
# Lance JARVIS après avoir installé automatiquement les mises à jour depuis GitHub.
{
cd "$(dirname "$0")" || exit 1
if [ -d .git ]; then
  echo "🔄 Recherche de mises à jour…"
  OLD=$(git rev-parse HEAD 2>/dev/null)
  if git pull --ff-only -q 2>/dev/null; then
    NEW=$(git rev-parse HEAD)
    if [ "$OLD" != "$NEW" ]; then
      echo "✨ Nouvelle version installée :"
      git log --format="   • %s" "$OLD..$NEW" | head -10
      if ! git diff --quiet "$OLD" "$NEW" -- requirements.txt; then
        echo "📦 Installation des nouveaux composants…"
        .venv/bin/pip install -q -r requirements.txt
      fi
    else
      echo "✅ JARVIS est à jour."
    fi
  else
    echo "⚠️  Mise à jour impossible (pas d'internet ?). Démarrage avec la version actuelle."
  fi
fi
exec .venv/bin/python jarvis_main.py "$@"
}
