# Test sportsapi365 (2026-11-12 12:38 UTC)

## 1. /round (référentiel des tours)
HTTP 200
Quota : x-quota-limit=150, x-quota-remaining=141, x-quota-reset=1797077623230
```
{"data":[{"round_id":6,"round_name":"Third"},{"round_id":9,"round_name":"1/4"},{"round_id":7,"round_name":"Fourth"},{"round_id":14,"round_name":"Rubber 2"},{"round_id":13,"round_name":"Rubber 1"},{"round_id":11,"round_name":"Bronze"},{"round_id":0,"round_name":"Pre-q"},{"round_id":16,"round_name":"Rubber 4"},{"round_id":10,"round_name":"1/2"},{"round_id":15,"round_name":"Rubber 3"},{"round_id":3,"round_name":"Q3"},{"round_id":20,"round_name":"N/A"},{"round_id":12,"round_name":"Final"},{"round_id":2,"round_name":"Q2"},{"round_id":5,"round_name":"Second"},{"round_id":1,"round_name":"Q1"},{"round_id":8,"round_name":"Robin"},{"round_id":4,"round_name":"First"},{"round_id":17,"round_name":"Rubber 5"},{"round_id":21,"round_name":"ER"},{"round_id":22,"round_name":"Q4"},{"round_id":23,"round_name":"CR"},{"round_id":24,"round_name":"QF"},{"round_id":25,"round_name":"Q5"},{"round_id":-1,"round_name":"N/A"}]}
```

## 2. Résultats du 27/10, pageSize=500
/atp/results/2026-10-27?pageSize=500
HTTP 200
Quota : x-quota-limit=150, x-quota-remaining=140, x-quota-reset=1797077623230

Structure (champs) :
```
data : liste de 326
data[].id : str
data[].matchId : str
data[].date : str
data[].roundId : int
data[].player1Id : int
data[].player2Id : int
data[].tournamentId : int
data[].match_winner : int
data[].result : str
data[].result_type : str
data[].best_of : str
data[].odd1 : str
data[].odd2 : str
data[].player1.id : int
data[].player1.name : str
data[].player1.countryAcr : str
data[].player2.id : int
data[].player2.name : str
data[].player2.countryAcr : str
data[].tournament.id : int
data[].tournament.name : str
data[].tournament.courtId : int
data[].tournament.date : str
data[].tournament.rankId : int
data[].tournament.countryAcr : str
data[].tournament.court : NoneType
data[].tournament.rank : NoneType
data[].tournament.country : NoneType
data[].oddsAvailable : bool
data[].links.odds : str
data[].links.match : str
data[].links.stats : str
data[].links.pointByPoint : str
data[].matchKey : str
page : int
pageNo : int
pageSize : int
limit : int
hasNextPage : bool
```

Lignes : 326
Tournois (nombre de lignes) :
```
{"M25 Norman": 31, "M15 Heraklion": 20, "M15 Selva Gardena": 18, "M15 Yanagawa City": 18, "M15 Monastir": 18, "M15 Fergana": 17, "M25 Las Vegas": 16, "M25 Tamworth": 16, "M15 Mazatlan": 16, "M15 Sharm ElSheikh": 16, "Guayaquil Challenger": 14, "Ningboo Challenger": 14, "M25 Sheffield": 14, "M25 Malta": 13, "M15 Pembroke": 13, "Seoul Challenger": 12, "Brest Challenger": 12, "Sioux Falls Challenger": 12, "M15 Joao Pessoa": 12, "Swiss Indoors Basel - Basel": 9, "M15 Singapore": 9, "Erste Bank Open - Vienna": 6}
```
Tours :
```
{"4": 224, "3": 83, "1": 19}
```
result_type :
```
{"completed": 316, "retired": 9, "walkover": 1}
```
Formes de score (chiffres remplacés par 9) :
```
{"9-9 9-9": 180, "9-9 9-9 9-9": 59, "9-9 9-9(9)": 20, "9-9(9) 9-9": 16, "9-9 9-9(9) 9-9": 15, "9-9(9) 9-9 9-9": 10, "9-9(9) 9-9(9)": 5, "9-9 9-9 9-9(9)": 4, "9-9 9-9 ret.": 3, "9-9(9) 9-9(9) 9-9": 3, "9-9 ret.": 3, "9-9(9) 9-9(9) 9-9(9)": 2, "9-9 9-9 9-9 ret.": 2, "9-9(9) 9-9 9-9(9)": 2, "9-9(9) 9-9(9) 9-9 ret.": 1}
```
(niveau, roundId) :
```
{"0/4": 148, "0/3": 80, "1/4": 61, "0/1": 19, "2/4": 15, "1/3": 3}
```
Valeurs distinctes (rank, statut, abandon) :
```
```

