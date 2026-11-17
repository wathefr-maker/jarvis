"""Vérifie l'état de chaque connexion de JARVIS et l'affiche dans l'onglet « Connexions » du HUD.

Statuts : ok (vert), warn (orange : à configurer / à connecter), off (gris : non utilisé), error (rouge).
"""
import json
import threading
import urllib.request


class Status:
    ORDER = ["claude", "web", "micro", "voix", "gmail", "agenda", "tasks", "maison", "memoire"]

    def __init__(self, cfg, emit):
        self.cfg = cfg
        self.emit = emit
        self.items = {}
        self.lock = threading.Lock()
        self._google_login = threading.Lock()

    def set(self, key, label, status, detail=""):
        with self.lock:
            self.items[key] = {"key": key, "label": label, "status": status, "detail": detail,
                               "order": self.ORDER.index(key) if key in self.ORDER else 99}
        self.emit("connection", **self.items[key])

    def snapshot(self):
        with self.lock:
            return sorted(self.items.values(), key=lambda i: i["order"])

    # ------------------------------------------------------------------ vérifications
    def check_all(self, voice=None, memory=None, ears_enabled=True):
        threading.Thread(target=self._check_all, args=(voice, memory, ears_enabled), daemon=True).start()

    def _check_all(self, voice, memory, ears_enabled):
        self.set("claude", "Cerveau Claude", "warn", f"{self.cfg.model} · vérification…")
        self.set("web", "Recherche web", "ok", "Météo, actualités, prix en direct")
        if not ears_enabled:
            self.set("micro", "Micro", "off", "Désactivé (--sans-micro)")
        elif "micro" not in self.items:
            self.set("micro", "Micro", "warn", "Démarrage…")
        if voice is not None:
            mode = getattr(voice, "mode", None)
            if not voice.enabled:
                self.set("voix", "Voix", "off", "Désactivée (--muet)")
            elif mode == "edge":
                self.set("voix", "Voix", "ok", f"Voix neurale {self.cfg.voice}")
            elif mode == "offline":
                self.set("voix", "Voix", "warn", "Voix hors-ligne de secours")
            else:
                self.set("voix", "Voix", "error", "Aucun moteur vocal")
        if memory is not None:
            n = len(memory.facts)
            self.set("memoire", "Mémoire", "ok", f"{n} souvenir{'s' if n > 1 else ''} enregistré{'s' if n > 1 else ''}")
        self._check_claude()
        self._check_google()
        self._check_home()

    def _check_claude(self):
        try:
            import anthropic
            client = anthropic.Anthropic(api_key=self.cfg.api_key)
            client.messages.count_tokens(model=self.cfg.model, messages=[{"role": "user", "content": "ping"}])
            self.set("claude", "Cerveau Claude", "ok", self.cfg.model)
        except Exception as e:
            name = type(e).__name__
            msg = {"AuthenticationError": "Clé API refusée", "APIConnectionError": "Pas d'internet",
                   "PermissionDeniedError": "Accès refusé (crédit ?)"}.get(name, f"Erreur : {name}")
            self.set("claude", "Cerveau Claude", "error", msg)

    def _check_google(self):
        from . import google_tools as G
        labels = {"gmail": "Gmail", "agenda": "Google Agenda", "tasks": "Google Tasks"}
        if not G.adopt_downloaded(self.cfg):
            for k, l in labels.items():
                self.set(k, l, "warn", "Non configuré : crée l'accès sur console.cloud.google.com")
            return
        if not G.token_path(self.cfg).exists():
            if self._google_login.locked():
                return  # une fenêtre d'autorisation est déjà ouverte
            with self._google_login:
                for k, l in labels.items():
                    self.set(k, l, "warn", "Autorise JARVIS dans la page Google qui vient de s'ouvrir")
                try:
                    G.get_creds(self.cfg, interactive=True)
                    if hasattr(self.cfg, "_tools_cache"):
                        del self.cfg._tools_cache  # active les outils Google sans redémarrer
                except Exception as e:
                    for k, l in labels.items():
                        self.set(k, l, "error", f"Autorisation non terminée : {str(e)[:70]}")
                    return
        try:
            from googleapiclient.discovery import build
            creds = G.get_creds(self.cfg)
        except Exception as e:
            if "expir" in str(e).lower() or "absente" in str(e):
                G.token_path(self.cfg).unlink(missing_ok=True)  # on repartira sur une nouvelle autorisation
                msg = "Connexion expirée : clique sur REVÉRIFIER pour te reconnecter"
            else:
                msg = str(e)[:80]
            for k, l in labels.items():
                self.set(k, l, "error", msg)
            return
        checks = {
            "gmail": lambda: build("gmail", "v1", credentials=creds, cache_discovery=False).users().getProfile(userId="me").execute()["emailAddress"],
            "agenda": lambda: build("calendar", "v3", credentials=creds, cache_discovery=False).calendars().get(calendarId="primary").execute().get("summary", "Agenda principal"),
            "tasks": lambda: f"{len(build('tasks', 'v1', credentials=creds, cache_discovery=False).tasklists().list().execute().get('items', []))} liste(s) de tâches",
        }
        for k, fn in checks.items():
            try:
                self.set(k, labels[k], "ok", fn())
            except Exception as e:
                self.set(k, labels[k], "error", f"Erreur : {str(e)[:90]}")

    def _check_home(self):
        if not (self.cfg.ha_url and self.cfg.ha_token):
            self.set("maison", "Maison connectée", "off", "Home Assistant non configuré")
            return
        try:
            req = urllib.request.Request(self.cfg.ha_url + "/api/config", headers={"Authorization": f"Bearer {self.cfg.ha_token}"})
            with urllib.request.urlopen(req, timeout=6) as r:
                name = json.loads(r.read()).get("location_name", "Home Assistant")
            self.set("maison", "Maison connectée", "ok", name)
        except Exception as e:
            self.set("maison", "Maison connectée", "error", f"Injoignable : {str(e)[:70]}")
