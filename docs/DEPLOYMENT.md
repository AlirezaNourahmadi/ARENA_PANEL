# استقرار و عملیات

## محیط محلی

```bash
cp .env.example .env
docker compose up -d --build
curl http://localhost:8080/api/health
```

Compose یک volume فقط برای PostgreSQL می‌سازد. برنامه و Xray stateless هستند.

## متغیرهای ضروری production

| متغیر | کاربرد |
|---|---|
| `ARENA_ENV=production` | فعال‌کردن کنترل secretهای ضعیف |
| `ARENA_PUBLIC_URL=auto` | ساخت آدرس پنل و کانفیگ‌ها از دامنه درخواست؛ می‌توان URL ثابت HTTPS نیز داد |
| `ARENA_DATABASE_URL` | DSN پایدار PostgreSQL |
| `ARENA_APP_SECRET` | امضای subscription و رمزنگاری secretها، حداقل ۳۲ کاراکتر |
| `ARENA_GATEWAY_SECRET` | احراز هویت Gateway، حداقل ۳۲ کاراکتر |
| `ARENA_ADMIN_USERNAME` | مدیر اولیه |
| `ARENA_ADMIN_PASSWORD` | رمز قوی مدیر اولیه |
| `ARENA_COOKIE_SECURE=true` | ارسال cookie فقط روی HTTPS |
| `ARENA_TRUSTED_PROXY_HOPS` | تعداد proxyهای قابل اعتماد جلوی Gateway |

## آدرس‌دهی adaptive

نودهای پیش‌فرض VLESS و VMess با `adaptive_endpoint=true` ساخته می‌شوند. در این حالت برنامه برای هر درخواست موارد زیر را از origin عمومی پنل استخراج می‌کند:

- آدرس و پورت VLESS/VMess
- نوع امنیت بر اساس `https` یا `http`
- مقدار TLS SNI
- مقدار WebSocket Host
- مبدا لینک subscription و دانلودها

ترتیب تشخیص origin در حالت `auto`، ابتدا `X-Forwarded-Proto` و `X-Forwarded-Host` و سپس scheme و `Host` خود درخواست است. Ingress production باید headerهای forwarded را خودش بازنویسی کند. اگر این تضمین وجود ندارد یا فقط یک دامنه مجاز است، `ARENA_PUBLIC_URL` را به URL ثابت همان دامنه تنظیم کنید.

نودهای خارجی WireGuard/Cisco و نودهای Xray که گزینه «آدرس از دامنه پنل» در آن‌ها خاموش است، همچنان از آدرس و پورت ذخیره‌شده خود نود استفاده می‌کنند.

## استقرار روی پلتفرم کانتینری

1. PostgreSQL پایدار بسازید و backup دوره‌ای فعال کنید.
2. image برنامه و image Gateway را deploy کنید.
3. پورت‌های 11000، 11001 و 10085 را public نکنید.
4. فقط ingress عمومی 443 را به Caddy/Ingress بدهید.
5. `/edge/*` به Gateway و بقیه مسیرها به `arena:8000` route شوند.
6. Gateway و برنامه باید در یک شبکه خصوصی به هم و Xray دسترسی داشته باشند.
7. health check برنامه `/api/health` و health check Gateway `/health` است.
8. برای فاز ۱ Gateway را با یک replica اجرا کنید.

تنها deploy کردن کانتینر `arena` کافی نیست؛ اتصال عمومی WebSocket به سرویس `gateway` و اتصال خصوصی Gateway به Xray داخل سرویس `arena` وابسته است.

در Northflank یا سرویس مشابه نیازی به volume روی `/data` نیست. فقط PostgreSQL باید پایدار باشد؛ config Xray در startup از دیتابیس بازسازی می‌شود.

## TLS و IP واقعی

در production، TLS باید روی ingress معتبر terminate شود. Caddy همراه پروژه header `X-Arena-Client-IP` را با IP اتصال خودش بازنویسی می‌کند تا header ارسالی کاربر قابل جعل نباشد. اگر Cloudflare جلوی ingress قرار دارد، فقط پس از محدودکردن origin به IPهای Cloudflare گزینه `ARENA_TRUST_CLOUDFLARE_HEADER=true` را فعال کنید.

مقدار اشتباه `ARENA_TRUSTED_PROXY_HOPS` می‌تواند محدودیت IP را خراب کند؛ آن را مطابق تعداد proxyهای واقعی تنظیم کنید.

## migration و backup

Migrationها در startup اجرا می‌شوند. قبل از upgrade production:

```bash
pg_dump "$ARENA_DATABASE_URL" > arena-backup.sql
docker compose up -d --build
```

Downgrade migration شمارنده‌ها از BIGINT به INTEGER ممکن است برای دیتای بزرگ loss ایجاد کند و برای production توصیه نمی‌شود.

## کنترل بعد از استقرار

1. وضعیت `/api/health` باید `ok` باشد.
2. از پنل یک کاربر با نود VLESS و VMess بسازید.
3. Subscription را در Hiddify یا کلاینت Xray وارد کنید.
4. یک مقصد HTTPS و DNS را تست کنید.
5. در بخش ردیابی باید IP، uplink، downlink و close reason دیده شود.
6. در log برنامه فقط یک پیام startup هسته دیده شود؛ ساخت کاربر نباید Xray را restart کند.
