"""Mémoire à long terme : des faits que JARVIS retient d'une session à l'autre."""
import json
import threading
from datetime import datetime
from pathlib import Path


class Memory:
    def __init__(self, path: Path):
        self.path = path
        self.lock = threading.Lock()
        self.facts = []
        if path.exists():
            try:
                self.facts = json.loads(path.read_text(encoding="utf-8")).get("faits", [])
            except Exception:
                self.facts = []

    def _save(self):
        self.path.write_text(json.dumps({"faits": self.facts}, ensure_ascii=False, indent=2), encoding="utf-8")

    def add(self, fact: str) -> str:
        with self.lock:
            self.facts.append({"fait": fact.strip(), "date": datetime.now().strftime("%Y-%m-%d")})
            self._save()
        return f"Mémorisé : {fact}"

    def forget(self, keyword: str) -> str:
        kw = keyword.lower()
        with self.lock:
            before = len(self.facts)
            self.facts = [f for f in self.facts if kw not in f["fait"].lower()]
            self._save()
            n = before - len(self.facts)
        return f"{n} souvenir(s) effacé(s)." if n else "Aucun souvenir ne correspond."

    def as_text(self) -> str:
        if not self.facts:
            return "(aucun souvenir pour l'instant)"
        return "\n".join(f"- {f['fait']} (noté le {f['date']})" for f in self.facts[-200:])
