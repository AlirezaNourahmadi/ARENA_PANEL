# فلوهای اپلیکیشن ARENA

## ۱. ورود مدیر

1. مدیر `/login` را باز می‌کند.
2. Control Plane نام کاربری و رمز را بررسی می‌کند.
3. یک session token تصادفی و یک CSRF token جدا صادر می‌شود.
4. session فقط به‌صورت hash در PostgreSQL ذخیره و cookie آن `HttpOnly` می‌شود.
5. درخواست‌های تغییردهنده علاوه بر session به `X-CSRF-Token` نیاز دارند.

## ۲. ساخت کاربر

1. مدیر نام، حجم، تعداد روز، IP همزمان، سرعت و نودها را انتخاب می‌کند.
2. رکورد کاربر و یک credential مستقل برای هر نود ساخته می‌شود.
3. credentialهای VLESS/VMess با HandlerService به inbound مناسب اضافه می‌شوند.
4. Xray ری‌استارت نمی‌شود و نشست‌های موجود ادامه پیدا می‌کنند.
5. رخداد `user.created` در Audit log ثبت می‌شود.

اعتبار روزانه با اولین اتصال مجاز شروع می‌شود، نه با لحظه ساخت کاربر.

## ۳. دریافت Subscription

1. پنل یک token امضاشده شامل شناسه کاربر و نسخه subscription تولید می‌کند.
2. کلاینت `/sub/{token}` را با فرمت Base64 یا `?format=raw` دریافت می‌کند.
3. خط اول یک VLESS عمداً غیرقابل اتصال با UUID صفر و مقصد `127.0.0.1:1` است.
4. نام خط اول مقدار مصرف، حجم و روز باقی‌مانده را نمایش می‌دهد.
5. خطوط بعدی کانفیگ‌های فعال VLESS/VMess هستند.
6. headerهای استاندارد `Subscription-Userinfo`، `Profile-Title` و `Profile-Update-Interval` ارسال می‌شوند.

چرخاندن subscription نسخه token را افزایش می‌دهد و لینک قبلی بلافاصله باطل می‌شود.

## ۴. اتصال WebSocket

1. کلاینت به path یکتای `/edge/{node_id}/{user_id}` متصل می‌شود.
2. Caddy مقدار IP قابل اعتماد را بازنویسی می‌کند.
3. Gateway از API داخلی مجوز می‌خواهد.
4. Control Plane فعال‌بودن کاربر/نود/کلید، حجم، انقضا و تعداد IP را بررسی می‌کند.
5. در صورت مجازبودن، session ساخته و upstream داخلی اعلام می‌شود.
6. Gateway WebSocket عمومی و WebSocket داخلی Xray را با compression خاموش relay می‌کند.
7. uplink و downlink هر ۱۵ ثانیه و هنگام close ثبت می‌شوند.
8. اگر سهمیه یا اعتبار تمام شود، heartbeat دستور terminate می‌دهد.

## ۵. محدودیت‌ها

- حجم: مجموع `used_up_bytes + used_down_bytes` با quota مقایسه می‌شود.
- روز: `expires_at` در اولین اتصال تعیین می‌شود.
- IP: نشست‌های stale بسته و تعداد IPهای یکتای زنده محاسبه می‌شود.
- سرعت: یک token bucket مشترک برای همه اتصال‌های همان کاربر، uplink و downlink را محدود می‌کند.
- غیرفعال‌سازی: Gateway اتصال جدید را رد می‌کند و Xray credential را پویا حذف می‌کند.

## ۵.۱ اتصال REALITY

1. Subscription برای Node نوع `VLESS / TCP / REALITY` لینک دارای `pbk`، `sid`، `sni` و flow رسمی Vision می‌سازد.
2. اتصال مستقیماً به inbound عمومی Xray می‌رسد و به HTTP، Caddy و WebSocket وابسته نیست.
3. StatsService حجم و IPهای آنلاین را هر ۱۵ ثانیه گزارش می‌کند.
4. Control Plane مصرف، شروع اعتبار و نشست‌ها را در PostgreSQL ثبت می‌کند.
5. RoutingService اتصال IPهای بیشتر از سقف کاربر را برای درخواست‌های بعدی به outbound مسدود هدایت می‌کند.
6. پایان حجم، پایان اعتبار یا غیرفعال‌سازی باعث حذف پویا credential می‌شود.

سرعت تنظیم‌شده کاربر روی مسیر REALITY اندازه‌گیری می‌شود اما shape نمی‌شود؛ token bucket فقط در Gateway WebSocket قرار دارد.

## ۶. ردیابی

پنل دو نمای مستقل دارد:

- نشست‌ها: کاربر، نود، IP، uplink، downlink، زمان و علت close.
- Audit: ورود مدیر، ساخت/ویرایش کاربر، اتصال/رد Gateway، تغییر نود و چرخش subscription.

هیچ رمز، private key یا subscription token در log ثبت نمی‌شود.

## ۷. WireGuard و Cisco

این دو در فاز ۱ backend خارجی هستند:

- WireGuard: کلید X25519 معتبر، IP یکتا از pool و فایل client تولید می‌شود. public key کاربر باید روی سرور WireGuard ثبت شود.
- Cisco/OpenConnect: XML پروفایل، group، username و password تولید می‌شود. سرور ocserv/ASA باید جداگانه آماده باشد.

ARENA در فاز ۱ daemon این دو پروتکل را نصب یا مدیریت نمی‌کند.
