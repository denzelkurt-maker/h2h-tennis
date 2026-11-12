# Test sportsapi365 (2026-11-12 12:13 UTC)

## 1. /upcoming/filters/atp?include=options
HTTP 200
X-Empty-Reason : -
Restant (en-têtes) : x-ratelimit-reset=60, x-quota-limit=150, x-quota-remaining=149, x-quota-reset=1797077623230, x-ratelimit-limit=3000, x-ratelimit-remaining=2999

Structure :
```
levels : liste de 3
levels[].id : int
levels[].name : str
tournaments : liste de 24
tournaments[].id : int
tournaments[].name : str
tournaments[].type : str
tournaments[].rankId : int
tournaments[].surfaceId : int
tournaments[].country : str
surfaces : liste de 3
surfaces[].id : int
surfaces[].name : str
countries : liste de 20
countries[].acronym : str
countries[].name : str
```
Contenu (référence, tronqué) :
```
{"levels": [{"id": 0, "name": "Futures/Satellites/ITF tournaments $10K"}, {"id": 1, "name": "Challengers/ITF tournaments > $10K"}, {"id": 2, "name": "Main tour"}], "tournaments": [{"id": 21363, "name": "BNP Paribas Nordic Open - Stockholm", "type": "atp", "rankId": 2, "surfaceId": 3, "country": "SWE"}, {"id": 22197, "name": "Brisbane 3 Challenger", "type": "atp", "rankId": 1, "surfaceId": 1, "country": "AUS"}, {"id": 22201, "name": "Hersonissos 3 Challenger", "type": "atp", "rankId": 1, "surfaceId": 1, "country": "GRE"}, {"id": 22198, "name": "Knoxville Challenger", "type": "atp", "rankId": 1, "surfaceId": 3, "country": "USA"}, {"id": 22199, "name": "Lima 3 Challenger", "type": "atp", "rankId": 1, "surfaceId": 2, "country": "PER"}, {"id": 22250, "name": "M15 Antalya", "type": "atp", "rankId": 0, "surfaceId": 2, "country": "TUR"}, {"id": 22248, "name": "M15 Heraklion", "type": "atp", "rankId": 0, "surfaceId": 1, "country": "GRE"}, {"id": 22257, "name": "M15 Hua Hin", "type": "atp", "rankId": 0, "surfaceId": 1, "country": "THA"}, {"id": 22252, "name": "M15 Kuala Lumpur", "type": "atp", "rankId": 0, "surfaceId": 1, "country": "MAS"}, {"id": 22247, "name": "M15 Las Palmas de Gran Canaria", "type": "atp", "rankId": 0, "surfaceId": 2, "country": "ESP"}, {"id": 22253, "name": "M15 Maanshan", "type": "atp", "rankId": 0, "surfaceId": 3, "country": "CHN"}, {"id": 22255, "name": "M15 Monastir", "type": "atp", "rankId": 0, "surfaceId": 1, "country": "TUN"}, {"id": 22249, "name": "M15 Naples", "type": "atp", "rankId": 0, "surfaceId": 2, "country": "USA"}, {"id": 22254, "name": "M15 Roldan", "type": "atp", "rankId": 0, "surfaceId": 2, "country": "ARG"}, {"id": 22256, "name": "M15 Sharm ElSheikh", "type": "atp", "rankId": 0, "surfaceId": 1, "country": "EGY"}, {"id": 22251, "name": "M15 Zamora", "type": "atp", "rankId": 0, "surfaceId": 2, "country": "MEX"}, {"id": 22245, "name": "M25 Columbus", "type": "atp", "rankId": 0, "surfaceId": 3, "country": "USA"}, {"id": 22246, "name": "M25 Montreal", "type": "atp", "rankId": 0, "surfaceId": 3, "country": "CAN"}, {"id": 22244, "name": "M25 San Gregorio di Catania", "type": "atp", "rankId": 0, "surfaceId": 2, "country": "ITA"}, {"id": 22243, "name": "M25 Santa Cruz do Sul", "type": "atp", "rankId": 0, "surfaceId": 2, "country": "BRA"}, {"id": 22242, "name": "M25 Vale do Lobo", "type": "atp", "rankId": 0, "surfaceId": 1, "country": "POR"}, {"id": 22200, "name": "Matsuyama Challenger", "type": "atp", "rankId": 1, "surfaceId": 1, "country": "JPN"}, {"id": 22202, "name": "Monastir 1 Challenger", "type": "atp", "rankId": 1, "surfaceId": 1, "country": "TUN"}, {"id": 22196, "name": "Orleans Challenger", "type": "atp", "rankId": 1, "surfaceId": 3, "country": "FRA"}], "surfaces": [{"id": 1, "name": "Hard"}, {"id": 2, "name": "Clay"}, {"id": 3, "name": "I.hard"}], "countries": [{"acronym": "ARG", "name": "Argentina"}, {"acronym": "AUS", "name": "Australia"}, {"acronym": "BRA", "name": "Brazil"}, {"acronym": "CAN", "name": "Canada"}, {"acronym": "CHN", "name": "China"}, {"acronym": "EGY", "name": "Egypt"}, {"acronym": "ESP", "name": "Spain"}, {"acronym": "FRA", "name": "France"}, {"acronym": "GRE", "name": "Greece"}, {"acronym": "ITA", "name": "Italy"}, {"acronym": "JPN", "name": "Japan"}, {"acronym": "MAS", "name": "Malaysia"}, {"acronym": "MEX", "name": "Mexico"}, {"acronym": "PER", "name": "Peru"}, {"acronym": "POR", "name": "Portugal"}, {"acronym": "SWE", "name": "Sweden"}, {"acronym": "THA", "name": "Thailand"}, {"ac
```

## 2. /upcoming/matches/atp?group=singles&limit=20
HTTP 200
X-Empty-Reason : -

Structure (noms de champs) :
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
matches[].tournament.court.id : int
matches[].tournament.rank.id : int
matches[].tournament.rank.name : str
matches[].tournament.courtId : int
matches[].tournament.countryDetails.name : str
matches[].tournament.countryDetails.acronym : str
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
matches[].odds.totalUnit : str
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
matches[].player2.seed : str
matches[].player2.image : str
matches[].player2.image_p_name : str
matches[].h2h : str
matches[].h2hSummary.matchCount : int
matches[].h2hSummary.player1Wins : int
matches[].h2hSummary.player2Wins : int
matches[].h2hSummary.scope : str
matches[].startTimeStatus : str
matches[].preMatchOdds.player1 : float
matches[].preMatchOdds.player2 : float
matches[].preMatchOdds.updatedAt : NoneType
matches[].preMatchOdds.bookmaker : str
matches[].predictionSummary.available : bool
matches[].predictionSummary.source : str
matches[].predictionSummary.predictedWinnerId : int
matches[].predictionSummary.bookmakerOdds.player1 : float
matches[].predictionSummary.bookmakerOdds.player2 : float
matches[].predictionSummary.bookmakerOdds.bookmaker : str
matches[].predictionSummary.player1ImpliedProbability : float
matches[].predictionSummary.player2ImpliedProbability : float
matches[].predictionSummary.normalized : bool
matches[].modelPrediction.available : bool
matches[].modelPrediction.error : str
matches[].modelPrediction.message : str
matches[].modelPrediction.requiredPlan : str
matches[].modelPrediction.upgradeUrl : str
matches[].startTimeSource : str
matches[].startTimeUpdatedAt : NoneType
matches[].round.id : int
matches[].round.name : str
matches[].startTime : str
page : int
pageNo : int
pageSize : int
limit : int
hasNextPage : bool
totalPages : int
```

Valeurs distinctes des champs de niveau (20 lignes) :
```
rankId : ['1', '2']
rank : ['1', '2']
```

