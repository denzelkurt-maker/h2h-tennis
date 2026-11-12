# Test sportsapi365 (2026-11-12 12:09 UTC)

## 1. /upcoming/filters/atp?include=options
HTTP 403
X-Empty-Reason : -
Restant (en-têtes) : 

Corps non JSON :
```
{"type":"https://developers.cloudflare.com/support/troubleshooting/http-status-codes/cloudflare-1xxx-errors/error-1010/","title":"Error 1010: Access denied","status":403,"detail":"The site owner has blocked access based on your browser's signature.","instance":"a5956dc43ffd5d13","error_code":1010,"error_name":"browser_signature_banned","error_category":"access_denied","ray_id":"a5956dc43ffd5d13","
```

## 2. /upcoming/matches/atp?group=singles&limit=20
HTTP 403
X-Empty-Reason : -

Corps non JSON :
```
{"type":"https://developers.cloudflare.com/support/troubleshooting/http-status-codes/cloudflare-1xxx-errors/error-1010/","title":"Error 1010: Access denied","status":403,"detail":"The site owner has blocked access based on your browser's signature.","instance":"a5956dc47ec77abc","error_code":1010,"error_name":"browser_signature_banned","error_category":"access_denied","ray_id":"a5956dc47ec77abc","
```

