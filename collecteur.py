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

Aucune clé n'est écrite dans ce fichier. Python 3.10+, bibliothèque standard
seulement (l'outil kaggle est installé par le workflow si la clé existe).
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import gzip
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

VERSION = "1.0.2"

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

# Présentation du dépôt, réécrite à chaque passage (attribution exigée par les licences)
README = "# H2H Tennis\n\nApplication personnelle et non commerciale de statistiques de tennis masculin (ATP, Challenger, ITF) : face-à-face, fiches joueurs, bilans.\n\n## Fonctionnement\n\n- `collecteur.py` construit chaque nuit les fichiers de `donnees/` à partir des sources ci-dessous (planification : `.github/workflows/collecte.yml`).\n- `rapport/rapport.md` décrit la dernière collecte (chiffres, alertes, erreurs).\n- `etat/` conserve une copie compacte de l'historique et le cache des tableaux Wikipédia.\n\n## Sources et licences\n\n| Source | Usage | Licence |\n|---|---|---|\n| Jeff Sackmann, [tennis_atp](https://github.com/JeffSackmann/tennis_atp), via la copie [Aneeshers/tennis-sackmann-archive](https://github.com/Aneeshers/tennis-sackmann-archive) | Historique des matchs, joueurs, classements jusqu'à juin 2026 | [CC BY-NC-SA 4.0](https://creativecommons.org/licenses/by-nc-sa/4.0/) |\n| [Valuebetennis](https://www.valuebetennis.com/en/donnees.htm), « Tennis results and odds since 2021 » | Matchs récents, mis à jour chaque jour | [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/) |\n| [Wikipédia](https://en.wikipedia.org) (anglais), pages de tableaux de double | Doubles ATP et Challenger depuis 2021 | [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/) |\n| [Kaggle, dissfya/atp-tennis-2000-2023daily-pull](https://www.kaggle.com/datasets/dissfya/atp-tennis-2000-2023daily-pull) | Complément des scores du circuit ATP principal (facultatif) | À confirmer |\n\nLes fichiers de `donnees/` sont des œuvres dérivées de ces sources et sont partagés dans les mêmes conditions : usage non commercial, attribution, partage dans les mêmes conditions (CC BY-NC-SA 4.0).\n\nAucun lien avec l'ATP, l'ITF ou les tournois cités. Les noms de tournois sont utilisés à titre descriptif.\n"

RACINE = os.path.dirname(os.path.abspath(__file__))
DONNEES = os.path.join(RACINE, "donnees")
ETAT = os.path.join(RACINE, "etat")
RAPPORT = os.path.join(RACINE, "rapport")

# Codes de niveau utilisés par l'appli
# G Grand Chelem, M Masters 1000, A ATP 250/500, F Finales ATP, D Coupe Davis,
# O Jeux olympiques, C Challenger, I15 / I25 / I ITF masculin
NIVEAUX = {"G": "Grand Chelem", "M": "Masters 1000", "A": "ATP 250/500",
           "F": "Finales ATP", "D": "Coupe Davis", "O": "Jeux olympiques",
           "C": "Challenger", "I15": "ITF M15", "I25": "ITF M25", "I": "ITF"}

# Drapeaux d'un match (somme de bits)
COMPLET, ABANDON, FORFAIT, SRC_VBT, SRC_KAGGLE, SRC_WIKI = 1, 2, 4, 8, 16, 32


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
                niveau = niveau_sackmann(r["tourney_level"], r["tourney_name"], genre)
                tour = tour_relatif(r["round"], r["draw_size"])
                # les fichiers qual_chall contiennent aussi les qualifications ATP
                if tid not in base.tournois:
                    surface = (r["surface"] or "").strip() or None
                    base.tournois[tid] = {
                        "nom": r["tourney_name"], "niveau": niveau, "surface": surface,
                        "salle": 1 if surface == "Carpet" else None, "debut": debut,
                        "bo": int(r["best_of"]) if (r["best_of"] or "").isdigit() else 3,
                        "annee": int(debut[:4])}
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
                base.simples.append({"t": tid, "tour": tour, "g": g, "p": p_, "score": score,
                                     "date": None, "dr": drap, "debut": debut})
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
                                  "debut": jour, "bo": 3, "annee": int(jour[:4])}
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
        mo = re.sub(r"\[\[([^\]|]+)\|([^\]]+)\]\]", r"\2", mo)
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
        tours, matchs = matchs_tableau(nb, params)
        precedents = [t for p, t in titres if p < pos]
        est_finale = bool(precedents) and precedents[-1].startswith("final")
        infos.append((nb, tours, matchs, est_finale))
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
        if saison["verifiee"] and not recente and not toutes:
            continue
        if budget <= 0:
            stats["saisons_reportees"] += 1
            continue
        complete = True
        for circuit in ("A", "C"):
            try:
                revs = pages_double_saison(annee, circuit)   # {titre: révision}
                titres = sorted(revs)
                a_lire = sorted(t for t in titres if saison["pages"].get(t, {}).get("rev") != revs.get(t))
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
                                          "debut": debut, "matchs": matchs, "alertes": alertes[:5]}
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

    def joueur(nom):
        k = cle_nom(nom)
        if k in corresp:
            pid = corresp[k]
        else:
            cands = base.par_cle.get(k, [])
            pid = cands[0] if len(cands) == 1 else "w" + k.replace(" ", "_")
            corresp[k] = pid
        if pid not in base.joueurs:
            base.ajouter_joueur(pid, nom)
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


# ---------------------------------------------------------------- écriture
ORDRE_TOURS = {"Q1": 0, "Q2": 1, "Q3": 2, "Q4": 3, "1T": 10, "2T": 11, "3T": 12, "4T": 13, "5T": 14,
               "RR": 15, "QF": 20, "SF": 21, "BR": 22, "F": 23}


def ecrire_donnees(base):
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
                         base.tournois[tid]["debut"], base.tournois[tid]["bo"]] for tid in tids]
            lignes = []
            for m in liste:
                lignes.append([idx[m["t"]], m["tour"], m["g"], m["p"], m["score"], m["date"], m["dr"]])
                utilises.update(m["g"].split("+"))
                utilises.update(m["p"].split("+"))
            nom_fichier = f"{genre}-{annee}.json"
            ecrire_json(os.path.join(DONNEES, nom_fichier),
                        {"colonnes_tournois": ["id", "nom", "niveau", "surface", "salle", "debut", "bo"],
                         "colonnes_matchs": ["tournoi", "tour", "gagnant", "perdant", "score", "date", "drapeaux"],
                         "tournois": tournois, "matchs": lignes})
            ecrits.add(nom_fichier)
            resume.setdefault(genre, {})[str(annee)] = len(lignes)
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
                     "16": "score Kaggle", "32": "source Wikipédia"},
        "sources": [
            {"nom": "Jeff Sackmann, tennis_atp (copie Aneeshers/tennis-sackmann-archive)",
             "licence": "CC BY-NC-SA 4.0", "lien": SACKMANN_DEPOT},
            {"nom": "Valuebetennis, Tennis results and odds since 2021", "licence": "CC BY 4.0",
             "lien": "https://www.valuebetennis.com/en/donnees.htm"},
            {"nom": "Kaggle, dissfya/atp-tennis-2000-2023daily-pull", "licence": "à confirmer",
             "lien": "https://www.kaggle.com/datasets/" + KAGGLE_JEU},
            {"nom": "Wikipédia (en), tableaux de double", "licence": "CC BY-SA 4.0",
             "lien": "https://en.wikipedia.org"},
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
    ap.add_argument("--wikipedia-complet", action="store_true", help="relire toutes les saisons")
    args = ap.parse_args()

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
        if os.path.exists(copie) and not args.sackmann_local:
            # copie compacte faite au premier passage : l'archive n'est plus nécessaire
            with gzip.open(copie, "rt", encoding="utf-8") as f:
                h = json.load(f)
            for pid, j in h["joueurs"].items():
                base.ajouter_joueur(pid, *j)
            base.tournois, base.simples = h["tournois"], h["simples"]
            base.classements, base.activite, fin = h["classements"], h["activite"], h["fin"]
            J.info(f"Historique Sackmann relu depuis la copie du dépôt : {len(base.simples)} matchs")
        else:
            dossier = obtenir_sackmann(args.sackmann_local)
            fin = charger_sackmann(base, dossier)
            classements_fin_annee(base, dossier)
            os.makedirs(ETAT, exist_ok=True)
            with gzip.open(copie, "wt", encoding="utf-8") as f:
                json.dump({"fin": fin, "classements": base.classements, "activite": base.activite,
                           "joueurs": {p: [j["nom"], j["pays"], j["main"], j["taille"], j["naissance"]]
                                       for p, j in base.joueurs.items()},
                           "tournois": base.tournois, "simples": base.simples},
                          f, ensure_ascii=False, separators=(",", ":"))
            J.info(f"Copie compacte de l'historique écrite ({os.path.getsize(copie) // 1024} Ko)")
        integrer_vbt(base, charger_vbt(args.vbt_local), fin, etat_corresp)
        try:
            completer_scores_kaggle(base, obtenir_kaggle(args.kaggle_local), fin)
        except Exception as e:  # noqa: BLE001
            J.alerte(f"Kaggle : {e}")
        if not args.sans_wikipedia:
            try:
                collecter_wikipedia(etat_wiki, toutes=args.wikipedia_complet)
            except Exception as e:  # noqa: BLE001
                J.alerte(f"Wikipédia : {e}\n{traceback.format_exc(limit=3)}")
            for annee, saison in etat_wiki.items():
                ecrire_json(os.path.join(ETAT, f"wikipedia-doubles-{annee}.json"), saison)
        integrer_doubles(base, etat_wiki, etat_corresp)
        resume, nb = ecrire_donnees(base)
        ecrire_meta(resume, nb, fin)
        J.chiffres["fichiers"] = resume
        J.info(f"Données écrites : {nb} joueurs")
    except Exception:  # noqa: BLE001
        ok, erreur = False, traceback.format_exc()
        print(erreur, file=sys.stderr)
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
