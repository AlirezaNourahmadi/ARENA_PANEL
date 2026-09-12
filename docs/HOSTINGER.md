# استقرار ARENA روی Hostinger VPS

این استقرار برای Ubuntu 24.04 LTS و Docker Compose طراحی شده است. فایل `.env` فقط روی VPS ساخته می‌شود و در Git قرار نمی‌گیرد.

## معماری

```text
Internet :80/:443
  -> Caddy
     -> /edge/* -> Gateway :8081
     -> other   -> ARENA :8000
Gateway -> Xray :11000/:11001
ARENA/Gateway -> PostgreSQL
```

تنها Caddy پورت عمومی دارد. PostgreSQL، Gateway، پنل و inboundهای Xray داخل شبکه Docker باقی می‌مانند.

## نصب اولیه

```bash
apt-get update
apt-get install -y ca-certificates curl git
curl -fsSL https://get.docker.com | sh
systemctl enable --now docker
```

سورس شاخه `hostinger` را در `/opt/arena` قرار دهید و `.env.vps.example` را به `.env` تبدیل کنید. همه placeholderها باید با مقادیر تصادفی مستقل تعویض شوند.

برای اجرای اولیه با IP:

```text
ARENA_SITE_ADDRESS=http://SERVER_IP
ARENA_COOKIE_SECURE=false
```

سپس:

```bash
docker compose -f docker-compose.vps.yml up -d --build
docker compose -f docker-compose.vps.yml ps
```

برای پذیرش کامل دیتا‌پلین روی خود VPS، بعد از سالم‌شدن همه containerها اجرا کنید:

```bash
ARENA_ACCEPTANCE_URL=http://localhost ./scripts/acceptance.sh
```

این سناریو یک کاربر موقت می‌سازد، VLESS، VMess و DNS را از مسیر عمومی Caddy/Gateway/Xray آزمایش می‌کند، ثابت‌ماندن PID هسته را کنترل می‌کند و کاربر موقت را حذف می‌کند.

## اتصال دامنه و HTTPS

رکورد `A` دامنه را به IPv4 سرور متصل کنید. پس از انتشار DNS، در `.env` تنظیم کنید:

```text
ARENA_SITE_ADDRESS=panel.example.com
ARENA_COOKIE_SECURE=true
```

با اجرای مجدد Compose، Caddy گواهی TLS را به‌صورت خودکار دریافت و تمدید می‌کند:

```bash
docker compose -f docker-compose.vps.yml up -d
```

## فایروال

بعد از تأیید SSH، فقط پورت‌های لازم باز بمانند:

```bash
ufw allow OpenSSH
ufw allow 80/tcp
ufw allow 443/tcp
ufw allow 443/udp
ufw --force enable
```

## کنترل سلامت

```bash
curl -fsS http://127.0.0.1/healthz
curl -fsS http://127.0.0.1/api/health
docker compose -f docker-compose.vps.yml ps
```

پس از فعال‌شدن HTTPS، پنل از `/login` باز می‌شود. لینک Subscription و مشخصات TLS/SNI/WebSocket به‌صورت adaptive از همان دامنه تولید می‌شوند.

## نگهداری

- داده PostgreSQL در volume `arena-postgres` ذخیره می‌شود.
- گواهی‌های Caddy در `arena-caddy-data` ذخیره می‌شوند.
- قبل از ارتقا از PostgreSQL backup بگیرید.
- فایل `.env` را با مجوز `600` نگه دارید.
- برای Gateway در فاز ۱ فقط یک replica اجرا کنید.

برای دریافت نسخه جدید شاخه و بازسازی سرویس‌ها، ابتدا از دیتابیس backup بگیرید و سپس source را جایگزین کنید؛ فایل `.env` و volumeهای Docker نباید حذف شوند.
