# apps/ota/services.py
from __future__ import annotations

import os
import socket
import logging
from typing import Optional, Dict, Any, List
from django.conf import settings
from django.db import transaction
from django.db.models import Count, Q
from django.core.files.uploadedfile import UploadedFile

from .models import App, Patch

logger = logging.getLogger("ota.services")


class AppService:
    """لایه سرویس مدیریت اپلیکیشن‌های فلاتر"""

    @staticmethod
    def list_apps_summary() -> List[Dict[str, Any]]:
        """دریافت لیست اپلیکیشن‌ها به همراه اطلاعات پچ فعال جاری و تعداد کل نسخه‌ها"""
        apps = App.objects.all().order_by('id')
        result = []
        for a in apps:
            active = a.active_patch
            result.append({
                "id": a.id,
                "app_id": a.app_id,
                "name": a.name,
                "package_name": a.package_name,
                "platform": a.platform,
                "description": a.description,
                "is_active": a.is_active,
                "total_patches": a.total_patches,
                "icon_url": a.icon_url,
                "active_version": active.version if active else None,
                "active_is_force": active.is_force if active else False,
                "created_at": a.created_at.strftime("%Y-%m-%d %H:%M:%S") if a.created_at else "",
            })
        return result

    @staticmethod
    def get_app_by_id(app_id: str) -> Optional[App]:
        return App.objects.filter(Q(app_id=app_id) | Q(package_name=app_id)).first()

    @staticmethod
    def create_app(
        app_id: str,
        name: str,
        package_name: str,
        description: str = "",
        platform: str = "all",
        extra_metadata: Optional[Dict[str, Any]] = None
    ) -> App:
        """ثبت اپلیکیشن جدید با اعتبارسنجی یکتایی شناسه"""
        app_id = app_id.strip()
        if App.objects.filter(app_id=app_id).exists():
            raise ValueError(f"اپلیکیشنی با شناسه '{app_id}' قبلاً ثبت شده است.")

        app = App.objects.create(
            app_id=app_id,
            name=name.strip(),
            package_name=package_name.strip(),
            description=description.strip(),
            platform=platform,
            extra_metadata=extra_metadata or {}
        )
        logger.info(f"Created new Flutter App: {app.app_id} ({app.name})")
        return app


class PatchService:
    """لایه سرویس مدیریت نسخه‌های پچ، استعلام OTA، انتشار و رول‌بک ایمن"""

    @staticmethod
    def get_patches_for_app(app_id: str) -> List[Dict[str, Any]]:
        """دریافت تمام پچ‌های یک اپلیکیشن به ترتیب جدیدترین"""
        patches = Patch.objects.filter(app__app_id=app_id).order_by('-id')
        result = []
        for p in patches:
            result.append({
                "id": p.id,
                "app_id": p.app.app_id,
                "version": p.version,
                "target_version_code": p.target_version_code,
                "status": p.status,
                "is_active": 1 if p.is_active else 0,
                "is_force": 1 if p.is_force else 0,
                "canary_percentage": p.canary_percentage,
                "filename": p.filename,
                "size_bytes": p.size_bytes,
                "formatted_size": p.formatted_size,
                "md5": p.md5,
                "sha256": p.sha256,
                "release_notes": p.release_notes,
                "created_at": p.created_at.strftime("%Y-%m-%d %H:%M:%S") if p.created_at else "",
            })
        return result

    @staticmethod
    def check_update(
        app_id: str,
        version_code: Optional[int] = None,
        current_patch: Optional[str] = None,
        host: Optional[str] = None,
        scheme: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        بررسی استعلام کلاینت فلاتر و ارائه آخرین پچ فعال با ساخت لینک مستقیم دانلود
        """
        app = App.objects.filter(Q(app_id=app_id) | Q(package_name=app_id), is_active=True).first()
        if not app:
            return {
                "has_update": False,
                "message": f"اپلیکیشن با شناسه یا پکیج '{app_id}' یافت نشد یا غیرفعال است."
            }

        active_patch = app.active_patch
        if not active_patch:
            return {
                "has_update": False,
                "message": "هیچ پچ فعالی برای این اپلیکیشن تعریف نشده است (نسخه خام استور)."
            }

        # بررسی کد بیلد نیتیو تارگت در صورت ارسال
        if version_code is not None and active_patch.target_version_code:
            try:
                vc = int(version_code)
                if vc != active_patch.target_version_code:
                    return {
                        "has_update": False,
                        "message": f"پچ جاری مخصوص بیلد {active_patch.target_version_code} است (بیلد کلاینت: {vc})."
                    }
            except (ValueError, TypeError):
                pass

        # بررسی تطابق با پچ جاری کلاینت
        if current_patch and str(current_patch).strip() == str(active_patch.version).strip():
            return {
                "has_update": False,
                "message": "کلاینت هم‌اکنون به آخرین نسخه پچ مجهز است.",
                "current_version": current_patch
            }

        # ساخت لینک دانلود مطمئن
        server_host = host or "localhost:8080"
        url_scheme = scheme or "http"
        download_url = f"{url_scheme}://{server_host}/patches/{app.app_id}/{active_patch.version}/{active_patch.filename}"

        return {
            "has_update": True,
            "app_id": app.app_id,
            "version": active_patch.version,
            "is_force": active_patch.is_force,
            "target_version_code": active_patch.target_version_code,
            "download_url": download_url,
            "md5": active_patch.md5,
            "sha256": active_patch.sha256,
            "size_bytes": active_patch.size_bytes,
            "release_notes": active_patch.release_notes,
            "created_at": active_patch.created_at.strftime("%Y-%m-%d %H:%M:%S") if active_patch.created_at else ""
        }

    @staticmethod
    def publish_patch(
        app_id: str,
        file_obj: UploadedFile | Any,
        version: str,
        target_version_code: int = 1,
        is_force: bool = False,
        activate: bool = True,
        release_notes: str = "",
        extra_metadata: Optional[Dict[str, Any]] = None
    ) -> Patch:
        """بارگذاری و انتشار امن پچ جدید با ثبت اندازه، هش و متادیتا"""
        app = App.objects.filter(app_id=app_id).first()
        if not app:
            raise ValueError(f"اپلیکیشن '{app_id}' یافت نشد.")

        version = version.strip()
        if not version:
            raise ValueError("شماره نسخه پچ نمی‌تواند خالی باشد.")

        with transaction.atomic():
            # در صورت انتشار به عنوان پچ فعال، پچ‌های قبلی همین اپ را آرشیو کن
            if activate:
                Patch.objects.filter(app=app, status='active').update(status='archived')

            patch = Patch(
                app=app,
                version=version,
                target_version_code=int(target_version_code),
                status='active' if activate else 'archived',
                is_force=is_force,
                release_notes=release_notes.strip(),
                extra_metadata=extra_metadata or {}
            )
            # انتساب فایل (متد save مدل، هش و مسیر را خودکار محاسبه می‌کند)
            patch.file = file_obj
            patch.filename = os.path.basename(file_obj.name) if hasattr(file_obj, 'name') else 'patch.zip'
            patch.save()

            logger.info(f"Published Patch #{patch.id} (v{version}) for app {app.app_id}. Status: {patch.status}")
            return patch

    @staticmethod
    def rollback_to_patch(app_id: str, patch_id: int) -> bool:
        """رول‌بک اختصاصی و امن به یک نسخه مشخص از همین اپلیکیشن بدون قطع سایر پچ‌ها"""
        app = App.objects.filter(app_id=app_id).first()
        if not app:
            raise ValueError(f"اپلیکیشن '{app_id}' یافت نشد.")

        # اگر patch_id برابر 0 باشد، فقط تمام پچ‌های همین اپ را آرشیو می‌کند (بازگشت به نسخه استور)
        if patch_id == 0:
            with transaction.atomic():
                Patch.objects.filter(app=app, status='active').update(status='archived')
            logger.info(f"Reverted app '{app_id}' to native store version.")
            return True

        patch = Patch.objects.filter(id=patch_id, app=app).first()
        if not patch:
            raise ValueError(f"پچ شماره #{patch_id} برای اپلیکیشن '{app_id}' یافت نشد.")

        patch.activate_and_rollback()
        logger.info(f"Safely rolled back app '{app_id}' to patch #{patch_id} (v{patch.version}).")
        return True

    @staticmethod
    def toggle_force_policy(patch_id: int) -> bool:
        """تغییر سیاست اجباری / اختیاری پچ"""
        patch = Patch.objects.filter(id=patch_id).first()
        if not patch:
            raise ValueError(f"پچ شماره #{patch_id} یافت نشد.")

        patch.is_force = not patch.is_force
        patch.save(update_fields=['is_force', 'updated_at'])
        logger.info(f"Toggled force policy for patch #{patch_id} to {patch.is_force}")
        return patch.is_force

    @staticmethod
    def delete_patch(patch_id: int) -> bool:
        """حذف فیزیکی فایل باینری از دیسک و رکورد از پایگاه داده"""
        patch = Patch.objects.filter(id=patch_id).first()
        if not patch:
            raise ValueError(f"پچ شماره #{patch_id} یافت نشد.")

        # حذف فایل از دیسک
        try:
            if patch.file and os.path.exists(patch.file.path):
                file_dir = os.path.dirname(patch.file.path)
                os.remove(patch.file.path)
                if os.path.exists(file_dir) and not os.listdir(file_dir):
                    os.rmdir(file_dir)
        except Exception as e:
            logger.warning(f"Could not remove patch file from disk: {e}")

        patch_version = patch.version
        app_id = patch.app.app_id
        patch.delete()
        logger.info(f"Deleted patch #{patch_id} (v{patch_version}) for app {app_id}.")
        return True


class SystemService:
    """اطلاعات سلامت سرور، پورت‌ها و آدرس‌های شناسایی‌شده شبکه"""

    @staticmethod
    def get_status() -> Dict[str, Any]:
        ips = []
        try:
            hostname = socket.gethostname()
            for ip in socket.gethostbyname_ex(hostname)[2]:
                if not ip.startswith("127.") and not ip.startswith("169.254."):
                    ips.append(ip)
        except Exception:
            pass

        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            primary = s.getsockname()[0]
            s.close()
            if primary not in ips and not primary.startswith("127."):
                ips.append(primary)
        except Exception:
            pass

        return {
            "port": getattr(settings, "PORT", 8080),
            "ips": ips or ["127.0.0.1"],
            "total_apps": App.objects.count(),
            "total_patches": Patch.objects.count()
        }
