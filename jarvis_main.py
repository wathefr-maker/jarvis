"""Point d'entrée : python jarvis_main.py   (options : --muet, --sans-micro, --sans-hud)"""
import argparse
import queue
import re
import sys
import threading
import time
from datetime import datetime

from jarvis.config import load_config
from jarvis.memory import Memory

STOP = re.compile(r"\b(au revoir|eteins[- ]toi|éteins[- ]toi|arrete[- ]toi|arrête[- ]toi|extinction|bonne nuit jarvis)\b", re.I)
RESET = re.compile(r"\b(oublie (la|cette) conversation|nouvelle conversation|on repart de zero|on repart de zéro)\b", re.I)
YES = re.compile(r"\b(oui|ouais|vas[- ]y|confirme|d'accord|ok|okay|exact|fais[- ]le|go)\b", re.I)


def main():
    ap = argparse.ArgumentParser(description="J.A.R.V.I.S. propulsé par Claude")
    ap.add_argument("--muet", action="store_true", help="pas de voix, réponses écrites seulement")
    ap.add_argument("--sans-micro", action="store_true", help="ne pas écouter le micro (clavier / HUD seulement)")
    ap.add_argument("--sans-hud", action="store_true", help="ne pas lancer l'interface Iron Man")
    args = ap.parse_args()

    cfg = load_config()
    if not cfg.api_key or not cfg.api_key.startswith("sk-"):
        print("\n[!] Clé API Claude manquante.\n"
              "    1. Crée une clé sur https://console.anthropic.com (rubrique API Keys)\n"
              "    2. Copie le fichier .env.example en .env\n"
              "    3. Colle ta clé après ANTHROPIC_API_KEY=\n")
        sys.exit(1)

    from jarvis.brain import Brain
    from jarvis.tools import Context
    from jarvis.voice import Voice

    commands = queue.Queue()
    busy = threading.Event()

    hud = None
    if not args.sans_hud:
        from jarvis.hud import HUD
        hud = HUD(cfg, commands)
        hud.start()

    def emit(type_, **data):
        if hud:
            hud.emit(type_, **data)

    def state(s, detail=""):
        emit("state", state=s, detail=detail)

    voice = Voice(cfg, enabled=not args.muet)
    memory = Memory(cfg.data_dir / "memoire.json")

    from jarvis.status import Status
    status = Status(cfg, emit)
    if hud:
        hud.status = status
        hud.on_refresh = lambda: status.check_all(voice, memory, not args.sans_micro)

    ears = None
    if not args.sans_micro:
        from jarvis.ears import Ears
        ears = Ears(cfg, commands, busy, on_state=lambda st, d: status.set("micro", "Micro", st, d))
        ears.start()
    status.check_all(voice, memory, not args.sans_micro)

    def speak(text):
        print(f"\nJARVIS > {text}\n")
        emit("jarvis", text=text)
        state("speaking")
        busy.set()
        voice.say(text)
        time.sleep(0.25)  # évite que le micro capte la fin de la phrase

    def open_window(seconds):
        if ears:
            ears.awake_until = time.time() + seconds

    def confirm(question):
        speak(question)
        state("listening", "Confirmation attendue : « oui » ou « non »")
        busy.clear()
        open_window(20)
        try:
            _, answer = commands.get(timeout=20)
        except queue.Empty:
            answer = ""
        busy.set()
        state("thinking")
        ok = bool(YES.search(answer or "")) and not re.search(r"\b(non|annule|stop)\b", answer or "", re.I)
        emit("tool", text=f"confirmation : {'accordée' if ok else 'refusée'}")
        return ok

    ctx = Context(cfg, memory, confirm, commands, emit)
    brain = Brain(cfg, ctx, memory)

    def on_tool(name, params):
        label = {"web_search": "recherche web"}.get(name, name)
        print(f"   [outil] {name} {params}")
        emit("tool", text=f"{label} {params if params else ''}")
        state("thinking", label)

    # Clavier : on peut toujours taper dans la console.
    def keyboard():
        while True:
            try:
                line = input()
            except (EOFError, KeyboardInterrupt):
                return
            if line.strip():
                commands.put(("clavier", line.strip()))

    if sys.stdin and sys.stdin.isatty():
        threading.Thread(target=keyboard, daemon=True).start()

    h = datetime.now().hour
    salut = "Bonjour" if 5 <= h < 18 else "Bonsoir"
    speak(f"{salut} {cfg.user_name}. Tous les systèmes sont opérationnels.")
    busy.clear()
    state("idle")
    print("Parle (en commençant par « Jarvis »), tape ici, ou utilise le HUD. Ctrl+C pour quitter.\n")

    try:
        while True:
            source, text = commands.get()
            if source == "activation":
                busy.set()
                speak(f"Oui {cfg.user_name} ?")
                busy.clear()
                open_window(cfg.followup_seconds)
                state("listening")
                continue
            print(f"VOUS ({source}) > {text}")
            if source != "minuteur":
                emit("user", text=text)
            if STOP.search(text):
                speak(f"À votre service, {cfg.user_name}. Je me mets en veille.")
                break
            if RESET.search(text):
                brain.reset()
                speak("Conversation réinitialisée. Je garde néanmoins mes souvenirs importants.")
                busy.clear()
                state("idle")
                continue
            busy.set()
            voice.stop()
            state("thinking")
            answer = brain.think(text, on_tool=on_tool)
            speak(answer)
            busy.clear()
            open_window(cfg.followup_seconds)  # on peut enchaîner sans redire « Jarvis »
            state("listening" if ears else "idle")
            if ears:
                threading.Timer(cfg.followup_seconds, lambda: (not busy.is_set()) and state("idle")).start()
    except KeyboardInterrupt:
        print("\nExtinction.")


if __name__ == "__main__":
    main()
