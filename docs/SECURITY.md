# مدل امنیتی ARENA

## کنترل‌های پیاده‌شده

- Argon2 برای hash رمز مدیر.
- session token تصادفی و ذخیره فقط hash آن در دیتابیس.
- cookie مدیر با `HttpOnly`، `SameSite=Lax` و حالت Secure قابل تنظیم.
- CSRF token جدا برای همه عملیات تغییردهنده.
- subscription token امضاشده، بدون افشای secret سرور و قابل ابطال با version.
- رمزنگاری secretهای WireGuard/Cisco با Fernet مشتق‌شده از app secret.
- secret مستقل بین Gateway و Control Plane با compare ثابت‌زمان.
- overwrite کردن IP header در ingress و آزمون جلوگیری از XFF/CF spoofing.
- عدم publish پورت‌های داخلی Xray و API آن.
- نگهداری کلید خصوصی REALITY فقط در secret محیط اجرا؛ API، subscription و دیتابیس فقط کلید عمومی و short ID را می‌بینند.
- اجرای کانتینر برنامه و Gateway با کاربر غیر root.
- حذف compression در WebSocket برای کاهش پیچیدگی و رفتار ناهمسان کلاینت‌ها.
- `Cache-Control: no-store` برای subscription.
- فایل `.env` در Git نادیده گرفته می‌شود و فقط `.env.example` با placeholderها نگهداری می‌شود.
- اسکریپت acceptance هیچ credential پیش‌فرضی ندارد و در نبود متغیر محیطی با خطا متوقف می‌شود.

## Secret scanning

عبارت اعتبارسنجی credential در نسخه اولیه اسکریپت acceptance به‌صورت `${variable:?message}` نوشته شده بود و توسط GitGuardian به‌اشتباه Password تشخیص داده شد. این عبارت بدون تغییر رفتار امنیتی با شرط صریح خالی‌بودن بازنویسی شد. تاریخچه repository برای مقادیر واقعی `ARENA_APP_SECRET`، `ARENA_GATEWAY_SECRET` و `ARENA_ADMIN_PASSWORD` کنترل شده و هیچ‌یک در Git وجود ندارند؛ incident مربوطه false positive است.

## چک‌لیست production

1. همه secretهای نمونه را تعویض کنید.
2. HTTPS اجباری و `ARENA_COOKIE_SECURE=true` باشد.
3. دسترسی شبکه به PostgreSQL، API Xray و Control Plane داخلی محدود شود.
4. اگر REALITY فعال است، فقط پورت TCP عمومی آن را باز کنید و پورت داخلی 12000 و API آمار را private نگه دارید.
5. origin فقط ترافیک ingress مورد اعتماد را بپذیرد.
6. backup رمزنگاری‌شده PostgreSQL و آزمون restore داشته باشید.
7. logها را با retention محدود نگه دارید؛ IP کاربر داده حساس محسوب می‌شود.
8. دسترسی مدیر را پشت MFA/SSO لایه ingress قرار دهید تا زمانی که MFA داخلی اضافه شود.
9. Gateway در فاز ۱ تک replica باشد؛ برای چند replica محدودکننده سرعت باید Redis-backed شود.

## موارد خارج از فاز ۱

- MFA و نقش‌های چندمدیره.
- Redis برای rate limit توزیع‌شده.
- rotation خودکار کلید رمزنگاری secretها.
- مدیریت daemonهای WireGuard و ocserv.
- تشخیص ناهنجاری و alerting خودکار.
- VLESS Encryption و XHTTP/H2/H3.
