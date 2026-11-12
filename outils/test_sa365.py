"""Test minimal de sportsapi365 (2 requêtes). Ne publie aucune donnée brute."""
import json, os, urllib.request, urllib.error, datetime as dt

BASE = "https://api.sportsapi365.com/v1/tennis"
CLE = os.environ.get("SA365_KEY", "").strip()
sortie = [f"# Test sportsapi365 ({dt.datetime.utcnow():%Y-%m-%d %H:%M} UTC)", ""]

def appel(chemin):
    req = urllib.request.Request(BASE + chemin, headers={"X-Gravitee-Api-Key": CLE, "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=40) as r:
            return r.status, dict(r.headers), r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers), e.read().decode("utf-8", "replace")[:400]
    except Exception as e:
        return 0, {}, str(e)[:300]

def structure(o, chemin="", sortie=None, profondeur=0):
    if sortie is None:
        sortie = {}
    if isinstance(o, dict):
        for k, v in o.items():
            structure(v, f"{chemin}.{k}" if chemin else k, sortie, profondeur + 1)
    elif isinstance(o, list):
        sortie[chemin] = f"liste de {len(o)}"
        if o:
            structure(o[0], chemin + "[]", sortie, profondeur + 1)
    else:
        sortie[chemin] = type(o).__name__
    return sortie

def valeurs(o, cles, trouve=None):
    if trouve is None:
        trouve = {}
    if isinstance(o, dict):
        for k, v in o.items():
            if isinstance(v, (str, int)) and any(c in k.lower() for c in cles):
                trouve.setdefault(k, set()).add(str(v))
            else:
                valeurs(v, cles, trouve)
    elif isinstance(o, list):
        for x in o:
            valeurs(x, cles, trouve)
    return trouve

if not CLE:
    sortie.append("Secret SPORTSAPI365_KEY absent.")
else:
    # 1. niveaux de tournoi disponibles pour le circuit masculin (données de référence)
    st, h, corps = appel("/upcoming/filters/atp?include=options")
    sortie += ["## 1. /upcoming/filters/atp?include=options", f"HTTP {st}", f"X-Empty-Reason : {h.get('X-Empty-Reason', '-')}",
               f"Restant (en-têtes) : " + ", ".join(f"{k}={v}" for k, v in h.items() if "limit" in k.lower() or "remaining" in k.lower() or "quota" in k.lower()), ""]
    try:
        d = json.loads(corps)
        sortie += ["Structure :", "```"] + [f"{k} : {v}" for k, v in list(structure(d).items())[:40]] + ["```"]
        sortie += ["Contenu (référence, tronqué) :", "```", json.dumps(d, ensure_ascii=False)[:3500], "```", ""]
    except Exception:
        sortie += ["Corps non JSON :", "```", corps[:400], "```", ""]
    # 2. matchs à venir ATP simples (structure et niveaux, 20 lignes)
    st, h, corps = appel("/upcoming/matches/atp?group=singles&include=all%2CfixtureDetails%2Cmetadata&limit=20")
    sortie += ["## 2. /upcoming/matches/atp?group=singles&limit=20", f"HTTP {st}", f"X-Empty-Reason : {h.get('X-Empty-Reason', '-')}", ""]
    try:
        d = json.loads(corps)
        sortie += ["Structure (noms de champs) :", "```"] + [f"{k} : {v}" for k, v in list(structure(d).items())[:120]] + ["```", ""]
        v = valeurs(d, ("rank", "level", "categor", "tourtype", "series"))
        sortie += ["Valeurs distinctes des champs de niveau (20 lignes) :", "```"] + [f"{k} : {sorted(x)[:12]}" for k, x in v.items()] + ["```", ""]
    except Exception:
        sortie += ["Corps non JSON :", "```", corps[:400], "```", ""]

os.makedirs("rapport", exist_ok=True)
open("rapport/test-sa365.md", "w", encoding="utf-8").write("\n".join(sortie) + "\n")
print("\n".join(sortie)[:1500])
