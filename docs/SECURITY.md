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
- اجرای کانتینر برنامه و Gateway با کاربر غیر root.
- حذف compression در WebSocket برای کاهش پیچیدگی و رفتار ناهمسان کلاینت‌ها.
- `Cache-Control: no-store` برای subscription.

## چک‌لیست production

1. همه secretهای نمونه را تعویض کنید.
2. HTTPS اجباری و `ARENA_COOKIE_SECURE=true` باشد.
3. دسترسی شبکه به PostgreSQL، API Xray و Control Plane داخلی محدود شود.
4. origin فقط ترافیک ingress مورد اعتماد را بپذیرد.
5. backup رمزنگاری‌شده PostgreSQL و آزمون restore داشته باشید.
6. logها را با retention محدود نگه دارید؛ IP کاربر داده حساس محسوب می‌شود.
7. دسترسی مدیر را پشت MFA/SSO لایه ingress قرار دهید تا زمانی که MFA داخلی اضافه شود.
8. Gateway در فاز ۱ تک replica باشد؛ برای چند replica محدودکننده سرعت باید Redis-backed شود.

## موارد خارج از فاز ۱

- MFA و نقش‌های چندمدیره.
- Redis برای rate limit توزیع‌شده.
- rotation خودکار کلید رمزنگاری secretها.
- مدیریت daemonهای WireGuard و ocserv.
- تشخیص ناهنجاری و alerting خودکار.
- VLESS Encryption و XHTTP/H2/H3.
