"""Test minimal de sportsapi365 (2 requêtes). Ne publie aucune donnée brute."""
import json, os, urllib.request, urllib.error, datetime as dt

BASE = "https://api.sportsapi365.com/v1/tennis"
CLE = os.environ.get("SA365_KEY", "").strip()
sortie = [f"# Test sportsapi365 ({dt.datetime.utcnow():%Y-%m-%d %H:%M} UTC)", ""]

def appel(chemin):
    req = urllib.request.Request(BASE + chemin, headers={"X-Gravitee-Api-Key": CLE, "Accept": "application/json",
                                              "User-Agent": "h2h-tennis/1.0 (projet personnel, github.com/denzelkurt-maker/h2h-tennis)"})
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

def liste_matchs(d):
    if isinstance(d, dict):
        for k in ("matches", "results", "data", "items"):
            if isinstance(d.get(k), list):
                return d[k]
    return d if isinstance(d, list) else []

def trouver(o, cle):
    """Premières valeurs d'une clé, n'importe où dans une ligne."""
    if isinstance(o, dict):
        if cle in o and isinstance(o[cle], (str, int)):
            return str(o[cle])
        for v in o.values():
            r = trouver(v, cle)
            if r is not None:
                return r
    return None

def essai(titre, chemin):
    st, h, corps = appel(chemin)
    sortie.extend([f"## {titre}", chemin, f"HTTP {st}", "Quota : " + ", ".join(f"{k}={v}" for k, v in h.items() if "quota" in k.lower()), ""])
    try:
        d = json.loads(corps)
    except Exception:
        sortie.extend(["Corps non JSON :", "```", corps[:400], "```", ""])
        return
    sortie.extend(["Structure (champs) :", "```"] + [f"{k} : {v}" for k, v in list(structure(d).items())[:110]] + ["```", ""])
    lignes = liste_matchs(d)
    sortie.append(f"Lignes : {len(lignes)}")
    if lignes:
        from collections import Counter
        trn = Counter((trouver(l, "name") if not isinstance(l.get("tournament"), dict) else l["tournament"].get("name")) for l in lignes)
        sortie.extend(["Tournois (nombre de lignes) :", "```", json.dumps(dict(trn.most_common(25)), ensure_ascii=False), "```"])
        tours = Counter((l.get("round") or {}).get("name") if isinstance(l.get("round"), dict) else str(l.get("roundId")) for l in lignes)
        sortie.extend(["Tours :", "```", json.dumps(dict(tours.most_common(12)), ensure_ascii=False), "```"])
        import re
        rt = Counter(str(l.get("result_type")) for l in lignes if "result_type" in l)
        if rt:
            sortie.extend(["result_type :", "```", json.dumps(dict(rt.most_common(12)), ensure_ascii=False), "```"])
            motifs = Counter(re.sub(r"\d+", "9", str(l.get("result"))) for l in lignes)
            sortie.extend(["Formes de score (chiffres remplacés par 9) :", "```", json.dumps(dict(motifs.most_common(15)), ensure_ascii=False), "```"])
            par_tr = Counter((str(trouver(l, "rankId")), str(l.get("roundId"))) for l in lignes)
            sortie.extend(["(niveau, roundId) :", "```", json.dumps({f"{a}/{b}": n for (a, b), n in par_tr.most_common(20)}), "```"])
        v = valeurs(d, ("status", "retire", "walkover"))
        sortie.extend(["Valeurs distinctes (rank, statut, abandon) :", "```"] + [f"{k} : {sorted(x)[:10]}" for k, x in v.items()] + ["```"])
    sortie.append("")

if not CLE:
    sortie.append("Secret SPORTSAPI365_KEY absent.")
else:
    st, h, corps = appel("/round")
    sortie.extend(["## 1. /round (référentiel des tours)", f"HTTP {st}", "Quota : " + ", ".join(f"{k}={v}" for k, v in h.items() if "quota" in k.lower()), "```", corps[:2500], "```", ""])
    essai("2. Résultats du 27/10, pageSize=500", "/atp/results/2026-10-27?pageSize=500")

os.makedirs("rapport", exist_ok=True)
open("rapport/test-sa365.md", "w", encoding="utf-8").write("\n".join(sortie) + "\n")
print("\n".join(sortie)[:1500])
