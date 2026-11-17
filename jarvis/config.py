"""Configuration de JARVIS, lue depuis le fichier .env à la racine du projet."""
import os
from dataclasses import dataclass, field
from pathlib import Path

try:
    from dotenv import load_dotenv
except ImportError:  # python-dotenv absent : on lit seulement les variables d'environnement
    load_dotenv = None

ROOT = Path(__file__).resolve().parent.parent


def _bool(v: str, default: bool) -> bool:
    if v is None or v == "":
        return default
    return v.strip().lower() in ("1", "true", "oui", "yes", "on")


@dataclass
class Config:
    api_key: str = ""
    model: str = "claude-sonnet-5-5"
    user_name: str = "Monsieur"
    voice: str = "fr-FR-HenriNeural"
    voice_rate: str = "+8%"
    whisper_model: str = "small"
    wake_words: list = field(default_factory=lambda: ["jarvis"])
    followup_seconds: float = 8.0
    hud_port: int = 7777
    hud_open_browser: bool = True
    allow_shell: bool = True
    ha_url: str = ""
    ha_token: str = ""
    data_dir: Path = ROOT / "data"
    max_turns: int = 20


def load_config() -> Config:
    if load_dotenv:
        load_dotenv(ROOT / ".env")
    e = os.environ.get
    cfg = Config(
        api_key=e("ANTHROPIC_API_KEY", ""),
        model=e("JARVIS_MODELE", "claude-sonnet-5-5"),
        user_name=e("JARVIS_NOM_UTILISATEUR", "Monsieur"),
        voice=e("JARVIS_VOIX", "fr-FR-HenriNeural"),
        voice_rate=e("JARVIS_VITESSE_VOIX", "+8%"),
        whisper_model=e("JARVIS_WHISPER", "small"),
        wake_words=[w.strip().lower() for w in e("JARVIS_MOTS_ACTIVATION", "jarvis").split(",") if w.strip()],
        followup_seconds=float(e("JARVIS_FENETRE_SUIVI", "8")),
        hud_port=int(e("JARVIS_PORT_HUD", "7777")),
        hud_open_browser=_bool(e("JARVIS_OUVRIR_HUD"), True),
        allow_shell=_bool(e("JARVIS_AUTORISER_COMMANDES"), True),
        ha_url=e("HOME_ASSISTANT_URL", "").rstrip("/"),
        ha_token=e("HOME_ASSISTANT_TOKEN", ""),
    )
    cfg.data_dir.mkdir(parents=True, exist_ok=True)
    return cfg
