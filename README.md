# H2H Tennis

Application personnelle et non commerciale de statistiques de tennis masculin (ATP, Challenger, ITF) : face-à-face, fiches joueurs, bilans.

## Fonctionnement

- `collecteur.py` construit chaque nuit les fichiers de `donnees/` à partir des sources ci-dessous (planification : `.github/workflows/collecte.yml`).
- `rapport/rapport.md` décrit la dernière collecte (chiffres, alertes, erreurs).
- `etat/` conserve une copie compacte de l'historique et le cache des tableaux Wikipédia.

## Sources et licences

| Source | Usage | Licence |
|---|---|---|
| Jeff Sackmann, [tennis_atp](https://github.com/JeffSackmann/tennis_atp), via la copie [Aneeshers/tennis-sackmann-archive](https://github.com/Aneeshers/tennis-sackmann-archive) | Historique des matchs, statistiques de match (aces, breaks…), joueurs, classements jusqu'à juin 2026 | [CC BY-NC-SA 4.0](https://creativecommons.org/licenses/by-nc-sa/4.0/) |
| [Valuebetennis](https://www.valuebetennis.com/en/donnees.htm), « Tennis results and odds since 2021 » | Matchs récents, mis à jour chaque jour | [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/) |
| [Wikipédia](https://en.wikipedia.org) (anglais), pages de tableaux de double | Doubles ATP et Challenger depuis 2021 | [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/) |
| [Kaggle, dissfya/atp-tennis-2000-2023daily-pull](https://www.kaggle.com/datasets/dissfya/atp-tennis-2000-2023daily-pull) | Scores, catégorie 250/500, intérieur ou extérieur, classement au moment du match (circuit principal) | CC0 (domaine public) |
| [TennisMyLife](https://stats.tennismylife.org/tennis-match-database) | Scores complets et statistiques ATP et Challenger depuis juin 2026, **fichiers `donnees/tml-*.json` chiffrés** (usage personnel du propriétaire ; la redistribution des CSV n'est pas autorisée) | Usage personnel et non commercial |
| [Cito API](https://citoapi.com) | Résultats ATP, Challenger (qualifications comprises) et ITF, statistiques de match, classement ATP complet, depuis juin 2026, **fichiers `donnees/cito-*.json` et `etat/cito-*.json` chiffrés** (redistribution interdite) | Usage dans sa propre application |

Les fichiers de `donnees/` (hors `tml-*.json` et `cito-*.json`, chiffrés et non partagés) sont des œuvres dérivées de ces sources et sont partagés dans les mêmes conditions : usage non commercial, attribution, partage dans les mêmes conditions (CC BY-NC-SA 4.0).

Aucun lien avec l'ATP, l'ITF ou les tournois cités. Les noms de tournois sont utilisés à titre descriptif.
