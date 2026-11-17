"""Le cerveau de JARVIS : Claude, avec ses outils, la recherche web et la mémoire."""
import platform
from datetime import datetime

import anthropic

from . import tools as T

PERSONA = """Tu es J.A.R.V.I.S. (Just A Rather Very Intelligent System), l'assistant personnel de {user}, \
inspiré de l'IA de Tony Stark. Tu fonctionnes grâce à Claude, le modèle d'Anthropic.

Personnalité : flegme britannique, élégance, humour pince-sans-rire discret, loyauté totale. \
Tu appelles l'utilisateur « {user} ». Tu es efficace avant tout.

Règles de réponse — tes réponses sont LUES À VOIX HAUTE :
- Réponds en français, en 1 à 3 phrases courtes, sauf si on te demande explicitement du détail.
- Jamais de markdown, de listes à puces, d'émojis ni d'URL dans ce que tu dis.
- Les nombres et heures s'écrivent comme on les prononce naturellement.
- Agis directement avec tes outils plutôt que d'expliquer ce que tu pourrais faire. \
Pour une info actuelle (météo, actualité, score, prix), utilise la recherche web.
- Si un outil échoue, dis-le simplement et propose une alternative.
- E-mails : résume à l'oral (expéditeur et sujet en une phrase chacun), ne lis jamais un mail en entier sauf demande. \
Pour écrire un mail, rédige-le proprement au nom de l'utilisateur ; en cas de doute sur le destinataire ou le ton, fais un brouillon.
- Agenda et tâches : donne les heures naturellement (« à quatorze heures »). Pour « demain », « lundi prochain », calcule la date à partir de la date du jour.
- Quand l'utilisateur révèle une info durable sur lui (prénom, goûts, projets, proches), mémorise-la avec l'outil remember, sans l'annoncer lourdement.

Contexte : nous sommes le {now}. Système : {os}.
Ce que tu sais de {user} :
{memories}"""


class Brain:
    def __init__(self, cfg, ctx, memory):
        self.cfg = cfg
        self.ctx = ctx
        self.memory = memory
        self.client = anthropic.Anthropic(api_key=cfg.api_key)
        self.history = []

    def _system(self):
        return PERSONA.format(
            user=self.cfg.user_name,
            now=T.get_datetime(None),
            os=f"{platform.system()} {platform.release()}",
            memories=self.memory.as_text(),
        )

    def _trim(self):
        # On coupe toujours sur un message utilisateur « texte » pour ne jamais séparer
        # un appel d'outil de son résultat.
        starts = [i for i, m in enumerate(self.history) if m["role"] == "user" and isinstance(m["content"], str)]
        if len(starts) > self.cfg.max_turns:
            self.history = self.history[starts[-self.cfg.max_turns]:]

    def reset(self):
        self.history = []

    def think(self, text, on_tool=None):
        snapshot = list(self.history)
        self.history.append({"role": "user", "content": text})
        tools = T.schemas(self.cfg) + [{"type": "web_search_20250305", "name": "web_search", "max_uses": 3}]
        try:
            resp = None
            for _ in range(15):
                resp = self.client.messages.create(
                    model=self.cfg.model,
                    max_tokens=1500,
                    system=self._system(),
                    tools=tools,
                    messages=self.history,
                )
                self.history.append({"role": "assistant", "content": resp.content})
                if resp.stop_reason == "pause_turn":  # recherche web longue : on relance
                    continue
                if resp.stop_reason != "tool_use":
                    break
                results = []
                for block in resp.content:
                    if block.type == "tool_use":
                        if on_tool:
                            on_tool(block.name, block.input)
                        out = T.run(block.name, block.input, self.ctx)
                        results.append({"type": "tool_result", "tool_use_id": block.id, "content": out})
                self.history.append({"role": "user", "content": results})
            answer = "".join(b.text for b in resp.content if b.type == "text").strip()
            self._trim()
            return answer or "C'est fait, " + self.cfg.user_name + "."
        except anthropic.AuthenticationError:
            self.history = snapshot
            return "Ma clé d'accès est refusée. Vérifiez la clé API dans le fichier point env."
        except anthropic.APIConnectionError:
            self.history = snapshot
            return "Je n'arrive pas à joindre mes serveurs. Vérifiez la connexion internet."
        except anthropic.APIStatusError as e:
            self.history = snapshot
            return f"Mes serveurs ont renvoyé une erreur {e.status_code}. Réessayons dans un instant."
        except Exception as e:
            self.history = snapshot
            return f"Une erreur inattendue s'est produite : {e}"
