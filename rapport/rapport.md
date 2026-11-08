# Rapport de collecte H2H Tennis

- Date (UTC) : 2026-11-08T21:05:15+00:00
- Version du collecteur : 1.0.1
- État : **OK avec alertes**

## Alertes

- Wikipédia : téléchargement impossible : https://en.wikipedia.org/w/api.php?action=query&prop=revisions&rvprop=content%7Cids&rvslots=main&redirects=1&titles=2021+San+Diego+Open%7C2021+Sardegna+Open%7C2021+Serbia+Open%7C2021+Singapore+Tennis+Open%7C2021+Sofia+Open%7C2021+St.+Petersburg+Open%7C2021+Stockholm+Open%7C2021+Swedish+Open%7C2021+Swiss+Open+Gstaad%7C2021+US+Open%7C2021+Western+%26+Southern+Open%7C2021+Wimbledon+Championships%7C2021+Winston-Salem+Open&format=json&formatversion=2&maxlag=5 (HTTP Error 429: Too Many Requests)
Traceback (most recent call last):
  File "/home/runner/work/h2h-tennis/h2h-tennis/collecteur.py", line 1239, in main
    collecter_wikipedia(etat_wiki, toutes=args.wikipedia_complet)
  File "/home/runner/work/h2h-tennis/h2h-tennis/collecteur.py", line 1001, in collecter_wikipedia
    infos = wiki_contenus(sorted(set(parents.values())))
            ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/home/runner/work/h2h-tennis/h2h-tennis/collecteur.py", line 698, in wiki_contenus
    data = wiki_requete({"action": "query", "prop": "revisions", "rvprop": "content|ids",
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
RuntimeError: téléchargement impossible : https://en.wikipedia.org/w/api.php?action=query&prop=revisions&rvprop=content%7Cids&rvslots=main&redirects=1&titles=2021+San+Diego+Open%7C2021+Sardegna+Open%7C2021+Serbia+Open%7C2021+Singapore+Tennis+Open%7C2021+Sofia+Open%7C2021+St.+Petersburg+Open%7C2021+Stockholm+Open%7C2021+Swedish+Open%7C2021+Swiss+Open+Gstaad%7C2021+US+Open%7C2021+Western+%26+Southern+Open%7C2021+Wimbledon+Championships%7C2021+Winston-Salem+Open&format=json&formatversion=2&maxlag=5 (HTTP Error 429: Too Many Requests)


## Chiffres

```json
{
 "sackmann_doublons_fusionnes": 37,
 "sackmann_matchs": 339936,
 "sackmann_fin": "2026-06-01",
 "exemples_orthographe": [
  [
   "Cagan Efe Tufekci",
   "Cagan Efe Tufecki"
  ],
  [
   "Manas Manoj Dhamne",
   "Manas Dhamne"
  ],
  [
   "Diego Dedura",
   "Diego Dedura Palomero"
  ],
  [
   "Jacopo Borsoi",
   "Jacobo Borsoi"
  ],
  [
   "Karl Lee",
   "Karl Kazuma Lee"
  ],
  [
   "Seongwoo Cho",
   "Seung Woo Cho"
  ],
  [
   "Alafia Ayeni",
   "Olukayode Alafia Damina Ayeni"
  ],
  [
   "Pedro Martinez Portero",
   "Pedro Martinez"
  ],
  [
   "Donald Nikolas Stoot",
   "Nikolas Stoot"
  ],
  [
   "Alan Raul Sau Franco",
   "Alan Sau Franco"
  ],
  [
   "Marton Liszka",
   "Marton Liszk"
  ],
  [
   "Adrian Boitan",
   "Gabi Adrian Boitan"
  ],
  [
   "Johan Alexander Rodriguez",
   "Johan Alexander Rodriguez Rodriguez"
  ],
  [
   "Jose Gabriel Fernandez",
   "Jose Fernandez"
  ],
  [
   "Jaume Antoni Munar Clar",
   "Jaume Munar"
  ],
  [
   "Juan Alejandro Hernandez",
   "Juan Alejandro Hernandez Serrano"
  ],
  [
   "Santiago Rodriguez Taverna",
   "Santiago Fa Rodriguez Taverna"
  ],
  [
   "Paulo Saraiva Dos Santos",
   "Paulo Andre Saraiva Dos Santos"
  ],
  [
   "Duckhee Lee",
   "Duck Hee Lee"
  ],
  [
   "Sebastian Grundtvig",
   "Sebastian Grundtvig Jorgensen"
  ],
  [
   "Taylor Harry Fritz",
   "Taylor Fritz"
  ],
  [
   "Federico Gonzalez Benitez",
   "Federico Gaston Gonzalez Benitez"
  ],
  [
   "Alvaro Frutos Alonso",
   "Alvaro Ariel Frutos Alonso"
  ],
  [
   "Kaan Isik Kosaner",
   "Kaan Isak Kosaner"
  ],
  [
   "Andre Souza Pinto De Camargo",
   "Andre Souza"
  ]
 ],
 "vbt": {
  "avant_fenetre": 15147,
  "noms_rapproches": 2493,
  "doublons_sackmann": 1041,
  "noms_nouveaux": 456,
  "ajoutes": 16056,
  "score_complet": 4864,
  "noms_rapproches_orthographe": 58,
  "noms_homonymes_resolus_par_activite": 20,
  "qualifs_itf_ignorees": 12811,
  "categorie_inconnue": 189,
  "coupe_davis_ignoree": 61
 },
 "vbt_noms_ambigus": [
  [
   "Andrej Djokic",
   1
  ],
  [
   "Jerry Roddick",
   1
  ],
  [
   "Benjamin O'Connell",
   1
  ],
  [
   "Lorenzo Angelini",
   1
  ],
  [
   "Carles Cordoba",
   1
  ],
  [
   "Axel Garcian",
   1
  ],
  [
   "Yuki Mochizuki",
   1
  ],
  [
   "Timeo Trufelli",
   1
  ],
  [
   "Joaquin Aguilar Cardozo",
   1
  ],
  [
   "Jakub Vrba",
   1
  ],
  [
   "Alex Santino Nunez Vera",
   1
  ],
  [
   "Denis Constantin Spiridon",
   1
  ],
  [
   "Jack Kennedy",
   1
  ],
  [
   "Frazier Rengifo",
   1
  ],
  [
   "Saba George Nanobashvili",
   1
  ],
  [
   "Hugo Cardinaud",
   1
  ],
  [
   "Eric Jr. Olivarez",
   1
  ],
  [
   "Claude Ishimwe",
   1
  ],
  [
   "Etienne Niyigena",
   1
  ],
  [
   "Julian Alonso",
   1
  ]
 ],
 "kaggle": {
  "lignes": 1177,
  "non_rapproches": 124,
  "rapproches": 1053,
  "scores_completes": 432
 },
 "doubles": {},
 "fichiers": {
  "simple": {
   "2011": 9386,
   "2012": 9666,
   "2013": 9408,
   "2014": 9094,
   "2015": 9841,
   "2016": 32640,
   "2017": 30555,
   "2018": 30162,
   "2019": 28015,
   "2020": 9336,
   "2021": 22063,
   "2022": 29239,
   "2023": 31275,
   "2024": 33000,
   "2025": 32168,
   "2026-01": 2078,
   "2026-02": 2533,
   "2026-03": 3228,
   "2026-04": 2591,
   "2026-05": 3060,
   "2026-06": 3740,
   "2026-07": 3057,
   "2026-08": 3184,
   "2026-09": 3091,
   "2026-10": 2912,
   "2026-11": 670
  }
 }
}
```

## Déroulement

```
   0.0s  Archive Sackmann : clonage partiel du dossier atp
  11.1s  Sackmann : 339936 matchs, 10802 joueurs, dernier tournoi 2026-06-01
  12.5s  Classements : 2011 (2011-12-26), 2012 (2012-12-31), 2013 (2013-12-30), 2014 (2014-12-29), 2015 (2015-12-28), 2016 (2016-12-26), 2017 (2017-12-25), 2018 (2018-12-31), 2019 (2019-12-30), 2020 (2020-12-28), 2021 (2021-12-27), 2022 (2022-12-26), 2023 (2023-12-25), 2024 (2024-12-30), 2025 (2025-12-29), 2026 (2026-06-08)
  18.4s  Copie compacte de l'historique écrite (4026 Ko)
  19.0s  Valuebetennis 2026 : 45305 matchs ATP
  19.7s  Valuebetennis intégré : ajoutes=16056, avant_fenetre=15147, categorie_inconnue=189, coupe_davis_ignoree=61, doublons_sackmann=1041, noms_homonymes_resolus_par_activite=20, noms_nouveaux=456, noms_rapproches=2493, noms_rapproches_orthographe=58, qualifs_itf_ignorees=12811, score_complet=4864
  21.5s  Kaggle : lignes=1177, non_rapproches=124, rapproches=1053, scores_completes=432
  60.9s  ALERTE Wikipédia : téléchargement impossible : https://en.wikipedia.org/w/api.php?action=query&prop=revisions&rvprop=content%7Cids&rvslots=main&redirects=1&titles=2021+San+Diego+Open%7C2021+Sardegna+Open%7C2021+Serbia+Open%7C2021+Singapore+Tennis+Open%7C2021+Sofia+Open%7C2021+St.+Petersburg+Open%7C2021+Stockholm+Open%7C2021+Swedish+Open%7C2021+Swiss+Open+Gstaad%7C2021+US+Open%7C2021+Western+%26+Southern+Open%7C2021+Wimbledon+Championships%7C2021+Winston-Salem+Open&format=json&formatversion=2&maxlag=5 (HTTP Error 429: Too Many Requests)
Traceback (most recent call last):
  File "/home/runner/work/h2h-tennis/h2h-tennis/collecteur.py", line 1239, in main
    collecter_wikipedia(etat_wiki, toutes=args.wikipedia_complet)
  File "/home/runner/work/h2h-tennis/h2h-tennis/collecteur.py", line 1001, in collecter_wikipedia
    infos = wiki_contenus(sorted(set(parents.values())))
            ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/home/runner/work/h2h-tennis/h2h-tennis/collecteur.py", line 698, in wiki_contenus
    data = wiki_requete({"action": "query", "prop": "revisions", "rvprop": "content|ids",
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
RuntimeError: téléchargement impossible : https://en.wikipedia.org/w/api.php?action=query&prop=revisions&rvprop=content%7Cids&rvslots=main&redirects=1&titles=2021+San+Diego+Open%7C2021+Sardegna+Open%7C2021+Serbia+Open%7C2021+Singapore+Tennis+Open%7C2021+Sofia+Open%7C2021+St.+Petersburg+Open%7C2021+Stockholm+Open%7C2021+Swedish+Open%7C2021+Swiss+Open+Gstaad%7C2021+US+Open%7C2021+Western+%26+Southern+Open%7C2021+Wimbledon+Championships%7C2021+Winston-Salem+Open&format=json&formatversion=2&maxlag=5 (HTTP Error 429: Too Many Requests)

  60.9s  Doubles intégrés : 
  62.8s  Données écrites : 11258 joueurs
```
