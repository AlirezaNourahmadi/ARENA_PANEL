# گزارش تحویل فاز ۱ ARENA

تاریخ گزارش: ۱۴۰۵/۰۶/۲۲ (2026-09-13)

## به‌روزرسانی آدرس‌دهی عمومی

- مقدار پیش‌فرض `ARENA_PUBLIC_URL` از آدرس ثابت localhost به `auto` تغییر کرد.
- URL سابسکریپشن و دانلودها از origin عمومی همان درخواست ساخته می‌شود.
- نودهای پیش‌فرض VLESS/VMess به حالت adaptive منتقل شدند؛ آدرس، پورت، TLS، SNI و WebSocket Host از دامنه deployment تولید می‌شود.
- برای نود Xray امکان خاموش‌کردن حالت adaptive و ثبت endpoint ثابت در پنل حفظ شده است.
- سناریوی forwarded host/proto به تست‌های API اضافه شد تا بازگشت ناخواسته localhost شناسایی شود.
- false positive ابزار GitGuardian در اسکریپت acceptance حذف و نبود credentialهای محلی در کل تاریخچه Git کنترل شد.

## شاخه و استقرار Hostinger

- نسخه پایدار قبلی VPS در شاخه `hostinger` حفظ شده و مسیر بازیابی جدید در شاخه مستقل `hostinger-reality` نگهداری می‌شود؛ شاخه `main` بدون تنظیمات میزبان باقی می‌ماند.
- Compose تولید با PostgreSQL، ARENA، Gateway، Xray و Caddy در `docker-compose.vps.yml` تعریف شده است.
- پورت‌های `80`، `443` و `8443` از Caddy منتشر می‌شوند و مسیر مستقل VLESS/TCP/REALITY روی `2053/TCP` قرار دارد؛ دیتابیس، API هسته و inboundهای داخلی از اینترنت قابل دسترسی نیستند.
- state برنامه در volume نام‌دار PostgreSQL و گواهی‌های Caddy در volumeهای مستقل نگهداری می‌شوند.
- فایل `.env` روی VPS و خارج از Git ساخته می‌شود؛ مخزن فقط `.env.vps.example` بدون secret را دارد.
- اجرای اولیه با IP و HTTP ممکن است. پس از تنظیم DNS، Caddy با قرارگرفتن دامنه در `ARENA_SITE_ADDRESS` گواهی TLS را خودکار صادر و تمدید می‌کند.
- `ARENA_PUBLIC_URL=auto` باعث می‌شود لینک Subscription، آدرس نود، پورت، TLS، SNI و WebSocket Host از origin عمومی درخواست ساخته شوند و به localhost وابسته نباشند.
- راهنمای نصب، فایروال، اتصال دامنه، کنترل سلامت و نگهداری در `docs/HOSTINGER.md` ثبت شده است.

## هدف

ساخت یک ریپازیتوری مستقل برای پنل ARENA بدون تغییر پروژه قبلی Railway/Northflank. هیچ سرویس پولی، volume ابری یا دیتابیس مدیریت‌شده خریداری یا ایجاد نشده است.

## خروجی‌های تحویل‌شده

### کنترل‌پلین

- FastAPI و SQLAlchemy با PostgreSQL.
- Alembic برای نسخه‌بندی schema و ارتقای دیتابیس موجود.
- مدل‌های مدیر، کاربر، نود، کلید، نشست و Audit.
- سهمیه حجم، اعتبار از اولین اتصال، IP همزمان و سرعت.
- login امن، session، CSRF و subscription قابل ابطال.

### دیتا‌پلین

- Xray Core 26.3.27 رسمی داخل image برنامه.
- inboundهای جداگانه VLESS/WS و VMess/WS.
- HandlerService برای افزودن و حذف پویا بدون restart.
- Go WebSocket Gateway با relay دودطرفه، heartbeat و ثبت uplink/downlink.
- token bucket مشترک هر کاربر برای محدودیت سرعت.
- کنترل IP واقعی با ingress header بازنویسی‌شده و محافظت در برابر spoofing.
- outbound با `UseIPv4` برای رفتار پایدارتر در محیط‌های فاقد IPv6 سالم.
- سقف خواندن هر پیام WebSocket در Gateway از پیش‌فرض ۳۲ کیلوبایت به ۱۶ مگابایت افزایش یافته است تا payloadهای بزرگ با `StatusMessageTooBig` بسته نشوند.
- Gateway پیش از ثبت نهایی ترافیک منتظر پایان هر دو relay و heartbeat می‌ماند و خطاهای غیرعادی را با شناسه نشست لاگ می‌کند.
- token bucket اکنون chunk بزرگ‌تر از نرخ یک‌ثانیه‌ای را مرحله‌ای مصرف می‌کند و در سرعت‌های پایین وارد انتظار بی‌نهایت نمی‌شود.
- inbound اختیاری VLESS/TCP/REALITY با Vision بدون وابستگی به HTTP، TLS سایت یا WebSocket اضافه شده است.
- افزودن و حذف کاربر REALITY با HandlerService و بدون restart هسته انجام می‌شود.
- StatsService مصرف uplink/downlink، شروع اعتبار و IPهای آنلاین را به PostgreSQL منتقل می‌کند؛ RoutingService محدودیت IP همزمان را اعمال می‌کند.
- کلید خصوصی REALITY فقط در `.env` VPS نگهداری می‌شود و هیچ‌گاه در API، دیتابیس، subscription یا Git قرار نمی‌گیرد.

### Subscription و فرمت‌ها

- Subscription Base64 و raw.
- headerهای استاندارد مصرف، انقضا، عنوان و دوره update.
- اولین کانفیگ اطلاع‌رسان عمداً غیرفعال با UUID صفر و مقصد loopback.
- لینک مستقیم VLESS و VMess.
- deep link واردکردن Subscription در Hiddify.
- فایل WireGuard با کلید X25519 و IP یکتا برای backend خارجی.
- XML و اعتبارنامه Cisco/OpenConnect برای backend خارجی.

### رابط ARENA

- طراحی اختصاصی RTL با نشان ARENA، رنگ‌بندی graphite/green/cyan و فونت فارسی.
- داشبورد مصرف و نشست‌های اخیر.
- ساخت، جست‌وجو، ویرایش، توقف و حذف کاربر.
- تولید و کپی لینک‌های خروجی.
- ساخت و ویرایش نود با Protocol، TLS، SNI، WebSocket Host/Path، Fingerprint و ALPN.
- نمای ردیابی نشست و Audit.
- وضعیت سلامت دیتابیس و Xray.
- navigation و لیست کاربران مخصوص موبایل بدون اسکرول افقی.

## اصلاح‌های ریشه‌ای نسبت به نمونه قبلی

1. state دیگر در `/data` یا فایل محلی نگهداری نمی‌شود؛ PostgreSQL منبع حقیقت است.
2. WebSocket توسط Gateway اختصاصی relay می‌شود و فقط پس از authorize به Xray می‌رسد.
3. IP، حجم، اعتبار و سرعت قبل و حین اتصال کنترل می‌شوند.
4. افزودن کاربر Xray را restart نمی‌کند؛ تست PID این موضوع را کنترل می‌کند.
5. شمارنده‌ها و quota از نوع BIGINT هستند و در PostgreSQL overflow سی‌ودوبیتی ندارند.
6. schema دیتابیس migration دارد و بین محیط‌ها به ساخت ضمنی وابسته نیست.

## شواهد آزمون

آخرین اجرای acceptance محلی:

```text
health=ok
google=204 cloudflare=204 dns=192.178.25.206
payload=8388608/8388608 speed_Bps=38694269 seconds=0.216792
xray_pid=13 dynamic_user_sync=ok
cleanup=ok
```

تفسیر:

- درخواست Google از VLESS عبور کرده است.
- درخواست Cloudflare از VMess عبور کرده است.
- DNS/UDP از VLESS پاسخ گرفته است.
- PID هسته هنگام ساخت کاربر ثابت مانده است.
- payload هشت مگابایتی بدون کم‌شدن یا قطع اتصال از کل مسیر WebSocket عبور کرده است.

## نتیجه عیب‌یابی دانلود VPS

- همه کاربران production با `speed_limit_bps=0` بررسی شدند؛ محدودیت نرم‌افزاری روی دانلود فعال نبود.
- سلامت VPS در زمان بررسی مناسب بود: حدود ۱۹٪ RAM و ۴ از ۵۰ گیگابایت دیسک مصرف شده بود و Gateway زیر بار نمونه حدود ۱٪ CPU داشت.
- تست مستقیم ورودی سرور از Cloudflare حدود `425 Mbps` بود، اما خروجی TCP با `cubic` حدود `63 Mbps` اندازه‌گیری شد.
- با بارگذاری `tcp_bbr` و تغییر qdisc به `fq`، دو تست خروجی بعدی حدود `467 Mbps` و `285 Mbps` ثبت کردند.
- تنظیم BBR در فایل‌های versioned بخش `deploy/` نگهداری و با `scripts/tune-vps-network.sh` به‌صورت دائمی نصب می‌شود.

آزمون‌های خودکار:

```text
Python: 14 passed
Go gateway/limiter: passed
Frontend production build: passed
Xray config validation: passed
REALITY: Google 204, payload 20971520/20971520, accounting/session passed
```

## قطعی ۱۴ سپتامبر و مسیر بازیابی

- پنل و آزمون داخلی سالم بودند، اما TLS/HTTP/WebSocket روی اینترنت مستقیم کاربر پس از برقراری TCP reset یا متوقف می‌شدند؛ بنابراین مشکل از UUID، دیتابیس، `/data` یا تفاوت هسته کلاینت و سرور نبود.
- packet capture روی VPS retransmit پاسخ TLS و نرسیدن ACKهای بعدی را نشان داد و بازه رخداد با نگهداری اعلام‌شده دیتاسنتر Hostinger هم‌پوشانی داشت.
- مسیر VLESS/TCP/REALITY روی پورت مستقل `2053` با مقصد آزموده‌شده `www.google.com:443` اضافه شد و WebSocket موجود برای سازگاری حفظ شد.
- تست مستقیم اینترنت کاربر HTTP 204 و payload هشت MiB را عبور داد؛ IP واقعی ورودی نیز در سمت VPS مشاهده شد.
- اسکریپت `scripts/reality-acceptance.sh` یک کاربر موقت می‌سازد، لینک adaptive را به کانفیگ Xray تبدیل می‌کند، ۲۰ MiB داده عبور می‌دهد و ثبت مصرف/session را از API پنل کنترل می‌کند.
- جزئیات packet-level و تصمیم معماری در `docs/HOSTINGER_OUTAGE_2026-09-14.md` ثبت شده است.

رابط در اندازه دسکتاپ و موبایل با Browser Playwright بررسی شد. فرم ساخت کاربر، خروجی‌های Subscription و navigation اصلی نیز طی شدند.

## محدودیت‌های شفاف فاز ۱

- WireGuard و Cisco/OpenConnect فقط پروفایل backend خارجی تولید می‌کنند؛ daemon سرور را provision نمی‌کنند.
- محدودیت سرعت در یک Gateway دقیق است. حالت چند replica به Redis نیاز دارد.
- مسیر REALITY حجم، روز و IP همزمان را اعمال می‌کند، اما محدودیت سرعت کاربرمحور فعلاً فقط روی WebSocket/Gateway فعال است.
- MFA و RBAC چندمدیره هنوز وجود ندارد.
- WebSocket و VMess در Xray 26.3.27 deprecated اعلام شده‌اند؛ پشتیبانی فعلی برای سازگاری محصول است.
- سرعت نهایی روی هر ISP به route بین کاربر و دیتاسنتر فرانکفورت وابسته است؛ benchmark سرور جای تست واقعی دستگاه کاربر را نمی‌گیرد.
- مخزن خصوصی GitHub با نام `ARENA_PANEL` ایجاد شده و شاخه‌های محیطی مستقل نگهداری می‌شوند.

## سناریوی تست پذیرش کاربر

1. آدرس `/login` روی origin همان محیط را باز کنید؛ برای نمونه `http://localhost:8080/login` در توسعه یا `https://panel.example.com/login` در production.
2. در کاربران، یک کاربر با حجم کم، ۷ روز، ۱ IP و هر دو نود بسازید.
3. «لینک‌ها» را باز و Subscription را در Hiddify/NekoBox/V2Box وارد کنید.
4. ابتدا یک سایت HTTPS و سپس DNS را آزمایش کنید.
5. در «ردیابی» نشست، IP و uplink/downlink را کنترل کنید.
6. سرعت و حجم را کاهش دهید و terminate شدن اتصال را بررسی کنید.
7. subscription را rotate کنید و مطمئن شوید لینک قدیمی دیگر پاسخ نمی‌دهد.

پس از این تست، لاگ کلاینت و بخش ردیابی ARENA مبنای دیباگ فاز بعد خواهد بود.
