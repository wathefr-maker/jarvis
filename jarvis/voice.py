"""La voix de JARVIS : voix neurale Microsoft (edge-tts), avec repli hors-ligne (pyttsx3)."""
import asyncio
import os
import re
import tempfile
import threading
import time


def clean_for_speech(text: str) -> str:
    """Retire le markdown, les liens et les symboles qui sonnent mal à l'oral."""
    text = re.sub(r"```.*?```", " (je vous ai affiché le code à l'écran) ", text, flags=re.S)
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    text = re.sub(r"https?://\S+", "", text)
    text = re.sub(r"[*_#`>|]+", "", text)
    text = re.sub(r"^\s*[-•]\s+", "", text, flags=re.M)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


class Voice:
    def __init__(self, cfg, enabled=True):
        self.cfg = cfg
        self.enabled = enabled
        self.lock = threading.Lock()
        self.mode = None
        self._tts = None
        if not enabled:
            return
        try:
            import edge_tts  # noqa: F401
            import pygame
            pygame.mixer.init()
            self._pygame = pygame
            self.mode = "edge"
        except Exception:
            self._init_offline()

    def _init_offline(self):
        try:
            import pyttsx3
            self._tts = pyttsx3.init()
            for v in self._tts.getProperty("voices"):
                if "fr" in (v.id + str(v.languages)).lower():
                    self._tts.setProperty("voice", v.id)
                    break
            self._tts.setProperty("rate", 185)
            self.mode = "offline"
        except Exception:
            self.mode = None
            print("[voix] Aucun moteur vocal disponible : JARVIS répondra par écrit.")

    def _say_edge(self, text: str):
        import edge_tts
        fd, path = tempfile.mkstemp(suffix=".mp3")
        os.close(fd)
        try:
            asyncio.run(edge_tts.Communicate(text, self.cfg.voice, rate=self.cfg.voice_rate).save(path))
            m = self._pygame.mixer.music
            m.load(path)
            m.play()
            while m.get_busy():
                time.sleep(0.05)
            m.unload()
        finally:
            try:
                os.remove(path)
            except OSError:
                pass

    def say(self, text: str):
        if not self.enabled or not self.mode:
            return
        text = clean_for_speech(text)
        if not text:
            return
        with self.lock:
            if self.mode == "edge":
                try:
                    self._say_edge(text)
                    return
                except Exception as e:  # pas d'internet, etc. : on bascule hors-ligne
                    print(f"[voix] edge-tts indisponible ({e}), passage à la voix hors-ligne.")
                    self._init_offline()
            if self.mode == "offline":
                self._tts.say(text)
                self._tts.runAndWait()

    def stop(self):
        if self.mode == "edge":
            try:
                self._pygame.mixer.music.stop()
            except Exception:
                pass
