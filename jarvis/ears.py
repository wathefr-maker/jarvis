"""Les oreilles de JARVIS : écoute continue du micro, transcription (Whisper local) et mot d'activation."""
import re
import threading
import time
import unicodedata


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFD", s.lower())
    return "".join(c for c in s if unicodedata.category(c) != "Mn")


# Whisper écrit parfois « Jarvis » de travers : on accepte les variantes courantes.
VARIANTS = ["jarvis", "jarvi", "jarviss", "djarvis", "jervis", "charvis", "jarvice", "garvis"]


class Ears(threading.Thread):
    def __init__(self, cfg, out_queue, busy_event, on_state=None):
        super().__init__(daemon=True)
        self.cfg = cfg
        self.q = out_queue
        self.busy = busy_event
        self.on_state = on_state or (lambda *a, **k: None)
        self.awake_until = 0.0  # fenêtre pendant laquelle le mot d'activation n'est plus nécessaire
        words = set(VARIANTS) | {_norm(w) for w in cfg.wake_words}
        self.wake_re = re.compile(r"\b(" + "|".join(sorted(map(re.escape, words), key=len, reverse=True)) + r")\b[\s,.!?]*")
        self._whisper = None
        self._load_stt()

    def _load_stt(self):
        try:
            from faster_whisper import WhisperModel
            print(f"[oreilles] Chargement de Whisper « {self.cfg.whisper_model} » (première fois : téléchargement)…")
            self._whisper = WhisperModel(self.cfg.whisper_model, device="auto", compute_type="int8")
            print("[oreilles] Whisper prêt (transcription locale, hors-ligne).")
        except Exception as e:
            print(f"[oreilles] Whisper indisponible ({e}) : repli sur la reconnaissance Google en ligne.")

    def transcribe(self, audio, recognizer) -> str:
        if self._whisper is not None:
            import numpy as np
            raw = audio.get_raw_data(convert_rate=16000, convert_width=2)
            pcm = np.frombuffer(raw, np.int16).astype(np.float32) / 32768.0
            segments, _ = self._whisper.transcribe(
                pcm, language="fr", beam_size=3, vad_filter=True, initial_prompt="Jarvis, assistant personnel."
            )
            return " ".join(s.text for s in segments).strip()
        try:
            return recognizer.recognize_google(audio, language="fr-FR")
        except Exception:
            return ""

    def extract_command(self, text: str):
        """Renvoie (activé, commande). Gère « Jarvis, quelle heure ? » et « quelle heure, Jarvis ? »."""
        n = _norm(text)
        m = self.wake_re.search(n)
        if not m:
            return False, text
        before, after = n[: m.start()].strip(" ,.!?"), n[m.end():].strip()
        # On repart du texte original (avec accents) en gardant les mêmes positions.
        cmd = (text[: m.start()].strip(" ,.!?") + " " + text[m.end():].strip()).strip() if (before or after) else ""
        return True, cmd

    def run(self):
        try:
            import speech_recognition as sr
        except ImportError:
            print("[oreilles] SpeechRecognition non installé : micro désactivé.")
            return
        r = sr.Recognizer()
        r.pause_threshold = 0.8
        r.dynamic_energy_threshold = True
        try:
            mic = sr.Microphone()
        except Exception as e:
            print(f"[oreilles] Aucun micro utilisable ({e}). Utilise le clavier ou le HUD.")
            return
        with mic as source:
            print("[oreilles] Calibrage du bruit ambiant, silence 1 seconde…")
            r.adjust_for_ambient_noise(source, duration=1)
            print("[oreilles] J'écoute. Dites « Jarvis » suivi de votre demande.")
            while True:
                if self.busy.is_set():
                    time.sleep(0.1)
                    continue
                try:
                    audio = r.listen(source, timeout=1, phrase_time_limit=12)
                except sr.WaitTimeoutError:
                    continue
                except Exception as e:
                    print(f"[oreilles] erreur micro : {e}")
                    time.sleep(1)
                    continue
                if self.busy.is_set():  # JARVIS a parlé pendant la capture : on jette
                    continue
                text = self.transcribe(audio, r)
                if not text or len(text) < 2:
                    continue
                awake = time.time() < self.awake_until
                woke, cmd = self.extract_command(text)
                if awake and not woke:
                    self.q.put(("voix", text))
                elif woke and cmd:
                    self.q.put(("voix", cmd))
                elif woke:
                    self.q.put(("activation", ""))
