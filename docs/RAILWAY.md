# استقرار ARENA روی Railway

Railway فایل `.env` را از repository نمی‌خواند و نباید این فایل در Git باشد. متغیرهای production در Variables خود Railway ثبت می‌شوند. این deployment از چهار سرویس در یک Project و Environment استفاده می‌کند:

| سرویس | Source | Root Directory | دسترسی عمومی |
|---|---|---|---|
| `Postgres` | Railway PostgreSQL | - | خیر |
| `arena` | شاخه `railway` همین repository | `/` | خیر |
| `gateway` | شاخه `railway` همین repository | `/gateway` | خیر |
| `edge` | شاخه `railway` همین repository | `/deploy/railway` | بله |

Railway `docker-compose.yml` را به‌عنوان runtime اجرا نمی‌کند؛ هر عضو Compose یک Railway Service مستقل است. فقط `edge` دامنه عمومی می‌گیرد. ارتباط داخلی از دامنه‌های `*.railway.internal` انجام می‌شود.

## Variables سرویس arena

```text
ARENA_ENV=production
ARENA_PUBLIC_URL=auto
ARENA_DATABASE_URL=${{Postgres.DATABASE_URL}}
ARENA_APP_SECRET=<random secret, at least 32 chars>
ARENA_GATEWAY_SECRET=<same shared value used by gateway>
ARENA_ADMIN_USERNAME=admin
ARENA_ADMIN_PASSWORD=<strong password, at least 12 chars>
ARENA_COOKIE_SECURE=true
ARENA_XRAY_ENABLED=true
ARENA_XRAY_INTERNAL_HOST=arena.railway.internal
ARENA_TRUST_PROXY_HEADERS=true
```

پورت داخلی برنامه `8000` است. Healthcheck این سرویس باید `/api/health` و target port آن `8000` باشد.

## Variables سرویس gateway

```text
ARENA_API_URL=http://arena.railway.internal:8000
ARENA_GATEWAY_SECRET=<same value used by arena>
ARENA_GATEWAY_LISTEN=:8081
ARENA_TRUST_PROXY_HEADERS=true
ARENA_TRUSTED_PROXY_HOPS=1
ARENA_TRUST_CLOUDFLARE_HEADER=false
```

پورت داخلی Gateway مقدار `8081` است. Healthcheck آن `/health` است و نباید public domain داشته باشد.

## Variables سرویس edge

```text
ARENA_APP_UPSTREAM=arena.railway.internal:8000
ARENA_GATEWAY_UPSTREAM=gateway.railway.internal:8081
```

برای `edge` یک Railway Domain بسازید و target port را روی مقدار `PORT` خود سرویس قرار دهید. Healthcheck آن `/healthz` است. Railway روی این دامنه TLS را terminate و `X-Forwarded-Proto=https` و `X-Forwarded-Host` را ارسال می‌کند؛ Edge آن‌ها را به ARENA منتقل می‌کند تا Subscription و کانفیگ‌ها از همان دامنه عمومی ساخته شوند.

## ترتیب کنترل

1. هر چهار سرویس باید Active باشند.
2. `https://<edge-domain>/healthz` باید 200 برگرداند.
3. `https://<edge-domain>/api/health` باید وضعیت database و Xray را `ok` نشان دهد.
4. پنل فقط از `https://<edge-domain>/login` باز شود.
5. یک کاربر بسازید و بررسی کنید Subscription و VLESS/VMess دامنه Edge و پورت 443 داشته باشند.
6. WebSocket path باید `/edge/{node_id}/{user_id}` باشد.

هیچ volume برای `arena`، `gateway` یا `edge` لازم نیست. پایداری داده توسط سرویس PostgreSQL Railway تأمین می‌شود.
