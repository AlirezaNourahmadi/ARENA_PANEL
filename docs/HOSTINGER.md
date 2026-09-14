# استقرار ARENA روی Hostinger VPS

این استقرار برای Ubuntu 24.04 LTS و Docker Compose طراحی شده است. فایل `.env` فقط روی VPS ساخته می‌شود و در Git قرار نمی‌گیرد.

## معماری

```text
Internet :80/:443/:8443
  -> Caddy
     -> /edge/* -> Gateway :8081
     -> other   -> ARENA :8000
Gateway -> Xray :11000/:11001
ARENA/Gateway -> PostgreSQL
```

تنها Caddy پورت عمومی دارد. پورت `8443` همان TLS listener را به‌عنوان مسیر پشتیبان منتشر می‌کند و با `ARENA_FALLBACK_TLS_PORT` قابل تغییر است. PostgreSQL، Gateway، پنل و inboundهای Xray داخل شبکه Docker باقی می‌مانند.

## نصب اولیه

```bash
apt-get update
apt-get install -y ca-certificates curl git jq
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
ARENA_ACCEPTANCE_URL=https://panel.example.com \
ARENA_ACCEPTANCE_COMPOSE_FILE=docker-compose.vps.yml \
ARENA_ACCEPTANCE_PROXY_PORT=443 \
ARENA_ACCEPTANCE_PROXY_SECURITY=tls \
ARENA_ACCEPTANCE_WS_HOST=panel.example.com \
ARENA_ACCEPTANCE_SERVER_NAME=panel.example.com \
./scripts/acceptance.sh
```

`panel.example.com` را با دامنه production جایگزین کنید. این سناریو یک کاربر موقت می‌سازد، VLESS، VMess و DNS را از مسیر TLS واقعی Caddy/Gateway/Xray آزمایش می‌کند، یک payload هشت مگابایتی را کامل عبور می‌دهد، سرعت آن را گزارش می‌کند، ثابت‌ماندن PID هسته را کنترل می‌کند و کاربر موقت را حذف می‌کند.

## بهینه‌سازی شبکه VPS

برای مسیرهای با latency یا packet loss بالاتر، BBR همراه `fq` از افت شدید خروجی TCP جلوگیری می‌کند. تنظیم versioned پروژه را یک‌بار با دسترسی root اجرا کنید:

```bash
./scripts/tune-vps-network.sh
```

خروجی نهایی باید شامل این دو مقدار باشد:

```text
net.ipv4.tcp_congestion_control = bbr
net.core.default_qdisc = fq
```

فایل‌های دائمی در `/etc/modules-load.d/arena-bbr.conf` و `/etc/sysctl.d/99-arena-network.conf` نصب می‌شوند و پس از reboot نیز اعمال خواهند شد.

برای مقایسه مستقیم خروجی سرور می‌توان از یک upload کنترل‌شده استفاده کرد:

```bash
dd if=/dev/zero bs=1M count=50 2>/dev/null | \
  curl -sS --max-time 30 -o /dev/null \
  -w 'bytes=%{size_upload} seconds=%{time_total} speed_Bps=%{speed_upload}\n' \
  -X POST --data-binary @- https://speed.cloudflare.com/__up
```

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
ufw allow 8443/tcp
ufw --force enable
```

## مسیر TLS پشتیبان

اگر مسیر مستقیم ISP روی SNI دامنه یا پورت `443` مختل شد، یک hostname ثانویه با گواهی معتبر به `ARENA_SITE_ADDRESS` اضافه کنید و در پنل یک Node غیر adaptive با همان hostname و پورت `8443` بسازید. نمونه:

```text
ARENA_SITE_ADDRESS=panel.example.com, edge.example.net
ARENA_FALLBACK_TLS_PORT=8443
```

Node پشتیبان همچنان از Caddy، Gateway و Xray عبور می‌کند؛ بنابراین محدودیت حجم، IP، سرعت و ثبت نشست‌ها دور زده نمی‌شود. دامنه اصلی و پورت `443` نیز فعال می‌مانند.

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
- بعد از تغییر kernel یا image سیستم، خروجی `scripts/tune-vps-network.sh` را دوباره کنترل کنید.

برای دریافت نسخه جدید شاخه و بازسازی سرویس‌ها، ابتدا از دیتابیس backup بگیرید و سپس source را جایگزین کنید؛ فایل `.env` و volumeهای Docker نباید حذف شوند.
