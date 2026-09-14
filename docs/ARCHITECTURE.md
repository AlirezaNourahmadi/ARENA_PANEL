# معماری ARENA

## اجزا

1. `caddy`: ورودی عمومی HTTP/HTTPS. درخواست‌های `/edge/*` را به Gateway و بقیه مسیرها را به Control Plane می‌فرستد.
2. `gateway`: سرویس Go برای WebSocket. قبل از Upgrade مجوز می‌گیرد، IP و سرعت را اعمال می‌کند و ترافیک را گزارش می‌دهد.
3. `arena`: برنامه FastAPI و فایل‌های build شده React. این کانتینر پردازش رسمی Xray Core را نیز مدیریت می‌کند.
4. `postgres`: منبع اصلی و پایدار کاربران، کلیدها، نشست‌ها، مصرف و رویدادها.
5. `xray`: دو inbound داخلی WebSocket، یک inbound اختیاری VLESS/REALITY و APIهای HandlerService/StatsService/RoutingService دارد.

## مسیر داده

```text
Client
  -> TLS/HTTP ingress
  -> /edge/{node_id}/{user_id}
  -> ARENA Gateway
  -> authorize در Control Plane
  -> ws://arena:11000/internal/vless
     یا ws://arena:11001/internal/vmess
  -> Xray freedom outbound (IPv4)
  -> Destination
```

ورودی‌های WebSocket مستقیماً publish نشده‌اند. مسیر عمومی آن‌ها فقط Gateway است؛ بنابراین کاربر پیش از رسیدن به Xray از کنترل سهمیه، اعتبار و IP عبور می‌کند.

مسیر بازیابی REALITY عمداً از HTTP و WebSocket مستقل است:

```text
Client -> public-host:2053/TCP -> Xray REALITY :12000 -> Destination
```

این ورودی با متغیر محیطی فعال می‌شود. کلید خصوصی فقط در `.env` سرور می‌ماند. برنامه آمار ترافیک و IPهای آنلاین را هر ۱۵ ثانیه از StatsService می‌خواند، در PostgreSQL ثبت می‌کند و ruleهای محدودیت IP را با RoutingService همگام می‌سازد. سهمیه و انقضا با حذف پویا از inbound اعمال می‌شوند. محدودیت سرعت token bucket فقط متعلق به Gateway است و روی REALITY اعمال نمی‌شود.

## همگام‌سازی Xray

هنگام startup، config کامل Xray از PostgreSQL ساخته و اعتبارسنجی می‌شود. در زمان اجرا، ساخت/حذف کاربر و تغییر مجوز با `HandlerService` و فرمان‌های API خود Xray انجام می‌شود. نشست‌های دیگر ری‌استارت نمی‌شوند. اگر API پویا خطا بدهد، runtime یک‌بار با وضعیت مطلوب دیتابیس بازیابی می‌شود.

هر credential ایمیل داخلی یکتا به شکل زیر دارد:

```text
{credential}@{protocol}.arena
{credential}@reality.arena
```

این شناسه فقط برای مدیریت داخلی Xray است و در UI نمایش داده نمی‌شود.

## منبع حقیقت و persistence

همه state پایدار در PostgreSQL ذخیره می‌شود. دایرکتوری Xray در `/tmp/arena-xray` فقط config قابل بازسازی است و به volume نیاز ندارد. بنابراین حذف یا جابه‌جایی کانتینر برنامه باعث از دست رفتن کاربران نمی‌شود، مشروط به اینکه PostgreSQL پایدار باشد.

تغییر schema با Alembic نسخه‌بندی می‌شود. نصب‌های قدیمی فاقد `alembic_version` روی revision اولیه stamp می‌شوند و سپس migrationهای جدید را اجرا می‌کنند.

## مدل داده

- `admins`, `admin_sessions`: مدیر و نشست‌های opaque.
- `users`: سهمیه، مصرف، اعتبار، IP و سرعت.
- `nodes`: نوع، پروتکل، Host، TLS، SNI، WS Host، Path، Fingerprint و ALPN.
- `access_keys`: credential هر کاربر روی هر نود و secret رمزنگاری‌شده پروفایل‌های خارجی.
- `connection_sessions`: IP، زمان، ترافیک، وضعیت و علت بسته‌شدن.
- `audit_events`: رخدادهای مدیریتی و Gateway.

شمارنده‌های حجم و سرعت `BIGINT` هستند تا حجم‌های بالاتر از ۲ گیگابایت در PostgreSQL overflow نکنند.

## مرز مقیاس‌پذیری فاز ۱

محدودیت IP در PostgreSQL اعمال می‌شود و میان replicaها مشترک است. در مسیر REALITY، IPهای آنلاین هسته منبع اعمال ruleهای user+source هستند. token bucket سرعت داخل حافظه Gateway نگهداری می‌شود؛ برای اعمال دقیق سرعت روی REALITY به data plane دارای shaping کاربرمحور نیاز است و در نسخه فعلی فعال نیست. در فاز ۱ Gateway را با یک replica اجرا کنید.
