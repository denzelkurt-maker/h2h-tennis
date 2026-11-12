# Test sportsapi365 (2026-11-12 12:17 UTC)

## 1. Résultats d'un jour (ATP, tous niveaux)
/atp/results/2026-10-27
HTTP 200
Quota : x-quota-limit=150, x-quota-remaining=147, x-quota-reset=1797077623230

Structure (champs) :
```
data : liste de 100
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

Lignes : 100
Tournois (nombre de lignes) :
```
{"M25 Norman": 21, "Guayaquil Challenger": 14, "Ningboo Challenger": 14, "Seoul Challenger": 12, "Brest Challenger": 12, "Sioux Falls Challenger": 12, "Swiss Indoors Basel - Basel": 9, "Erste Bank Open - Vienna": 6}
```
Tours :
```
{"4": 79, "1": 11, "3": 10}
```
Valeurs distinctes (rank, statut, abandon) :
```
rankId : ['0', '1', '2']
```

## 2. À venir niveau 0 (ITF M15/M25)
/upcoming/matches/atp?group=singles&rank=0&limit=20
HTTP 200
Quota : x-quota-limit=150, x-quota-remaining=146, x-quota-reset=1797077623230

Structure (champs) :
```
total : int
matches : liste de 20
matches[].id : int
matches[].matchId : int
matches[].liveMatchId : str
matches[].links.match : str
matches[].links.live : str
matches[].tournament.id : int
matches[].tournament.name : str
matches[].tournament.date : str
matches[].tournament.rankId : int
matches[].tournament.country : str
matches[].tournament.court.name : str
matches[].court : str
matches[].roundId : int
matches[].rank : int
matches[].date : str
matches[].type : str
matches[].odds.id_b_o : int
matches[].odds.bookmaker : str
matches[].odds.id1_o : int
matches[].odds.id2_o : int
matches[].odds.total : float
matches[].odds.k1 : float
matches[].odds.k2 : float
matches[].odds.ktb : float
matches[].odds.ktm : float
matches[].player1.name : str
matches[].player1.odd : str
matches[].player1.oddBookmaker : str
matches[].player1.countryAcr : str
matches[].player1.seed : NoneType
matches[].player1.image : str
matches[].player1.image_p_name : str
matches[].player1.id : int
matches[].player2.id : int
matches[].player2.name : str
matches[].player2.odd : str
matches[].player2.oddBookmaker : str
matches[].player2.countryAcr : str
matches[].player2.seed : NoneType
matches[].player2.image : str
matches[].player2.image_p_name : str
matches[].h2h : str
matches[].h2hSummary.matchCount : int
matches[].h2hSummary.player1Wins : int
matches[].h2hSummary.player2Wins : int
matches[].startTimeStatus : str
matches[].modelPrediction.available : bool
matches[].modelPrediction.error : str
matches[].modelPrediction.message : str
matches[].modelPrediction.requiredPlan : str
matches[].modelPrediction.upgradeUrl : str
page : int
pageNo : int
pageSize : int
limit : int
hasNextPage : bool
totalPages : int
```

Lignes : 20
Tournois (nombre de lignes) :
```
{"M15 Roldan": 6, "M25 Santa Cruz do Sul": 4, "M15 Naples": 4, "M25 Montreal": 3, "M25 San Gregorio di Catania": 1, "M15 Las Palmas de Gran Canaria": 1, "M25 Vale do Lobo": 1}
```
Tours :
```
{"5": 19, "4": 1}
```
Valeurs distinctes (rank, statut, abandon) :
```
rankId : ['0']
rank : ['0']
startTimeStatus : ['scheduled']
```

