"""Les mains et les yeux de JARVIS : tout ce qu'il peut faire sur ton ordinateur et ta maison.

Pour ajouter un pouvoir : écris une fonction `def mon_outil(ctx, **params) -> str`, puis
ajoute-la à la liste TOOLS avec une description claire. Claude décidera seul quand l'utiliser.
"""
import base64
import io
import json
import platform
import shutil
import subprocess
import threading
import urllib.request
import webbrowser
from datetime import datetime
from pathlib import Path

OS = platform.system()  # "Windows", "Darwin" (Mac) ou "Linux"


class Context:
    """Ce que les outils ont le droit d'utiliser : config, mémoire, confirmation, file d'attente."""

    def __init__(self, cfg, memory, confirm, queue, emit):
        self.cfg = cfg
        self.memory = memory
        self.confirm = confirm  # confirm("question ?") -> bool
        self.queue = queue
        self.emit = emit


# ----------------------------------------------------------------- outils de base
def get_datetime(ctx):
    jours = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]
    n = datetime.now()
    return f"{jours[n.weekday()]} {n.strftime('%d/%m/%Y, %H:%M:%S')}"


def open_url(ctx, url):
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    webbrowser.open(url)
    return f"Ouvert : {url}"


def open_application(ctx, name):
    try:
        if OS == "Windows":
            subprocess.Popen(["cmd", "/c", "start", "", name], shell=False)
        elif OS == "Darwin":
            subprocess.Popen(["open", "-a", name])
        else:
            exe = shutil.which(name) or shutil.which(name.lower())
            if not exe:
                return f"Application « {name} » introuvable."
            subprocess.Popen([exe], start_new_session=True)
        return f"Application « {name} » lancée."
    except Exception as e:
        return f"Échec du lancement de {name} : {e}"


def system_status(ctx):
    try:
        import psutil
    except ImportError:
        return "psutil n'est pas installé."
    vm = psutil.virtual_memory()
    disk = psutil.disk_usage(str(Path.home().anchor or "/"))
    parts = [
        f"Processeur : {psutil.cpu_percent(interval=0.5)} %",
        f"Mémoire : {vm.percent} % ({vm.used // 2**30} / {vm.total // 2**30} Go)",
        f"Disque : {disk.percent} % utilisé, {disk.free // 2**30} Go libres",
    ]
    bat = psutil.sensors_battery() if hasattr(psutil, "sensors_battery") else None
    if bat:
        parts.append(f"Batterie : {round(bat.percent)} % {'(en charge)' if bat.power_plugged else '(sur batterie)'}")
    top = sorted(psutil.process_iter(["name", "memory_percent"]), key=lambda p: p.info["memory_percent"] or 0, reverse=True)[:5]
    parts.append("Plus gourmands en mémoire : " + ", ".join(f"{p.info['name']} ({p.info['memory_percent']:.1f} %)" for p in top))
    parts.append(f"Système : {platform.system()} {platform.release()}")
    return "\n".join(parts)


def run_command(ctx, command):
    if not ctx.cfg.allow_shell:
        return "Les commandes système sont désactivées dans la configuration."
    if not ctx.confirm(f"Je vais exécuter la commande : {command}. Je confirme ?"):
        return "L'utilisateur a refusé l'exécution."
    try:
        p = subprocess.run(command, shell=True, capture_output=True, text=True, timeout=60)
        out = (p.stdout + p.stderr).strip()
        return f"Code retour {p.returncode}\n{out[-4000:]}" if out else f"Terminé (code {p.returncode})."
    except subprocess.TimeoutExpired:
        return "La commande a dépassé 60 secondes."


def _path(p):
    return Path(p).expanduser()


def list_directory(ctx, path="~"):
    d = _path(path)
    if not d.is_dir():
        return f"{d} n'est pas un dossier."
    items = sorted(d.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower()))[:200]
    return "\n".join(("[dossier] " if i.is_dir() else "") + i.name for i in items) or "(vide)"


def read_file(ctx, path):
    f = _path(path)
    if not f.is_file():
        return f"Fichier introuvable : {f}"
    try:
        return f.read_text(encoding="utf-8", errors="replace")[:15000]
    except Exception as e:
        return f"Lecture impossible : {e}"


def write_file(ctx, path, content, append=False):
    f = _path(path)
    action = "ajouter du texte à" if append else ("écraser" if f.exists() else "créer")
    if not ctx.confirm(f"Je vais {action} le fichier {f.name}. Je confirme ?"):
        return "L'utilisateur a refusé."
    f.parent.mkdir(parents=True, exist_ok=True)
    with open(f, "a" if append else "w", encoding="utf-8") as h:
        h.write(content)
    return f"Fichier écrit : {f}"


def take_note(ctx, text):
    f = ctx.cfg.data_dir / "notes.md"
    with open(f, "a", encoding="utf-8") as h:
        h.write(f"- [{datetime.now().strftime('%d/%m/%Y %H:%M')}] {text}\n")
    return "Note enregistrée."


def read_notes(ctx):
    f = ctx.cfg.data_dir / "notes.md"
    return f.read_text(encoding="utf-8")[-6000:] if f.exists() else "Aucune note."


def look_at_screen(ctx):
    """Capture d'écran envoyée à Claude, qui la « voit »."""
    try:
        import mss
        from PIL import Image
    except ImportError:
        return "Il faut installer mss et pillow pour que je puisse voir l'écran."
    with mss.mss() as s:
        shot = s.grab(s.monitors[1])
        img = Image.frombytes("RGB", shot.size, shot.rgb)
    img.thumbnail((1568, 1568))
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return [
        {"type": "text", "text": "Voici l'écran principal de l'utilisateur à l'instant :"},
        {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": base64.b64encode(buf.getvalue()).decode()}},
    ]


def remember(ctx, fact):
    return ctx.memory.add(fact)


def forget(ctx, keyword):
    return ctx.memory.forget(keyword)


def set_timer(ctx, seconds, label="minuteur"):
    seconds = max(1, int(seconds))

    def ring():
        ctx.queue.put(("minuteur", f"[ALERTE INTERNE] Le minuteur « {label} » ({seconds} s) vient de se terminer. Préviens l'utilisateur en une phrase."))

    t = threading.Timer(seconds, ring)
    t.daemon = True
    t.start()
    m, s = divmod(seconds, 60)
    return f"Minuteur « {label} » lancé pour {m} min {s} s."


def media_control(ctx, action):
    keys = {"lecture_pause": "playpause", "suivant": "nexttrack", "precedent": "prevtrack",
            "volume_plus": "volumeup", "volume_moins": "volumedown", "muet": "volumemute"}
    if action not in keys:
        return f"Action inconnue. Possibles : {', '.join(keys)}"
    try:
        import pyautogui
        n = 5 if action.startswith("volume_") else 1
        for _ in range(n):
            pyautogui.press(keys[action])
        return f"Fait : {action}"
    except Exception as e:
        return f"Contrôle média impossible : {e}"


def type_text(ctx, text):
    try:
        import pyautogui
        pyautogui.write(text, interval=0.01)
        return "Texte tapé."
    except Exception as e:
        return f"Impossible de taper : {e}"


# ----------------------------------------------------------------- maison connectée (Home Assistant)
def _ha(ctx, method, path, body=None):
    req = urllib.request.Request(
        ctx.cfg.ha_url + path,
        data=json.dumps(body).encode() if body is not None else None,
        method=method,
        headers={"Authorization": f"Bearer {ctx.cfg.ha_token}", "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read() or b"null")


def home_list_devices(ctx, domain=""):
    states = _ha(ctx, "GET", "/api/states")
    rows = [f"{s['entity_id']} = {s['state']} ({s['attributes'].get('friendly_name', '')})"
            for s in states if not domain or s["entity_id"].startswith(domain + ".")]
    return "\n".join(rows[:150]) or "Aucun appareil."


def home_control(ctx, domain, service, entity_id, data=None):
    body = {"entity_id": entity_id, **(data or {})}
    _ha(ctx, "POST", f"/api/services/{domain}/{service}", body)
    return f"OK : {domain}.{service} sur {entity_id}"


# ----------------------------------------------------------------- catalogue envoyé à Claude
def _t(fn, desc, props=None, required=None):
    return {"fn": fn, "name": fn.__name__, "description": desc,
            "input_schema": {"type": "object", "properties": props or {}, "required": required or []}}


S = {"type": "string"}
TOOLS = [
    _t(get_datetime, "Date et heure exactes actuelles."),
    _t(open_url, "Ouvre un site web dans le navigateur (YouTube, Netflix, une recherche Google…).", {"url": S}, ["url"]),
    _t(open_application, "Lance une application installée (ex : Spotify, Calculatrice, code, notepad, Safari).", {"name": S}, ["name"]),
    _t(system_status, "État de l'ordinateur : processeur, mémoire, disque, batterie, programmes gourmands."),
    _t(run_command, "Exécute une commande shell sur l'ordinateur (l'utilisateur doit confirmer). À utiliser avec prudence.", {"command": S}, ["command"]),
    _t(list_directory, "Liste le contenu d'un dossier (~ = dossier personnel).", {"path": S}),
    _t(read_file, "Lit un fichier texte.", {"path": S}, ["path"]),
    _t(write_file, "Crée, écrase ou complète un fichier texte (confirmation demandée).",
       {"path": S, "content": S, "append": {"type": "boolean"}}, ["path", "content"]),
    _t(take_note, "Ajoute une note rapide au carnet de JARVIS.", {"text": S}, ["text"]),
    _t(read_notes, "Relit le carnet de notes."),
    _t(look_at_screen, "Prend une capture de l'écran pour voir ce que l'utilisateur regarde (erreur, page, document…)."),
    _t(remember, "Mémorise durablement un fait sur l'utilisateur (préférence, info perso, projet).", {"fact": S}, ["fact"]),
    _t(forget, "Efface les souvenirs contenant un mot-clé.", {"keyword": S}, ["keyword"]),
    _t(set_timer, "Lance un minuteur / rappel. JARVIS préviendra à la fin.",
       {"seconds": {"type": "integer"}, "label": S}, ["seconds"]),
    _t(media_control, "Contrôle la musique et le son.",
       {"action": {"type": "string", "enum": ["lecture_pause", "suivant", "precedent", "volume_plus", "volume_moins", "muet"]}}, ["action"]),
    _t(type_text, "Tape du texte au clavier dans la fenêtre active (dictée).", {"text": S}, ["text"]),
]
HOME_TOOLS = [
    _t(home_list_devices, "Liste les appareils de la maison connectée et leur état. domain optionnel : light, switch, climate, cover, media_player…",
       {"domain": S}),
    _t(home_control, "Pilote un appareil de la maison (ex : domain=light, service=turn_on, entity_id=light.salon, data={brightness_pct: 40}).",
       {"domain": S, "service": S, "entity_id": S, "data": {"type": "object"}}, ["domain", "service", "entity_id"]),
]


def _google_tools(cfg):
    from . import google_tools as G
    if not (G.available(cfg) and G.token_path(cfg).exists()):
        return []
    try:
        import googleapiclient  # noqa: F401
    except ImportError:
        return []
    return G.tools(_t)


def active_tools(cfg):
    if not hasattr(cfg, "_tools_cache"):
        cfg._tools_cache = TOOLS + (HOME_TOOLS if cfg.ha_url and cfg.ha_token else []) + _google_tools(cfg)
    return cfg._tools_cache


def schemas(cfg):
    return [{k: v for k, v in t.items() if k != "fn"} for t in active_tools(cfg)]


def run(name, params, ctx):
    for t in active_tools(ctx.cfg):
        if t["name"] == name:
            try:
                return t["fn"](ctx, **(params or {}))
            except Exception as e:
                return f"Erreur dans l'outil {name} : {e}"
    return f"Outil inconnu : {name}"
