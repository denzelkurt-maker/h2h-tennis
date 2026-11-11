#!/usr/bin/env python3
"""Collecteur H2H Tennis (tennis masculin : ATP, Challenger, ITF).

Lancé chaque nuit par GitHub Actions (.github/workflows/collecte.yml).
Construit les fichiers de données de l'appli dans le dossier donnees/
et un rapport lisible dans rapport/.

Sources et licences :
  - Archive Jeff Sackmann (tennis_atp), copie Aneeshers/tennis-sackmann-archive,
    CC BY-NC-SA 4.0 : historique jusqu'à juin 2026.
  - Valuebetennis, fichiers par saison, CC BY 4.0 : matchs récents, chaque jour.
  - Kaggle dissfya/atp-tennis-2000-2023daily-pull : scores du circuit ATP
    principal (facultatif, clé KAGGLE_API_TOKEN, licence à confirmer).
  - Wikipédia (en.wikipedia.org), CC BY-SA 4.0 : tableaux de double.
  - TennisMyLife (stats.tennismylife.org), usage personnel et non commercial,
    redistribution des CSV interdite : scores complets et statistiques ATP et
    Challenger depuis la fin de l'archive. Ces données ne sont JAMAIS écrites en
    clair : elles sont chiffrées (AES-256-GCM, clé dérivée du secret CODE_TML)
    dans donnees/tml-AAAA.json. Sans le secret, l'étape est sautée.
  - Cito API (citoapi.com), clé CITO_API_KEY, plan gratuit (500 appels / 30 jours) :
    résultats ATP, Challenger (qualifications comprises) et ITF, statistiques, classement
    ATP complet. Données chiffrées comme TennisMyLife (etat/cito-*.json, donnees/cito-*.json).

Aucune clé n'est écrite dans ce fichier. Python 3.10+, bibliothèque standard,
plus « cryptography » pour le chiffrement (installé par le workflow).
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import gzip
import html
import io
import json
import os
import re
import subprocess
import sys
import tempfile
import time
import traceback
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from collections import Counter, defaultdict

VERSION = "1.9.0"
VERSION_COPIE = 2   # copie compacte de l'archive : 2 = avec statistiques et classements
PARSEUR_WIKI = 2   # une page lue par une version antérieure du lecteur est relue

# ---------------------------------------------------------------- périmètre
DEBUT_ATP = 2011          # ATP et Challenger, simple : 15 ans
DEBUT_ITF = 2016          # ITF masculin, simple : 10 ans
DEBUT_DOUBLE = 2021       # doubles ATP et Challenger : 5 ans

SACKMANN_DEPOT = "https://github.com/Aneeshers/tennis-sackmann-archive"
SACKMANN_BRANCHE = "main"
VBT_URL = "https://www.valuebetennis.com/datasets/valuebetennis-matchs-{annee}.csv"
VBT_PREMIERE_SAISON = 2026  # l'archive Sackmann couvre tout ce qui précède
KAGGLE_JEU = "dissfya/atp-tennis-2000-2023daily-pull"
WIKI_API = "https://en.wikipedia.org/w/api.php"
# Wikipédia exige un agent identifiable avec un moyen de contact (adresse du dépôt)
AGENT = ("H2H-Tennis-perso/1.0 (https://github.com/"
         + os.environ.get("GITHUB_REPOSITORY", "denzelkurt-maker/h2h-tennis")
         + "; collecteur personnel non commercial) python-urllib")
BUDGET_WIKI = 500   # pages de double lues au plus par passage (rattrapage étalé)
TML_URLS = ["https://stats.tennismylife.org/data/{annee}.csv",
            "https://stats.tennismylife.org/data/{annee}_challenger.csv",
            "https://stats.tennismylife.org/data/atp_quali/{annee}_atp_quali.csv"]
TML_ITERATIONS = 600_000   # dérivation de clé volontairement lente (PBKDF2-SHA256)

# Présentation du dépôt, réécrite à chaque passage (attribution exigée par les licences)
README = "# H2H Tennis\n\nApplication personnelle et non commerciale de statistiques de tennis masculin (ATP, Challenger, ITF) : face-à-face, fiches joueurs, bilans.\n\n## Fonctionnement\n\n- `collecteur.py` construit chaque nuit les fichiers de `donnees/` à partir des sources ci-dessous (planification : `.github/workflows/collecte.yml`).\n- `rapport/rapport.md` décrit la dernière collecte (chiffres, alertes, erreurs).\n- `etat/` conserve une copie compacte de l'historique et le cache des tableaux Wikipédia.\n\n## Sources et licences\n\n| Source | Usage | Licence |\n|---|---|---|\n| Jeff Sackmann, [tennis_atp](https://github.com/JeffSackmann/tennis_atp), via la copie [Aneeshers/tennis-sackmann-archive](https://github.com/Aneeshers/tennis-sackmann-archive) | Historique des matchs, statistiques de match (aces, breaks…), joueurs, classements jusqu'à juin 2026 | [CC BY-NC-SA 4.0](https://creativecommons.org/licenses/by-nc-sa/4.0/) |\n| [Valuebetennis](https://www.valuebetennis.com/en/donnees.htm), « Tennis results and odds since 2021 » | Matchs récents, mis à jour chaque jour | [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/) |\n| [Wikipédia](https://en.wikipedia.org) (anglais), pages de tableaux de double | Doubles ATP et Challenger depuis 2021 ; calendrier des tournois Challenger de la saison (pages « AAAA ATP Challenger Tour ») | [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/) |\n| API publique d'ESPN (tennis ATP) | Programme des matchs de simple ATP à venir et calendrier du circuit ATP, `donnees/programme.json` (noms, heures, tours ; rien d'autre n'est repris) | API publique non officielle, pas de licence indiquée |\n| [Kaggle, dissfya/atp-tennis-2000-2023daily-pull](https://www.kaggle.com/datasets/dissfya/atp-tennis-2000-2023daily-pull) | Scores, catégorie 250/500, intérieur ou extérieur, classement au moment du match (circuit principal) | CC0 (domaine public) |\n| [TennisMyLife](https://stats.tennismylife.org/tennis-match-database) | Scores complets et statistiques ATP et Challenger depuis juin 2026, **fichiers `donnees/tml-*.json` chiffrés** (usage personnel du propriétaire ; la redistribution des CSV n'est pas autorisée) | Usage personnel et non commercial |\n| [Wikidata](https://www.wikidata.org) et [Wikimedia Commons](https://commons.wikimedia.org) | Photos des joueurs (licences libres, auteur et licence indiqués pour chaque photo dans `donnees/photos.json`), poids, taille | CC0 (Wikidata) ; licence de chaque photo |\n| [Wikimedia Commons, Data:ATP singles ranking.tab](https://commons.wikimedia.org/wiki/Data:ATP_singles_ranking.tab) | Classement ATP en simple complet (rangs, points, âge, tournois joués), `donnees/classement.json` ; le collecteur vérifie que la licence de la table est libre avant de l'utiliser | Licence indiquée sur la table (contrôlée à chaque collecte) |\n| [Cito API](https://citoapi.com) | Résultats ATP, Challenger (qualifications comprises) et ITF, statistiques de match, classement ATP complet, depuis juin 2026, **fichiers `donnees/cito-*.json` et `etat/cito-*.json` chiffrés** (redistribution interdite) | Usage dans sa propre application |\n\nLes fichiers de `donnees/` (hors `tml-*.json` et `cito-*.json`, chiffrés et non partagés) sont des œuvres dérivées de ces sources et sont partagés dans les mêmes conditions : usage non commercial, attribution, partage dans les mêmes conditions (CC BY-NC-SA 4.0).\n\nAucun lien avec l'ATP, l'ITF ou les tournois cités. Les noms de tournois sont utilisés à titre descriptif.\n"

RACINE = os.path.dirname(os.path.abspath(__file__))
DONNEES = os.path.join(RACINE, "donnees")
ETAT = os.path.join(RACINE, "etat")
RAPPORT = os.path.join(RACINE, "rapport")

# Codes de niveau utilisés par l'appli
# G Grand Chelem, M Masters 1000, A ATP 250/500 (détail dans « categorie »), F Finales ATP,
# N NextGen Finals, D Coupe Davis,
# O Jeux olympiques, C Challenger, I15 / I25 / I ITF masculin
NIVEAUX = {"G": "Grand Chelem", "M": "Masters 1000", "A": "ATP 250/500",
           "F": "Finales ATP", "D": "Coupe Davis", "O": "Jeux olympiques",
           "C": "Challenger", "I15": "ITF M15", "I25": "ITF M25", "I": "ITF",
           "N": "NextGen Finals"}

# Drapeaux d'un match (somme de bits)
COMPLET, ABANDON, FORFAIT, SRC_VBT, SRC_KAGGLE, SRC_WIKI, SRC_TML = 1, 2, 4, 8, 16, 32, 64  # 128 : Cito

# Statistiques d'un match (fichiers stats-simple-*.json et complément chiffré),
# même ordre que l'archive Sackmann ; « g_ » = gagnant, « p_ » = perdant
COLONNES_STATS = ["minutes", "ace", "df", "svpt", "1stIn", "1stWon", "2ndWon", "SvGms", "bpSaved", "bpFaced"]
CHAMPS_STATS = (["minutes"] + [f"w_{x}" for x in COLONNES_STATS[1:]] + [f"l_{x}" for x in COLONNES_STATS[1:]]
                + ["winner_rank", "winner_rank_points", "loser_rank", "loser_rank_points"])
NOMS_STATS = (["minutes"] + [f"g_{x}" for x in COLONNES_STATS[1:]] + [f"p_{x}" for x in COLONNES_STATS[1:]]
              + ["g_rang", "g_points", "p_rang", "p_points"])


def stats_ligne(r):
    """Statistiques d'une ligne au format Sackmann / TennisMyLife, ou None si vide."""
    vals = []
    for champ in CHAMPS_STATS:
        v = (r.get(champ) or "").strip()
        try:
            vals.append(int(float(v)) if v not in ("", "NA", "nan") else None)
        except ValueError:
            vals.append(None)
    return vals if any(v is not None for v in vals) else None


def niveau_par_nom(niveau, nom):
    """Corrige les classements erronés de l'archive (ex. Finales ATP 2023 en « A »,
    NextGen Finals en « F ») d'après le nom du tournoi."""
    n = (nom or "").lower()
    if "next gen" in n or "nextgen" in n:
        return "N"
    if "olympic" in n and niveau in ("A", "O"):
        return "O"
    if niveau in ("A", "F", "M") and (re.search(r"\b(atp|tour|nitto|barclays)\b.*\bfinals\b", n)
                                     or "masters cup" in n or n.strip() == "atp finals"):
        return "F"
    return niveau


def lundi(jour):
    d = dt.date.fromisoformat(jour)
    return (d - dt.timedelta(days=d.weekday())).isoformat()


class Journal:
    """Rassemble ce qui sera écrit dans le rapport."""

    def __init__(self):
        self.lignes, self.alertes, self.chiffres = [], [], {}
        self.t0 = time.time()

    def info(self, texte):
        horodate = f"{time.time() - self.t0:6.1f}s"
        self.lignes.append(f"{horodate}  {texte}")
        print(horodate, texte, flush=True)

    def alerte(self, texte):
        self.alertes.append(texte)
        self.info("ALERTE " + texte)


J = Journal()


# ---------------------------------------------------------------- outils
def lire_json(chemin, defaut):
    try:
        with open(chemin, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return defaut


def lire_texte(chemin):
    try:
        with open(chemin, encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        return None


def ecrire_json(chemin, objet, compact=True):
    os.makedirs(os.path.dirname(chemin), exist_ok=True)
    tmp = chemin + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        if compact:
            json.dump(objet, f, ensure_ascii=False, separators=(",", ":"))
        else:
            json.dump(objet, f, ensure_ascii=False, indent=1)
    os.replace(tmp, chemin)


def telecharger(url, entetes=None, essais=5, delai=5):
    req = urllib.request.Request(url, headers={"User-Agent": AGENT, **(entetes or {})})
    derniere = None
    for i in range(essais):
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                data = r.read()
                if r.headers.get("Content-Encoding") == "gzip":
                    data = gzip.decompress(data)
                return data
        except urllib.error.HTTPError as e:
            derniere = e
            if e.code in (429, 503):
                # le serveur demande de ralentir : on respecte son délai
                try:
                    attente = int(e.headers.get("Retry-After", "0"))
                except ValueError:
                    attente = 0
                attente = max(attente, 30 * (i + 1))
                J.info(f"Serveur saturé ({e.code}), pause de {attente} s")
                time.sleep(min(attente, 300))
            elif e.code in (403, 404):
                break
            else:
                time.sleep(delai * (i + 1))
        except Exception as e:  # noqa: BLE001
            derniere = e
            time.sleep(delai * (i + 1))
    raise RuntimeError(f"téléchargement impossible : {url[:200]} ({derniere})")


def cle_nom(nom):
    """Clé de rapprochement : sans accents, minuscules, mots triés."""
    n = unicodedata.normalize("NFKD", nom or "").encode("ascii", "ignore").decode().lower()
    n = re.sub(r"[^a-z ]", " ", n.replace("-", " ").replace("'", ""))
    return " ".join(sorted(n.split()))


def iso(d8):
    """'20260525' -> '2026-05-25'."""
    d8 = (d8 or "").strip()
    return f"{d8[:4]}-{d8[4:6]}-{d8[6:8]}" if len(d8) == 8 else None


def jours(a, b):
    return abs((dt.date.fromisoformat(a) - dt.date.fromisoformat(b)).days)


# ---------------------------------------------------------------- scores
RE_SET = re.compile(r"^(\d{1,2})-(\d{1,2})(?:\((\d+)\))?$")


def analyser_score(score, best_of):
    """Renvoie (score normalisé, drapeaux). Le score est vu du vainqueur."""
    s = (score or "").strip()
    if not s:
        return "", 0
    bas = s.lower()
    if bas in ("w/o", "wo", "walkover") or "w/o" in bas:
        return "w/o", FORFAIT
    abandon = bool(re.search(r"\b(ret|ret\.|rtd|abd|def|disq)\b", bas))
    sets = [x for x in re.split(r"\s+", re.sub(r"(?i)\b(ret\.?|rtd|abd|def\.?|disq\.?)", "", s)) if x]
    gagnes = perdus = 0
    for x in sets:
        m = RE_SET.match(x.strip("[]"))
        if not m:
            return s, (ABANDON if abandon else 0)
        a, b = int(m.group(1)), int(m.group(2))
        fini = (max(a, b) >= 6 and abs(a - b) >= 2) or {a, b} == {7, 6} or \
               (x.startswith("[") or max(a, b) >= 10 and abs(a - b) >= 2)
        if fini:
            gagnes += a > b
            perdus += b > a
    besoin = 3 if best_of == 5 else 2
    drapeaux = 0
    if abandon:
        drapeaux |= ABANDON
    elif gagnes == besoin and perdus < besoin:
        drapeaux |= COMPLET
    return " ".join(sets), drapeaux


def inverser_score(score):
    """'6-4 3-6 7-6(5)' vu du joueur 1 -> vu du joueur 2."""
    out = []
    for x in score.split():
        m = RE_SET.match(x)
        if m:
            tb = f"({m.group(3)})" if m.group(3) else ""
            out.append(f"{m.group(2)}-{m.group(1)}{tb}")
        else:
            out.append(x)
    return " ".join(out)


# ---------------------------------------------------------------- tours
def tour_relatif(tour, taille_tableau):
    """Convertit R128/R64/R32/R16 en 1T/2T/... selon la taille du tableau."""
    if tour in ("QF", "SF", "F", "RR", "BR", "Q1", "Q2", "Q3", "Q4"):
        return tour
    m = re.match(r"R(\d+)$", tour or "")
    if not m:
        return tour or "?"
    n = int(m.group(1))
    try:
        taille = int(taille_tableau)
    except (TypeError, ValueError):
        taille = n
    premier = 1
    while premier < taille:
        premier *= 2
    k = 1
    while premier > n and premier > 8:
        premier //= 2
        k += 1
    return "QF" if n == 8 else f"{k}T"


VBT_TOURS = {"4": "1T", "5": "2T", "6": "3T", "7": "4T", "8": "RR", "9": "QF",
             "10": "SF", "12": "F", "1": "Q1", "2": "Q2"}


# ---------------------------------------------------------------- base
class Base:
    """Joueurs, tournois et matchs, en mémoire."""

    def __init__(self):
        self.joueurs = {}            # id -> dict(nom, pays, main, taille, naissance)
        self.par_cle = defaultdict(list)  # clé de nom -> [ids]
        self.tournois = {}           # id -> dict(nom, niveau, surface, salle, debut, bo, annee)
        self.simples = []            # dicts
        self.doubles = []
        self.classements = {}        # annee -> {id: rang}
        self.activite = {}           # id -> date du dernier tournoi (Sackmann)
        self.recents = {}            # id -> [lundi, rang, points, source] : dernier classement officiel connu

    def ajouter_joueur(self, pid, nom, pays=None, main=None, taille=None, naissance=None):
        if pid in self.joueurs:
            return
        self.joueurs[pid] = {"nom": nom, "pays": pays, "main": main, "taille": taille,
                             "naissance": naissance}
        self.par_cle[cle_nom(nom)].append(pid)


# ---------------------------------------------------------------- Sackmann
FICHIERS_SACKMANN = (
    [("atp_matches_{}.csv", a, "principal") for a in range(DEBUT_ATP, 2027)]
    + [("atp_matches_qual_chall_{}.csv", a, "chall") for a in range(DEBUT_ATP, 2027)]
    + [("atp_matches_futures_{}.csv", a, "itf") for a in range(DEBUT_ITF, 2027)]
)


def obtenir_sackmann(dossier_local=None):
    """Renvoie le dossier contenant les CSV ATP de l'archive."""
    if dossier_local:
        return dossier_local
    cible = tempfile.mkdtemp(prefix="sackmann_")
    J.info("Archive Sackmann : clonage partiel du dossier atp")
    cmd = ["git", "clone", "-q", "--depth", "1", "--filter=blob:none", "--sparse",
           "-b", SACKMANN_BRANCHE, SACKMANN_DEPOT, cible]
    subprocess.run(cmd, check=True)
    subprocess.run(["git", "-C", cible, "sparse-checkout", "set", "atp"], check=True)
    return os.path.join(cible, "atp")


def niveau_sackmann(lvl, nom, fichier):
    if fichier == "itf":
        if lvl in ("15", "25"):
            return "I" + lvl
        m = re.match(r"M(15|25)\b", nom or "")
        return "I" + m.group(1) if m else "I"
    if lvl == "C":
        return "C"
    return {"G": "G", "M": "M", "A": "A", "F": "F", "D": "D", "O": "O"}.get(lvl, "A")


def fusions_sackmann(dossier, joueurs):
    """L'archive contient des doublons (même nom, même date de naissance, deux identifiants).
    Renvoie {id_doublon: id_retenu}, en gardant l'identifiant le plus présent dans les matchs."""
    presence = Counter()
    for modele, annee, _ in FICHIERS_SACKMANN:
        chemin = os.path.join(dossier, modele.format(annee))
        if os.path.exists(chemin):
            with open(chemin, encoding="utf-8", errors="replace") as f:
                for r in csv.DictReader(f):
                    presence[r["winner_id"]] += 1
                    presence[r["loser_id"]] += 1
    groupes = defaultdict(list)
    for pid, r in joueurs.items():
        if r.get("dob") and presence[pid]:
            groupes[(cle_nom(f"{r['name_first']} {r['name_last']}"), r["dob"])].append(pid)
    fusion = {}
    for ids in groupes.values():
        if len(ids) > 1:
            def poids(p):
                r = joueurs[p]
                return (presence[p], bool(r.get("height")), r.get("hand") in ("R", "L"), p)
            garde = max(ids, key=poids)
            for p in ids:
                if p != garde:
                    fusion[p] = garde
                    # garder les informations du doublon si le retenu n'en a pas
                    for champ in ("height", "hand", "ioc"):
                        if not joueurs[garde].get(champ) or joueurs[garde].get(champ) == "U":
                            joueurs[garde][champ] = joueurs[p].get(champ)
    return fusion


def charger_sackmann(base, dossier):
    joueurs = {}
    with open(os.path.join(dossier, "atp_players.csv"), encoding="utf-8", errors="replace") as f:
        for r in csv.DictReader(f):
            joueurs[r["player_id"]] = r
    fusion = fusions_sackmann(dossier, joueurs)
    J.chiffres["sackmann_doublons_fusionnes"] = len(fusion)
    vus = set()
    fin = ""
    for modele, annee, genre in FICHIERS_SACKMANN:
        chemin = os.path.join(dossier, modele.format(annee))
        if not os.path.exists(chemin):
            J.alerte(f"Sackmann : fichier absent {modele.format(annee)}")
            continue
        with open(chemin, encoding="utf-8", errors="replace") as f:
            for r in csv.DictReader(f):
                for cote in ("winner_id", "loser_id"):
                    r[cote] = fusion.get(r[cote], r[cote])
                tid = "s" + r["tourney_id"]
                debut = iso(r["tourney_date"])
                if not debut:
                    continue
                fin = max(fin, debut)
                niveau = niveau_par_nom(niveau_sackmann(r["tourney_level"], r["tourney_name"], genre),
                                        r["tourney_name"])
                tour = tour_relatif(r["round"], r["draw_size"])
                # les fichiers qual_chall contiennent aussi les qualifications ATP
                if tid not in base.tournois:
                    surface = (r["surface"] or "").strip() or None
                    base.tournois[tid] = {
                        "nom": r["tourney_name"], "niveau": niveau, "surface": surface,
                        "salle": 1 if surface == "Carpet" else None, "debut": debut,
                        "bo": int(r["best_of"]) if (r["best_of"] or "").isdigit() else 3,
                        "annee": int(debut[:4]),
                        "cat": niveau[1:] if niveau.startswith("I") and len(niveau) > 1 else None}
                for cote in ("winner", "loser"):
                    pid = r[f"{cote}_id"]
                    if pid and ("s" + pid) not in base.joueurs:
                        p = joueurs.get(pid, {})
                        nom = (f"{p.get('name_first', '')} {p.get('name_last', '')}".strip()
                               or r[f"{cote}_name"])
                        taille = p.get("height") or r.get(f"{cote}_ht") or None
                        base.ajouter_joueur(
                            "s" + pid, nom, p.get("ioc") or r.get(f"{cote}_ioc") or None,
                            (p.get("hand") or r.get(f"{cote}_hand") or None),
                            int(float(taille)) if taille else None, iso(p.get("dob")))
                g, p_ = "s" + r["winner_id"], "s" + r["loser_id"]
                cle = (tid, r["match_num"], g, p_)
                if cle in vus:
                    continue
                vus.add(cle)
                bo = base.tournois[tid]["bo"]
                score, drap = analyser_score(r["score"], bo)
                m = {"t": tid, "tour": tour, "g": g, "p": p_, "score": score,
                     "date": None, "dr": drap, "debut": debut}
                st = stats_ligne(r)
                if st:
                    m["st"] = st
                base.simples.append(m)
                for pid in (g, p_):
                    base.activite[pid] = max(base.activite.get(pid, ""), debut)
    for pid, j in base.joueurs.items():
        if j["main"] not in ("R", "L"):
            j["main"] = None
    J.chiffres["sackmann_matchs"] = len(base.simples)
    J.chiffres["sackmann_fin"] = fin
    J.info(f"Sackmann : {len(base.simples)} matchs, {len(base.joueurs)} joueurs, dernier tournoi {fin}")
    return fin


def classements_fin_annee(base, dossier):
    actifs = set(base.joueurs)
    derniers = {}
    for f in ("atp_rankings_10s.csv", "atp_rankings_20s.csv", "atp_rankings_current.csv"):
        chemin = os.path.join(dossier, f)
        if not os.path.exists(chemin):
            continue
        with open(chemin, encoding="utf-8", errors="replace") as fh:
            for r in csv.reader(fh):
                if not r or not r[0].isdigit():
                    continue
                d, rang, pid = r[0], r[1], "s" + r[2]
                annee = int(d[:4])
                if annee < DEBUT_ATP or pid not in actifs:
                    continue
                cur = derniers.get(annee)
                if cur is None or d > cur[0]:
                    derniers[annee] = [d, {}]
                if d == derniers[annee][0]:
                    derniers[annee][1][pid] = int(rang)
    for annee, (d, rangs) in sorted(derniers.items()):
        base.classements[str(annee)] = {"date": iso(d), "rangs": rangs}
    # dernier classement complet publié dans l'archive (tous les joueurs classés)
    chemin = os.path.join(dossier, "atp_rankings_current.csv")
    if os.path.exists(chemin):
        lignes = []
        with open(chemin, encoding="utf-8", errors="replace") as fh:
            for r in csv.reader(fh):
                if r and r[0].isdigit():
                    lignes.append(r)
        if lignes:
            d = max(r[0] for r in lignes)
            for r in lignes:
                if r[0] == d and ("s" + r[2]) in actifs:
                    pts = int(r[3]) if len(r) > 3 and r[3].isdigit() else None
                    base.recents["s" + r[2]] = [iso(d), int(r[1]), pts, "sackmann"]
            J.info(f"Dernier classement complet de l'archive : {iso(d)} ({len(base.recents)} joueurs)")
    J.info("Classements : " + ", ".join(f"{a} ({v['date']})" for a, v in base.classements.items()))


# ---------------------------------------------------------------- Valuebetennis
def niveau_vbt(categorie, tournoi):
    c = (categorie or "").strip()
    if c == "ITF":
        m = re.match(r"M(15|25)\b", tournoi or "")
        return "I" + m.group(1) if m else "I"
    return {"Grand Chelem": "G", "Masters": "M", "Main tour": "A", "Challenger": "C",
            "Coupe Davis / BJK Cup": "D"}.get(c)


SURFACES_VBT = {"dur": ("Hard", 0), "dur intérieur": ("Hard", 1), "terre battue": ("Clay", 0),
                "terre battue intérieur": ("Clay", 1), "gazon": ("Grass", 0),
                "moquette intérieur": ("Carpet", 1), "moquette": ("Carpet", None)}


def charger_vbt(fichiers_locaux=None):
    annee_courante = dt.date.today().year
    lignes = []
    if fichiers_locaux:
        sources = [(f, None) for f in fichiers_locaux]
    else:
        sources = [(None, a) for a in range(VBT_PREMIERE_SAISON, annee_courante + 1)]
    for chemin, annee in sources:
        try:
            if chemin:
                brut = open(chemin, "rb").read()
            else:
                brut = telecharger(VBT_URL.format(annee=annee))
            texte = brut.decode("utf-8-sig")
            n = 0
            for r in csv.DictReader(io.StringIO(texte), delimiter=";"):
                if r.get("genre") == "atp":
                    lignes.append(r)
                    n += 1
            J.info(f"Valuebetennis {annee or os.path.basename(chemin)} : {n} matchs ATP")
        except Exception as e:  # noqa: BLE001
            J.alerte(f"Valuebetennis {annee} : {e}")
    return lignes


def integrer_vbt(base, lignes, fin_sackmann, etat_corresp):
    """Ajoute les matchs Valuebetennis postérieurs à l'archive Sackmann."""
    import difflib
    # corrections manuelles éventuelles : {"vbt:<id>": "s<id>"} dans etat/fusions.json
    manuelles = lire_json(os.path.join(ETAT, "fusions.json"), {})
    corresp = {}
    etat_corresp["vbt"] = corresp
    seuil_actif = (dt.date.fromisoformat(fin_sackmann) - dt.timedelta(days=3 * 365)).isoformat()
    par_mot = defaultdict(set)
    for pid, j in base.joueurs.items():
        if pid.startswith("s") and base.activite.get(pid, "") >= seuil_actif:
            for mot in cle_nom(j["nom"]).split():
                if len(mot) >= 3:
                    par_mot[mot].add(pid)
    debut_fenetre = (dt.date.fromisoformat(fin_sackmann) - dt.timedelta(days=7)).isoformat()
    # matchs Sackmann récents, pour le dédoublonnage
    recents = defaultdict(list)
    for m in base.simples:
        if m["debut"] >= (dt.date.fromisoformat(fin_sackmann) - dt.timedelta(days=21)).isoformat():
            recents[frozenset((m["g"], m["p"]))].append(m["debut"])
    stats = Counter()
    noms_inconnus = Counter()

    def approchant(nom):
        cle = cle_nom(nom)
        mots = set(cle.split())
        cands = set()
        for mot in mots:
            cands |= par_mot.get(mot, set())
        retenus = []
        for c in cands:
            cm = set(cle_nom(base.joueurs[c]["nom"]).split())
            commun = mots & cm
            inclus = len(commun) >= 2 and (mots <= cm or cm <= mots)
            proche = commun and difflib.SequenceMatcher(None, cle, cle_nom(base.joueurs[c]["nom"])).ratio() >= 0.88
            if inclus or proche:
                retenus.append(c)
        return retenus[0] if len(retenus) == 1 else None

    def joueur(vid, nom):
        if vid in corresp:
            return corresp[vid]
        if "vbt:" + vid in manuelles:
            pid = manuelles["vbt:" + vid]
            stats["noms_corriges_a_la_main"] += 1
        else:
            candidats = [c for c in base.par_cle.get(cle_nom(nom), []) if c.startswith("s")]
            if len(candidats) == 1:
                pid = candidats[0]
                stats["noms_rapproches"] += 1
            elif candidats:
                pid = max(candidats, key=lambda c: base.activite.get(c, ""))
                stats["noms_homonymes_resolus_par_activite"] += 1
                noms_inconnus[nom] += 1
            else:
                pid = approchant(nom)
                if pid:
                    stats["noms_rapproches_orthographe"] += 1
                    if len(J.chiffres.setdefault("exemples_orthographe", [])) < 25:
                        J.chiffres["exemples_orthographe"].append([nom, base.joueurs[pid]["nom"]])
                else:
                    pid = "v" + vid
                    stats["noms_nouveaux"] += 1
        if pid not in base.joueurs:
            base.ajouter_joueur(pid, nom)
        corresp[vid] = pid
        return pid

    for r in lignes:
        jour = (r["date"] or "")[:10]
        if not jour or jour < debut_fenetre:
            stats["avant_fenetre"] += 1
            continue
        if not r["vainqueur_id"]:
            stats["sans_vainqueur"] += 1
            continue
        niveau = niveau_vbt(r["categorie"], r["tournoi"])
        if niveau is None:
            stats["categorie_inconnue"] += 1
            continue
        niveau = niveau_par_nom(niveau, r["tournoi"])
        if niveau == "D":
            stats["coupe_davis_ignoree"] += 1
            continue
        tour = VBT_TOURS.get(r["tour"])
        if r["tour"] == "3":
            tour = "Q3" if niveau == "G" or niveau.startswith("I") else "Q2"
        if tour is None:
            stats["tour_inconnu"] += 1
            continue
        if niveau.startswith("I") and tour.startswith("Q"):
            # l'historique Sackmann ne contient pas les qualifications ITF
            stats["qualifs_itf_ignorees"] += 1
            continue
        j1 = joueur(r["joueur1_id"], r["joueur1"])
        j2 = joueur(r["joueur2_id"], r["joueur2"])
        if r["vainqueur_id"] == r["joueur1_id"]:
            g, p, score = j1, j2, r["score"]
        else:
            g, p, score = j2, j1, inverser_score(r["score"])
        doublon = any(0 <= (dt.date.fromisoformat(jour) - dt.date.fromisoformat(d)).days <= 21
                      for d in recents.get(frozenset((g, p)), []))
        if doublon:
            stats["doublons_sackmann"] += 1
            continue
        tid = "v" + r["tournoi_id"]
        surface, salle = SURFACES_VBT.get(r["surface"], (None, None))
        bo = 5 if niveau == "G" and not tour.startswith("Q") else 3
        if tid not in base.tournois:
            base.tournois[tid] = {"nom": re.sub(r"\s+-\s+.*$", "", r["tournoi"]) if niveau in "GMA" else r["tournoi"],
                                  "niveau": niveau, "surface": surface, "salle": salle,
                                  "debut": jour, "bo": 3, "annee": int(jour[:4]),
                                  "cat": niveau[1:] if niveau.startswith("I") and len(niveau) > 1 else None}
        t = base.tournois[tid]
        t["debut"] = min(t["debut"], jour)
        if niveau == "G":
            t["bo"] = 5
        sc, drap = analyser_score(score, bo)
        drap |= SRC_VBT
        heure = (r["date"] or "")[11:16]
        base.simples.append({"t": tid, "tour": tour, "g": g, "p": p, "score": sc,
                             "date": jour + ("T" + heure if heure and heure != "00:00" else ""),
                             "dr": drap, "debut": t["debut"], "vbt": r["match_id"]})
        stats["ajoutes"] += 1
        stats["score_complet"] += bool(drap & COMPLET)
    # l'année d'un tournoi suit son premier match
    for t in base.tournois.values():
        t["annee"] = int(t["debut"][:4])
    J.chiffres["vbt"] = dict(stats)
    J.info("Valuebetennis intégré : " + ", ".join(f"{k}={v}" for k, v in sorted(stats.items())))
    if noms_inconnus:
        J.chiffres["vbt_noms_ambigus"] = noms_inconnus.most_common(30)


# ---------------------------------------------------------------- Kaggle
def obtenir_kaggle(fichier_local=None):
    if fichier_local:
        return fichier_local
    if not os.environ.get("KAGGLE_API_TOKEN"):
        J.info("Kaggle : pas de clé KAGGLE_API_TOKEN, étape sautée")
        return None
    cible = tempfile.mkdtemp(prefix="kaggle_")
    erreurs = []
    for cmd in (["kaggle", "datasets", "download", KAGGLE_JEU, "-p", cible, "--unzip"],
                ["kaggle", "datasets", "download", "-d", KAGGLE_JEU, "-p", cible, "--unzip"]):
        try:
            subprocess.run(cmd, check=True, capture_output=True, text=True, timeout=600)
            break
        except Exception as e:  # noqa: BLE001
            erreurs.append((getattr(e, "stderr", "") or str(e)).strip()[:300])
    else:
        J.alerte(f"Kaggle : téléchargement impossible ({' | '.join(erreurs)})")
        return None
    for nom in os.listdir(cible):
        if nom.endswith(".zip"):
            with zipfile.ZipFile(os.path.join(cible, nom)) as z:
                z.extractall(cible)
    for nom in os.listdir(cible):
        if nom.endswith(".csv"):
            return os.path.join(cible, nom)
    J.alerte("Kaggle : aucun fichier CSV dans le jeu téléchargé")
    return None


def nom_kaggle(n):
    """'De Minaur A.' -> (['de', 'minaur'], 'a')"""
    n = unicodedata.normalize("NFKD", n or "").encode("ascii", "ignore").decode().lower().strip()
    m = re.match(r"^(.*?)\s+([a-z])[a-z.\- ]*\.?$", n)
    if not m:
        return re.sub(r"[^a-z ]", " ", n).split(), ""
    return re.sub(r"[^a-z ]", " ", m.group(1).replace("-", " ")).split(), m.group(2)


def correspond(nom_complet, nk):
    nom_tokens, initiale = nk
    toks = cle_nom(nom_complet).split()
    if not nom_tokens or not all(t in toks for t in nom_tokens):
        return False
    reste = [t for t in toks if t not in nom_tokens]
    return not initiale or not reste or any(t.startswith(initiale) for t in reste)


def completer_scores_kaggle(base, fichier, fin_sackmann):
    if not fichier:
        return
    stats = Counter()
    index = defaultdict(list)
    for i, m in enumerate(base.simples):
        if m["dr"] & SRC_VBT and base.tournois[m["t"]]["niveau"] in ("G", "M", "A", "F") \
                and not m["tour"].startswith("Q"):
            index[m["date"][:10] if m["date"] else m["debut"]].append(i)
    with open(fichier, encoding="utf-8", errors="replace") as f:
        for r in csv.DictReader(f):
            d = r.get("Date", "")
            if d < fin_sackmann:
                continue
            stats["lignes"] += 1
            score = (r.get("Score") or "").strip()
            if not score:
                continue
            k1, k2, kw = nom_kaggle(r["Player_1"]), nom_kaggle(r["Player_2"]), r["Winner"]
            trouve = None
            for decal in (0, -1, 1, -2, 2, -3, 3):
                jour = (dt.date.fromisoformat(d) + dt.timedelta(days=decal)).isoformat()
                for i in index.get(jour, []):
                    m = base.simples[i]
                    ng, np_ = base.joueurs[m["g"]]["nom"], base.joueurs[m["p"]]["nom"]
                    if (correspond(ng, k1) and correspond(np_, k2)) or (correspond(ng, k2) and correspond(np_, k1)):
                        trouve = i
                        break
                if trouve is not None:
                    break
            if trouve is None:
                stats["non_rapproches"] += 1
                continue
            m = base.simples[trouve]
            gagnant_k1 = kw == r["Player_1"]
            if correspond(base.joueurs[m["g"]]["nom"], k1) != gagnant_k1:
                stats["vainqueur_different"] += 1
                continue
            sc = score if gagnant_k1 else inverser_score(score)
            bo = int(r.get("Best of") or 3)
            sc, drap = analyser_score(sc, bo)
            stats["rapproches"] += 1
            if not (m["dr"] & COMPLET) and drap & COMPLET:
                # Kaggle n'a pas le détail des jeux décisifs : on garde celui de VBT s'il est identique
                m["score"], m["dr"] = sc, (m["dr"] & ~ABANDON) | drap | SRC_KAGGLE
                stats["scores_completes"] += 1
    J.chiffres["kaggle"] = dict(stats)
    J.info("Kaggle : " + ", ".join(f"{k}={v}" for k, v in sorted(stats.items())))


SERIES_KAGGLE = {"atp250": "250", "international": "250", "atp500": "500", "international gold": "500"}


def enrichir_kaggle(base, fichier, fin_sackmann):
    """Circuit principal : catégorie ATP 250 / 500, intérieur ou extérieur, et classement
    officiel au moment du match (colonnes Series, Court, Rank, Pts de Kaggle, CC0)."""
    if not fichier:
        return
    stats = Counter()
    index = defaultdict(lambda: defaultdict(set))   # tid -> jeton du nom -> {id}
    jetons = {}
    par_debut = defaultdict(list)
    for m in base.simples:
        t = base.tournois[m["t"]]
        if t["niveau"] in ("G", "M", "A", "F") and not m["tour"].startswith("Q") and t["annee"] >= DEBUT_ATP:
            for pid in (m["g"], m["p"]):
                if pid not in jetons:
                    jetons[pid] = set(cle_nom(base.joueurs[pid]["nom"]).split())
                for tok in jetons[pid]:
                    index[m["t"]][tok].add(pid)
    for tid in index:
        par_debut[base.tournois[tid]["debut"]].append(tid)

    def cherche(tid, nk):
        toks, ini = nk
        if not toks:
            return None
        cands = None
        for tok in toks:
            s = index[tid].get(tok, set())
            cands = s if cands is None else cands & s
            if not cands:
                return None
        retenus = [pid for pid in cands
                   if not ini or not (jetons[pid] - set(toks)) or any(x.startswith(ini) for x in jetons[pid] - set(toks))]
        return retenus[0] if len(retenus) == 1 else None

    # les lignes Kaggle sont d'abord regroupées par tournoi : tout le tournoi est rattaché
    # au tournoi de notre base qui partage le plus de matchs (évite de confondre deux
    # tournois proches dans le temps, ex. Halle et les qualifications de Wimbledon)
    groupes = defaultdict(list)
    with open(fichier, encoding="utf-8", errors="replace") as f:
        for r in csv.DictReader(f):
            d = (r.get("Date") or "")[:10]
            if d[:4] < str(DEBUT_ATP) or len(d) < 10:
                continue
            try:
                r["_jour"] = dt.date.fromisoformat(d)
            except ValueError:
                continue
            groupes[((r.get("Tournament") or "").strip(), d[:4])].append(r)
    # un même nom peut servir à deux tournois la même année (ex. « European Open » :
    # Hambourg en juillet, Anvers en octobre) : on coupe quand deux dates sont à plus de 10 jours
    decoupes = []
    for lignes in groupes.values():
        lignes.sort(key=lambda r: r["_jour"])
        bloc = [lignes[0]]
        for r in lignes[1:]:
            if (r["_jour"] - bloc[-1]["_jour"]).days > 10:
                decoupes.append(bloc)
                bloc = []
            bloc.append(r)
        decoupes.append(bloc)
    votes = defaultdict(Counter)
    lignes_rangs = []          # (tid, id, rang, points)
    premiere = {}              # tid -> première date Kaggle (début réel du tableau principal)
    for lignes in decoupes:
        noms = [(nom_kaggle(r["Player_1"]), nom_kaggle(r["Player_2"])) for r in lignes]
        choix = Counter()
        for r, (k1, k2) in zip(lignes, noms):
            for decal in range(-2, 21):
                for tid in par_debut.get((r["_jour"] - dt.timedelta(days=decal)).isoformat(), []):
                    a, b = cherche(tid, k1), cherche(tid, k2)
                    if a and b and a != b:
                        choix[tid] += 1
        if not choix:
            stats["lignes_non_rapprochees"] += len(lignes)
            continue
        tid, n = choix.most_common(1)[0]
        for r, (k1, k2) in zip(lignes, noms):
            a, b = cherche(tid, k1), cherche(tid, k2)
            if not (a and b and a != b):
                stats["lignes_non_rapprochees"] += 1
                continue
            stats["lignes_rapprochees"] += 1
            d = r["_jour"].isoformat()
            votes[tid][((r.get("Series") or "").strip().lower(), (r.get("Court") or "").strip().lower())] += 1
            premiere[tid] = min(premiere.get(tid, d), d)
            for pid, rk, pts in ((a, r.get("Rank_1"), r.get("Pts_1")), (b, r.get("Rank_2"), r.get("Pts_2"))):
                try:
                    rk, pts = int(float(rk)), int(float(pts))
                except (TypeError, ValueError):
                    continue
                if rk > 0:
                    lignes_rangs.append((tid, pid, rk, pts if pts > 0 else None))
    # classement d'entrée : semaine du premier match du tableau principal
    rangs = {}
    for tid, pid, rk, pts in lignes_rangs:
        semaine = lundi(premiere[tid])
        if pid not in rangs or semaine >= rangs[pid][0]:
            rangs[pid] = [semaine, rk, pts]
    for tid, v in votes.items():
        (serie, court), _ = v.most_common(1)[0]
        t = base.tournois[tid]
        if t["niveau"] == "A" and any(x in t["nom"].lower() for x in ("laver cup", "atp cup", "united cup")):
            t["cat"] = "equipes"
        elif t["niveau"] == "A" and serie in SERIES_KAGGLE:
            t["cat"] = SERIES_KAGGLE[serie]
            stats["tournois_250_500"] += 1
        if court in ("indoor", "outdoor") and t.get("salle") is None:
            t["salle"] = 1 if court == "indoor" else 0
            stats["tournois_salle_renseignee"] += 1
    for pid, (semaine, rk, pts) in rangs.items():
        cur = base.recents.get(pid)
        if cur is None or semaine > cur[0]:
            base.recents[pid] = [semaine, rk, pts, "kaggle"]
            stats["classements_recents_kaggle"] += 1
    for t in base.tournois.values():
        if t["niveau"] == "A" and not t.get("cat") and any(x in t["nom"].lower() for x in ("laver cup", "atp cup", "united cup")):
            t["cat"] = "equipes"
    sans = sum(1 for t in base.tournois.values() if t["niveau"] == "A" and t["annee"] >= DEBUT_ATP and not t.get("cat"))
    stats["tournois_A_sans_categorie"] = sans
    J.chiffres["kaggle_enrichissement"] = dict(stats)
    J.info("Kaggle (catégories, salle, classements) : " + ", ".join(f"{k}={v}" for k, v in sorted(stats.items())))


# ---------------------------------------------------------------- Wikipédia
MOTS_MASTERS = ("indian wells", "miami open", "monte carlo", "monte-carlo", "madrid open",
                "italian open", "canadian open", "national bank open", "cincinnati",
                "shanghai masters", "paris masters", "rolex paris")
MOTS_CHELEM = ("australian open", "french open", "wimbledon", "us open")


def wiki_requete(params, pause=2.0):
    params = {**params, "format": "json", "formatversion": "2", "maxlag": "5"}
    url = WIKI_API + "?" + urllib.parse.urlencode(params)
    for essai in range(5):
        data = json.loads(telecharger(url, {"Accept-Encoding": "gzip"}))
        if data.get("error", {}).get("code") == "maxlag":
            time.sleep(10 * (essai + 1))
            continue
        time.sleep(pause)
        return data
    raise RuntimeError("Wikipédia surchargé (maxlag)")


def wiki_requete_complete(params, pause=2.0):
    """Une requête et ses suites (Wikipédia tronque les réponses trop lourdes)."""
    pages, renvois, suite = {}, {}, {}
    for _ in range(30):
        data = wiki_requete({**params, **suite}, pause)
        if "error" in data:
            raise RuntimeError(f"Wikipédia : {data['error'].get('info', data['error'])}")
        q = data.get("query", {})
        renvois.update({r["from"]: r["to"] for r in q.get("redirects", [])})
        renvois.update({n["from"]: n["to"] for n in q.get("normalized", [])})
        for p in q.get("pages", []):
            ancien = pages.get(p["title"])
            if ancien and ancien.get("revisions") and not p.get("revisions"):
                continue
            pages[p["title"]] = p
        if "continue" not in data:
            break
        suite = data["continue"]
    return pages, renvois


def _cible(t, renvois):
    t2 = renvois.get(t, t)
    return renvois.get(t2, t2)


def wiki_contenus(titres, intro_seulement=False, lot_max=10):
    """Contenu wikitexte et révision, par petits paquets."""
    resultat = {}
    for i in range(0, len(titres), lot_max):
        lot = titres[i:i + lot_max]
        params = {"action": "query", "prop": "revisions", "rvprop": "content|ids",
                  "rvslots": "main", "redirects": "1", "titles": "|".join(lot)}
        if intro_seulement:
            params["rvsection"] = "0"   # encadré du tournoi seulement : bien plus léger
        try:
            pages, renvois = wiki_requete_complete(params)
        except RuntimeError:
            if not intro_seulement:
                raise
            params.pop("rvsection")
            pages, renvois = wiki_requete_complete(params)
        for t in lot:
            p = pages.get(_cible(t, renvois))
            if p and not p.get("missing") and p.get("revisions"):
                rev = p["revisions"][0]
                texte = rev.get("slots", {}).get("main", {}).get("content")
                if texte is not None:
                    resultat[t] = {"rev": rev["revid"], "texte": texte}
    return resultat


def wiki_revisions(titres):
    resultat = {}
    for i in range(0, len(titres), 50):
        lot = titres[i:i + 50]
        pages, renvois = wiki_requete_complete({"action": "query", "prop": "revisions", "rvprop": "ids",
                                                "redirects": "1", "titles": "|".join(lot)}, pause=1.0)
        for t in lot:
            p = pages.get(_cible(t, renvois))
            if p and not p.get("missing") and p.get("revisions"):
                resultat[t] = p["revisions"][0]["revid"]
    return resultat


RE_LIEN = re.compile(r"\[\[([^\]|#]+)(?:#[^\]|]*)?(?:\|([^\]]*))?\]\]")


def liens(texte):
    return [m.group(1).strip() for m in RE_LIEN.finditer(texte)]


def pages_double_saison(annee, circuit):
    """Titres des pages de tableau de double d'une saison."""
    titre_saison = f"{annee} ATP Tour" if circuit == "A" else f"{annee} ATP Challenger Tour"
    candidats = []
    pages = wiki_contenus([titre_saison])
    if titre_saison in pages:
        candidats += liens(pages[titre_saison]["texte"])
    else:
        J.alerte(f"Wikipédia : page de saison introuvable « {titre_saison} »")
    # seconde voie : la catégorie de la saison liste les pages de tournoi
    suite = {}
    for _ in range(10):
        data = wiki_requete({"action": "query", "list": "categorymembers", "cmlimit": "500",
                             "cmtitle": f"Category:{titre_saison}", "cmnamespace": "0", **suite}, pause=1.0)
        if "error" in data:
            J.alerte(f"Wikipédia : catégorie {titre_saison} : {data['error'].get('info')}")
            break
        candidats += [m["title"] for m in data.get("query", {}).get("categorymembers", [])]
        if "continue" not in data:
            break
        suite = {"cmcontinue": data["continue"]["cmcontinue"]}
    cibles = {}
    for l in candidats:
        if not l.startswith(str(annee)) or "ATP Tour" in l or "Challenger Tour" in l:
            continue
        if re.search(r"\s[–-]\s(Men's )?[Dd]oubles$", l):
            cibles[l] = circuit
        elif not re.search(r"\s[–-]\s", l):
            cibles[l + " – Doubles"] = circuit
            cibles[l + " – Men's doubles"] = circuit
    existantes = wiki_revisions(sorted(cibles))   # {titre: révision}
    return existantes


def nettoyer_cellule(v):
    v = re.sub(r"<ref[^>]*/>|<ref[^>]*>.*?</ref>", "", v, flags=re.S)
    v = re.sub(r"\{\{(?:flagicon|flag icon|flagdeco|flagathlete)[^{}]*\}\}", "", v, flags=re.I)
    return v


def noms_equipe(v):
    """Extrait les noms d'une cellule d'équipe (1 ou 2 joueurs)."""
    v = nettoyer_cellule(v)
    v = re.sub(r"\{\{(?:nowrap|nobr)\|(.*?)\}\}", r"\1", v, flags=re.I)
    morceaux = re.split(r"<br\s*/?>|&nbsp;/\s|\s/\s", v)
    noms = []
    for mo in morceaux:
        # le texte affiché est souvent abrégé (« S Arends ») : on prend la cible du lien
        mo = re.sub(r"\[\[([^\]|]+)\|([^\]]+)\]\]", r"\1", mo)
        mo = re.sub(r"\[\[([^\]]+)\]\]", r"\1", mo)
        mo = re.sub(r"\{\{[^{}]*\}\}", "", mo)
        mo = re.sub(r"<[^>]+>|'''|''|\(.*?\)", "", mo)
        mo = re.sub(r"\s+", " ", mo).strip(" ,")
        if mo:
            noms.append(mo)
    return noms


def score_cellule(v):
    """'7<sup>7</sup>' -> (7, 7) ; \"'''6'''\" -> (6, None) ; '' -> None"""
    v = nettoyer_cellule(v).replace("'''", "")
    m = re.match(r"^\s*\[?(\d{1,2})\]?\s*(?:<sup>\s*(\d+)\s*</sup>)?", v)
    if not m:
        return None
    return int(m.group(1)), (int(m.group(2)) if m.group(2) else None)


RE_MODELE = re.compile(r"\{\{\s*(\d+)TeamBracket[^|]*", re.I)


def extraire_modeles(texte):
    """Renvoie [(nb_equipes, params, position)] pour chaque modèle de tableau."""
    sortie = []
    for m in RE_MODELE.finditer(texte):
        debut, i, prof = m.start(), m.start(), 0
        while i < len(texte):
            if texte.startswith("{{", i):
                prof += 1
                i += 2
            elif texte.startswith("}}", i):
                prof -= 1
                i += 2
                if prof == 0:
                    break
            else:
                i += 1
        corps = texte[m.end():i - 2]
        # découpage des paramètres au premier niveau
        params, prof, courant = [], 0, ""
        for c in re.split(r"(\{\{|\}\}|\[\[|\]\]|\|)", corps):
            if c in ("{{", "[["):
                prof += 1
            elif c in ("}}", "]]"):
                prof -= 1
            if c == "|" and prof == 0:
                params.append(courant)
                courant = ""
            else:
                courant += c
        params.append(courant)
        d = {}
        for p in params:
            if "=" in p:
                k, v = p.split("=", 1)
                d[k.strip()] = v.strip()
        sortie.append((int(m.group(1)), d, debut))
    return sortie


def matchs_tableau(nb_equipes, params):
    """[(rd, index, equipeA, equipeB, scoresA, scoresB, gras A, gras B)]"""
    tours = 0
    n = nb_equipes
    while n > 1:
        n //= 2
        tours += 1
    def val(modele, k, *suite):
        # Wikipédia écrit selon les modèles « team01 » ou « team1 »
        for cle in (f"{k:02d}", f"{k}"):
            v = params.get(modele.format(cle, *suite))
            if v is not None and v.strip():
                return v
        return ""

    sortie = []
    for rd in range(1, tours + 1):
        nb = nb_equipes >> (rd - 1)
        for k in range(1, nb + 1, 2):
            ea, eb = val(f"RD{rd}-team{{}}", k), val(f"RD{rd}-team{{}}", k + 1)
            sa = [val(f"RD{rd}-score{{}}-{{}}", k, s) for s in range(1, 6)]
            sb = [val(f"RD{rd}-score{{}}-{{}}", k + 1, s) for s in range(1, 6)]
            sortie.append((rd, k, ea, eb, sa, sb, "'''" in ea, "'''" in eb))
    return tours, sortie


def tour_depuis_fin(i):
    return {0: "F", 1: "SF", 2: "QF"}.get(i)


def lire_page_double(texte):
    """Matchs d'une page de tableau de double. Renvoie (matchs, alertes)."""
    modeles = extraire_modeles(texte)
    if not modeles:
        return [], ["aucun modèle de tableau"]
    # le tableau « Finals » est celui placé sous un titre contenant « Final »
    titres = [(m.start(), m.group(1).strip().lower())
              for m in re.finditer(r"^=+\s*([^=\n]+?)\s*=+\s*$", texte, re.M)]
    infos = []
    for nb, params, pos in modeles:
        precedents = [t for p, t in titres if p < pos]
        if any("qualif" in t or "lucky" in t for t in precedents[-2:]):
            continue   # tableau des qualifications : hors du tableau principal
        tours, matchs = matchs_tableau(nb, params)
        est_finale = bool(precedents) and precedents[-1].startswith("final")
        infos.append((nb, tours, matchs, est_finale))
    if not infos:
        return [], ["aucun tableau principal"]
    finales = [x for x in infos if x[3]]
    tours_finale = finales[0][1] if finales else 0
    if len(infos) > 1 and not finales:
        return [], ["plusieurs tableaux sans section Finals : page ignorée"]
    sortie, alertes = [], []
    profondeur_max = 0
    for nb, tours, matchs, est_finale in infos:
        profondeur_max = max(profondeur_max, (tours - 1) if (est_finale or not finales)
                             else (tours_finale + tours - 1))
    for nb, tours, matchs, est_finale in infos:
        for rd, k, ea, eb, sa, sb, ga, gb in matchs:
            na, nb_ = noms_equipe(ea), noms_equipe(eb)
            if not na or not nb_ or any(x.lower() in ("bye", "") for x in na + nb_):
                continue
            depuis_fin = (tours - rd) if (est_finale or not finales) else (tours_finale + tours - rd)
            tour = tour_depuis_fin(depuis_fin) or f"{profondeur_max - depuis_fin + 1}T"
            sca = [score_cellule(x) for x in sa]
            scb = [score_cellule(x) for x in sb]
            sets = []
            for a, b in zip(sca, scb):
                if a is None or b is None:
                    continue
                sets.append((a, b))
            if not sets:
                continue
            gagnes_a = sum(1 for a, b in sets if a[0] > b[0])
            gagnes_b = sum(1 for a, b in sets if b[0] > a[0])
            if ga != gb:
                a_gagne = ga
            elif gagnes_a != gagnes_b:
                a_gagne = gagnes_a > gagnes_b
            else:
                alertes.append(f"vainqueur indéterminé : {na} / {nb_}")
                continue
            if not a_gagne:
                na, nb_ = nb_, na
                sets = [(b, a) for a, b in sets]
            txt = []
            for a, b in sets:
                if a[0] >= 10 or b[0] >= 10:
                    txt.append(f"[{a[0]}-{b[0]}]")
                else:
                    tb = a[1] if a[1] is not None else b[1]
                    txt.append(f"{a[0]}-{b[0]}" + (f"({min(a[1] or 99, b[1] or 99)})" if tb is not None else ""))
            sortie.append({"tour": tour, "g": na, "p": nb_, "score": " ".join(txt)})
    return sortie, alertes


RE_INFOBOX_SURFACE = re.compile(r"\|\s*surface\s*=\s*([^\n]*)", re.I)
MOIS = {m: i for i, m in enumerate(["january", "february", "march", "april", "may", "june", "july",
                                     "august", "september", "october", "november", "december"], 1)}


def infos_tournoi(texte, annee):
    surf, salle, debut = None, None, None
    m = RE_INFOBOX_SURFACE.search(texte or "")
    if m:
        s = m.group(1).lower()
        for cle, val in (("clay", "Clay"), ("grass", "Grass"), ("carpet", "Carpet"), ("hard", "Hard")):
            if cle in s:
                surf = val
                break
        salle = 1 if "indoor" in s else (0 if "outdoor" in s else None)
    m = re.search(r"\|\s*date\s*=\s*([^\n]*)", texte or "", re.I)
    if m:
        d = re.sub(r"\{\{[^{}]*\}\}|\[\[|\]\]|<[^>]+>", " ", m.group(1)).lower()
        m2 = re.search(r"(\d{1,2})\s*[–-]\s*\d{1,2}\s+([a-z]+)", d) or \
            re.search(r"(\d{1,2})\s+([a-z]+)\s*[–-]", d)
        m3 = re.search(r"([a-z]+)\s+(\d{1,2})\s*[–-]", d)
        try:
            if m2 and m2.group(2) in MOIS:
                debut = dt.date(annee, MOIS[m2.group(2)], int(m2.group(1))).isoformat()
            elif m3 and m3.group(1) in MOIS:
                debut = dt.date(annee, MOIS[m3.group(1)], int(m3.group(2))).isoformat()
        except ValueError:
            debut = None
    return surf, salle, debut


def niveau_double(titre, circuit):
    t = titre.lower()
    if circuit == "C":
        return "C"
    if any(x in t for x in MOTS_CHELEM):
        return "G"
    if "atp finals" in t or "tour finals" in t:
        return "F"
    if any(x in t for x in MOTS_MASTERS):
        return "M"
    if "olympics" in t or "olympic" in t:
        return "O"
    return "A"


def collecter_wikipedia(etat_wiki, toutes=False):
    """Met à jour le cache des doubles. Seules les pages modifiées sont relues."""
    annee_courante = dt.date.today().year
    stats = Counter()
    budget = BUDGET_WIKI
    # saisons récentes d'abord : ce sont les plus utiles
    for annee in range(annee_courante, DEBUT_DOUBLE - 1, -1):
        recente = annee >= annee_courante - (1 if dt.date.today().month == 1 else 0)
        cle_saison = str(annee)
        saison = etat_wiki.setdefault(cle_saison, {"pages": {}, "verifiee": None})
        a_jour = all(pg.get("v") == PARSEUR_WIKI for pg in saison["pages"].values())
        if saison["verifiee"] and a_jour and not recente and not toutes:
            continue
        if budget <= 0:
            stats["saisons_reportees"] += 1
            continue
        complete = True
        for circuit in ("A", "C"):
            try:
                revs = pages_double_saison(annee, circuit)   # {titre: révision}
                titres = sorted(revs)
                a_lire = sorted(t for t in titres if saison["pages"].get(t, {}).get("rev") != revs.get(t)
                                or saison["pages"].get(t, {}).get("v") != PARSEUR_WIKI)
                stats["pages_trouvees"] += len(titres)
                if len(a_lire) > budget:
                    a_lire, complete = a_lire[:budget], False
                if not a_lire:
                    continue
                budget -= len(a_lire)
                contenus = wiki_contenus(a_lire)
                parents = {t: re.sub(r"\s[–-]\s(Men's )?[Dd]oubles$", "", t) for t in a_lire}
                infos = wiki_contenus(sorted(set(parents.values())), intro_seulement=True)
                for t in a_lire:
                    if t not in contenus:
                        continue
                    matchs, alertes = lire_page_double(contenus[t]["texte"])
                    parent = parents[t]
                    surf, salle, debut = infos_tournoi(infos.get(parent, {}).get("texte", ""), annee)
                    saison["pages"][t] = {"rev": contenus[t]["rev"], "tournoi": parent,
                                          "niveau": niveau_double(t, circuit), "surface": surf, "salle": salle,
                                          "debut": debut, "matchs": matchs, "alertes": alertes[:5],
                                          "v": PARSEUR_WIKI}
                    stats["pages_lues"] += 1
                    stats["matchs"] += len(matchs)
                    if not matchs:
                        stats["pages_sans_match"] += 1
            except Exception as e:  # noqa: BLE001
                complete = False
                J.alerte(f"Wikipédia {annee} {'ATP' if circuit == 'A' else 'Challenger'} : {e}")
        if complete:
            saison["verifiee"] = dt.date.today().isoformat()
        else:
            stats["saisons_incompletes"] += 1
    stats["budget_restant"] = budget
    J.chiffres["wikipedia"] = dict(stats)
    J.info("Wikipédia : " + ", ".join(f"{k}={v}" for k, v in sorted(stats.items())))


def integrer_doubles(base, etat_wiki, etat_corresp):
    corresp = etat_corresp.setdefault("wiki", {})
    stats = Counter()
    # repères de date par tournoi : premiers matchs de simple de même nom et même année
    reperes = defaultdict(list)
    for tid, t in base.tournois.items():
        reperes[(t["annee"], cle_nom(re.sub(r"\d{4}", "", t["nom"])))].append(t)

    import difflib
    par_mot = defaultdict(set)
    for pid, j in base.joueurs.items():
        for mot in cle_nom(j["nom"]).split():
            if len(mot) >= 2:
                par_mot[mot].add(pid)

    def joueur(nom):
        nom = re.sub(r"\s*\([^)]*\)\s*$", "", nom).strip()   # « Nom (tennis) »
        k = cle_nom(nom)
        if k in corresp:
            pid = corresp[k]
        else:
            cands = base.par_cle.get(k, [])
            if len(cands) > 1:
                cands = [max(cands, key=lambda c: base.activite.get(c, ""))]
            pid = cands[0] if cands else None
            if pid is None:
                # « S Arends » ou « S. Arends » : initiale + nom de famille, si un seul joueur correspond
                m = re.match(r"^([A-Za-zÀ-ÿ])(?:[A-Za-zÀ-ÿ]|-[A-Za-zÀ-ÿ])?\.?\s+(.+)$", nom)
                mots = cle_nom(m.group(2) if m else nom).split()
                initiale = cle_nom(m.group(1)) if m else ""
                if mots:
                    cands = set.intersection(*[par_mot.get(w, set()) for w in mots]) if all(
                        len(w) >= 2 for w in mots) else set()
                    if initiale:
                        cands = {c for c in cands if any(
                            w.startswith(initiale) for w in cle_nom(base.joueurs[c]["nom"]).split()
                            if w not in mots)}
                    elif cands:
                        cands = {c for c in cands if set(cle_nom(base.joueurs[c]["nom"]).split()) <= set(mots)
                                 or set(mots) <= set(cle_nom(base.joueurs[c]["nom"]).split())}
                    if len(cands) == 1:
                        pid = cands.pop()
                        stats["noms_abreges_rapproches" if initiale else "noms_rapproches_orthographe"] += 1
                    elif not cands and not initiale and len(mots) >= 2:
                        # orthographes voisines (« Pütz » / « Puetz ») : un seul candidat très proche
                        voisins = set()
                        for w in mots:
                            voisins |= par_mot.get(w, set())
                        proches = [c for c in voisins if difflib.SequenceMatcher(
                            None, k, cle_nom(base.joueurs[c]["nom"])).ratio() >= 0.88]
                        if len(proches) == 1:
                            pid = proches[0]
                            stats["noms_rapproches_orthographe"] += 1
            if pid is None:
                pid = "w" + k.replace(" ", "_")
                stats["joueurs_double_nouveaux"] += 1
            corresp[k] = pid
        if pid not in base.joueurs:
            base.ajouter_joueur(pid, nom)
            for mot in k.split():
                if len(mot) >= 2:
                    par_mot[mot].add(pid)
        return pid

    for annee, saison in sorted(etat_wiki.items()):
        for titre, page in saison["pages"].items():
            if not page["matchs"]:
                continue
            tid = "w" + re.sub(r"[^a-z0-9]", "", cle_nom(titre))[:40] + annee
            debut = page["debut"]
            surface, salle = page["surface"], page["salle"]
            nom_court = re.sub(r"^\d{4}\s+", "", page["tournoi"])
            if not debut or not surface:
                mots = set(cle_nom(nom_court).split()) - {"open", "international", "challenger", "cup",
                                                          "tennis", "championships", "atp", "trophy"}
                for (a, cle), liste in reperes.items():
                    if a == int(annee) and mots and (set(cle.split()) & mots):
                        t = liste[0]
                        debut = debut or t["debut"]
                        surface = surface or t["surface"]
                        stats["date_ou_surface_par_simple"] += 1
                        break
            if not debut:
                stats["sans_date"] += 1
                debut = f"{annee}-01-01"
            base.tournois[tid] = {"nom": nom_court, "niveau": page["niveau"], "surface": surface,
                                  "salle": salle, "debut": debut, "bo": 5 if page["niveau"] == "G" else 3,
                                  "annee": int(annee), "double": 1}
            for m in page["matchs"]:
                if len(m["g"]) != 2 or len(m["p"]) != 2:
                    stats["equipes_incompletes"] += 1
                    continue
                g = "+".join(sorted(joueur(n) for n in m["g"]))
                p = "+".join(sorted(joueur(n) for n in m["p"]))
                _, drap = analyser_score(m["score"].replace("[", "").replace("]", ""), 3)
                base.doubles.append({"t": tid, "tour": m["tour"], "g": g, "p": p, "score": m["score"],
                                     "date": None, "dr": drap | SRC_WIKI, "debut": debut})
                stats["matchs"] += 1
    J.chiffres["doubles"] = dict(stats)
    J.info("Doubles intégrés : " + ", ".join(f"{k}={v}" for k, v in sorted(stats.items())))


# ---------------------------------------------------------------- TennisMyLife (chiffré)
def charger_tml(fin_sackmann, fichiers_locaux=None):
    """Lignes TennisMyLife (ATP, Challenger, qualifications) depuis l'année de fin de l'archive."""
    lignes = []
    if fichiers_locaux:
        sources = [(f, None, True) for f in fichiers_locaux]
    else:
        an = dt.date.today().year
        sources = [(None, u.format(annee=a), a == an)
                   for a in range(int(fin_sackmann[:4]), an + 1) for u in TML_URLS]
    for chemin, url, important in sources:
        nom = os.path.basename(chemin or url)
        try:
            brut = open(chemin, "rb").read() if chemin else telecharger(url)
            n = 0
            for r in csv.DictReader(io.StringIO(brut.decode("utf-8-sig", errors="replace"))):
                r["_fichier"] = nom
                lignes.append(r)
                n += 1
            J.info(f"TennisMyLife {nom} : {n} matchs")
        except Exception as e:  # noqa: BLE001
            (J.alerte if important else J.info)(f"TennisMyLife {nom} : {e}")
    return lignes


class Rapprocheur:
    """Rattache un joueur d'une source extérieure (TennisMyLife, Cito) à un joueur de la base :
    nom identique, sinon orthographe proche parmi les joueurs actifs ; sinon nouveau joueur.
    « autres » : joueurs nouveaux d'une autre source chiffrée (même personne = même identifiant)."""

    def __init__(self, base, fin_sackmann, stats, prefixe, autres=None):
        self.base, self.stats, self.prefixe = base, stats, prefixe
        limite_index = (dt.date.fromisoformat(fin_sackmann) - dt.timedelta(days=30)).isoformat()
        self.paires = defaultdict(list)
        self.dernier = {}
        for i, m in enumerate(base.simples):
            for pid in (m["g"], m["p"]):
                self.dernier[pid] = max(self.dernier.get(pid, ""), m["debut"])
            if m["debut"] >= limite_index:
                self.paires[frozenset((m["g"], m["p"]))].append(i)
        seuil_actif = (dt.date.fromisoformat(fin_sackmann) - dt.timedelta(days=3 * 365)).isoformat()
        self.par_mot = defaultdict(set)
        for pid, j in base.joueurs.items():
            if self.dernier.get(pid, "") >= seuil_actif:
                for mot in cle_nom(j["nom"]).split():
                    if len(mot) >= 3:
                        self.par_mot[mot].add(pid)
        self.autres = {}
        for pid, j in (autres or {}).items():
            self.autres.setdefault(cle_nom(j[0] or ""), pid)
        self.corresp, self.nouveaux = {}, {}

    def joueur(self, ext_id, nom, pays=None, main=None, taille=None):
        import difflib
        cle_c = ext_id or nom
        if cle_c in self.corresp:
            return self.corresp[cle_c]
        cle = cle_nom(nom)
        cands = self.base.par_cle.get(cle, [])
        if len(cands) == 1:
            pid = cands[0]
            self.stats["joueurs_rapproches"] += 1
        elif cands:
            pid = max(cands, key=lambda c: self.dernier.get(c, ""))
            self.stats["joueurs_homonymes_par_activite"] += 1
        elif cle in self.autres:
            pid = self.autres[cle]
            self.stats["joueurs_communs_autre_source"] += 1
        else:
            mots = set(cle.split())
            vus = set()
            for mot in mots:
                vus |= self.par_mot.get(mot, set())
            retenus = []
            for c in vus:
                cm = cle_nom(self.base.joueurs[c]["nom"])
                commun = mots & set(cm.split())
                if (len(commun) >= 2 and (mots <= set(cm.split()) or set(cm.split()) <= mots)) or \
                        (commun and difflib.SequenceMatcher(None, cle, cm).ratio() >= 0.88):
                    retenus.append(c)
            if len(retenus) == 1:
                pid = retenus[0]
                self.stats["joueurs_rapproches_orthographe"] += 1
            else:
                pid = self.prefixe + re.sub(r"[^A-Za-z0-9]", "", ext_id or cle.replace(" ", "_"))
                self.stats["joueurs_nouveaux"] += 1
                self.nouveaux[pid] = [nom, pays or None, main if main in ("R", "L") else None, taille, None]
        self.corresp[cle_c] = pid
        return pid


def integrer_tml(base, lignes, fin_sackmann):
    """Prépare le complément chiffré : scores et statistiques des matchs déjà publiés,
    matchs absents des autres sources. Rien n'est ajouté à la base publique."""
    stats = Counter()
    debut_fenetre = (dt.date.fromisoformat(fin_sackmann) - dt.timedelta(days=7)).isoformat()
    rap = Rapprocheur(base, fin_sackmann, stats, "t")
    paires, nouveaux = rap.paires, rap.nouveaux

    def joueur(r, cote):
        taille = (r.get(f"{cote}_ht") or "").strip()
        try:
            taille = int(float(taille)) if taille else None
        except ValueError:
            taille = None
        return rap.joueur((r.get(f"{cote}_id") or "").strip(), (r.get(f"{cote}_name") or "").strip(),
                          (r.get(f"{cote}_ioc") or "").strip() or None, (r.get(f"{cote}_hand") or "").strip(), taille)

    complements = defaultdict(list)
    seuls = []
    vote_tournoi = defaultdict(Counter)
    classements = {}
    salles = {}
    for r in lignes:
        debut = iso((r.get("tourney_date") or "").strip()[:8])
        if not debut or debut < debut_fenetre:
            stats["avant_fenetre"] += 1
            continue
        nom_t = (r.get("tourney_name") or "").strip()
        fichier = r.get("_fichier", "")
        if "challenger" in fichier.lower():
            niveau = "C"
        else:
            niveau = niveau_par_nom(niveau_sackmann((r.get("tourney_level") or "").strip(), nom_t, "principal"), nom_t)
        if niveau == "D" or (r.get("tourney_level") or "").strip() == "D":
            stats["coupe_davis_ignoree"] += 1
            continue
        tour = tour_relatif((r.get("round") or "").strip(), r.get("draw_size"))
        if "quali" in fichier.lower() and not tour.startswith("Q"):
            tour = "Q" + tour[0] if tour[:1].isdigit() else tour
        try:
            bo = int(float(r.get("best_of") or 3))
        except ValueError:
            bo = 3
        g, p = joueur(r, "winner"), joueur(r, "loser")
        sc, drap = analyser_score(r.get("score"), bo)
        drap |= SRC_TML
        st = stats_ligne(r)
        semaine = lundi(debut)
        for pid, rk, pts in ((g, r.get("winner_rank"), r.get("winner_rank_points")),
                             (p, r.get("loser_rank"), r.get("loser_rank_points"))):
            try:
                rk = int(float(rk))
            except (TypeError, ValueError):
                continue
            try:
                pts = int(float(pts))
            except (TypeError, ValueError):
                pts = None
            if rk > 0 and (pid not in classements or semaine >= classements[pid][0]):
                classements[pid] = [semaine, rk, pts]
        trouve = None
        for i in paires.get(frozenset((g, p)), []):
            m = base.simples[i]
            jour = (m["date"] or m["debut"])[:10]
            if -3 <= (dt.date.fromisoformat(jour) - dt.date.fromisoformat(debut)).days <= 20:
                trouve = i
                break
        tml_tid = "t" + re.sub(r"[^A-Za-z0-9-]", "", (r.get("tourney_id") or nom_t + debut))
        indoor = (r.get("indoor") or "").strip().upper()
        if trouve is not None:
            m = base.simples[trouve]
            vote_tournoi[tml_tid][m["t"]] += 1
            if indoor in ("I", "O") and base.tournois[m["t"]].get("salle") is None:
                salles[m["t"]] = 1 if indoor == "I" else 0
            if not m["dr"] & (SRC_VBT | SRC_WIKI):
                stats["deja_dans_archive"] += 1
                continue
            if m["g"] != g:
                stats["vainqueur_different_ignore"] += 1
                continue
            nouveau_score = None
            if drap & (COMPLET | ABANDON | FORFAIT) and not m["dr"] & COMPLET:
                nouveau_score = sc
                stats["scores_completes"] += 1
            if st:
                stats["statistiques_ajoutees"] += 1
            if nouveau_score is None and not st:
                continue
            annee = base.tournois[m["t"]]["annee"]
            complements[annee].append([m["t"], m["g"], m["p"], nouveau_score,
                                       drap if nouveau_score is not None else None, st])
        else:
            surface = (r.get("surface") or "").strip() or None
            seuls.append((tml_tid, [nom_t, niveau, surface, 1 if indoor == "I" else (0 if indoor == "O" else None),
                                    debut, bo, None], [tour, g, p, sc, None, drap, st], niveau))
    # un match absent des autres sources est rattaché au tournoi public correspondant s'il existe
    resultat = defaultdict(lambda: {"tournois": {}, "joueurs": {}, "complements": [], "matchs": [],
                                    "classements": {}})
    for annee, liste in complements.items():
        resultat[annee]["complements"] = liste
    for tml_tid, t, ligne, niveau in seuls:
        tid = vote_tournoi[tml_tid].most_common(1)[0][0] if vote_tournoi.get(tml_tid) else tml_tid
        annee = base.tournois[tid]["annee"] if tid in base.tournois else int(t[4][:4])
        res = resultat[annee]
        if tid not in base.tournois and tid not in res["tournois"]:
            res["tournois"][tid] = t
        elif tid in res["tournois"]:
            res["tournois"][tid][4] = min(res["tournois"][tid][4], t[4])
        for pid in (ligne[1], ligne[2]):
            if pid in nouveaux:
                res["joueurs"][pid] = nouveaux[pid]
        res["matchs"].append([tid] + ligne)
        stats["matchs_absents_ailleurs_" + niveau] += 1
    if resultat:
        an = max(resultat)
        resultat[an]["classements"] = classements
        resultat[an]["salles"] = salles
        stats["tournois_salle_completee"] = len(salles)
    J.chiffres["tml"] = dict(stats)
    J.info("TennisMyLife : " + ", ".join(f"{k}={v}" for k, v in sorted(stats.items())))
    return dict(resultat)


_CLES = {}


def cle_derivee(code, sel):
    """PBKDF2-SHA256 (lent par construction) : calculé une fois par passage."""
    import hashlib
    if (code, sel) not in _CLES:
        _CLES[(code, sel)] = hashlib.pbkdf2_hmac("sha256", code.encode("utf-8"), sel, TML_ITERATIONS, 32)
    return _CLES[(code, sel)]


def chiffrer(objet, code, sel):
    """AES-256-GCM, clé = PBKDF2-SHA256(code, sel, TML_ITERATIONS). Contenu : JSON compressé (gzip)."""
    import base64
    import secrets
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    iv = secrets.token_bytes(12)
    clair = gzip.compress(json.dumps(objet, ensure_ascii=False, separators=(",", ":")).encode("utf-8"), mtime=0)
    b64 = lambda x: base64.b64encode(x).decode("ascii")  # noqa: E731
    return {"format": "h2h-tml-1", "algo": "AES-256-GCM", "kdf": "PBKDF2-SHA256",
            "iterations": TML_ITERATIONS, "sel": b64(sel), "iv": b64(iv), "contenu": "json+gzip",
            "donnees": b64(AESGCM(cle_derivee(code, sel)).encrypt(iv, clair, None))}


def dechiffrer(enveloppe, code):
    import base64
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    sel = base64.b64decode(enveloppe["sel"])
    clair = AESGCM(cle_derivee(code, sel)).decrypt(base64.b64decode(enveloppe["iv"]),
                                                   base64.b64decode(enveloppe["donnees"]), None)
    return json.loads(gzip.decompress(clair).decode("utf-8"))


def sel_commun():
    import secrets
    chemin_sel = os.path.join(ETAT, "tml-sel.txt")
    sel_hex = (lire_texte(chemin_sel) or "").strip()
    if len(sel_hex) != 32:
        sel_hex = secrets.token_hex(16)
        os.makedirs(ETAT, exist_ok=True)
        with open(chemin_sel, "w", encoding="utf-8") as f:
            f.write(sel_hex + "\n")
    return bytes.fromhex(sel_hex)


def lire_chiffre(chemin, code, defaut):
    """Fichier chiffré -> objet. Fichier absent -> défaut. Fichier illisible -> exception
    (on ne réécrit jamais par-dessus des données qu'on n'a pas pu relire)."""
    env = lire_json(chemin, None)
    if not env:
        return defaut
    return dechiffrer(env, code)


def ecrire_chiffre(chemin, objet, code):
    """N'écrit que si le contenu a changé : le chiffrement produit un fichier différent à chaque
    écriture, ce qui alourdirait l'historique du dépôt."""
    ancien = lire_json(chemin, None)
    if ancien:
        try:
            if dechiffrer(ancien, code) == json.loads(json.dumps(objet, ensure_ascii=False)):
                return False
        except Exception:  # noqa: BLE001
            pass
    os.makedirs(os.path.dirname(chemin), exist_ok=True)
    ecrire_json(chemin, chiffrer(objet, code, sel_commun()), compact=False)
    return True


def ecrire_tml(resultat, code, prefixe="tml"):
    """Écrit donnees/<prefixe>-AAAA.json (chiffré). Renvoie la liste des fichiers."""
    ecrits = []
    for annee, contenu in sorted(resultat.items()):
        nom = f"{prefixe}-{annee}.json"
        contenu = dict(contenu, colonnes_tournois=["nom", "niveau", "surface", "salle", "debut", "bo", "categorie"],
                       colonnes_joueurs=["nom", "pays", "main", "taille_cm", "naissance"],
                       colonnes_complements=["tournoi", "gagnant", "perdant", "score", "drapeaux", "stats", "inverse"],
                       note_inverse="inverse = 1 : le vainqueur réel est le perdant publié (score et stats dans son sens)",
                       colonnes_matchs=["tournoi", "tour", "gagnant", "perdant", "score", "date", "drapeaux", "stats"],
                       colonnes_classements=["semaine", "rang", "points"], colonnes_stats=NOMS_STATS,
                       note_salles="tournoi public -> 1 en salle, 0 en extérieur (quand la base publique l'ignore)")
        ecrire_chiffre(os.path.join(DONNEES, nom), contenu, code)
        ecrits.append(nom)
    return ecrits


# ---------------------------------------------------------------- Cito API (appel)
CITO_BASE = "https://api.citoapi.com/api/v1"


def cito_appel(cle, chemin):
    """Un appel à Cito. Renvoie (code HTTP, en-têtes utiles, objet JSON ou None). La clé reste dans l'en-tête."""
    req = urllib.request.Request(CITO_BASE + chemin, headers={"User-Agent": AGENT, "x-api-key": cle,
                                                              "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            code, entetes, brut = r.status, r.headers, r.read()
    except urllib.error.HTTPError as e:
        code, entetes, brut = e.code, e.headers, e.read()
    except Exception as e:  # noqa: BLE001
        return None, {}, {"erreur_reseau": type(e).__name__}
    utiles = {k: v for k, v in (entetes or {}).items() if "limit" in k.lower() or "quota" in k.lower()
              or "remaining" in k.lower()}
    try:
        return code, utiles, json.loads(brut.decode("utf-8", errors="replace"))
    except ValueError:
        return code, utiles, None


# ---------------------------------------------------------------- Cito API (collecte)
# Quota gratuit : 500 appels par période de 30 jours, 10 par minute. Chaque appel est rentabilisé :
#  - résultats d'une journée entière par page de 200 lignes, statistiques comprises (include=stats),
#    filtrés sur le circuit masculin quand l'API l'accepte ;
#  - classement ATP complet (jusqu'à 5 000 rangs, avec les points) en un appel par semaine ;
#  - calendrier de l'année (tous les tournois, salle ou plein air, taille du tableau) en un appel par mois ;
#  - statistiques manquantes par lots de 50 matchs (facturés 1 appel pour 10 matchs) avec le reliquat.
# Une réserve proportionnelle aux jours restants avant la remise à zéro du quota garantit la collecte
# des nuits suivantes. Les données sont rangées chiffrées (etat/cito-*.json, donnees/cito-*.json).
SRC_CITO = 128
CITO_PAUSE = 6.5            # 10 appels par minute au plus
CITO_MAX_NUIT = 250         # environ 30 minutes de collecte au plus
CITO_RESERVE_JOUR = 5       # appels gardés par jour restant avant la remise à zéro du quota
CITO_LOTS_STATS_NUIT = 30
CITO_STATS = [("aces",), ("double_faults",), ("serve_points", "service_points_played"), ("first_serves_in",),
              ("first_serves_won", "first_serve_points_won"), ("second_serves_won", "second_serve_points_won"),
              ("service_games_played",), ("break_points_saved",), ("break_points_faced",)]
CITO_COLONNES = ["date", "tournoi", "tour", "tour_qualif", "gagnant", "perdant", "score", "issue", "bo",
                 "minutes", "g_rang", "p_rang", "g_entree", "p_entree", "stats", "g_partenaire", "p_partenaire"]


def _entete(entetes, nom):
    for k, v in (entetes or {}).items():
        if k.lower() == nom.lower():
            return v
    return None


class Cito:
    """Appels comptés : quota restant lu dans les en-têtes, coût mesuré par type d'appel."""

    def __init__(self, cle, pages_par_jour=2.5):
        self.cle = cle
        self.besoin_jour = 2 * pages_par_jour + 0.5   # deux journées relues chaque nuit + classement
        self.restant = self.reset = None
        self.appels = 0
        self.cout = defaultdict(lambda: [0, 0])

    def reserve(self):
        if not self.reset:
            return 40
        jours = max(0.0, (self.reset - time.time()) / 86400)
        return max(8, int(jours * min(CITO_RESERVE_JOUR, self.besoin_jour)) + 3)

    def peut(self, unites=1):
        if self.appels >= CITO_MAX_NUIT:
            return False
        return self.restant is None or self.restant - unites >= self.reserve()

    def appel(self, genre, chemin):
        code, obj = None, None
        for essai in range(2):
            avant = self.restant
            code, entetes, obj = cito_appel(self.cle, chemin)
            self.appels += 1
            try:
                self.restant = int(_entete(entetes, "X-RateLimit-Monthly-Remaining"))
            except (TypeError, ValueError):
                pass
            try:
                self.reset = int(float(_entete(entetes, "X-RateLimit-Monthly-Reset")))
            except (TypeError, ValueError):
                pass
            if avant is not None and self.restant is not None:
                self.cout[genre][0] += 1
                self.cout[genre][1] += max(0, avant - self.restant)
            time.sleep(CITO_PAUSE)
            if code == 429 and essai == 0:
                time.sleep(65)
                continue
            break
        return code, obj


def cito_items(obj):
    if not isinstance(obj, dict):
        return []
    for k in ("items", "data", "matches", "results"):
        v = obj.get(k)
        if isinstance(v, list):
            return v
        if isinstance(v, dict) and isinstance(v.get("items"), list):
            return v["items"]
    return []


def cito_stats_cote(d):
    if not isinstance(d, dict):
        return None
    out = []
    for noms in CITO_STATS:
        v = next((d[n] for n in noms if d.get(n) is not None), None)
        try:
            out.append(int(v) if v is not None else None)
        except (TypeError, ValueError):
            out.append(None)
    return out if any(x is not None for x in out) else None


def cito_stats(obj):
    """Statistiques au format de l'archive (9 du gagnant puis 9 du perdant).
    [] = absentes pour ce match ; None = inconnues (pas demandées, ou attendues plus tard)."""
    if not isinstance(obj, dict):
        return None
    st = obj.get("stats")
    if obj.get("stats_available") is False or (not isinstance(st, dict) and "stats_available" in obj):
        cov = obj.get("stats_coverage") or {}
        return None if cov.get("expected_later") else []
    if not isinstance(st, dict):
        return None
    w, l = st.get("winner"), st.get("loser")
    if w is None and isinstance(st.get("player1"), dict):
        p1_gagne = bool((obj.get("player1") or {}).get("is_winner"))
        w, l = (st["player1"], st.get("player2")) if p1_gagne else (st.get("player2"), st["player1"])
    sw, sl = cito_stats_cote(w), cito_stats_cote(l)
    if not sw and not sl:
        return []
    return (sw or [None] * 9) + (sl or [None] * 9)


def cito_score(item):
    """Score vu du vainqueur, au format de l'archive : '6-4 7-6(5)', ' RET' si abandon, 'W/O' si forfait."""
    issue = (item.get("outcome") or item.get("status") or "").upper()
    if "WALKOVER" in issue or issue in ("W/O", "WO"):
        return "W/O"
    morceaux = []
    for s in item.get("sets") or []:
        w, l = s.get("winner_games"), s.get("loser_games")
        if w is None or l is None:
            morceaux = []
            break
        x = f"{w}-{l}"
        tb = s.get("tiebreak") or {}
        if isinstance(tb, dict) and tb.get("loser_points") is not None and {w, l} == {7, 6}:
            x += f"({tb['loser_points']})"
        morceaux.append(x)
    score = " ".join(morceaux) if morceaux else re.sub(r"[,;]", " ", item.get("score") or "").strip()
    if "RETIRE" in issue and not re.search(r"(?i)\bret", score):
        score += " RET"
    return re.sub(r"\s+", " ", score).strip()


def cito_compacter(item, joueurs, tournois):
    """Une ligne de résultat Cito -> (identifiant, ligne compacte) ; rien pour le circuit féminin."""
    tour_c = (item.get("tour") or "").upper()
    if tour_c and tour_c != "ATP":
        return None, "circuit_feminin_ignore"
    mid = str(item.get("id") or item.get("match_id") or item.get("canonical_id") or "")
    w, l = item.get("winner") or {}, item.get("loser") or {}
    wid, lid = str(item.get("winner_id") or w.get("id") or ""), str(item.get("loser_id") or l.get("id") or "")
    date = (item.get("match_date") or item.get("starts_at") or "")[:10]
    if not (mid and wid and lid and date):
        return None, "incomplete"
    for pid, d in ((wid, w), (lid, l)):
        if d.get("name"):
            joueurs[pid] = [d["name"], d.get("ioc")]
    part = []
    for cote in ("winner", "loser"):
        pp = item.get(f"{cote}_partner") or {}
        ppid = item.get(f"{cote}_partner_id") or (pp.get("id") if isinstance(pp, dict) else None)
        if ppid and isinstance(pp, dict) and pp.get("name"):
            joueurs[str(ppid)] = [pp["name"], pp.get("ioc")]
        part.append(str(ppid) if ppid else None)
    tid = str(item.get("tournament_id") or "")
    t = tournois.setdefault(tid, {})
    for src, k in (("tournament_name", "nom"), ("level", "level"), ("category", "category"),
                   ("edition_category", "edition_category"), ("surface", "surface"), ("year", "annee")):
        if item.get(src) is not None:
            t[k] = item[src]
    ligne = [date, tid, item.get("round"), item.get("qualifying_round"), wid, lid, cito_score(item),
             (item.get("outcome") or item.get("status") or "")[:12], item.get("best_of"),
             item.get("duration_minutes"), w.get("rank"), l.get("rank"), w.get("entry"), l.get("entry"),
             cito_stats(item), part[0], part[1]]
    return (mid, ligne), "gardee"


def collecter_cito(cle, code, fin_sackmann):
    """Collecte de la nuit. Renvoie (cache par mois, méta) ; tout est relu et réécrit chiffré."""
    suivi = lire_json(os.path.join(ETAT, "cito-suivi.json"), {})
    suivi.setdefault("v", 1)
    jours = suivi.setdefault("jours", {})
    params = suivi.setdefault("parametres", {"taille": 200, "stats": True, "tour": True})
    meta_ch = os.path.join(ETAT, "cito-meta.json")
    meta = lire_chiffre(meta_ch, code, {"tournois": {}, "classement": None})
    meta_avant = json.dumps(meta, sort_keys=True)
    mois = {}
    for nom in sorted(os.listdir(ETAT)) if os.path.isdir(ETAT) else []:
        m = re.match(r"cito-(\d{4}-\d{2})\.json$", nom)
        if m:
            mois[m.group(1)] = lire_chiffre(os.path.join(ETAT, nom), code, {"matchs": {}, "joueurs": {}})
    pages = [j["pages"] for j in jours.values() if j.get("pages")]
    api = Cito(cle, sum(pages) / len(pages) if pages else 2.5)
    st = Counter()
    aujourd = dt.date.today()
    debut = dt.date.fromisoformat(fin_sackmann) - dt.timedelta(days=7)
    limite_finale = (aujourd - dt.timedelta(days=2)).isoformat()

    def chemin_jour(d, page):
        q = [f"date={d}", f"page={page}", f"page_size={params['taille']}", f"limit={params['taille']}"]
        if params["stats"]:
            q.append("include=stats")
        if params["tour"]:
            q.append("tour=ATP")
        return "/tennis/matches/completed?" + "&".join(q)

    def lire_jour(d):
        page, lignes, feminin = 1, 0, 0
        while True:
            if not api.peut():
                st["jours_interrompus_quota"] += 1
                return False
            code_http, obj = api.appel("journee", chemin_jour(d, page))
            if code_http in (400, 422) and page == 1:
                # paramètre refusé : on simplifie la requête, un réglage à la fois
                if params["taille"] > 100:
                    params["taille"] = 100
                    continue
                if params["tour"]:
                    params["tour"] = False
                    continue
                if params["stats"]:
                    params["stats"] = False
                    continue
            if code_http != 200 or not isinstance(obj, dict):
                st[f"journee_http_{code_http}"] += 1
                J.info(f"Cito {d} page {page} : HTTP {code_http}")
                e = jours.setdefault(d, {})
                e["erreurs"] = e.get("erreurs", 0) + 1
                e["final"] = e["erreurs"] >= 3 and d <= limite_finale   # on n'insiste pas au-delà de 3 nuits
                return False
            n_app, n_un = api.cout["journee"]
            if params["stats"] and n_app >= 3 and n_un / n_app > 2.5:
                # include=stats facturé au match : on passe aux lots de statistiques, limités à ATP et Challenger
                params["stats"] = False
                J.alerte(f"Cito : include=stats coûte {n_un / n_app:.1f} appels par page, abandonné au profit des lots")
            items = cito_items(obj)
            st["lignes_recues"] += len(items)
            for it in items:
                joueurs = {}
                res, etat = cito_compacter(it, joueurs, meta["tournois"])
                st["lignes_" + etat] += 1
                feminin += etat == "circuit_feminin_ignore"
                if res is None:
                    continue
                mid, ligne = res
                c = mois.setdefault(ligne[0][:7], {"matchs": {}, "joueurs": {}})
                ancien = c["matchs"].get(mid)
                if ancien and ligne[14] is None and ancien[14] is not None:
                    ligne[14] = ancien[14]
                c["matchs"][mid] = ligne
                c["joueurs"].update(joueurs)
                lignes += 1
                st["avec_stats"] += bool(ligne[14])
            total_pages = obj.get("total_pages") or 1
            if obj.get("has_next") is True or page < total_pages:
                page += 1
                if page <= 60:
                    continue
            break
        if feminin and params["tour"]:
            st["filtre_circuit_sans_effet"] += 1
        jours[d] = {"pages": page, "lignes_atp": lignes, "final": d <= limite_finale, "le": aujourd.isoformat()}
        return True

    # 1. les deux dernières journées (la veille est relue le lendemain pour les résultats tardifs) ;
    #    collecte lancée à la main : aussi les matchs déjà terminés aujourd'hui
    jours_a_lire = [(aujourd - dt.timedelta(days=1)).isoformat(), limite_finale]
    if os.environ.get("GITHUB_EVENT_NAME") == "workflow_dispatch":
        jours_a_lire.insert(0, aujourd.isoformat())
    for d in jours_a_lire:
        if not jours.get(d, {}).get("final"):
            lire_jour(d)
    # 2. classement ATP complet, une fois par semaine
    lundi_courant = lundi(aujourd.isoformat())
    cl = meta.get("classement") or {}
    # au plus deux lectures par jour (une seconde si la première n'a rapporté que 100 rangs)
    essais_jour = suivi.get("classement_essais", {}).get(aujourd.isoformat(), 0)
    if (cl.get("date") or "") < lundi_courant and essais_jour < 2 and api.peut():
        suivi["classement_essais"] = {aujourd.isoformat(): essais_jour + 1}
        liste, date_cl, page, pages = [], None, 1, 1
        diag = J.chiffres.setdefault("cito_classement_reponses", [])
        vus = set()
        while page <= pages and page <= 25 and api.peut():
            code_http, obj = api.appel("classement", f"/tennis/rankings/atp?page={page}&page_size=100&limit=100&offset={(page - 1) * 100}")
            items = cito_items(obj)
            # diagnostic : tout ce que la réponse dit de la pagination (sans la liste)
            if isinstance(obj, dict):
                diag.append({"page": page, "http": code_http, "items": len(items),
                             "premier_rang": items[0].get("rank") if items else None,
                             "dernier_rang": items[-1].get("rank") if items else None,
                             **{k: v for k, v in obj.items() if k not in ("items", "data", "results")}})
            if code_http != 200 or not items:
                st[f"classement_http_{code_http}"] += 1
                break
            nouveaux = [it for it in items if (it.get("rank"), str(it.get("player_id"))) not in vus]
            if not nouveaux:   # paramètre de page ignoré : même liste renvoyée
                st["classement_page_ignoree"] += 1
                pages = page - 1
                break
            vus.update((it.get("rank"), str(it.get("player_id"))) for it in items)
            items = nouveaux
            for it in items:
                pid = str(it.get("player_id") or it.get("id") or "")
                if pid and it.get("rank") is not None:
                    liste.append([it.get("rank"), pid, it.get("player_name") or it.get("name"), it.get("ioc"),
                                  it.get("points"), it.get("tournaments_played")])
            date_cl = date_cl or (obj.get("ranking_date") or "")[:10]
            # Cito renvoie 100 joueurs par page ; sans indication du nombre de pages, on continue tant que la page est pleine
            cov = obj.get("list_coverage") or {}
            profondeur = cov.get("deepest_rank") or cov.get("ranked_players") or 0
            if obj.get("total_pages"):   # le plan gratuit annonce 1 page (100 rangs) : on s'y fie, sans appel inutile
                pages = int(obj["total_pages"])
            else:
                pages = max(-(-int(profondeur) // 100) if profondeur else 0,
                            page + 1 if obj.get("has_next") or len(items) >= 100 else page)
            page += 1
        st["classement_pages"] = page - 1
        if liste and (page > pages or page > 25):   # liste complète, ou 25 pages au plus
            meta["classement"] = {"date": date_cl or aujourd.isoformat(),
                                  "colonnes": ["rang", "id_cito", "nom", "pays", "points", "tournois"],
                                  "liste": liste}
            st["classement_rangs"] = len(liste)
        elif liste:
            suivi.pop("classement_essais", None)   # interrompu par le quota : on reprendra la nuit suivante
    # 3. calendrier (salle ou plein air, taille du tableau, dates), une fois par mois et par année utile
    cal = suivi.setdefault("calendrier", {})
    for annee in range(debut.year, aujourd.year + 1):
        if cal.get(str(annee), "") >= (aujourd - dt.timedelta(days=30)).isoformat() or not api.peut():
            continue
        code_http, obj = api.appel("calendrier", f"/tennis/tournaments/calendar?year={annee}")
        if code_http == 200:
            n = 0
            for it in cito_items(obj):
                if (it.get("tour") or "").upper() != "ATP" or not it.get("id"):
                    continue
                t = meta["tournois"].setdefault(str(it["id"]), {})
                for src, k in (("name", "nom"), ("level", "level"), ("category", "category"),
                               ("edition_category", "edition_category"), ("surface", "surface"),
                               ("indoor", "indoor"), ("draw_size", "draw_size"), ("start_date", "debut"),
                               ("end_date", "fin"), ("city", "ville"), ("country_code", "pays"), ("year", "annee")):
                    if it.get(src) is not None:
                        t[k] = it[src]
                n += 1
            cal[str(annee)] = aujourd.isoformat()
            st[f"calendrier_{annee}_tournois_atp"] = n
    # 4. rattrapage depuis la fin de l'archive, des plus récentes journées aux plus anciennes
    d = aujourd - dt.timedelta(days=3)
    while d >= debut:
        iso_d = d.isoformat()
        if not jours.get(iso_d, {}).get("final"):
            if not lire_jour(iso_d):
                if not api.peut():
                    break
        d -= dt.timedelta(days=1)
    restants = sum(1 for k in range((aujourd - debut).days - 2)
                   if not jours.get((debut + dt.timedelta(days=k)).isoformat(), {}).get("final"))
    # 5. statistiques encore absentes (ATP et Challenger, simple), par lots de 50, avec le reliquat
    niveaux_stats = {"challenger", "atp_tour", "masters_1000", "grand_slam"}
    candidats = []
    for c in mois.values():
        for mid, l in c["matchs"].items():
            if l[14] is None and l[0] <= limite_finale and not l[15] and \
                    (meta["tournois"].get(l[1], {}).get("category") or "challenger") in niveaux_stats:
                candidats.append((l[0], mid, l))
    candidats.sort(reverse=True)
    lots = 0
    while candidats and lots < CITO_LOTS_STATS_NUIT and api.peut(5):
        lot, candidats = candidats[:50], candidats[50:]
        code_http, obj = api.appel("statistiques_lot", "/tennis/matches/stats?ids=" +
                                   ",".join(urllib.parse.quote(m, safe="") for _, m, _ in lot))
        lots += 1
        if code_http != 200:
            st[f"stats_lot_http_{code_http}"] += 1
            break
        par_id = {}
        for it in cito_items(obj) or ([obj] if isinstance(obj, dict) and obj.get("match_id") else []):
            if isinstance(it, dict):
                par_id[str(it.get("match_id") or it.get("id") or "")] = cito_stats(it)
        for _, mid, l in lot:
            s = par_id.get(mid)
            l[14] = s if s is not None else []
            st["stats_lot_obtenues" if s else "stats_lot_absentes"] += 1
    # enregistrement (chiffré ; seulement ce qui a changé)
    for m, contenu in mois.items():
        ecrire_chiffre(os.path.join(ETAT, f"cito-{m}.json"), contenu, code)
    if json.dumps(meta, sort_keys=True) != meta_avant:
        ecrire_chiffre(meta_ch, meta, code)
    suivi["quota"] = {"restant": api.restant, "remise_a_zero": dt.datetime.fromtimestamp(
        api.reset, dt.timezone.utc).isoformat(timespec="minutes") if api.reset else None, "le": aujourd.isoformat()}
    ecrire_json(os.path.join(ETAT, "cito-suivi.json"), suivi, compact=False)
    nb = sum(len(c["matchs"]) for c in mois.values())
    J.chiffres["cito"] = {
        "appels_cette_nuit": api.appels, "quota_restant": api.restant, "reserve_gardee": api.reserve(),
        "remise_a_zero": suivi["quota"]["remise_a_zero"],
        "cout_mesure": {k: {"appels": v[0], "unites": v[1]} for k, v in api.cout.items()},
        "lignes_par_appel_journee": round(st["lignes_recues"] / max(1, api.cout["journee"][0] or 1), 1),
        "parametres": params, "journees_restant_a_rattraper": restants,
        "matchs_atp_en_cache": nb, "details": dict(st)}
    J.info(f"Cito : {api.appels} appels, {nb} matchs en cache, {restants} journées à rattraper, "
           f"quota restant {api.restant}")
    return mois, meta


def niveau_cito(t, nom):
    cat = (t.get("category") or "").lower()
    lv = str(t.get("level") or "").upper()
    ed = str(t.get("edition_category") or "")
    if cat == "grand_slam" or lv == "G":
        n = "G"
    elif cat == "masters_1000" or lv == "M":
        n = "M"
    elif cat == "challenger" or lv == "C":
        n = "C"
    elif lv == "J" or "junior" in cat:
        return "J"
    elif cat == "itf" or re.match(r"(15|25)(\+H)?$", lv) or re.match(r"M(15|25)", ed):
        n = "I15" if "15" in ed or lv == "15" else ("I25" if "25" in ed or lv == "25" else "I")
    elif cat == "davis_cup" or lv == "D":
        n = "D"
    elif "final" in cat or lv == "F":
        n = "F"
    elif "olymp" in cat or lv == "O":
        n = "O"
    elif cat == "atp_tour" or lv == "A":
        n = "A"
    else:
        return None
    return niveau_par_nom(n, nom)


def tour_cito(rnd, qualif, taille):
    if qualif:
        return str(qualif).upper()
    r = str(rnd or "").upper()
    if r.startswith("Q"):
        return r if re.match(r"Q\d$", r) else "Q"
    return tour_relatif(r, taille)


def integrer_cito(base, mois, meta, fin_sackmann, resultat_tml):
    """Complément chiffré tiré de Cito, même forme que celui de TennisMyLife."""
    stats = Counter()
    fenetre = (dt.date.fromisoformat(fin_sackmann) - dt.timedelta(days=7)).isoformat()
    autres, seuls_tml = {}, defaultdict(list)
    for annee, contenu in (resultat_tml or {}).items():
        autres.update(contenu.get("joueurs", {}))
        for m in contenu.get("matchs", []):
            t = contenu.get("tournois", {}).get(m[0])
            debut_t = t[4] if t else (base.tournois[m[0]]["debut"] if m[0] in base.tournois else None)
            seuls_tml[frozenset((m[2], m[3]))].append(debut_t)
    rap = Rapprocheur(base, fin_sackmann, stats, "c", autres)
    joueurs_c, lignes = {}, []
    for c in mois.values():
        joueurs_c.update(c["joueurs"])
        lignes.extend(c["matchs"].values())
    lignes.sort(key=lambda x: x[0])
    rmax, debut_t = defaultdict(int), {}
    for l in lignes:
        m = re.match(r"R(\d+)$", str(l[2] or "").upper())
        if m and not l[3]:
            rmax[l[1]] = max(rmax[l[1]], int(m.group(1)))
        debut_t[l[1]] = min(debut_t.get(l[1], l[0]), l[0])

    def jid(cid):
        j = joueurs_c.get(cid) or [cid, None]
        return rap.joueur(cid, j[0] or cid, j[1])

    complements, seuls, vote, salles = defaultdict(list), [], defaultdict(Counter), {}
    stats_cat = Counter()
    for l in lignes:
        date, tid, rnd, q, wid, lid, score, issue, bo, minutes, wr, lr, _we, _le, stl, wp, lp = l
        if wp or lp:
            stats["doubles_gardes_pour_plus_tard"] += 1
            continue
        if date < fenetre:
            stats["avant_fenetre"] += 1
            continue
        t = meta["tournois"].get(tid, {})
        nom_t = t.get("nom") or tid
        niveau = niveau_cito(t, nom_t)
        ed = str(t.get("edition_category") or "")
        if niveau == "J":
            stats["juniors_ignores"] += 1
            continue
        if niveau == "D" or ("cup" in ed.lower() and niveau == "A"):
            stats["equipes_ignorees"] += 1
            continue
        if niveau is None:
            stats["niveau_inconnu"] += 1
            stats_cat[f"{t.get('category')}/{t.get('level')}"] += 1
            continue
        est_q = bool(q) or str(rnd or "").upper().startswith("Q")
        if niveau.startswith("I") and est_q:
            stats["qualifs_itf_ignorees"] += 1
            continue
        tour = tour_cito(rnd, q, t.get("draw_size") or rmax.get(tid) or None)
        try:
            bo = int(bo)
        except (TypeError, ValueError):
            bo = 5 if niveau == "G" and not est_q else 3
        g, p = jid(wid), jid(lid)
        sc, drap = analyser_score(score, bo)
        if not drap & (COMPLET | ABANDON | FORFAIT) and score:
            sc2, d2 = analyser_score(inverser_score(score), bo)
            if d2 & COMPLET:
                sc, drap = sc2, d2
                stats["scores_retournes"] += 1
        drap |= SRC_CITO
        st = None
        if isinstance(stl, list) and len(stl) == 18:
            st = [minutes] + stl + [wr, None, lr, None]
        elif minutes is not None or wr is not None or lr is not None:
            st = [minutes] + [None] * 18 + [wr, None, lr, None]
        a_stats = bool(st and any(x is not None for x in st[1:19]))
        trouve = None
        for i in rap.paires.get(frozenset((g, p)), []):
            m = base.simples[i]
            ecart = (dt.date.fromisoformat(date) - dt.date.fromisoformat((m["date"] or m["debut"])[:10])).days
            # sans date de match, on compare au début du tournoi (qualifications : la semaine d'avant)
            if (m["date"] and abs(ecart) <= 3) or (not m["date"] and -10 <= ecart <= 20):
                trouve = i
                break
        if trouve is not None:
            m = base.simples[trouve]
            vote[tid][m["t"]] += 1
            if t.get("indoor") is not None and base.tournois[m["t"]].get("salle") is None:
                salles[m["t"]] = 1 if t["indoor"] else 0
            if not m["dr"] & (SRC_VBT | SRC_WIKI):
                stats["deja_dans_archive"] += 1
                continue
            if m["g"] != g:
                # Cito désigne l'autre joueur. On corrige seulement si le score publié le désigne aussi
                # (score complet une fois retourné) ou s'il est vide ; sinon on garde la version publique.
                _, d_pub = analyser_score(m.get("score") or "", bo)
                _, d_inv = analyser_score(inverser_score(m.get("score") or ""), bo)
                if drap & (COMPLET | ABANDON | FORFAIT) and not d_pub & COMPLET and \
                        (d_inv & COMPLET or not (m.get("score") or "").strip()):
                    complements[base.tournois[m["t"]]["annee"]].append(
                        [m["t"], m["g"], m["p"], sc, drap, st if a_stats else None, 1])
                    stats["vainqueur_corrige"] += 1
                else:
                    stats["vainqueur_different_ignore"] += 1
                continue
            nouveau = sc if drap & (COMPLET | ABANDON | FORFAIT) and not m["dr"] & COMPLET else None
            st_ok = st if a_stats and not m.get("st") else None
            stats["scores_completes"] += nouveau is not None
            stats["statistiques_ajoutees"] += st_ok is not None
            if nouveau is None and st_ok is None:
                stats["rien_a_ajouter"] += 1
                continue
            complements[base.tournois[m["t"]]["annee"]].append(
                [m["t"], m["g"], m["p"], nouveau, drap if nouveau is not None else None, st_ok])
            continue
        if any(dd and -25 <= (dt.date.fromisoformat(date) - dt.date.fromisoformat(dd)).days <= 25
               for dd in seuls_tml.get(frozenset((g, p)), [])):
            stats["deja_dans_tennismylife"] += 1
            continue
        m_cat = re.search(r"\b(250|500)\b", ed)
        salle = None if t.get("indoor") is None else (1 if t["indoor"] else 0)
        seuls.append((tid, [nom_t, niveau, t.get("surface"), salle, t.get("debut") or debut_t[tid], bo,
                            m_cat.group(1) if m_cat else None], [tour, g, p, sc, date, drap, st], niveau))
    resultat = defaultdict(lambda: {"tournois": {}, "joueurs": {}, "complements": [], "matchs": [],
                                    "classements": {}})
    for annee, liste in complements.items():
        resultat[annee]["complements"] = liste
    for ctid, t, ligne, niveau in seuls:
        tid = vote[ctid].most_common(1)[0][0] if vote.get(ctid) else "c" + re.sub(r"[^A-Za-z0-9-]", "", ctid)
        annee = base.tournois[tid]["annee"] if tid in base.tournois else int(t[4][:4])
        res = resultat[annee]
        if tid not in base.tournois and tid not in res["tournois"]:
            res["tournois"][tid] = t
        for pid in (ligne[1], ligne[2]):
            if pid in rap.nouveaux:
                res["joueurs"][pid] = rap.nouveaux[pid]
        res["matchs"].append([tid] + ligne)
        stats["matchs_absents_ailleurs_" + niveau] += 1
    cl = meta.get("classement")
    if cl and cl.get("liste"):
        an = int(cl["date"][:4])
        res = resultat[an]
        liste = []
        for rang, cid, nom, pays, pts, nb in cl["liste"]:
            pid = rap.joueur(cid, nom or cid, pays)
            if pid in rap.nouveaux:
                res["joueurs"][pid] = rap.nouveaux[pid]
            liste.append([rang, pid, pts, nb])
        res["classement_officiel"] = {"semaine": cl["date"], "colonnes": ["rang", "joueur", "points", "tournois"],
                                      "liste": liste}
    if resultat:
        resultat[max(resultat)]["salles"] = salles
    # diagnostic : pourquoi un match publié reste sans score complet (comptes et noms de tournois seulement)
    paires_cito = defaultdict(list)
    for l in lignes:
        if not (l[15] or l[16]) and l[0] >= fenetre:
            paires_cito[frozenset((jid(l[4]), jid(l[5])))].append(l)
    completes = {(c[0], c[1], c[2]) for liste in complements.values() for c in liste if c[4] is not None}
    raisons, absents = Counter(), Counter()
    for m in base.simples:
        if m["debut"] < fenetre or m["dr"] & (COMPLET | ABANDON | FORFAIT) or (m["t"], m["g"], m["p"]) in completes:
            continue
        if not m["dr"] & (SRC_VBT | SRC_WIKI):
            continue
        cands = paires_cito.get(frozenset((m["g"], m["p"])), [])
        if not cands:
            raisons["absent_de_cito_ou_noms_differents"] += 1
            tr = base.tournois[m["t"]]
            absents[f"{tr['nom']} ({tr['debut']})"] += 1
        elif all(analyser_score(c[6], 3)[1] & (COMPLET | ABANDON | FORFAIT) == 0 for c in cands):
            raisons["dans_cito_score_incomplet"] += 1
        else:
            raisons["dans_cito_autre_raison"] += 1
    J.chiffres["cito_trous_restants"] = {"raisons": dict(raisons),
                                         "tournois_absents_de_cito": dict(absents.most_common(15))}
    J.chiffres["cito_integration"] = dict(stats, categories_inconnues=dict(stats_cat.most_common(10)))
    J.info("Cito intégré : " + ", ".join(f"{k}={v}" for k, v in sorted(stats.items())))
    return dict(resultat)


# ---------------------------------------------------------------- Photos libres (Wikidata, Wikimedia Commons)
# Une requête Wikidata (CC0) par nuit ramène tous les joueurs qui ont un identifiant ATP (P536),
# avec photo (P18), poids (P2067), taille (P2048) et date de naissance. Rapprochement avec nos joueurs
# par date de naissance et nom, sinon par nom seul s'il est unique. Pour chaque photo, Commons donne
# la miniature, l'auteur et la licence (affichés sous la photo dans l'appli), par lots de 50.
WIKIDATA_SPARQL = "https://query.wikidata.org/sparql"
COMMONS_API = "https://commons.wikimedia.org/w/api.php"
PHOTOS_ETAT = os.path.join(ETAT, "photos-commons.json")
PHOTOS_RELECTURE_JOURS = 120
PHOTOS_LOTS_NUIT = 200
REQUETE_WD = """SELECT ?item ?atp ?nom ?naissance ?image ?masse ?taille WHERE {
  ?item wdt:P536 ?atp .
  %s
  OPTIONAL { ?item wdt:P569 ?naissance }
  OPTIONAL { ?item p:P2067/psn:P2067/wikibase:quantityAmount ?masse }
  OPTIONAL { ?item p:P2048/psn:P2048/wikibase:quantityAmount ?taille }
  OPTIONAL { ?item rdfs:label ?nom . FILTER(LANG(?nom) = "en") }
}"""


def wikidata_joueurs():
    """{qid: {nom, naissance, image, poids, taille, atp}} ; repli sur les seuls joueurs avec photo."""
    for filtre in ("OPTIONAL { ?item wdt:P18 ?image }", "?item wdt:P18 ?image ."):
        url = WIKIDATA_SPARQL + "?" + urllib.parse.urlencode({"query": REQUETE_WD % filtre, "format": "json"})
        try:
            data = json.loads(telecharger(url, {"Accept": "application/sparql-results+json",
                                                "Accept-Encoding": "gzip"}, essais=3, delai=20))
            break
        except Exception as e:  # noqa: BLE001
            J.info(f"Wikidata : requête refusée ({str(e)[:150]}), essai plus léger")
    else:
        raise RuntimeError("Wikidata injoignable")
    items = {}
    for b in data.get("results", {}).get("bindings", []):
        v = lambda k: b.get(k, {}).get("value")  # noqa: E731
        q = (v("item") or "").rsplit("/", 1)[-1]
        if not q:
            continue
        it = items.setdefault(q, {"atp": v("atp")})
        if v("nom") and not it.get("nom"):
            it["nom"] = v("nom")
        if v("naissance") and not it.get("naissance"):
            it["naissance"] = v("naissance")[:10]
        if v("image") and not it.get("image"):
            it["image"] = urllib.parse.unquote(v("image").rsplit("/", 1)[-1]).replace("_", " ")
        try:
            if v("masse") and not it.get("poids"):
                p = float(v("masse"))
                it["poids"] = round(p) if 45 <= p <= 150 else None
            if v("taille") and not it.get("taille"):
                t = float(v("taille")) * 100
                it["taille"] = round(t) if 150 <= t <= 230 else None
        except ValueError:
            pass
    return items


def rapprocher_wikidata(joueurs, items, stats):
    """joueurs : {pid: (nom, naissance)} -> {pid: qid}."""
    import difflib
    par_naiss, par_cle = defaultdict(list), defaultdict(list)
    for q, it in items.items():
        if it.get("nom"):
            par_cle[cle_nom(it["nom"])].append(q)
            if it.get("naissance"):
                par_naiss[it["naissance"]].append(q)
    res = {}
    for pid, (nom, naiss) in joueurs.items():
        cle = cle_nom(nom)
        if not cle:
            continue
        mots = set(cle.split())
        q = None
        if naiss and par_naiss.get(naiss):
            cands = [x for x in par_naiss[naiss]
                     if mots & set(cle_nom(items[x]["nom"]).split())
                     or difflib.SequenceMatcher(None, cle, cle_nom(items[x]["nom"])).ratio() >= 0.75]
            if len(cands) == 1:
                q = cands[0]
                stats["rapproches_naissance_et_nom"] += 1
        if q is None and len(par_cle.get(cle, [])) == 1:
            it = items[par_cle[cle][0]]
            if naiss and it.get("naissance") and it["naissance"] != naiss:
                stats["ecartes_naissance_differente"] += 1
            else:
                q = par_cle[cle][0]
                stats["rapproches_nom_seul"] += 1
        if q:
            res[pid] = q
    return res


def _texte_html(h):
    import html
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", h or ""))).strip()[:160]


def commons_infos(fichiers, stats):
    """{fichier: [miniature, auteur, licence, lien_licence, date]} pour une liste de fichiers Commons."""
    out = {}
    jour = dt.date.today().isoformat()
    for i in range(0, len(fichiers), 50):
        lot = fichiers[i:i + 50]
        params = {"action": "query", "prop": "imageinfo", "iiprop": "extmetadata|url", "iiurlwidth": "320",
                  "iiextmetadatafilter": "Artist|LicenseShortName|LicenseUrl|Credit",
                  "titles": "|".join("File:" + f for f in lot), "format": "json", "formatversion": "2",
                  "maxlag": "5"}
        data = json.loads(telecharger(COMMONS_API + "?" + urllib.parse.urlencode(params),
                                      {"Accept-Encoding": "gzip"}))
        q = data.get("query", {})
        renvoi = {n["to"]: n["from"] for n in q.get("normalized", [])}
        for p in q.get("pages", []):
            titre = renvoi.get(p.get("title"), p.get("title", ""))
            f = titre.split(":", 1)[-1]
            ii = (p.get("imageinfo") or [{}])[0]
            em = ii.get("extmetadata") or {}
            g = lambda k: (em.get(k) or {}).get("value")  # noqa: E731
            if p.get("missing") or not ii.get("thumburl") or not g("LicenseShortName"):
                out[f] = [None, None, None, None, jour]
                stats["photos_inutilisables"] += 1
                continue
            out[f] = [ii["thumburl"], _texte_html(g("Artist")) or _texte_html(g("Credit")) or "auteur non indiqué",
                      _texte_html(g("LicenseShortName")), g("LicenseUrl"), jour]
        stats["requetes_commons"] += 1
        time.sleep(1)
    return out


COMMONS_API = "https://commons.wikimedia.org/w/api.php"
TABLE_CLASSEMENT = "ATP_singles_ranking.tab"
LICENCES_OK = ("CC0", "CC-BY", "CC BY", "PD")


def _cle_nom(txt):
    t = unicodedata.normalize("NFKD", txt or "").encode("ascii", "ignore").decode().lower()
    return " ".join(re.sub(r"[^a-z ]", " ", t.replace("-", " ")).split())


def classement_depuis_table(lignes, base, codes_atp):
    """lignes : dicts de la table Commons. Rattache chaque joueur à l'identifiant de l'appli (code ATP, sinon nom + pays unique)."""
    par_nom = {}
    for pid, j in base.joueurs.items():
        par_nom.setdefault((_cle_nom(j["nom"]), j["pays"]), []).append(pid)
    liste, stats = [], Counter()
    for r in lignes:
        try:
            rang, pts = int(r["position"]), int(r["points"])
        except (TypeError, ValueError, KeyError):
            stats["lignes_ignorees"] += 1
            continue
        code = (r.get("atp_code") or "").lower()
        pid = codes_atp.get(code)
        via = "code"
        if not pid:
            c = par_nom.get((_cle_nom(r.get("name")), r.get("country_code")), [])
            pid, via = (c[0], "nom") if len(c) == 1 else (None, "aucun")
        stats["rattaches_" + via] += 1
        liste.append([rang, pts, pid, r.get("name") or "", r.get("country_code") or "", r.get("age"),
                      r.get("positions_difference"), r.get("tournaments_played"), code])
    liste.sort(key=lambda x: x[0])
    return liste, stats


def collecter_classement_commons(base):
    """Classement ATP complet (≈ 2 300 rangs) : table libre de Wikimedia Commons « Data:ATP singles ranking.tab ».
    Écrit donnees/classement.json ; refuse la table si sa licence n'est pas libre."""
    chemin = os.path.join(DONNEES, "classement.json")
    url = f"{COMMONS_API}?action=jsondata&format=json&formatversion=2&title={TABLE_CLASSEMENT}"
    obj = json.loads(telecharger(url, {"Accept": "application/json"}, essais=3, delai=5)).get("jsondata") or {}
    licence = obj.get("license") or ""
    if not licence.upper().startswith(tuple(x.upper() for x in LICENCES_OK)):
        raise RuntimeError(f"licence de la table non libre ou absente : « {licence} »")
    champs = [f.get("name") for f in (obj.get("schema") or {}).get("fields") or []]
    lignes = [dict(zip(champs, ligne)) for ligne in obj.get("data") or []]
    if len(lignes) < 500:
        raise RuntimeError(f"table trop courte ({len(lignes)} lignes)")
    maj = None
    try:
        rev = json.loads(telecharger(f"{COMMONS_API}?action=query&format=json&formatversion=2&prop=revisions&rvprop=timestamp"
                                     f"&titles=Data:{TABLE_CLASSEMENT}", {"Accept": "application/json"}, essais=2, delai=3))
        maj = rev["query"]["pages"][0]["revisions"][0]["timestamp"]
    except Exception as e:  # noqa: BLE001
        J.info(f"Classement Commons : date de modification non lue ({str(e)[:80]})")
    photos = lire_json(os.path.join(DONNEES, "photos.json"), {}) or {}
    codes = {v[8].lower(): pid for pid, v in (photos.get("joueurs") or {}).items() if len(v) > 8 and v[8]}
    liste, stats = classement_depuis_table(lignes, base, codes)
    sortie = {"source": "Wikimedia Commons, Data:ATP singles ranking.tab", "licence": licence, "modifie": maj,
              "colonnes": ["rang", "points", "pid", "nom", "pays", "age", "diff_rang", "tournois", "code_atp"],
              "liste": liste}
    if lire_json(chemin, {}).get("liste") != liste:
        ecrire_json(chemin, sortie)
    J.chiffres["classement_commons"] = {"rangs": len(liste), "licence": licence, "modifie": maj, **dict(stats)}
    J.info(f"Classement Commons : {len(liste)} rangs, licence {licence}, modifié {maj}, {dict(stats)}")
    return "classement.json"


def collecter_photos(base, autres_joueurs):
    """Écrit donnees/photos.json (public : Wikidata CC0, photos sous licence libre)."""
    stats = Counter()
    etat = lire_json(PHOTOS_ETAT, {"fichiers": {}})
    items = wikidata_joueurs()
    stats["joueurs_wikidata"] = len(items)
    stats["joueurs_wikidata_avec_photo"] = sum(1 for it in items.values() if it.get("image"))
    joueurs = {pid: (j["nom"], j.get("naissance")) for pid, j in base.joueurs.items()}
    for pid, j in (autres_joueurs or {}).items():
        joueurs.setdefault(pid, (j[0], j[4] if len(j) > 4 else None))
    corresp = rapprocher_wikidata(joueurs, items, stats)
    # métadonnées Commons : nouvelles photos d'abord, puis relecture des plus anciennes
    utiles = sorted({items[q]["image"] for q in corresp.values() if items[q].get("image")})
    limite = (dt.date.today() - dt.timedelta(days=PHOTOS_RELECTURE_JOURS)).isoformat()
    nouvelles = [f for f in utiles if f not in etat["fichiers"]]
    anciennes = sorted((f for f in utiles if f in etat["fichiers"] and etat["fichiers"][f][4] < limite),
                       key=lambda f: etat["fichiers"][f][4])
    a_lire = (nouvelles + anciennes)[:PHOTOS_LOTS_NUIT * 50]
    stats["photos_a_lire_cette_nuit"] = len(a_lire)
    try:
        etat["fichiers"].update(commons_infos(a_lire, stats))
    except Exception as e:  # noqa: BLE001
        J.alerte(f"Commons : {str(e)[:200]} (les photos déjà connues restent affichées)")
    etat["fichiers"] = {f: v for f, v in etat["fichiers"].items() if f in set(utiles)}
    ecrire_json(PHOTOS_ETAT, etat, compact=False)
    sortie = {}
    for pid, q in sorted(corresp.items()):
        it = items[q]
        f = it.get("image")
        info = etat["fichiers"].get(f) if f else None
        photo = f if info and info[0] else None
        if not (photo or it.get("poids") or it.get("taille")):
            continue
        sortie[pid] = [q, photo, info[0] if photo else None, info[1] if photo else None,
                       info[2] if photo else None, info[3] if photo else None,
                       it.get("poids"), it.get("taille"), it.get("atp")]
        stats["joueurs_avec_photo"] += bool(photo)
        stats["joueurs_avec_poids"] += bool(it.get("poids"))
    ecrire_json(os.path.join(DONNEES, "photos.json"), {
        "maj": dt.date.today().isoformat(),
        "sources": "Wikidata (CC0) ; photos Wikimedia Commons, licence et auteur propres à chaque photo, "
                   "à afficher sous la photo",
        "colonnes": ["wikidata", "fichier_commons", "miniature", "auteur", "licence", "lien_licence",
                     "poids_kg", "taille_cm", "code_atp"],
        "joueurs": sortie}, compact=False)
    J.chiffres["photos"] = dict(stats)
    J.info(f"Photos : {stats['joueurs_avec_photo']} joueurs avec photo libre, "
           f"{stats['joueurs_avec_poids']} avec poids")
    return "photos.json"



# ---------------------------------------------------------------- Actualités (flux RSS publics)
# Seuls le titre, la source, la date et le lien sont gardés (jamais le texte des articles).
# Lancé toutes les 2 heures par actus.yml (python collecteur.py --actus-seulement).
# Flux RSS publics. Pour chaque source, plusieurs adresses possibles : la première qui répond est gardée.
# (source, langue, [adresses])
FLUX_ACTUS = [
    ("L'Équipe", "fr", ["https://dwh.lequipe.fr/api/edito/rss?path=/Tennis/"]),
    ("Tennis Majors", "fr", ["https://www.tennismajors.com/fr/feed", "https://www.tennismajors.com/fr/feed/"]),
    ("Eurosport", "fr", ["https://www.eurosport.fr/tennis/rss.xml", "https://www.eurosport.fr/rss.xml"]),
    ("We Love Tennis", "fr", ["https://www.welovetennis.fr/feed", "https://www.welovetennis.fr/feed/"]),
    ("Tennis Actu", "fr", ["https://www.tennisactu.net/feed/", "https://www.tennisactu.net/feed", "https://www.tennisactu.net/rss.xml"]),
    ("RMC Sport", "fr", ["https://rmcsport.bfmtv.com/rss/tennis/"]),
    ("franceinfo", "fr", ["https://www.francetvinfo.fr/sports/tennis.rss"]),
    ("20 Minutes", "fr", ["https://www.20minutes.fr/feeds/rss-tennis.xml"]),
    ("ESPN", "en", ["https://www.espn.com/espn/rss/tennis/news", "https://www.espn.com/espn/rss/news"]),
    ("Tennis Majors (EN)", "en", ["https://www.tennismajors.com/feed"]),
    ("Ubitennis", "en", ["https://www.ubitennis.net/feed/"]),
]
MOTS_BLESSURE = re.compile(r"(?i)\b(injur\w*|withdr[ae]w\w*|pulls? out|pulled out|surgery|illness|ill\b|sidelined|"
                           r"retire[sd]? hurt|retirement|ruled out|fitness|setback|layoff|blessure|bless[ée]\w*|forfait|"
                           r"abandon\w*|déclare forfait|opér[ée]\w*|douleur|touché|incertain|se retire|retrait)")
# Tennis féminin écarté (l'appli ne couvre que le tennis masculin) : mots-clés et principales joueuses.
MOTS_WTA = re.compile(r"(?i)\b(WTA|women'?s|féminin\w*|Billie Jean King|Fed Cup|joueuse|"
                      r"Sabalenka|Swiatek|Świątek|Gauff|Rybakina|Pegula|Paolini|Andreeva|Zheng Qinwen|Keys|Navarro|"
                      r"Muchova|Muchová|Svitolina|Badosa|Osaka|Raducanu|Jabeur|Kasatkina|Krejcikova|Krejčíková|Vondrousova|"
                      r"Ostapenko|Kvitova|Garcia|Cornet|Parry|Burel|Boisson|Mladenovic|Samsonova|Alexandrova|Mertens|"
                      r"Shnaider|Mboko|Anisimova|Kostyuk|Haddad Maia|Fernandez|Bencic|Vekic|Azarenka|Sakkari|"
                      r"Siniakova|Collins|Stephens|Williams|Sharapova|Kerber|Halep|Wozniacki|Kenin|Tauson)\b")
ACTUS_JOURS = 60
TRADUCTIONS_PAR_PASSAGE = 40
NS_MEDIA = "{http://search.yahoo.com/mrss/}"


def image_article(it):
    """Image d'illustration fournie par le flux (affichée depuis le site de la source)."""
    for tag in ("content", "thumbnail"):
        for el in it.iter(NS_MEDIA + tag):
            u = el.get("url") or ""
            if u.startswith("http") and (tag == "thumbnail" or (el.get("medium") or "image") == "image"
                                         or re.search(r"\.(jpe?g|png|webp)", u, re.I)):
                return u
    for el in it.iter("enclosure"):
        if (el.get("type") or "").startswith("image") and (el.get("url") or "").startswith("http"):
            return el.get("url")
    for champ in ("{http://purl.org/rss/1.0/modules/content/}encoded", "description"):
        m = re.search(r'<img[^>]+src=["\'](https?://[^"\']+)', it.findtext(champ) or "")
        if m:
            return m.group(1)
    return None


def traduire(texte):
    """Traduction anglais → français par MyMemory (gratuit, sans compte, ~5 000 caractères par jour)."""
    url = ("https://api.mymemory.translated.net/get?langpair=en%7Cfr&q="
           + urllib.parse.quote(texte[:480]))
    obj = json.loads(telecharger(url, essais=1, delai=2))
    if obj.get("quotaFinished") or str(obj.get("responseStatus")) != "200":
        raise RuntimeError(f"quota ou refus : {obj.get('responseDetails', '')[:80]}")
    fr = html.unescape((obj.get("responseData") or {}).get("translatedText") or "").strip()
    if not fr or fr.upper() == fr and len(fr) > 20:   # réponse vide ou message d'erreur en capitales
        raise RuntimeError("traduction vide")
    return fr


def collecter_actus():
    import email.utils
    import xml.etree.ElementTree as ET
    chemin = os.path.join(DONNEES, "actus.json")
    ancien = lire_json(chemin, {}).get("articles", [])
    par_lien = {a["lien"]: a for a in ancien}
    stats, etat_flux = Counter(), {}
    for source, langue, adresses in FLUX_ACTUS:
        racine = None
        for url in adresses:
            try:
                racine = ET.fromstring(telecharger(url, {"Accept-Encoding": "gzip"}, essais=2, delai=5))
                break
            except Exception as e:  # noqa: BLE001
                etat_flux[source] = f"erreur : {str(e)[:100]}"
        if racine is None:
            stats["flux_en_erreur"] += 1
            continue
        n = 0
        for it in racine.iter("item"):
            titre = html.unescape(re.sub(r"\s+", " ", (it.findtext("title") or ""))).strip()
            lien = (it.findtext("link") or "").strip()
            if not titre or not lien.startswith("http"):
                continue
            if re.search(r"(?i)tous les programmes|résultats en direct\s*!?$", titre):   # titres bouche-trou
                stats["ecartes_vide"] += 1
                continue
            if MOTS_WTA.search(titre):
                stats["ecartes_wta"] += 1
                continue
            try:
                quand = email.utils.parsedate_to_datetime(it.findtext("pubDate") or "").astimezone(dt.timezone.utc)
                quand = quand.isoformat(timespec="minutes")
            except (TypeError, ValueError):
                quand = (par_lien.get(lien) or {}).get("date") or dt.datetime.now(dt.timezone.utc).isoformat(timespec="minutes")
            a = par_lien.get(lien)
            if a is None:
                stats["nouveaux"] += 1
                a = par_lien[lien] = {"lien": lien}
            a.update({"source": source, "langue": langue, "date": quand, "image": image_article(it) or a.get("image")})
            if langue == "fr":
                a["titre"] = titre[:220]
                a.pop("vo", None)
            elif a.get("vo") != titre[:220] or not a.get("titre_fr"):
                a["vo"] = titre[:220]          # titre d'origine, à traduire
                a["titre"] = titre[:220]
                a.pop("titre_fr", None)
            n += 1
        etat_flux[source] = f"ok, {n} articles"
        stats["lus_" + source] += n
    # anciens articles (version 1.5) : titre en anglais sans langue indiquée
    for a in par_lien.values():
        if "langue" not in a:
            a["langue"] = "en"
            a["vo"] = a.get("titre", "")
        if MOTS_WTA.search(a.get("vo") or a.get("titre") or ""):
            a["wta"] = True
    limite = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=ACTUS_JOURS)).isoformat()
    articles = sorted((a for a in par_lien.values() if a["date"] >= limite and not a.get("wta")),
                      key=lambda a: a["date"], reverse=True)[:400]
    # traduction des titres anglais, les plus récents d'abord, une seule fois par titre
    faites = 0
    for a in articles:
        if a["langue"] != "en" or a.get("titre_fr") or faites >= TRADUCTIONS_PAR_PASSAGE:
            continue
        try:
            a["titre_fr"] = a["titre"] = traduire(a["vo"])
            faites += 1
            time.sleep(1)
        except Exception as e:  # noqa: BLE001
            stats["traductions_refusees"] += 1
            J.info(f"Traduction interrompue : {str(e)[:100]}")
            break
    for a in articles:
        a["blessure"] = bool(MOTS_BLESSURE.search(a.get("titre", "")) or MOTS_BLESSURE.search(a.get("vo") or ""))
        a.pop("wta", None)
    os.makedirs(DONNEES, exist_ok=True)
    ecrire_json(chemin, {"maj": dt.datetime.now(dt.timezone.utc).isoformat(timespec="minutes"),
                         "note": "titres, liens et images des flux RSS publics (images affichées depuis le site source) ; "
                                 "titres anglais traduits par MyMemory ; texte des articles non repris",
                         "sources": [s for s, _, _ in FLUX_ACTUS], "flux": etat_flux, "articles": articles}, compact=False)
    J.chiffres["actus"] = dict(stats, articles=len(articles), traduits_ce_passage=faites,
                               en_anglais_restants=sum(1 for a in articles if a["langue"] == "en" and not a.get("titre_fr")),
                               avec_image=sum(1 for a in articles if a.get("image")),
                               blessures=sum(a["blessure"] for a in articles), flux=etat_flux)
    return "actus.json"

# ---------------------------------------------------------------- programme à venir (ESPN, public, sans clé ni quota)
ESPN_ATP = "https://site.api.espn.com/apis/site/v2/sports/tennis/atp/scoreboard?dates="


SONDES_CLASSEMENT = ["https://site.api.espn.com/apis/site/v2/sports/tennis/atp/rankings",
                     "https://site.web.api.espn.com/apis/v2/sports/tennis/atp/rankings"]


def sonder_classement_espn():
    """Essai (aucune donnée reprise) : le classement ATP d'ESPN, jusqu'à quel rang ? Résultat dans programme.json (sonde_classement)."""
    chemin = os.path.join(DONNEES, "programme.json")
    prog = lire_json(chemin, None)
    if not prog:
        return
    res = []
    for url in SONDES_CLASSEMENT:
        try:
            obj = json.loads(telecharger(url, {"Accept": "application/json"}, essais=1, delai=3))
        except Exception as e:  # noqa: BLE001
            res.append({"url": url, "erreur": str(e)[:80]})
            continue
        n, maxr, cles = 0, 0, sorted(obj.keys())[:8] if isinstance(obj, dict) else []
        def parcourir(x):
            nonlocal n, maxr
            if isinstance(x, dict):
                r = x.get("current")
                if isinstance(r, int) and "athlete" in x:
                    n += 1
                    maxr = max(maxr, r)
                for v in x.values():
                    parcourir(v)
            elif isinstance(x, list):
                for v in x:
                    parcourir(v)
        parcourir(obj)
        res.append({"url": url, "cles": cles, "lignes": n, "rang_max": maxr})
    prog["sonde_classement"] = {"date": dt.datetime.now(dt.timezone.utc).isoformat(timespec="minutes"), "essais": res}
    ecrire_json(chemin, prog, compact=False)


def collecter_programme():
    """Matchs de simple à venir (3 jours) et tournois du circuit ATP (5 semaines), depuis l'API publique d'ESPN.
    Écrit donnees/programme.json. Challenger et ITF : pas de source gratuite, l'appli affiche un calendrier attendu."""
    chemin = os.path.join(DONNEES, "programme.json")
    auj = dt.datetime.now(dt.timezone.utc).date()
    tournois, matchs, stats = {}, {}, Counter()
    ancien = lire_json(chemin, {})

    def lire(jour):
        try:
            return json.loads(telecharger(ESPN_ATP + jour.strftime("%Y%m%d"), {"Accept": "application/json"}, essais=2, delai=5))
        except Exception as e:  # noqa: BLE001
            stats["erreurs"] += 1
            J.info(f"Programme ESPN {jour} : {str(e)[:100]}")
            return None
    for k in range(0, 35):
        jour = auj + dt.timedelta(days=k)
        if k >= 3 and (jour.weekday() != 0 and k != 3):
            continue                                   # au-delà de J+2 : une lecture par semaine suffit pour les tournois
        obj = lire(jour)
        if not obj:
            continue
        stats["lectures"] += 1
        for ev in obj.get("events") or []:
            nom = (ev.get("name") or "").strip()
            if not nom:
                continue
            lieu = None
            for gr in ev.get("groupings") or []:
                slug = ((gr.get("grouping") or {}).get("slug") or "").lower()
                if "single" not in slug or "women" in slug:
                    continue
                for c in gr.get("competitions") or []:
                    lieu = lieu or (c.get("venue") or {}).get("fullName")
                    etat = ((c.get("status") or {}).get("type") or {}).get("state")
                    if k > 2 or etat not in ("pre", "in"):
                        continue
                    cp = sorted(c.get("competitors") or [], key=lambda x: x.get("order") or 0)
                    if len(cp) != 2 or any((x.get("type") or "athlete") != "athlete" for x in cp):
                        continue
                    joueurs = []
                    for x in cp:
                        a = x.get("athlete") or {}
                        joueurs.append([str(a.get("guid") or x.get("id") or ""), a.get("displayName") or a.get("fullName"),
                                        ((a.get("flag") or {}).get("alt")), ((x.get("curatedRank") or {}).get("current"))])
                    if not all(j[1] for j in joueurs) or any(j[1].strip().upper() in ("TBD", "TBA") or j[0].startswith("-") for j in joueurs):   # places vides du tableau
                        continue
                    matchs[str(c.get("id"))] = [c.get("startDate") or c.get("date"), 1 if c.get("timeValid") else 0,
                                                (c.get("venue") or {}).get("court"), str(ev.get("id")),
                                                ((c.get("round") or {}).get("displayName")), etat, joueurs[0], joueurs[1]]
            tid = str(ev.get("id"))
            if tid not in tournois:
                tournois[tid] = [tid, nom, (ev.get("date") or "")[:10], (ev.get("endDate") or "")[:10], lieu]
            elif lieu and not tournois[tid][4]:
                tournois[tid][4] = lieu
        time.sleep(0.5)
    if not stats["lectures"]:
        J.alerte("Programme ESPN : aucune lecture réussie, fichier précédent conservé")
        return None
    liste = sorted(matchs.values(), key=lambda m: (m[0] or "", m[2] or ""))
    sortie = {"maj": dt.datetime.now(dt.timezone.utc).isoformat(timespec="minutes"), "source": "ESPN (API publique)",
              "note": "matchs de simple ATP à venir sur 3 jours et tournois ATP des 5 prochaines semaines ; "
                      "heures en UTC ; Challenger et ITF non couverts",
              "colonnes_tournois": ["id", "nom", "debut", "fin", "lieu"],
              "colonnes_matchs": ["debut_utc", "heure_connue", "court", "id_tournoi", "tour", "etat", "joueur1", "joueur2"],
              "colonnes_joueur": ["id", "nom", "pays", "rang"],
              "tournois": sorted(tournois.values(), key=lambda t: t[2]), "matchs": liste}
    for k in ("challenger", "colonnes_challenger", "challenger_maj", "challenger_source", "sonde_classement"):
        if k in ancien:
            sortie[k] = ancien[k]
    if (ancien.get("tournois"), ancien.get("matchs")) != (sortie["tournois"], sortie["matchs"]):
        ecrire_json(chemin, sortie, compact=False)
    J.chiffres["programme"] = {"tournois": len(tournois), "matchs": len(liste), **dict(stats)}
    return "programme.json"


# ---------------------------------------------------------------- calendrier Challenger (Wikipédia, CC BY-SA 4.0)
MOIS_EN = {m: i + 1 for i, m in enumerate(["January", "February", "March", "April", "May", "June", "July", "August",
                                           "September", "October", "November", "December"])}
RE_SEMAINE = re.compile(r"^(" + "|".join(MOIS_EN) + r")\s+(\d{1,2})$")
RE_CHALL = re.compile(r"^(?P<nom>.+?)\s+(?P<ville>[^,\n]+?),\s*(?P<pays>[^\n]+?)\s+(?P<surf>Hard|Clay|Grass|Carpet)(?P<salle>\s*\(i\))?\s*[–—-]\s*Challenger\s*(?P<cat>\d+)", re.S)


class _TablesHtml(__import__("html.parser", fromlist=["HTMLParser"]).HTMLParser):
    """Extrait les lignes des tableaux : liste de lignes, chaque ligne = liste de textes de cellules."""
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.lignes, self.ligne, self.cellule, self.prof = [], None, None, 0

    def handle_starttag(self, tag, attrs):
        if tag == "tr":
            self.ligne = []
        elif tag in ("td", "th") and self.ligne is not None:
            self.cellule = []
        elif tag == "br" and self.cellule is not None:
            self.cellule.append("\n")
        elif tag in ("sup", "style", "script") and self.cellule is not None:
            self.prof += 1

    def handle_endtag(self, tag):
        if tag in ("td", "th") and self.cellule is not None and self.ligne is not None:
            self.ligne.append(re.sub(r"[ \t\xa0]+", " ", "".join(self.cellule)).strip())
            self.cellule = None
        elif tag == "tr" and self.ligne is not None:
            self.lignes.append(self.ligne)
            self.ligne = None
        elif tag in ("sup", "style", "script") and self.prof:
            self.prof -= 1

    def handle_data(self, data):
        if self.cellule is not None and not self.prof:
            self.cellule.append(data)


def collecter_calendrier_challenger():
    """Tournois Challenger semaine par semaine pour la saison en cours (page Wikipédia « AAAA ATP Challenger Tour »).
    Ajoute la clé « challenger » à donnees/programme.json (relue au plus une fois par jour)."""
    chemin = os.path.join(DONNEES, "programme.json")
    prog = lire_json(chemin, {})
    aujourdhui = dt.datetime.now(dt.timezone.utc).date()
    if (prog.get("challenger_maj") or "") >= (dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=20)).isoformat():
        return None
    resultat, diag = [], {}
    for annee in (aujourdhui.year, aujourdhui.year + 1):
        titre = f"{annee} ATP Challenger Tour"
        try:
            data = wiki_requete({"action": "parse", "page": titre, "prop": "text", "redirects": "1"}, pause=1.0)
        except Exception as e:  # noqa: BLE001
            diag[str(annee)] = f"erreur : {str(e)[:100]}"
            continue
        if "error" in data:
            diag[str(annee)] = f"page absente ({data['error'].get('code')})"
            continue
        parseur = _TablesHtml()
        parseur.feed((data.get("parse") or {}).get("text") or "")
        semaine, n, rejets = None, 0, []
        for ligne in parseur.lignes:
            for cell in ligne:
                m = RE_SEMAINE.match(cell.strip())
                if m:
                    semaine = dt.date(annee, MOIS_EN[m.group(1)], int(m.group(2)))
                    break
            if semaine is None:
                continue
            for cell in ligne:
                m = RE_CHALL.match(cell.strip())
                if m:
                    if "echantillon" not in diag:
                        diag["echantillon"] = cell.strip()[:160]
                    lundi = semaine - dt.timedelta(days=semaine.weekday())
                    resultat.append([lundi.isoformat(), m.group("nom").strip(), m.group("ville").strip(), m.group("pays").strip(),
                                     m.group("surf"), 1 if m.group("salle") else 0, int(m.group("cat"))])
                    n += 1
                    break
            else:
                if any("Challenger" in c for c in ligne) and len(rejets) < 3:
                    rejets.append(" | ".join(ligne)[:200])
        diag[str(annee)] = {"tournois": n, "lignes_non_reconnues": rejets, "lignes_totales": len(parseur.lignes)}
    J.chiffres["calendrier_challenger"] = diag
    if not resultat:
        J.alerte("Calendrier Challenger : aucun tournoi lu (format de la page Wikipédia changé ?)")
        return None
    prog["challenger"] = sorted(resultat)
    prog["colonnes_challenger"] = ["semaine_lundi", "nom", "ville", "pays", "surface", "salle", "categorie"]
    prog["challenger_maj"] = dt.datetime.now(dt.timezone.utc).isoformat(timespec="minutes")
    prog["challenger_source"] = "Wikipédia (CC BY-SA 4.0), pages « AAAA ATP Challenger Tour »"
    ecrire_json(chemin, prog, compact=False)
    return "programme.json"


# ---------------------------------------------------------------- trous restants
def compter_trous(base, fin_sackmann, resultats):
    """Compte, depuis la fin de l'archive, les matchs au score complet et avec statistiques,
    par catégorie, en tenant compte des compléments chiffrés (TennisMyLife, Cito)."""
    comp = {}
    seuls = []
    for resultat in resultats:
        for annee, contenu in (resultat or {}).items():
            for c in contenu.get("complements", []):
                t, g, p, sc, dr, st = c[:6]
                ancien = comp.get((t, g, p), (None, None))
                comp[(t, g, p)] = (ancien[0] or dr, ancien[1] or st)
            for m in contenu.get("matchs", []):
                t = contenu.get("tournois", {}).get(m[0])
                seuls.append((t[1] if t else None, m))

    def categorie(niveau, tour):
        q = tour.startswith("Q")
        if niveau == "C":
            return "Challenger qualifications" if q else "Challenger tableau"
        if niveau in ("G", "M", "A", "F", "N", "O"):
            return "ATP qualifications" if q else "ATP tableau"
        if niveau.startswith("I"):
            return "ITF"
        return None
    t = defaultdict(Counter)
    par_tournoi, exemples, sans_score = defaultdict(Counter), defaultdict(list), Counter()
    for m in base.simples:
        if m["debut"] <= fin_sackmann:
            continue
        cat = categorie(base.tournois[m["t"]]["niveau"], m["tour"])
        if not cat:
            continue
        dr, st = m["dr"], m.get("st")
        c = comp.get((m["t"], m["g"], m["p"]))
        if c:
            if c[0]:
                dr = c[0]
            st = st or c[1]
        t[cat]["matchs"] += 1
        t[cat]["score_ok"] += 1 if dr & (COMPLET | ABANDON | FORFAIT) else 0
        t[cat]["stats"] += 1 if st and any(x is not None for x in st[1:19]) else 0
        if not dr & (COMPLET | ABANDON | FORFAIT):
            tr = base.tournois[m["t"]]
            par_tournoi[cat][f"{tr['nom']} ({tr['debut']})"] += 1
            sans_score[cat] += not (m.get("score") or "").strip()
            if len(exemples[cat]) < 8:
                exemples[cat].append(f"{tr['nom']} {m['tour']} : « {m.get('score') or ''} »")
    for niveau, m in seuls:
        niveau = niveau or (base.tournois[m[0]]["niveau"] if m[0] in base.tournois else "C")
        cat = categorie(niveau, m[1])
        if not cat:
            continue
        t[cat]["matchs"] += 1
        t[cat]["score_ok"] += 1 if m[6] & (COMPLET | ABANDON | FORFAIT) else 0
        t[cat]["stats"] += 1 if m[7] and any(x is not None for x in m[7][1:19]) else 0
    tableau = {cat: {"matchs": v["matchs"], "score_complet_%": round(100 * v["score_ok"] / v["matchs"], 1),
                     "trous_score": v["matchs"] - v["score_ok"],
                     "avec_stats_%": round(100 * v["stats"] / v["matchs"], 1)}
               for cat, v in sorted(t.items()) if v["matchs"]}
    J.chiffres["trous_depuis_archive"] = tableau
    J.chiffres["trous_detail"] = {cat: {"sans_aucun_score": sans_score[cat],
                                        "tournois_les_plus_touches": dict(par_tournoi[cat].most_common(12)),
                                        "exemples": exemples[cat]} for cat in sorted(par_tournoi)}
    J.info("Trous depuis la fin de l'archive : " + "; ".join(
        f"{c} {v['trous_score']}/{v['matchs']}" for c, v in tableau.items()))


# ---------------------------------------------------------------- écriture
ORDRE_TOURS = {"Q1": 0, "Q2": 1, "Q3": 2, "Q4": 3, "1T": 10, "2T": 11, "3T": 12, "4T": 13, "5T": 14,
               "RR": 15, "QF": 20, "SF": 21, "BR": 22, "F": 23}


def ecrire_donnees(base, garder=()):
    """Années passées : un fichier par année. Année en cours : un fichier par mois,
    pour que seuls de petits fichiers changent chaque nuit."""
    os.makedirs(DONNEES, exist_ok=True)
    annee_courante = dt.date.today().year
    ecrits = set()
    utilises = set()
    resume = {}
    for genre, matchs in (("simple", base.simples), ("double", base.doubles)):
        par_annee = defaultdict(list)
        for m in matchs:
            t = base.tournois[m["t"]]
            if t["niveau"].startswith("I") and t["annee"] < DEBUT_ITF:
                continue
            cle = str(t["annee"]) if t["annee"] < annee_courante else t["debut"][:7]
            par_annee[cle].append(m)
        for annee, liste in sorted(par_annee.items()):
            liste.sort(key=lambda m: (base.tournois[m["t"]]["debut"], m["t"],
                                      ORDRE_TOURS.get(m["tour"], 9), m["date"] or ""))
            tids = list(dict.fromkeys(m["t"] for m in liste))
            idx = {tid: i for i, tid in enumerate(tids)}
            tournois = [[tid, base.tournois[tid]["nom"], base.tournois[tid]["niveau"],
                         base.tournois[tid]["surface"], base.tournois[tid]["salle"],
                         base.tournois[tid]["debut"], base.tournois[tid]["bo"],
                         base.tournois[tid].get("cat")] for tid in tids]
            lignes = []
            for m in liste:
                lignes.append([idx[m["t"]], m["tour"], m["g"], m["p"], m["score"], m["date"], m["dr"]])
                utilises.update(m["g"].split("+"))
                utilises.update(m["p"].split("+"))
            nom_fichier = f"{genre}-{annee}.json"
            ecrire_json(os.path.join(DONNEES, nom_fichier),
                        {"colonnes_tournois": ["id", "nom", "niveau", "surface", "salle", "debut", "bo", "categorie"],
                         "colonnes_matchs": ["tournoi", "tour", "gagnant", "perdant", "score", "date", "drapeaux"],
                         "tournois": tournois, "matchs": lignes})
            ecrits.add(nom_fichier)
            resume.setdefault(genre, {})[str(annee)] = len(lignes)
            # statistiques de match (archive Sackmann), alignées ligne à ligne sur le fichier des matchs
            st = [m.get("st") for m in liste]
            if any(st):
                nom_stats = f"stats-{genre}-{annee}.json"
                ecrire_json(os.path.join(DONNEES, nom_stats), {"fichier_matchs": nom_fichier,
                                                               "colonnes": NOMS_STATS, "stats": st})
                ecrits.add(nom_stats)
                resume.setdefault("stats", {})[str(annee)] = sum(1 for x in st if x)
    colonnes = ["nom", "pays", "main", "taille_cm", "naissance"]
    joueurs = {pid: [j["nom"], j["pays"], j["main"], j["taille"], j["naissance"]]
               for pid, j in base.joueurs.items() if pid in utilises}
    # joueurs de l'archive (figés) et joueurs apparus depuis (changent chaque nuit)
    for nom_fichier, filtre in (("joueurs-historique.json", lambda p: p.startswith("s")),
                                ("joueurs-recents.json", lambda p: not p.startswith("s"))):
        ecrire_json(os.path.join(DONNEES, nom_fichier),
                    {"colonnes": colonnes, "joueurs": {p: v for p, v in sorted(joueurs.items()) if filtre(p)}})
        ecrits.add(nom_fichier)
    classements = {a: {"date": v["date"], "rangs": {p: r for p, r in v["rangs"].items() if p in utilises}}
                   for a, v in base.classements.items()}
    ecrire_json(os.path.join(DONNEES, "classements-fin-annee.json"), classements)
    ecrits.add("classements-fin-annee.json")
    ecrire_json(os.path.join(DONNEES, "classements-recents.json"),
                {"colonnes": ["semaine", "rang", "points", "source"],
                 "note": "dernier classement officiel connu de chaque joueur : liste complète de l'archive, "
                         "puis classement d'entrée dans un tournoi du circuit principal (Kaggle)",
                 "joueurs": {p: v for p, v in sorted(base.recents.items()) if p in utilises}})
    ecrits.add("classements-recents.json")
    for nom_fichier in garder:
        if os.path.exists(os.path.join(DONNEES, nom_fichier)):
            ecrits.add(nom_fichier)
    # ménage : fichiers d'une organisation précédente (ex. mois devenus année)
    for nom_fichier in os.listdir(DONNEES):
        if nom_fichier.endswith(".json") and nom_fichier not in ecrits | {"meta.json", "index.json"}:
            os.remove(os.path.join(DONNEES, nom_fichier))
    # index : l'appli ne retélécharge que les fichiers dont l'empreinte a changé
    import hashlib
    index = {}
    for nom_fichier in sorted(ecrits):
        contenu = open(os.path.join(DONNEES, nom_fichier), "rb").read()
        index[nom_fichier] = {"octets": len(contenu), "empreinte": hashlib.sha1(contenu).hexdigest()[:12]}
    ecrire_json(os.path.join(DONNEES, "index.json"), index, compact=False)
    return resume, len(joueurs)


def ecrire_meta(resume, nb_joueurs, fin_sackmann):
    meta = {
        "version_collecteur": VERSION,
        "genere_le": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "historique_sackmann_jusqua": fin_sackmann,
        "matchs": resume, "joueurs": nb_joueurs,
        "niveaux": NIVEAUX,
        "drapeaux": {"1": "score complet", "2": "abandon", "4": "forfait", "8": "source Valuebetennis",
                     "16": "score Kaggle", "32": "source Wikipédia", "64": "TennisMyLife (complément chiffré)",
                     "128": "Cito API (complément chiffré)"},
        "categories": {"A": "250, 500 ou equipes (Laver Cup, ATP Cup, United Cup) ; source Kaggle, Series",
                       "I15/I25": "15 ou 25"},
        "colonnes_stats": NOMS_STATS,
        "fichiers_chiffres": "tml-AAAA.json et cito-AAAA.json (même code, même format) : AES-256-GCM, clé PBKDF2-SHA256 du code personnel ; "
                             "complements = scores et statistiques de matchs publiés (clé : tournoi + gagnant + perdant), "
                             "matchs = matchs absents des autres sources ; cito-AAAA.json porte aussi classement_officiel "
                             "(classement ATP complet de la dernière semaine connue : rang, joueur, points, tournois)",
        "sources": [
            {"nom": "Jeff Sackmann, tennis_atp (copie Aneeshers/tennis-sackmann-archive)",
             "licence": "CC BY-NC-SA 4.0", "lien": SACKMANN_DEPOT},
            {"nom": "Valuebetennis, Tennis results and odds since 2021", "licence": "CC BY 4.0",
             "lien": "https://www.valuebetennis.com/en/donnees.htm"},
            {"nom": "Kaggle, dissfya/atp-tennis-2000-2023daily-pull", "licence": "CC0 (domaine public)",
             "lien": "https://www.kaggle.com/datasets/" + KAGGLE_JEU},
            {"nom": "Wikipédia (en), tableaux de double", "licence": "CC BY-SA 4.0",
             "lien": "https://en.wikipedia.org"},
            {"nom": "TennisMyLife, Tennis Match Database", "licence": "usage personnel et non commercial, "
             "redistribution des CSV interdite : données chiffrées, réservées au propriétaire du dépôt",
             "lien": "https://stats.tennismylife.org/tennis-match-database"},
            {"nom": "Wikidata (fiches joueurs : photo, poids, taille)", "licence": "CC0",
             "lien": "https://www.wikidata.org"},
            {"nom": "Wikimedia Commons (photos des joueurs)", "licence": "licence libre propre à chaque photo "
             "(auteur et licence dans photos.json, à afficher sous la photo)", "lien": "https://commons.wikimedia.org"},
            {"nom": "Cito API, Tennis API", "licence": "usage dans sa propre application autorisé, "
             "redistribution comme flux ou jeu de données interdite : données chiffrées, réservées au propriétaire",
             "lien": "https://citoapi.com"},
        ],
    }
    ecrire_json(os.path.join(DONNEES, "meta.json"), meta, compact=False)


def ecrire_rapport(ok, erreur=None):
    os.makedirs(RAPPORT, exist_ok=True)
    maintenant = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    etat = "OK" if ok and not J.alertes else ("OK avec alertes" if ok else "ÉCHEC")
    lignes = [f"# Rapport de collecte H2H Tennis", "", f"- Date (UTC) : {maintenant}",
              f"- Version du collecteur : {VERSION}", f"- État : **{etat}**", ""]
    if erreur:
        lignes += ["## Erreur", "", "```", erreur, "```", ""]
    if J.alertes:
        lignes += ["## Alertes", ""] + [f"- {a}" for a in J.alertes] + [""]
    lignes += ["## Chiffres", "", "```json", json.dumps(J.chiffres, ensure_ascii=False, indent=1), "```", "",
               "## Déroulement", "", "```"] + J.lignes + ["```", ""]
    with open(os.path.join(RAPPORT, "rapport.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(lignes))
    historique = lire_json(os.path.join(RAPPORT, "historique.json"), [])
    historique.append({"date": maintenant, "etat": etat, "alertes": len(J.alertes),
                       "duree_s": round(time.time() - J.t0), "chiffres": {k: v for k, v in J.chiffres.items()
                                                                           if not isinstance(v, list)}})
    ecrire_json(os.path.join(RAPPORT, "historique.json"), historique[-60:], compact=False)


# ---------------------------------------------------------------- principal
def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--sackmann-local", help="dossier atp/ de l'archive (essais)")
    ap.add_argument("--vbt-local", nargs="*", help="fichiers Valuebetennis (essais)")
    ap.add_argument("--kaggle-local", help="fichier atp_tennis.csv (essais)")
    ap.add_argument("--sans-wikipedia", action="store_true")
    ap.add_argument("--sans-photos", action="store_true", help="essais : pas de Wikidata ni de Commons")
    ap.add_argument("--actus-seulement", action="store_true", help="seulement les actualités (actus.yml)")
    ap.add_argument("--wikipedia-complet", action="store_true", help="relire toutes les saisons")
    ap.add_argument("--tml-local", nargs="*", help="fichiers TennisMyLife (essais)")
    ap.add_argument("--couper-archive", help="essais : ignorer l'archive après cette date (AAAA-MM-JJ)")
    args = ap.parse_args()
    if args.actus_seulement:
        try:
            collecter_actus()
            print(json.dumps(J.chiffres.get("actus"), ensure_ascii=False))
            try:
                collecter_programme()
            except Exception as e:  # noqa: BLE001
                print("Programme : échec", e, file=sys.stderr)
            try:
                sonder_classement_espn()
            except Exception as e:  # noqa: BLE001
                print("Sonde classement : échec", e, file=sys.stderr)
            try:
                collecter_calendrier_challenger()
            except Exception as e:  # noqa: BLE001
                print("Calendrier Challenger : échec", e, file=sys.stderr)
            print(json.dumps(J.chiffres.get("calendrier_challenger"), ensure_ascii=False))
            print(json.dumps(J.chiffres.get("programme"), ensure_ascii=False))
            return 0
        except Exception as e:  # noqa: BLE001
            print("Actualités : échec", e, file=sys.stderr)
            return 1

    ok, erreur = True, None
    try:
        etat_corresp = {}
        etat_wiki = {}
        if os.path.isdir(ETAT):
            for nom in sorted(os.listdir(ETAT)):
                m = re.match(r"wikipedia-doubles-(\d{4})\.json$", nom)
                if m:
                    etat_wiki[m.group(1)] = lire_json(os.path.join(ETAT, nom), {})
        base = Base()
        copie = os.path.join(ETAT, "historique-sackmann.json.gz")
        h = None
        if os.path.exists(copie) and not args.sackmann_local:
            with gzip.open(copie, "rt", encoding="utf-8") as f:
                h = json.load(f)
            if h.get("v", 1) < VERSION_COPIE:
                J.info("Copie compacte d'une version précédente : relecture de l'archive (statistiques, classements)")
                h = None
        if h is not None:
            # copie compacte faite au premier passage : l'archive n'est plus nécessaire
            for pid, j in h["joueurs"].items():
                base.ajouter_joueur(pid, *j)
            base.tournois, base.simples = h["tournois"], h["simples"]
            base.classements, base.activite, fin = h["classements"], h["activite"], h["fin"]
            base.recents = h.get("recents", {})
            J.info(f"Historique Sackmann relu depuis la copie du dépôt : {len(base.simples)} matchs")
        else:
            dossier = obtenir_sackmann(args.sackmann_local)
            fin = charger_sackmann(base, dossier)
            if args.couper_archive:
                base.simples = [m for m in base.simples if m["debut"] < args.couper_archive]
                fin = max(m["debut"] for m in base.simples)
                J.info(f"ESSAI : archive coupée au {args.couper_archive}")
            classements_fin_annee(base, dossier)
            os.makedirs(ETAT, exist_ok=True)
            with gzip.open(copie, "wt", encoding="utf-8") as f:
                json.dump({"v": VERSION_COPIE, "fin": fin, "classements": base.classements,
                           "activite": base.activite, "recents": base.recents,
                           "joueurs": {p: [j["nom"], j["pays"], j["main"], j["taille"], j["naissance"]]
                                       for p, j in base.joueurs.items()},
                           "tournois": base.tournois, "simples": base.simples},
                          f, ensure_ascii=False, separators=(",", ":"))
            J.info(f"Copie compacte de l'historique écrite ({os.path.getsize(copie) // 1024} Ko)")
        integrer_vbt(base, charger_vbt(args.vbt_local), fin, etat_corresp)
        try:
            fichier_kaggle = obtenir_kaggle(args.kaggle_local)
            completer_scores_kaggle(base, fichier_kaggle, fin)
            enrichir_kaggle(base, fichier_kaggle, fin)
        except Exception as e:  # noqa: BLE001
            J.alerte(f"Kaggle : {e}\n{traceback.format_exc(limit=3)}")
        if not args.sans_wikipedia:
            try:
                collecter_wikipedia(etat_wiki, toutes=args.wikipedia_complet)
            except Exception as e:  # noqa: BLE001
                J.alerte(f"Wikipédia : {e}\n{traceback.format_exc(limit=3)}")
            for annee, saison in etat_wiki.items():
                ecrire_json(os.path.join(ETAT, f"wikipedia-doubles-{annee}.json"), saison)
        integrer_doubles(base, etat_wiki, etat_corresp)
        # TennisMyLife : uniquement chiffré, jamais en clair dans le dépôt public
        garder = [n for n in (os.listdir(DONNEES) if os.path.isdir(DONNEES) else [])
                  if re.match(r"(tml|cito)-\d{4}\.json$", n)]
        code = os.environ.get("CODE_TML", "").strip()
        resultat = {}
        if not code:
            J.alerte("TennisMyLife : secret CODE_TML absent, étape sautée (rien n'est écrit en clair)")
        else:
            try:
                import cryptography  # noqa: F401
                resultat = integrer_tml(base, charger_tml(fin, args.tml_local), fin)
                garder = sorted(set(garder) | set(ecrire_tml(resultat, code)))
                J.chiffres["tml_fichiers"] = garder
            except ImportError:
                J.alerte("TennisMyLife : module cryptography absent, étape sautée")
            except Exception as e:  # noqa: BLE001
                J.alerte(f"TennisMyLife : {e}\n{traceback.format_exc(limit=3)}")
        cle_cito = os.environ.get("CITO_API_KEY", "").strip()
        resultat_cito = {}
        if not cle_cito:
            J.info("Cito : secret CITO_API_KEY absent, étape sautée")
        elif not code:
            J.alerte("Cito : secret CODE_TML absent (il sert aussi à chiffrer Cito), étape sautée")
        else:
            try:
                mois, meta_cito = collecter_cito(cle_cito, code, fin)
                resultat_cito = integrer_cito(base, mois, meta_cito, fin, resultat)
                garder = sorted(set(garder) | set(ecrire_tml(resultat_cito, code, "cito")))
            except Exception as e:  # noqa: BLE001
                J.alerte(f"Cito : {type(e).__name__} {e}\n{traceback.format_exc(limit=4)}".replace(cle_cito, "***"))
        try:
            compter_trous(base, fin, [resultat, resultat_cito])
        except Exception as e:  # noqa: BLE001
            J.alerte(f"Compteur des trous : {e}")
        for nom_garde in ("photos.json", "actus.json", "programme.json"):
            if os.path.exists(os.path.join(DONNEES, nom_garde)):
                garder = sorted(set(garder) | {nom_garde})
        if not args.sans_photos:
            try:
                autres = {}
                for r in (resultat, resultat_cito):
                    for contenu in (r or {}).values():
                        autres.update(contenu.get("joueurs", {}))
                garder = sorted(set(garder) | {collecter_photos(base, autres)})
            except Exception as e:  # noqa: BLE001
                J.alerte(f"Photos : {type(e).__name__} {str(e)[:250]} (fichier précédent conservé)")
        try:
            garder = sorted(set(garder) | {collecter_classement_commons(base)})
        except Exception as e:  # noqa: BLE001
            J.alerte(f"Classement Commons : {type(e).__name__} {str(e)[:250]} (fichier précédent conservé)")
            if os.path.exists(os.path.join(DONNEES, "classement.json")):
                garder = sorted(set(garder) | {"classement.json"})
        vus, garde = {}, []
        for m in base.simples:
            k = (m["t"], m["g"], m["p"], m["tour"])
            if k in vus:
                autre = garde[vus[k]]
                if m["dr"] & COMPLET and not autre["dr"] & COMPLET:
                    garde[vus[k]] = m
                J.chiffres["doublons_retires"] = J.chiffres.get("doublons_retires", 0) + 1
                continue
            vus[k] = len(garde)
            garde.append(m)
        base.simples = garde
        resume, nb = ecrire_donnees(base, garder)
        ecrire_meta(resume, nb, fin)
        J.chiffres["fichiers"] = resume
        J.info(f"Données écrites : {nb} joueurs")
    except Exception:  # noqa: BLE001
        ok, erreur = False, traceback.format_exc()
        print(erreur, file=sys.stderr)
    try:
        # GitHub Pages sert les fichiers tels quels (sans Jekyll) : plus rapide, aucun fichier ignoré
        if not os.path.exists(os.path.join(RACINE, ".nojekyll")):
            open(os.path.join(RACINE, ".nojekyll"), "w").close()
    except OSError:
        pass
    try:
        chemin = os.path.join(RACINE, "README.md")
        if lire_texte(chemin) != README:
            with open(chemin, "w", encoding="utf-8") as f:
                f.write(README)
    except Exception as e:  # noqa: BLE001
        J.alerte(f"README : {e}")
    ecrire_rapport(ok, erreur)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
