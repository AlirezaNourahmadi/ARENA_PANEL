# ARENA Control Plane

ARENA یک پنل مستقل مدیریت دسترسی پراکسی است. فاز ۱ شامل پنل مدیر فارسی، سابسکریپشن، VLESS/VMess روی WebSocket، سهمیه و اعتبار، محدودیت IP و سرعت، ردیابی نشست‌ها و تولید پروفایل‌های خارجی WireGuard و Cisco/OpenConnect است.

## وضعیت فاز ۱

| قابلیت | وضعیت |
|---|---|
| VLESS + WebSocket | فعال و تست‌شده با Xray Core |
| VMess + WebSocket | فعال و تست‌شده با Xray Core |
| لینک Subscription و Hiddify | فعال |
| کانفیگ وضعیت مصرف در ابتدای Subscription | فعال و عمداً غیرقابل اتصال |
| محدودیت حجم، روز، IP همزمان و سرعت | فعال |
| نشست‌ها و Audit log | فعال |
| WireGuard | تولید پروفایل برای سرور خارجی |
| Cisco/OpenConnect | تولید XML و اعتبارنامه برای سرور خارجی |

جزئیات مرز قابلیت‌ها در [گزارش فاز ۱](docs/PHASE1_CHANGE_REPORT.md) آمده است.

## اجرای محلی

پیش‌نیاز: Docker Desktop و ابزارهای `curl` و `jq`.

```bash
cp .env.example .env
docker compose up -d --build
```

پنل از مسیر زیر در دسترس است:

```text
http://localhost:8080/login
```

قبل از هر استقرار عمومی، مقادیر `ARENA_APP_SECRET`، `ARENA_GATEWAY_SECRET` و `ARENA_ADMIN_PASSWORD` را تغییر دهید. مقدار پیش‌فرض `ARENA_PUBLIC_URL=auto` باعث می‌شود لینک سابسکریپشن، آدرس VLESS/VMess، `Host` و `SNI` از دامنه همان درخواست ساخته شوند؛ بنابراین سورس به `localhost` یا دامنه یک پلتفرم خاص وابسته نیست.

اگر دامنه ثابتی می‌خواهید، `ARENA_PUBLIC_URL=https://panel.example.com` را صریح تنظیم کنید. در صفحه نودها نیز گزینه «آدرس از دامنه پنل» برای نودهای Xray قابل فعال یا غیرفعال‌کردن است.

## آزمون انتها‌به‌انتها

```bash
./scripts/acceptance.sh
```

این آزمون یک کاربر واقعی می‌سازد، ثابت‌ماندن پردازش Xray هنگام افزودن کاربر را کنترل می‌کند، سپس VLESS، VMess و DNS/UDP را از داخل کانتینرهای Xray client آزمایش می‌کند.

## مستندات

- [معماری](docs/ARCHITECTURE.md)
- [فلوهای اپلیکیشن](docs/FLOWS.md)
- [استقرار و عملیات](docs/DEPLOYMENT.md)
- [استقرار روی Hostinger VPS](docs/HOSTINGER.md)
- [امنیت](docs/SECURITY.md)
- [گزارش کامل تغییرات فاز ۱](docs/PHASE1_CHANGE_REPORT.md)

## ساختار پروژه

```text
backend/     FastAPI، SQLAlchemy، Alembic و کنترل Xray
frontend/    React، Vite و رابط اختصاصی ARENA
gateway/     درگاه WebSocket و اعمال محدودیت سرعت
deploy/      تنظیم ingress با Caddy
scripts/     آزمون واقعی data plane
```

## نکته درباره Xray

Xray Core 26.3.27 برای WebSocket و VMess هشدار deprecation نمایش می‌دهد. این دو در فاز ۱ به درخواست محصول پشتیبانی شده‌اند، اما مسیر توسعه بعدی باید VLESS Encryption و XHTTP/H2/H3 باشد.

## نکته درباره اجرا

ساخت لینک به‌تنهایی سرور عمومی ایجاد نمی‌کند. برای پینگ و عبور ترافیک خارج از دستگاه توسعه، هر سه سرویس `arena`، `gateway` و ingress به‌همراه PostgreSQL باید روی یک میزبان عمومی deploy شوند و مسیر `/edge/*` به Gateway برسد.
