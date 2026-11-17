"""Connexion de JARVIS à ton compte Google (Gmail, Agenda, Tasks). À lancer une seule fois."""
import sys

from jarvis.config import load_config
from jarvis import google_tools as G

cfg = load_config()
if not G.available(cfg):
    print(f"\n[!] Fichier introuvable : {G.credentials_path(cfg)}\n"
          "    Télécharge le fichier JSON de ton client OAuth sur Google Cloud,\n"
          "    renomme-le credentials.json et place-le dans le dossier jarvis/data/\n")
    sys.exit(1)

print("Ton navigateur va s'ouvrir : connecte-toi avec ton compte Google pro et accepte les autorisations.")
creds = G.get_creds(cfg, interactive=True)

from googleapiclient.discovery import build

profile = build("gmail", "v1", credentials=creds, cache_discovery=False).users().getProfile(userId="me").execute()
print(f"\n✅ Connecté au compte {profile['emailAddress']}. Gmail, Agenda et Tasks sont prêts.")
print("   Relance JARVIS pour qu'il prenne en compte ses nouveaux pouvoirs.\n")
