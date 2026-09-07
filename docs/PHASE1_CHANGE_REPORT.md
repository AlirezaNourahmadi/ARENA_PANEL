# گزارش تحویل فاز ۱ ARENA

تاریخ گزارش: ۱۴۰۵/۰۶/۱۶ (2026-09-07)

## شاخه Railway

- شاخه مستقل `railway` بدون تغییر رفتار شاخه `main` ایجاد شد.
- PostgreSQL URL استاندارد Railway به driver صریح Psycopg 3 تبدیل می‌شود.
- migration تا آماده‌شدن دیتابیس Railway با فاصله کنترل‌شده retry می‌شود.
- Edge اختصاصی Caddy برای route کردن پنل و WebSocket روی یک دامنه عمومی افزوده شد.
- `arena`، `gateway` و PostgreSQL فقط روی شبکه خصوصی Railway قرار می‌گیرند و تنها `edge` عمومی است.
- Edge مخصوص Railway با VLESS، VMess، DNS/UDP و ثابت‌ماندن PID هسته به‌صورت محلی acceptance شد.

## به‌روزرسانی آدرس‌دهی عمومی

- مقدار پیش‌فرض `ARENA_PUBLIC_URL` از آدرس ثابت localhost به `auto` تغییر کرد.
- URL سابسکریپشن و دانلودها از origin عمومی همان درخواست ساخته می‌شود.
- نودهای پیش‌فرض VLESS/VMess به حالت adaptive منتقل شدند؛ آدرس، پورت، TLS، SNI و WebSocket Host از دامنه deployment تولید می‌شود.
- برای نود Xray امکان خاموش‌کردن حالت adaptive و ثبت endpoint ثابت در پنل حفظ شده است.
- سناریوی forwarded host/proto به تست‌های API اضافه شد تا بازگشت ناخواسته localhost شناسایی شود.
- false positive ابزار GitGuardian در اسکریپت acceptance حذف و نبود credentialهای محلی در کل تاریخچه Git کنترل شد.

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
google=204
cloudflare=204
dns=142.251.209.238
xray_pid=15 dynamic_user_sync=ok
cleanup=ok
```

تفسیر:

- درخواست Google از VLESS عبور کرده است.
- درخواست Cloudflare از VMess عبور کرده است.
- DNS/UDP از VLESS پاسخ گرفته است.
- PID هسته هنگام ساخت کاربر ثابت مانده است.

آزمون‌های خودکار:

```text
Python: 7 passed
Go gateway/limiter: passed
Frontend production build: passed
Xray config validation: passed
```

رابط در اندازه دسکتاپ و موبایل با Browser Playwright بررسی شد. فرم ساخت کاربر، خروجی‌های Subscription و navigation اصلی نیز طی شدند.

## محدودیت‌های شفاف فاز ۱

- WireGuard و Cisco/OpenConnect فقط پروفایل backend خارجی تولید می‌کنند؛ daemon سرور را provision نمی‌کنند.
- محدودیت سرعت در یک Gateway دقیق است. حالت چند replica به Redis نیاز دارد.
- MFA و RBAC چندمدیره هنوز وجود ندارد.
- WebSocket و VMess در Xray 26.3.27 deprecated اعلام شده‌اند؛ پشتیبانی فعلی برای سازگاری محصول است.
- استقرار ابری انجام نشده و هزینه‌ای ایجاد نشده است.
- ریپازیتوری فعلاً محلی است؛ ساخت remote باید با حساب GitHub مالک پروژه انجام شود.

## سناریوی تست پذیرش کاربر

1. `http://localhost:8080/login` را باز کنید.
2. در کاربران، یک کاربر با حجم کم، ۷ روز، ۱ IP و هر دو نود بسازید.
3. «لینک‌ها» را باز و Subscription را در Hiddify/NekoBox/V2Box وارد کنید.
4. ابتدا یک سایت HTTPS و سپس DNS را آزمایش کنید.
5. در «ردیابی» نشست، IP و uplink/downlink را کنترل کنید.
6. سرعت و حجم را کاهش دهید و terminate شدن اتصال را بررسی کنید.
7. subscription را rotate کنید و مطمئن شوید لینک قدیمی دیگر پاسخ نمی‌دهد.

پس از این تست، لاگ کلاینت و بخش ردیابی ARENA مبنای دیباگ فاز بعد خواهد بود.
