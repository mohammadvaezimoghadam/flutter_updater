# Flutter Updater (OTA & Native Release Hub)

سامانه جامع و ایزوله مدیریت به‌روزرسانی‌های ترکیبی (Hybrid Updates) اپلیکیشن‌های فلاتر شامل پچ‌های آنی دارت (OTA Patches) و فایل‌های نصبی کامل نیتیو (Full Native APK Releases).

---

## 🌟 ویژگی‌های کلیدی

1. **معماری به‌روزرسانی ترکیبی (Hybrid Update Architecture)**:
   - **پچ‌های آنی دارت (OTA Hot Patches)**: ارسال سریع تغییرات کدهای Dart و فایل‌های Asset با حجم اندک (چند کیلوبایت تا چند مگابایت) بدون نیاز به کامپایل مجدد یا انتشار در استورها.
   - **ریلیزهای کامل نیتیو (Full APK Releases)**: پشتیبانی از فایل‌های کامل APK با اعتبارسنجی خودکار شماره ساخت (Version Code). هنگامی که کدهای Kotlin/Swift، مجوزهای اندروید، پلاگین‌های نیتیو یا فایل‌های Gradle تغییر می‌کنند، سرور به‌صورت هوشمند به‌جای پچ دارت، فایل نصبی APK را ارائه می‌دهد.

2. **پشتیبانی از چندین اپلیکیشن به‌صورت مستقل (Multi-App Isolation)**:
   - امکان تعریف نامحدود برنامه‌های فلاتر در یک سرور واحد با ایزولاسیون کامل دایرکتوری‌های دیسک و دیتابیس (`patches/<app_id>/...` و `releases/<app_id>/...`).
   - بدون داده‌های هاردکدشده یا پیش‌فرض (تمیز و بدون وابستگی).

3. **اعتبارسنجی دقیق ترتیب نسخه‌ها (Strict Version Validation)**:
   - جلوگیری خودکار از ثبت نسخه‌های تکراری یا کمتر از نسخه‌های قبلی بر اساس قوانین استاندارد SemVer و کدهای بیلد افزایشی.

4. **تضمین ۱۰۰٪ آفلاین فونت‌ها و استایل‌ها (Zero External CDN Dependence)**:
   - تمام فونت‌های فارسی (ایران یکان، ایران‌سنس) و آیکون‌های Material Symbols به‌صورت محلی در سرور میزبانی می‌شوند تا در اینترنت‌های محدود یا شبکه ملی اطلاعات بدون تاخیر لود شوند.

5. **استقرار استاندارد در سرور و VPS (Production Docker Stack)**:
   - وب‌سرور معکوس Nginx Alpine (تنظیم روی پورت ۸۰ با استریم مستقیم فایل‌های استاتیک، پچ‌ها و APKها بدون درگیر کردن پردازشگر پایتون).
   - سرور برنامه Gunicorn با ۳ کارگر موازی (Worker).
   - پایگاه داده PostgreSQL 16 Alpine با قابلیت بازگشت خودکار (Fallback) به SQLite در محیط توسعه محلی.

---

## 🚀 راهنمای سریع راه‌اندازی (VPS و سرور محلی)

### ۱. تنظیم متغیرهای محیطی
یک فایل `.env` بر اساس نمونه بسازید:
```bash
cp .env.example .env
```
در صورت نیاز مقادیر دیتابیس، `ALLOWED_HOSTS` یا پورت را ویرایش کنید.

### ۲. اجرا با داکر کامپوز
```bash
docker compose up -d --build
```
سرویس‌های زیر اجرا خواهند شد:
- `db`: پایگاه‌داده PostgreSQL 16 Alpine
- `ota-server`: وب‌سرور جنگو با Gunicorn
- `nginx`: سرور معکوس و سرو فایل‌های حجیم روی پورت `80`

### ۳. بررسی سلامت سرویس
```bash
docker compose ps
curl http://localhost/api/status
```

---

## 📡 نحوه عملکرد کلاینت فلاتر (Client Flow & APIs)

کلاینت فلاتر هنگام شروع، یک درخواست به اندپوینت استعلام ارسال می‌کند:

```http
GET /check?app_id=<APP_ID>&version_code=<BUILD_NUMBER>&current_patch=<CURRENT_PATCH_VERSION>
```

### منطق تصمیم‌گیری سرور (Decision Flow):

1. **بررسی کد بیلد نیتیو (Native Version Code)**:
   اگر در سرور یک ریلیز فعال APK با کد ساختی بزرگتر از `version_code` کلاینت وجود داشته باشد، پاسخ زیر بازگردانده می‌شود:
   ```json
   {
     "has_update": true,
     "update_type": "native",
     "app_id": "my_app",
     "version": "2.0.0",
     "version_name": "2.0.0",
     "version_code": 2,
     "target_version_code": 2,
     "download_url": "http://your-server.com/releases/my_app/2/app-release.apk",
     "apk_url": "http://your-server.com/releases/my_app/2/app-release.apk",
     "is_force": false,
     "size_bytes": 35489000,
     "formatted_size": "33.8 MB",
     "md5": "...",
     "sha256": "...",
     "release_notes": "افزودن پلاگین جدید دوربین و به‌روزرسانی مجوزها"
   }
   ```
   کلاینت در این وضعیت کاربر را به دانلود و نصب مستقیم فایل APK هدایت می‌کند (`ota_update` یا دیالوگ دانلود).

2. **بررسی پچ دارت (OTA Hot Patch)**:
   اگر کد بیلد کلاینت با نسخه جاری همخوانی داشته باشد ولی پچ جدیدی برای این بیلد موجود باشد:
   ```json
   {
     "has_update": true,
     "update_type": "patch",
     "app_id": "my_app",
     "version": "v1.0.4-patch.2",
     "target_version_code": 1,
     "download_url": "http://your-server.com/patches/my_app/v1.0.4-patch.2/patch.zip",
     "is_force": false,
     "size_bytes": 1450000,
     "formatted_size": "1.4 MB",
     "md5": "...",
     "sha256": "...",
     "release_notes": "رفع ایراد صفحه لاگین و بهبود عملکرد ویجت‌ها"
   }
   ```

3. **در صورت نبود آپدیت**:
   ```json
   {
     "has_update": false,
     "message": "کلاینت به آخرین نسخه مجهز است."
   }
   ```

---

## 🔌 مستندات کامل اندپوینت‌های REST API

### اندپوینت‌های کلاینت فلاتر
- **استعلام آپدیت**: `GET /check`
- **دانلود پچ دارت**: `GET /patches/<app_id>/<version>/<filename>`
- **دانلود مستقیم فایل نصبی APK**: `GET /releases/<app_id>/<version_code>/<filename>`

### اندپوینت‌های مدیریت پچ‌های OTA
- `GET /api/patches?app_id=<app_id>`: لیست تمام پچ‌ها
- `POST /api/patches/upload`: آپلود و انتشار پچ جدید (`multipart/form-data`)
- `POST /api/patches/activate`: رول‌بک و فعال‌سازی یک پچ
- `POST /api/patches/toggle_force`: تغییر سیاست اجباری/اختیاری پچ
- `POST /api/patches/delete`: حذف پچ

### اندپوینت‌های مدیریت فایل‌های نصبی نیتیو APK
- `GET /api/releases?app_id=<app_id>`: لیست تمام ریلیزهای نصبی
- `POST /api/releases/upload`: آپلود و انتشار فایل APK (`multipart/form-data`)
- `POST /api/releases/activate`: رول‌بک و فعال‌سازی یک ریلیز به عنوان نسخه زنده
- `POST /api/releases/toggle_force`: تغییر سیاست اجباری/اختیاری ریلیز APK
- `POST /api/releases/delete`: حذف ریلیز و فایل باینری از دیسک

### اندپوینت‌های عمومی و سیستمی
- `GET /api/status`: اطلاعات پورت‌ها، آی‌پی‌ها و تعداد برنامه‌ها و فایل‌ها
- `GET /api/apps`: لیست برنامه‌ها
- `POST /api/apps`: ثبت برنامه فلاتر جدید (`app_id`, `name`, `package_name`)
- `POST /api/apps/delete` یا `DELETE /api/apps`: حذف کامل یک برنامه به همراه کلیه پچ‌ها، ریلیزهای APK و فایل‌های دیسک (`app_id`)


