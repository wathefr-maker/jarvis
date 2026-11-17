# J.A.R.V.I.S. propulsé par Claude

Le « cerveau » de JARVIS, c'est Claude. Ce programme lui donne un corps :

| Partie du corps | Ce qui la fait fonctionner |
|---|---|
| 🧠 Cerveau | Claude (API Anthropic) avec sa personnalité JARVIS |
| 👂 Oreilles | Ton micro + Whisper (transcription en local) + mot d'activation « Jarvis » |
| 🗣️ Voix | Voix neurale française (edge-tts), avec une voix hors-ligne en secours |
| ✋ Mains | Il ouvre des applis et des sites, lance des commandes, écrit des fichiers, contrôle la musique, tape au clavier et pilote ta maison connectée |
| 👁️ Yeux | Il fait une capture de ton écran et « voit » ce que tu regardes |
| 🌐 Savoir | Il fait des recherches web en direct : météo, actu, scores, prix |
| 💾 Mémoire | Il retient ce qu'il apprend sur toi d'une session à l'autre |
| 🖥️ HUD | L'interface Iron Man sur http://localhost:7777 |

## 1. Ce qu'il te faut

- **Python 3.10 ou plus récent** : https://python.org. Sur Windows, coche **« Add Python to PATH »** pendant l'installation.
- **Une clé API Claude** : https://console.anthropic.com → *API Keys* → *Create Key*.
  ⚠️ L'API se paie à l'usage et à part de l'abonnement Claude.ai. Il faut ajouter quelques euros de crédit dans *Billing*. Une conversation normale coûte quelques centimes.
- Un micro et des haut-parleurs.

## 2. Installation (une seule fois)

**Windows** : double-clique sur `installer_windows.bat`. Le fichier `.env` s'ouvre à la fin : colle ta clé après `ANTHROPIC_API_KEY=` puis enregistre.

**Mac / Linux** :
```bash
chmod +x installer_mac_linux.sh lancer_mac_linux.sh
./installer_mac_linux.sh
```
Ouvre ensuite `.env` et colle ta clé.

Au premier lancement, Whisper télécharge son modèle (environ 500 Mo pour la taille `small`).

## 3. Lancer JARVIS

- **Windows** : `lancer_windows.bat`
- **Mac / Linux** : `./lancer_mac_linux.sh`

Le HUD s'ouvre dans ton navigateur et JARVIS te salue.

Options utiles :
- `--sans-micro` : clavier et HUD seulement
- `--muet` : pas de voix
- `--sans-hud` : pas d'interface

Sur Mac, autorise le Terminal dans *Réglages → Confidentialité* pour le **Micro**, l'**Enregistrement de l'écran** (pour que JARVIS voie l'écran) et l'**Accessibilité** (pour le clavier et les touches média).

## 4. Lui parler

Commence ta phrase par **« Jarvis »**. Après sa réponse, tu as 8 secondes pour enchaîner sans redire son nom.

Exemples :
- « Jarvis, quel temps fera-t-il demain à Lyon ? »
- « Jarvis, ouvre Spotify » puis « mets pause » puis « monte le son »
- « Jarvis, regarde mon écran : pourquoi j'ai cette erreur ? »
- « Jarvis, mets un minuteur de 10 minutes pour les pâtes »
- « Jarvis, état du système »
- « Jarvis, note que je dois appeler le garagiste »
- « Jarvis, retiens que mon anniversaire est le 3 mars »
- « Jarvis, combien de fichiers dans mon dossier Téléchargements ? »
- « Jarvis, éteins la lumière du salon » (si Home Assistant est configuré)
- « Jarvis, nouvelle conversation » : il oublie la conversation en cours, mais garde ses souvenirs
- « Jarvis, au revoir » : il s'éteint

Tu peux aussi taper dans la console ou dans la barre du HUD.

## 5. Sécurité

- Avant d'**exécuter une commande** ou d'**écrire un fichier**, JARVIS demande toujours ta confirmation. Réponds « oui » ou « non ».
- Pour lui retirer complètement l'accès au terminal : `JARVIS_AUTORISER_COMMANDES=non` dans `.env`.
- Le HUD n'est accessible que depuis ton ordinateur (127.0.0.1).
- Ne partage jamais ton fichier `.env` : il contient ta clé.

## 6. Maison connectée (optionnel)

Si tu as **Home Assistant**, renseigne `HOME_ASSISTANT_URL` (par exemple `http://192.168.1.20:8123`) et un jeton longue durée (*Profil → Sécurité*) dans `.env`. JARVIS peut alors piloter les lumières, les prises, le chauffage, les volets et les enceintes.

## 7. Personnaliser

Tout se règle dans `.env` : ton nom, la voix, le modèle (`claude-opus-5-5` pour plus d'intelligence, `claude-haiku-5-5` pour plus de vitesse) et le mot d'activation.
La personnalité se modifie dans `jarvis/brain.py` (le texte `PERSONA`).
Pour **ajouter un pouvoir**, écris une fonction dans `jarvis/tools.py` et ajoute-la à la liste `TOOLS`. Claude comprendra seul quand l'utiliser.

## 8. En cas de problème

| Symptôme | Solution |
|---|---|
| `pyaudio` refuse de s'installer | Windows : `pip install pipwin` puis `pipwin install pyaudio`. Mac : `brew install portaudio`. |
| Il ne m'entend pas | Vérifie le micro par défaut du système. Parle après le message « J'écoute ». Lance-le dans une pièce calme pour le calibrage. |
| Il comprend mal « Jarvis » | Passe `JARVIS_WHISPER=medium`, ou ajoute des variantes dans `JARVIS_MOTS_ACTIVATION`. |
| Réponses lentes | Prends `claude-haiku-5-5` et `JARVIS_WHISPER=base`. |
| « clé refusée » | Vérifie la clé dans `.env` et ton crédit sur console.anthropic.com. |

## Structure

```
jarvis_main.py      chef d'orchestre
jarvis/brain.py     cerveau (Claude, personnalité, boucle d'outils)
jarvis/ears.py      oreilles (micro, Whisper, mot d'activation)
jarvis/voice.py     voix
jarvis/tools.py     mains et yeux (tous les pouvoirs)
jarvis/memory.py    mémoire long terme  → data/memoire.json
jarvis/hud.py/.html interface Iron Man
```
