"""Pouvoirs Google de JARVIS : Gmail, Google Agenda et Google Tasks.

Prérequis : un fichier data/credentials.json (client OAuth « Application de bureau »)
puis une première connexion avec :  python connecter_google.py
"""
import base64
import re
from datetime import datetime, timedelta
from email.mime.text import MIMEText
from html import unescape

SCOPES = [
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/calendar",
    "https://www.googleapis.com/auth/tasks",
]

_services = {}


def credentials_path(cfg):
    return cfg.data_dir / "credentials.json"


def token_path(cfg):
    return cfg.data_dir / "token_google.json"


def available(cfg):
    return credentials_path(cfg).exists()


def get_creds(cfg, interactive=False):
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials

    creds = None
    if token_path(cfg).exists():
        creds = Credentials.from_authorized_user_file(str(token_path(cfg)), SCOPES)
    if creds and creds.valid:
        return creds
    if creds and creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
            token_path(cfg).write_text(creds.to_json())
            return creds
        except Exception:
            creds = None
    if not interactive:
        raise RuntimeError("Connexion Google expirée ou absente : lance « python connecter_google.py ».")
    from google_auth_oauthlib.flow import InstalledAppFlow

    flow = InstalledAppFlow.from_client_secrets_file(str(credentials_path(cfg)), SCOPES)
    creds = flow.run_local_server(port=0, prompt="consent")
    token_path(cfg).write_text(creds.to_json())
    return creds


def svc(ctx, name):
    if name not in _services:
        from googleapiclient.discovery import build

        version = {"gmail": "v1", "calendar": "v3", "tasks": "v1"}[name]
        _services[name] = build(name, version, credentials=get_creds(ctx.cfg), cache_discovery=False)
    return _services[name]


def _local(dt_str):
    """« 2026-11-18T14:00 » ou « 2026-11-18 14:00 » -> datetime avec le fuseau local."""
    dt = datetime.fromisoformat(dt_str.strip().replace(" ", "T"))
    return dt.astimezone() if dt.tzinfo is None else dt


def _fmt(dt):
    jours = ["lun.", "mar.", "mer.", "jeu.", "ven.", "sam.", "dim."]
    return f"{jours[dt.weekday()]} {dt.strftime('%d/%m %H:%M')}"


# ============================================================ AGENDA
def agenda_lister(ctx, debut="", jours=1):
    start = _local(debut) if debut else datetime.now().astimezone().replace(hour=0, minute=0, second=0, microsecond=0)
    end = start + timedelta(days=max(1, int(jours)))
    items = svc(ctx, "calendar").events().list(
        calendarId="primary", timeMin=start.isoformat(), timeMax=end.isoformat(),
        singleEvents=True, orderBy="startTime", maxResults=50,
    ).execute().get("items", [])
    if not items:
        return "Aucun événement sur cette période."
    out = []
    for e in items:
        s = e["start"].get("dateTime") or e["start"].get("date")
        quand = _fmt(datetime.fromisoformat(s)) if "T" in s else f"{s} (journée entière)"
        lieu = f" @ {e['location']}" if e.get("location") else ""
        out.append(f"- {quand} : {e.get('summary', '(sans titre)')}{lieu}  [id={e['id']}]")
    return "\n".join(out)


def agenda_creer(ctx, titre, debut, duree_minutes=60, lieu="", description="", invites=None):
    start = _local(debut)
    end = start + timedelta(minutes=int(duree_minutes))
    invites = [m.strip() for m in (invites or []) if m.strip()]
    if invites and not ctx.confirm(f"Je crée « {titre} » le {_fmt(start)} et j'envoie une invitation à {', '.join(invites)}. Je confirme ?"):
        return "Création annulée par l'utilisateur."
    body = {
        "summary": titre, "location": lieu, "description": description,
        "start": {"dateTime": start.isoformat()}, "end": {"dateTime": end.isoformat()},
        "attendees": [{"email": m} for m in invites],
    }
    ev = svc(ctx, "calendar").events().insert(calendarId="primary", body=body, sendUpdates="all" if invites else "none").execute()
    return f"Événement créé : {titre}, {_fmt(start)} → {end.strftime('%H:%M')}  [id={ev['id']}]"


def agenda_supprimer(ctx, event_id, titre=""):
    if not ctx.confirm(f"Je supprime l'événement {titre or event_id} de l'agenda. Je confirme ?"):
        return "Suppression annulée."
    svc(ctx, "calendar").events().delete(calendarId="primary", eventId=event_id).execute()
    return "Événement supprimé."


# ============================================================ TÂCHES
def taches_lister(ctx, inclure_terminees=False):
    s = svc(ctx, "tasks")
    out = []
    for lst in s.tasklists().list(maxResults=20).execute().get("items", []):
        tasks = s.tasks().list(tasklist=lst["id"], showCompleted=bool(inclure_terminees),
                               showHidden=bool(inclure_terminees), maxResults=100).execute().get("items", [])
        if not tasks:
            continue
        out.append(f"Liste « {lst['title']} » [liste_id={lst['id']}] :")
        for t in tasks:
            due = f" (échéance {t['due'][:10]})" if t.get("due") else ""
            fait = " ✓" if t.get("status") == "completed" else ""
            out.append(f"  - {t.get('title', '')}{due}{fait}  [id={t['id']}]")
    return "\n".join(out) or "Aucune tâche en cours."


def taches_ajouter(ctx, titre, notes="", echeance="", liste_id="@default"):
    body = {"title": titre, "notes": notes}
    if echeance:
        body["due"] = echeance[:10] + "T00:00:00.000Z"
    svc(ctx, "tasks").tasks().insert(tasklist=liste_id or "@default", body=body).execute()
    return f"Tâche ajoutée : {titre}" + (f" (pour le {echeance[:10]})" if echeance else "")


def taches_terminer(ctx, task_id, liste_id="@default"):
    svc(ctx, "tasks").tasks().patch(tasklist=liste_id or "@default", task=task_id, body={"status": "completed"}).execute()
    return "Tâche cochée."


# ============================================================ GMAIL
def _header(msg, name):
    for h in msg.get("payload", {}).get("headers", []):
        if h["name"].lower() == name.lower():
            return h["value"]
    return ""


def _body_text(payload):
    """Extrait le texte d'un mail (préférence texte brut, sinon HTML nettoyé)."""
    plain, html = [], []

    def walk(p):
        mime = p.get("mimeType", "")
        data = p.get("body", {}).get("data")
        if data:
            txt = base64.urlsafe_b64decode(data + "==").decode("utf-8", errors="replace")
            (plain if mime == "text/plain" else html if mime == "text/html" else []).append(txt)
        for sub in p.get("parts", []) or []:
            walk(sub)

    walk(payload)
    if plain:
        return "\n".join(plain)
    text = re.sub(r"(?is)<(script|style).*?</\1>", " ", "\n".join(html))
    text = re.sub(r"(?i)<br\s*/?>|</p>|</div>", "\n", text)
    return unescape(re.sub(r"<[^>]+>", " ", text))


def gmail_chercher(ctx, requete="is:unread in:inbox", max_resultats=10):
    g = svc(ctx, "gmail").users()
    ids = g.messages().list(userId="me", q=requete, maxResults=min(int(max_resultats), 25)).execute().get("messages", [])
    if not ids:
        return "Aucun e-mail ne correspond."
    out = []
    for m in ids:
        msg = g.messages().get(userId="me", id=m["id"], format="metadata", metadataHeaders=["From", "Subject", "Date"]).execute()
        out.append(f"- De : {_header(msg, 'From')} | Objet : {_header(msg, 'Subject')} | {_header(msg, 'Date')[:22]}\n"
                   f"  Aperçu : {unescape(msg.get('snippet', ''))[:160]}  [id={m['id']}]")
    return "\n".join(out)


def gmail_lire(ctx, message_id, marquer_lu=True):
    g = svc(ctx, "gmail").users()
    msg = g.messages().get(userId="me", id=message_id, format="full").execute()
    if marquer_lu:
        g.messages().modify(userId="me", id=message_id, body={"removeLabelIds": ["UNREAD"]}).execute()
    body = re.sub(r"\n{3,}", "\n\n", _body_text(msg["payload"])).strip()
    return (f"De : {_header(msg, 'From')}\nÀ : {_header(msg, 'To')}\nObjet : {_header(msg, 'Subject')}\n"
            f"Date : {_header(msg, 'Date')}\n\n{body[:8000]}")


def _build_mail(ctx, destinataire, sujet, corps, cc="", repondre_a=""):
    mime = MIMEText(corps, "plain", "utf-8")
    mime["To"] = destinataire
    mime["Subject"] = sujet
    if cc:
        mime["Cc"] = cc
    body = {}
    if repondre_a:
        orig = svc(ctx, "gmail").users().messages().get(
            userId="me", id=repondre_a, format="metadata", metadataHeaders=["Message-ID", "Subject"]).execute()
        mid = _header(orig, "Message-ID")
        if mid:
            mime["In-Reply-To"] = mid
            mime["References"] = mid
        body["threadId"] = orig["threadId"]
    body["raw"] = base64.urlsafe_b64encode(mime.as_bytes()).decode()
    return body


def gmail_brouillon(ctx, destinataire, sujet, corps, cc="", repondre_a=""):
    msg = _build_mail(ctx, destinataire, sujet, corps, cc, repondre_a)
    svc(ctx, "gmail").users().drafts().create(userId="me", body={"message": msg}).execute()
    return f"Brouillon enregistré dans Gmail pour {destinataire} (objet : {sujet})."


def gmail_envoyer(ctx, destinataire, sujet, corps, cc="", repondre_a=""):
    apercu = corps if len(corps) < 300 else corps[:300] + "…"
    if not ctx.confirm(f"J'envoie à {destinataire} un e-mail ayant pour objet « {sujet} ». Contenu : {apercu}. Je confirme l'envoi ?"):
        return "Envoi annulé par l'utilisateur. Propose plutôt d'en faire un brouillon."
    msg = _build_mail(ctx, destinataire, sujet, corps, cc, repondre_a)
    svc(ctx, "gmail").users().messages().send(userId="me", body=msg).execute()
    return f"E-mail envoyé à {destinataire}."


# ============================================================ CATALOGUE
def tools(_t):
    S = {"type": "string"}
    I = {"type": "integer"}
    B = {"type": "boolean"}
    return [
        _t(agenda_lister, "Liste les événements Google Agenda. debut = date 'AAAA-MM-JJ' (défaut : aujourd'hui), jours = nombre de jours à couvrir.",
           {"debut": S, "jours": I}),
        _t(agenda_creer, "Crée un événement Google Agenda. debut au format 'AAAA-MM-JJTHH:MM' (heure locale). invites = liste d'e-mails (optionnel).",
           {"titre": S, "debut": S, "duree_minutes": I, "lieu": S, "description": S, "invites": {"type": "array", "items": S}},
           ["titre", "debut"]),
        _t(agenda_supprimer, "Supprime un événement de l'agenda (id obtenu via agenda_lister). Confirmation demandée.",
           {"event_id": S, "titre": S}, ["event_id"]),
        _t(taches_lister, "Liste les tâches Google Tasks en cours (toutes les listes).", {"inclure_terminees": B}),
        _t(taches_ajouter, "Ajoute une tâche dans Google Tasks. echeance optionnelle 'AAAA-MM-JJ'.",
           {"titre": S, "notes": S, "echeance": S, "liste_id": S}, ["titre"]),
        _t(taches_terminer, "Coche une tâche comme terminée (id et liste_id obtenus via taches_lister).",
           {"task_id": S, "liste_id": S}, ["task_id"]),
        _t(gmail_chercher, "Cherche des e-mails Gmail avec la syntaxe de recherche Gmail (ex : 'is:unread in:inbox', "
           "'from:dupont newer_than:7d', 'subject:facture'). Renvoie expéditeur, objet, aperçu et id.",
           {"requete": S, "max_resultats": I}),
        _t(gmail_lire, "Lit le contenu complet d'un e-mail (id obtenu via gmail_chercher) et le marque comme lu.",
           {"message_id": S, "marquer_lu": B}, ["message_id"]),
        _t(gmail_brouillon, "Prépare un e-mail en brouillon dans Gmail sans l'envoyer. repondre_a = id du mail auquel on répond (optionnel).",
           {"destinataire": S, "sujet": S, "corps": S, "cc": S, "repondre_a": S}, ["destinataire", "sujet", "corps"]),
        _t(gmail_envoyer, "Envoie un e-mail depuis Gmail (confirmation obligatoire de l'utilisateur). repondre_a = id du mail d'origine pour une réponse.",
           {"destinataire": S, "sujet": S, "corps": S, "cc": S, "repondre_a": S}, ["destinataire", "sujet", "corps"]),
    ]
