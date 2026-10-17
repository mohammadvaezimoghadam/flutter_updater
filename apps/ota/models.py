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
    app_id = instance.app.app_id if instance.app_id else 'unknown'
    safe_filename = os.path.basename(filename)
    return f"{app_id}/{instance.version}/{safe_filename}"


def artifact_upload_path(instance, filename):
    app_id = instance.patch.app.app_id if (instance.patch and instance.patch.app_id) else 'unknown'
    version = instance.patch.version if instance.patch else 'v1'
    safe_filename = os.path.basename(filename)
    return f"{app_id}/{version}/{instance.abi}/{safe_filename}"


def release_upload_path(instance, filename):
    app_id = instance.app.app_id if instance.app_id else 'unknown'
    safe_filename = os.path.basename(filename)
    return f"{app_id}/{instance.version_code}/{safe_filename}"


class App(models.Model):
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
        verbose_name="نام نمایشی برنامه"
    )
    package_name = models.CharField(
        max_length=128,
        verbose_name="Package Name / Bundle ID"
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
        verbose_name="آیکون برنامه"
    )
    is_active = models.BooleanField(
        default=True,
        verbose_name="فعال / در حال سرویس‌دهی"
    )
    extra_metadata = models.JSONField(
        default=dict,
        blank=True,
        verbose_name="متادیتای اضافی (JSON)"
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


class BaseRelease(models.Model):
    """نسخه‌های اصلی نصب‌شده از استور (مانند 1.0.0+1 یا 1.0.1+2)"""
    app = models.ForeignKey(
        App,
        on_delete=models.CASCADE,
        related_name='base_releases',
        null=True,
        blank=True,
        verbose_name="اپلیکیشن مربوطه"
    )
    release_name = models.CharField(
        max_length=64,
        unique=True,
        verbose_name="نام نسخه پایه (e.g. 1.0.1+2)"
    )
    build_number = models.PositiveIntegerField(
        db_index=True,
        verbose_name="شماره ساخت نیتیو (Build Number)"
    )
    version_string = models.CharField(
        max_length=32,
        verbose_name="نسخه نمایشی (Version String)"
    )
    store_url = models.CharField(
        max_length=255,
        default='bazaar://details?id=com.qurantafakor.app',
        verbose_name="آدرس بازار"
    )
    store_web_url = models.CharField(
        max_length=255,
        default='https://cafebazaar.ir/app/com.qurantafakor.app',
        verbose_name="آدرس وب استور"
    )
    is_active = models.BooleanField(
        default=True,
        verbose_name="فعال"
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="تاریخ ثبت"
    )

    class Meta:
        verbose_name = "نسخه پایه استور (Base Release)"
        verbose_name_plural = "نسخه‌های پایه استور"
        ordering = ['-build_number', '-created_at']

    def __str__(self):
        return f"{self.release_name} (Build {self.build_number})"


class Patch(models.Model):
    """مدل پچ‌های منتشر شده OTA"""
    CHANNEL_CHOICES = (
        ('stable', 'عمومی (پایدار)'),
        ('beta', 'آزمایشی (تسترها)'),
    )
    STATUS_CHOICES = (
        ('active', 'فعال در کلاینت‌ها (Live)'),
        ('archived', 'آرشیو شده (نسخه‌های پیشین)'),
        ('disabled', 'غیرفعال / لغو شده'),
    )

    app = models.ForeignKey(
        App,
        on_delete=models.CASCADE,
        related_name='patches',
        null=True,
        blank=True,
        verbose_name="اپلیکیشن مربوطه"
    )
    base_release = models.ForeignKey(
        BaseRelease,
        on_delete=models.CASCADE,
        related_name='patches',
        null=True,
        blank=True,
        verbose_name="نسخه پایه (Base Release)"
    )
    version = models.CharField(
        max_length=64,
        db_index=True,
        verbose_name="شماره نسخه پچ (SemVer)"
    )
    patch_number = models.PositiveIntegerField(
        default=1,
        verbose_name="شماره پچ عددی"
    )
    channel = models.CharField(
        max_length=16,
        choices=CHANNEL_CHOICES,
        default='stable',
        db_index=True,
        verbose_name="کانال انتشار"
    )
    target_version_code = models.PositiveIntegerField(
        default=1,
        verbose_name="کد بیلد نیتیو تارگت"
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
        verbose_name="دستگاه و پردازنده هدف (ABI)"
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
        verbose_name="سیاست اجباری (Force Update)"
    )
    is_mandatory = models.BooleanField(
        default=False,
        verbose_name="به‌روزرسانی الزامی (is_mandatory)"
    )
    canary_percentage = models.PositiveSmallIntegerField(
        default=100,
        verbose_name="درصد توزیع آزمایشی"
    )
    file = models.FileField(
        upload_to=patch_upload_path,
        blank=True,
        null=True,
        verbose_name="فایل باینری پچ"
    )
    filename = models.CharField(
        max_length=255,
        blank=True,
        verbose_name="نام فایل"
    )
    size_bytes = models.BigIntegerField(
        default=0,
        verbose_name="حجم فایل (بایت)"
    )
    md5 = models.CharField(
        max_length=64,
        blank=True,
        verbose_name="هش MD5"
    )
    sha256 = models.CharField(
        max_length=128,
        blank=True,
        default='',
        verbose_name="هش SHA256"
    )
    release_notes = models.TextField(
        blank=True,
        default='',
        verbose_name="توضیحات و گزارش تغییرات"
    )
    change_log = models.TextField(
        blank=True,
        default='',
        verbose_name="لیست تغییرات (change_log)"
    )
    extra_metadata = models.JSONField(
        default=dict,
        blank=True,
        verbose_name="متادیتای اضافی"
    )
    download_count = models.PositiveIntegerField(
        default=0,
        verbose_name="تعداد دانلود"
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

    def __str__(self):
        app_name = self.app.name if self.app else 'Global'
        return f"{app_name} - v{self.version} ({self.channel})"

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
        if self.app:
            Patch.objects.filter(app=self.app, status='active').exclude(id=self.id).update(status='archived')
        elif self.base_release:
            Patch.objects.filter(base_release=self.base_release, status='active').exclude(id=self.id).update(status='archived')
        self.status = 'active'
        self.save(update_fields=['status', 'updated_at'])

    def save(self, *args, **kwargs):
        # همگام‌سازی فیلدهای is_force و is_mandatory
        if self.is_mandatory and not self.is_force:
            self.is_force = True
        elif self.is_force and not self.is_mandatory:
            self.is_mandatory = True

        # همگام‌سازی release_notes و change_log
        if self.change_log and not self.release_notes:
            self.release_notes = self.change_log
        elif self.release_notes and not self.change_log:
            self.change_log = self.release_notes

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
                    Patch.objects.filter(id=self.id).update(
                        md5=self.md5,
                        sha256=self.sha256,
                        size_bytes=self.size_bytes,
                        filename=os.path.basename(file_path)
                    )
            except Exception:
                pass


class PatchArtifact(models.Model):
    """فایل‌های باینری پچ به ازای هر معماری پردازنده (Multi-ABI Architecture)"""
    ABI_CHOICES = (
        ('arm64-v8a', 'ARM 64-bit (گوشی‌های واقعی)'),
        ('armeabi-v7a', 'ARM 32-bit (گوشی‌های قدیمی)'),
        ('x86_64', 'x86_64 (شبیه‌ساز و امولاتور)'),
        ('multi', 'جامع (Multi-ABI)'),
    )

    patch = models.ForeignKey(
        Patch,
        on_delete=models.CASCADE,
        related_name='artifacts',
        verbose_name="پچ مربوطه"
    )
    abi = models.CharField(
        max_length=32,
        choices=ABI_CHOICES,
        verbose_name="معماری پردازنده (ABI)"
    )
    file = models.FileField(
        upload_to=artifact_upload_path,
        verbose_name="فایل پچ زیپ"
    )
    md5 = models.CharField(
        max_length=64,
        verbose_name="کد هش MD5"
    )
    file_size = models.PositiveIntegerField(
        default=0,
        verbose_name="حجم فایل (بایت)"
    )
    download_count = models.PositiveIntegerField(
        default=0,
        verbose_name="تعداد دانلود"
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="تاریخ ایجاد"
    )

    class Meta:
        verbose_name = "آرتیفکت پچ معماری (Patch Artifact)"
        verbose_name_plural = "آرتیفکت‌های پچ بر اساس معماری"
        unique_together = ('patch', 'abi')

    def __str__(self):
        return f"{self.patch.version} [{self.abi}]"

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if self.file and (not self.md5 or self.file_size == 0):
            try:
                file_path = self.file.path
                if os.path.exists(file_path):
                    hasher = hashlib.md5()
                    size = 0
                    with open(file_path, 'rb') as f:
                        for chunk in iter(lambda: f.read(65536), b""):
                            hasher.update(chunk)
                            size += len(chunk)
                    self.md5 = hasher.hexdigest()
                    self.file_size = size
                    PatchArtifact.objects.filter(id=self.id).update(
                        md5=self.md5,
                        file_size=self.file_size
                    )
            except Exception:
                pass


class Release(models.Model):
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
        verbose_name="نام نسخه (SemVer)"
    )
    version_code = models.PositiveIntegerField(
        db_index=True,
        verbose_name="کد بیلد نیتیو (Version Code)"
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
        verbose_name="سیاست ارتقای اجباری"
    )
    file = models.FileField(
        storage=get_release_storage,
        upload_to=release_upload_path,
        verbose_name="فایل نصبی نیتیو (APK)"
    )
    filename = models.CharField(
        max_length=255,
        blank=True,
        verbose_name="نام فایل"
    )
    size_bytes = models.BigIntegerField(
        default=0,
        verbose_name="حجم فایل (بایت)"
    )
    md5 = models.CharField(
        max_length=64,
        blank=True,
        verbose_name="هش MD5"
    )
    sha256 = models.CharField(
        max_length=128,
        blank=True,
        default='',
        verbose_name="هش SHA256"
    )
    release_notes = models.TextField(
        blank=True,
        default='',
        verbose_name="یادداشت‌های تغییرات"
    )
    download_count = models.PositiveIntegerField(
        default=0,
        verbose_name="تعداد دانلود"
    )
    extra_metadata = models.JSONField(
        default=dict,
        blank=True,
        verbose_name="متادیتای توسعه‌پذیر"
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
                        for chunk in iter(lambda: f.read(65536), b''):
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


class TelemetryReport(models.Model):
    """ثبت لاگ و تله‌متری رویدادهای کلاینت OTA (POST /api/v1/ota/report/)"""
    app_id = models.CharField(
        max_length=64,
        db_index=True,
        verbose_name="شناسه برنامه"
    )
    patch_version = models.CharField(
        max_length=64,
        verbose_name="نسخه پچ"
    )
    event = models.CharField(
        max_length=32,
        db_index=True,
        verbose_name="نوع رویداد (Event)"
    )
    duration_ms = models.PositiveIntegerField(
        null=True,
        blank=True,
        verbose_name="مدت زمان اعمال (میلی‌ثانیه)"
    )
    device_id = models.CharField(
        max_length=128,
        blank=True,
        default='',
        verbose_name="شناسه دستگاه"
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="زمان ثبت رویداد"
    )

    class Meta:
        verbose_name = "گزارش تله‌متری OTA"
        verbose_name_plural = "گزارش‌های تله‌متری OTA"
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.app_id} | {self.event} | v{self.patch_version}"
