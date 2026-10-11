import os
import hashlib
from django.db import models
from django.conf import settings
from django.core.files.storage import FileSystemStorage


def get_release_storage():
    return FileSystemStorage(
        location=str(getattr(settings, 'RELEASES_ROOT', settings.BASE_DIR / 'releases')),
        base_url=str(getattr(settings, 'RELEASES_URL', '/releases/'))
    )


def patch_upload_path(instance, filename):
    """ذخیره‌سازی پچ‌ها با ساختار منظم: app_id/version/filename"""
    app_id = instance.app.app_id if instance.app_id else 'unknown'
    safe_filename = os.path.basename(filename)
    return f"{app_id}/{instance.version}/{safe_filename}"


def release_upload_path(instance, filename):
    """ذخیره‌سازی باینری‌های نیتیو (APK) با ساختار منظم: app_id/version_code/filename"""
    app_id = instance.app.app_id if instance.app_id else 'unknown'
    safe_filename = os.path.basename(filename)
    return f"{app_id}/{instance.version_code}/{safe_filename}"



class App(models.Model):
    """مدل مدیریت اپلیکیشن‌های فلاتر تحت پوشش سامانه پچ و OTA"""

    PLATFORM_CHOICES = (
        ('all', 'همه پلتفرم‌ها (Android & iOS)'),
        ('android', 'اندروید (Android)'),
        ('ios', 'آی‌او‌اس (iOS)'),
    )

    app_id = models.SlugField(
        max_length=64,
        unique=True,
        db_index=True,
        verbose_name="شناسه سیستمی برنامه (App ID)",
        help_text="شناسه یکتا برای ارجاع کلاینت‌ها، مثال: my_app"
    )
    name = models.CharField(
        max_length=128,
        verbose_name="نام نمایشی برنامه",
        help_text="نام نمایشی برنامه، مثال: اپلیکیشن فروشگاهی"
    )
    package_name = models.CharField(
        max_length=128,
        verbose_name="Package Name / Bundle ID",
        help_text="شناسه بسته نرم‌افزاری، مثال: com.example.myapp"
    )
    platform = models.CharField(
        max_length=32,
        choices=PLATFORM_CHOICES,
        default='all',
        verbose_name="پلتفرم مقصد"
    )
    description = models.TextField(
        blank=True,
        default='',
        verbose_name="توضیحات کوتاه"
    )
    icon = models.FileField(
        upload_to='app_icons/',
        null=True,
        blank=True,
        verbose_name="آیکون / تصویر برنامه"
    )
    is_active = models.BooleanField(
        default=True,
        verbose_name="فعال / در حال سرویس‌دهی"
    )
    extra_metadata = models.JSONField(
        default=dict,
        blank=True,
        verbose_name="متادیتای توسعه‌پذیر (JSON)",
        help_text="ذخیره‌سازی متغیرهای اضافی و توسعه‌های آینده بدون تغییر اسکیمای دیتابیس"
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="زمان ثبت"
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name="آخرین به‌روزرسانی"
    )

    class Meta:
        verbose_name = "اپلیکیشن"
        verbose_name_plural = "اپلیکیشن‌ها"
        ordering = ['id']

    def __str__(self):
        return f"{self.name} ({self.app_id})"

    @property
    def active_patch(self):
        if not self.pk:
            return None
        return self.patches.filter(status='active').first()

    @property
    def total_patches(self):
        if not self.pk:
            return 0
        return self.patches.count()

    @property
    def active_release(self):
        if not self.pk:
            return None
        return self.releases.filter(status='active').order_by('-version_code').first()

    @property
    def total_releases(self):
        if not self.pk:
            return 0
        return self.releases.count()

    @property
    def icon_url(self) -> str:
        if self.icon and hasattr(self.icon, 'url') and self.icon.name:
            return self.icon.url
        if self.extra_metadata and 'icon_url' in self.extra_metadata:
            return self.extra_metadata['icon_url']
        return ''




class Patch(models.Model):
    """مدل مدیریت بسته‌های پچ OTA، نسخه‌ها، هش‌ها و سیاست‌های توزیع"""

    STATUS_CHOICES = (
        ('active', 'فعال در کلاینت‌ها (Live)'),
        ('archived', 'آرشیو شده (نسخه‌های پیشین)'),
        ('disabled', 'غیرفعال / لغو شده'),
    )

    app = models.ForeignKey(
        App,
        on_delete=models.CASCADE,
        related_name='patches',
        verbose_name="اپلیکیشن مربوطه"
    )
    version = models.CharField(
        max_length=64,
        db_index=True,
        verbose_name="شماره نسخه پچ (SemVer)",
        help_text="الگوی استاندارد: v1.0.4 یا v1.0.4-patch.2"
    )
    target_version_code = models.PositiveIntegerField(
        default=1,
        verbose_name="کد بیلد نیتیو تارگت (Target Build)",
        help_text="فقط کلاینت‌های با این شماره ساخت، پچ را دریافت می‌کنند"
    )

    ABI_CHOICES = (
        ('multi', 'همه دستگاه‌ها (جامع / Multi-ABI)'),
        ('arm64-v8a', 'گوشی‌های واقعی (arm64-v8a)'),
        ('x86_64', 'شبیه‌ساز و امولاتور (x86_64)'),
        ('armeabi-v7a', 'گوشی‌های ۳۲ بیتی قدیمی (armeabi-v7a)'),
    )

    target_abi = models.CharField(
        max_length=32,
        choices=ABI_CHOICES,
        default='multi',
        db_index=True,
        verbose_name="دستگاه و پردازنده هدف (ABI)",
        help_text="مشخص می‌کند این پچ مخصوص کدام پردازنده یا همه دستگاه‌هاست"
    )
    status = models.CharField(
        max_length=32,
        choices=STATUS_CHOICES,
        default='active',
        db_index=True,
        verbose_name="وضعیت پچ"
    )
    is_force = models.BooleanField(
        default=False,
        verbose_name="سیاست اجباری (Force Update)",
        help_text="در صورت فعال بودن، کلاینت بلافاصله و اجباراً پچ را دریافت می‌کند"
    )
    canary_percentage = models.PositiveSmallIntegerField(
        default=100,
        verbose_name="درصد توزیع آزمایشی (Canary %)",
        help_text="درصد کلاینت‌هایی که پچ را دریافت خواهند کرد (۱ تا ۱۰۰)"
    )
    min_app_version = models.CharField(
        max_length=32,
        blank=True,
        default='',
        verbose_name="حداقل نسخه نیتیو مجاز"
    )
    max_app_version = models.CharField(
        max_length=32,
        blank=True,
        default='',
        verbose_name="حداکثر نسخه نیتیو مجاز"
    )
    file = models.FileField(
        upload_to=patch_upload_path,
        verbose_name="فایل باینری پچ (.zip یا .bundle)"
    )
    filename = models.CharField(
        max_length=255,
        blank=True,
        verbose_name="نام فایل باینری"
    )
    size_bytes = models.BigIntegerField(
        default=0,
        verbose_name="حجم فایل (بایت)"
    )
    md5 = models.CharField(
        max_length=64,
        blank=True,
        verbose_name="هش MD5 یکپارچگی"
    )
    sha256 = models.CharField(
        max_length=128,
        blank=True,
        default='',
        verbose_name="هش پیشرفته SHA256"
    )
    release_notes = models.TextField(
        blank=True,
        default='',
        verbose_name="یادداشت‌های فنی تغییرات پچ"
    )
    extra_metadata = models.JSONField(
        default=dict,
        blank=True,
        verbose_name="متادیتای توسعه‌پذیر (JSON)",
        help_text="امکان ذخیره‌سازی اطلاعات موتور فلاتر، امضای دیجیتال و فیلدهای آینده"
    )
    download_count = models.PositiveIntegerField(
        default=0,
        verbose_name="تعداد دفعات دانلود"
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="زمان انتشار"
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name="آخرین به‌روزرسانی"
    )

    class Meta:
        verbose_name = "پچ فلاتر"
        verbose_name_plural = "پچ‌های فلاتر"
        ordering = ['-id']
        unique_together = ('app', 'version')

    def __str__(self):
        return f"{self.app.name} - v{self.version} ({self.get_status_display()})"

    @property
    def is_active(self):
        return self.status == 'active'

    @property
    def formatted_size(self):
        if self.size_bytes >= 1024 * 1024:
            return f"{round(self.size_bytes / (1024 * 1024), 2)} MB"
        elif self.size_bytes >= 1024:
            return f"{round(self.size_bytes / 1024, 1)} KB"
        return f"{self.size_bytes} B"

    def activate_and_rollback(self):
        """فعال‌سازی این پچ و رول‌بک ایمن بدون قطع همگانی سایر نسخه‌ها"""
        # فقط پچ‌های فعال همین اپلیکیشن را آرشیو کن
        Patch.objects.filter(app=self.app, status='active').exclude(id=self.id).update(status='archived')
        self.status = 'active'
        self.save(update_fields=['status', 'updated_at'])

    def save(self, *args, **kwargs):
        # تنظیم خودکار نام فایل
        if self.file and not self.filename:
            self.filename = os.path.basename(self.file.name)

        super().save(*args, **kwargs)

        # محاسبه خودکار هش MD5 و اندازه در صورت نیاز
        if self.file and (not self.md5 or self.size_bytes == 0):
            try:
                file_path = self.file.path
                if os.path.exists(file_path):
                    hasher_md5 = hashlib.md5()
                    hasher_sha = hashlib.sha256()
                    size = 0
                    with open(file_path, 'rb') as f:
                        for chunk in iter(lambda: f.read(65536), b""):
                            hasher_md5.update(chunk)
                            hasher_sha.update(chunk)
                            size += len(chunk)
                    self.md5 = hasher_md5.hexdigest()
                    self.sha256 = hasher_sha.hexdigest()
                    self.size_bytes = size
                    Patch.objects.filter(id=self.id).update(
                        md5=self.md5,
                        sha256=self.sha256,
                        size_bytes=self.size_bytes,
                        filename=os.path.basename(file_path)
                    )
            except Exception:
                pass


class Release(models.Model):
    """مدل مدیریت نسخه‌های نصبی نیتیو و کامل برنامه (فایل‌های APK اندروید)"""

    STATUS_CHOICES = (
        ('active', 'فعال در کلاینت‌ها (Live)'),
        ('archived', 'آرشیو شده (نسخه‌های پیشین)'),
        ('disabled', 'غیرفعال / لغو شده'),
    )

    app = models.ForeignKey(
        App,
        on_delete=models.CASCADE,
        related_name='releases',
        verbose_name="اپلیکیشن مربوطه"
    )
    version_name = models.CharField(
        max_length=64,
        verbose_name="نام نسخه (SemVer)",
        help_text="مثال: 1.2.0 یا 2.0.1"
    )
    version_code = models.PositiveIntegerField(
        db_index=True,
        verbose_name="کد بیلد نیتیو (Version Code)",
        help_text="شماره ساخت نیتیو، مثال: 15"
    )
    status = models.CharField(
        max_length=32,
        choices=STATUS_CHOICES,
        default='active',
        db_index=True,
        verbose_name="وضعیت انتشار"
    )
    is_force = models.BooleanField(
        default=False,
        verbose_name="سیاست ارتقای اجباری (Force Update)",
        help_text="در صورت فعال بودن، کلاینت اجباراً باید فایل نصبی را دانلود و نصب کند"
    )
    file = models.FileField(
        storage=get_release_storage,
        upload_to=release_upload_path,
        verbose_name="فایل نصبی نیتیو (APK)"
    )
    filename = models.CharField(
        max_length=255,
        blank=True,
        verbose_name="نام فایل نصبی"
    )
    size_bytes = models.BigIntegerField(
        default=0,
        verbose_name="حجم فایل (بایت)"
    )
    md5 = models.CharField(
        max_length=64,
        blank=True,
        verbose_name="هش MD5 یکپارچگی"
    )
    sha256 = models.CharField(
        max_length=128,
        blank=True,
        default='',
        verbose_name="هش پیشرفته SHA256"
    )
    release_notes = models.TextField(
        blank=True,
        default='',
        verbose_name="یادداشت‌های تغییرات نسخه"
    )
    download_count = models.PositiveIntegerField(
        default=0,
        verbose_name="تعداد دفعات دانلود"
    )
    extra_metadata = models.JSONField(
        default=dict,
        blank=True,
        verbose_name="متادیتای توسعه‌پذیر (JSON)"
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="زمان انتشار"
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name="آخرین به‌روزرسانی"
    )

    class Meta:
        verbose_name = "نسخه نصبی نیتیو (APK)"
        verbose_name_plural = "نسخه‌های نصبی نیتیو (APK)"
        ordering = ['-version_code', '-id']
        unique_together = ('app', 'version_code')

    def __str__(self):
        return f"{self.app.name} - v{self.version_name} (Build {self.version_code})"

    @property
    def is_active(self):
        return self.status == 'active'

    @property
    def formatted_size(self):
        if self.size_bytes >= 1024 * 1024:
            return f"{round(self.size_bytes / (1024 * 1024), 2)} MB"
        elif self.size_bytes >= 1024:
            return f"{round(self.size_bytes / 1024, 1)} KB"
        return f"{self.size_bytes} B"

    def activate_and_rollback(self):
        """فعال‌سازی این نسخه و آرشیو سایر نسخه‌های فعال همین اپلیکیشن"""
        Release.objects.filter(app=self.app, status='active').exclude(id=self.id).update(status='archived')
        self.status = 'active'
        self.save(update_fields=['status', 'updated_at'])

    def save(self, *args, **kwargs):
        if self.file and not self.filename:
            self.filename = os.path.basename(self.file.name)

        super().save(*args, **kwargs)

        if self.file and (not self.md5 or self.size_bytes == 0):
            try:
                file_path = self.file.path
                if os.path.exists(file_path):
                    hasher_md5 = hashlib.md5()
                    hasher_sha = hashlib.sha256()
                    size = 0
                    with open(file_path, 'rb') as f:
                        for chunk in iter(lambda: f.read(65536), b""):
                            hasher_md5.update(chunk)
                            hasher_sha.update(chunk)
                            size += len(chunk)
                    self.md5 = hasher_md5.hexdigest()
                    self.sha256 = hasher_sha.hexdigest()
                    self.size_bytes = size
                    Release.objects.filter(id=self.id).update(
                        md5=self.md5,
                        sha256=self.sha256,
                        size_bytes=self.size_bytes,
                        filename=os.path.basename(file_path)
                    )
            except Exception:
                pass

