from __future__ import annotations
import json
import hashlib
# apps/ota/services.py

import os
import socket
import logging
from typing import Optional, Dict, Any, List
from django.conf import settings
from django.db import transaction
from django.db.models import Count, Q
from django.core.files.uploadedfile import UploadedFile

from .models import App, Patch, Release, BaseRelease, PatchArtifact, TelemetryReport
from .version_utils import validate_new_patch_version, compare_versions

logger = logging.getLogger("ota.services")



class AppService:
    """لایه سرویس مدیریت اپلیکیشن‌های فلاتر"""

    @staticmethod
    def list_apps_summary() -> List[Dict[str, Any]]:
        """دریافت لیست اپلیکیشن‌ها به همراه اطلاعات پچ فعال جاری، آخرین نسخه نصبی و تعداد کل نسخه‌ها"""
        apps = App.objects.all().order_by('id')
        result = []
        for a in apps:
            active_p = a.active_patch
            active_r = a.active_release
            result.append({
                "id": a.id,
                "app_id": a.app_id,
                "name": a.name,
                "package_name": a.package_name,
                "platform": a.platform,
                "description": a.description,
                "is_active": a.is_active,
                "total_patches": a.total_patches,
                "total_releases": a.total_releases,
                "icon_url": a.icon_url,
                "active_version": active_p.version if active_p else None,
                "active_is_force": active_p.is_force if active_p else False,
                "active_release_version": active_r.version_name if active_r else None,
                "active_release_code": active_r.version_code if active_r else None,
                "active_release_is_force": active_r.is_force if active_r else False,
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
        icon_file = None,
        extra_metadata: Optional[Dict[str, Any]] = None
    ) -> App:
        """ثبت اپلیکیشن جدید با اعتبارسنجی یکتایی شناسه و آپلود اختیاری آیکون"""
        app_id = app_id.strip()
        if App.objects.filter(app_id=app_id).exists():
            raise ValueError(f"اپلیکیشنی با شناسه '{app_id}' قبلاً ثبت شده است.")

        app = App(
            app_id=app_id,
            name=name.strip(),
            package_name=package_name.strip(),
            description=description.strip(),
            platform=platform,
            extra_metadata=extra_metadata or {}
        )
        if icon_file:
            app.icon = icon_file
        app.save()
        logger.info(f"Created new Flutter App: {app.app_id} ({app.name})")
        return app

    @staticmethod
    def update_app(
        app_id: str,
        name: Optional[str] = None,
        package_name: Optional[str] = None,
        description: Optional[str] = None,
        platform: Optional[str] = None,
        icon_file = None,
        extra_metadata: Optional[Dict[str, Any]] = None
    ) -> App:
        """ویرایش مشخصات اپلیکیشن ثبت‌شده و به‌روزرسانی آیکون"""
        app = App.objects.filter(app_id=app_id.strip()).first()
        if not app:
            raise ValueError(f"اپلیکیشنی با شناسه '{app_id}' یافت نشد.")

        if name is not None and name.strip():
            app.name = name.strip()
        if package_name is not None and package_name.strip():
            app.package_name = package_name.strip()
        if description is not None:
            app.description = description.strip()
        if platform is not None:
            app.platform = platform
        if icon_file:
            app.icon = icon_file
        if extra_metadata is not None:
            app.extra_metadata = extra_metadata
        app.save()
        logger.info(f"Updated Flutter App: {app.app_id} ({app.name})")
        return app

    @staticmethod
    def delete_app(app_id: str) -> bool:
        """حذف کامل یک اپلیکیشن همراه با تمامی پچ‌ها، ریلیزهای APK و فایل‌های ذخیره شده روی دیسک"""
        app = App.objects.filter(app_id=app_id.strip()).first()
        if not app:
            raise ValueError(f"اپلیکیشنی با شناسه '{app_id}' یافت نشد.")

        # ۱. حذف فیزیکی پوشه پچ‌های این اپلیکیشن
        patches_root = str(getattr(settings, 'PATCHES_ROOT', getattr(settings, 'MEDIA_ROOT', 'patches')))
        patch_dir = os.path.join(patches_root, app.app_id)
        if os.path.exists(patch_dir):
            try:
                import shutil
                shutil.rmtree(patch_dir)
            except Exception as e:
                logger.warning(f"Could not remove patch directory {patch_dir}: {e}")

        # ۲. حذف فیزیکی پوشه فایل‌های نصبی APK این اپلیکیشن
        releases_root = str(getattr(settings, 'RELEASES_ROOT', 'releases'))
        release_dir = os.path.join(releases_root, app.app_id)
        if os.path.exists(release_dir):
            try:
                import shutil
                shutil.rmtree(release_dir)
            except Exception as e:
                logger.warning(f"Could not remove release directory {release_dir}: {e}")

        app_name = app.name
        app.delete()
        logger.info(f"Deleted Flutter App: {app_id} ({app_name}) and all its artifacts.")
        return True


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
                "target_abi": getattr(p, 'target_abi', 'multi'),
                "target_abi_display": p.get_target_abi_display() if hasattr(p, 'get_target_abi_display') else 'همه دستگاه‌ها (Multi)',
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
                "download_count": getattr(p, 'download_count', 0),
                "created_at": p.created_at.strftime("%Y-%m-%d %H:%M:%S") if p.created_at else "",
            })
        return result

    @staticmethod
    def check_update(
        app_id: str,
        version_code: Optional[int] = None,
        current_patch: Optional[str] = None,
        abi: Optional[str] = None,
        host: Optional[str] = None,
        scheme: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        بررسی یکپارچه و هوشمند استعلام کلاینت فلاتر:
        - اولویت اول: بررسی نیاز به ارتقای نیتیو با فایل نصبی کامل (APK)
        - اولویت دوم: در صورت به‌روز بودن بیلد نیتیو، بررسی پچ دارت (OTA)
        """
        app = App.objects.filter(Q(app_id=app_id) | Q(package_name=app_id), is_active=True).first()
        if not app:
            return {
                "has_update": False,
                "message": f"اپلیکیشن با شناسه یا پکیج '{app_id}' یافت نشد یا غیرفعال است."
            }

        server_host = host or "localhost:8080"
        url_scheme = scheme or "http"

        client_vc = None
        if version_code is not None:
            try:
                client_vc = int(version_code)
            except (ValueError, TypeError):
                pass

        # اولویت ۱: استعلام آپدیت نیتیو (فایل نصبی کامل APK)
        active_release = app.active_release
        if active_release and client_vc is not None and client_vc < active_release.version_code:
            apk_url = f"{url_scheme}://{server_host}/releases/{app.app_id}/{active_release.version_code}/{active_release.filename}"
            return {
                "has_update": True,
                "update_type": "native",
                "app_id": app.app_id,
                "version": active_release.version_name,
                "version_name": active_release.version_name,
                "version_code": active_release.version_code,
                "target_version_code": active_release.version_code,
                "download_url": apk_url,
                "apk_url": apk_url,
                "is_force": active_release.is_force,
                "size_bytes": active_release.size_bytes,
                "formatted_size": active_release.formatted_size,
                "md5": active_release.md5,
                "sha256": active_release.sha256,
                "release_notes": active_release.release_notes,
                "created_at": active_release.created_at.strftime("%Y-%m-%d %H:%M:%S") if active_release.created_at else ""
            }

        # اولویت ۲: استعلام پچ دارت (OTA Hot Update)
        active_patch = None
        client_abi = (abi or '').strip().lower() if abi else None
        
        # ۱. استعلام بر اساس کد بیلد و معماری دقیق کلاینت
        if client_vc is not None and client_abi:
            active_patch = app.patches.filter(status='active', target_version_code=client_vc, target_abi=client_abi).first()
            if not active_patch:
                active_patch = app.patches.filter(status='active', target_version_code=client_vc, target_abi='multi').first()
        
        # ۲. استعلام فقط بر اساس کد بیلد
        if not active_patch and client_vc is not None:
            active_patch = app.patches.filter(status='active', target_version_code=client_vc).first()
            
        # ۳. پچ پیش‌فرض فعال برنامه
        if not active_patch:
            active_patch = app.active_patch

        if not active_patch:
            # اگر پچ فعالی در سرور وجود ندارد ولی کلاینت پچ نصب کرده دارد (رول‌بک به نسخه پایه)
            if current_patch:
                return {
                    "has_update": True,
                    "action": "rollback",
                    "should_rollback": True,
                    "message": "پچ‌های فعال آرشیو شده‌اند؛ بازگشت به نسخه پایه."
                }
            return {
                "has_update": False,
                "message": "کلاینت به آخرین نسخه مجهز است و پچ فعال یا فایل نصبی جدیدی وجود ندارد."
            }

        # بررسی سازگاری شماره ساخت نیتیو با پچ
        if client_vc is not None and active_patch.target_version_code:
            if client_vc != active_patch.target_version_code:
                return {
                    "has_update": False,
                    "message": f"پچ جاری مخصوص بیلد نیتیو {active_patch.target_version_code} است (بیلد کلاینت: {client_vc})."
                }

        # بررسی تطابق با پچ جاری کلاینت
        if current_patch:
            curr_clean = str(current_patch).strip()
            # فقط در صورتی که کلاینت دقیقاً همین پچ فعال را داشته باشد آپدیتی نیست:
            if curr_clean == active_patch.version:
                return {
                    "has_update": False,
                    "message": "کلاینت هم‌اکنون به آخرین نسخه پچ مجهز است.",
                    "current_version": curr_clean,
                    "release_notes": active_patch.release_notes
                }

        patch_download_url = f"{url_scheme}://{server_host}/patches/{app.app_id}/{active_patch.version}/{active_patch.filename}"
        return {
            "has_update": True,
            "update_type": "patch",
            "app_id": app.app_id,
            "version": active_patch.version,
            "target_version_code": active_patch.target_version_code,
            "target_abi": getattr(active_patch, 'target_abi', 'multi'),
            "download_url": patch_download_url,
            "is_force": active_patch.is_force,
            "size_bytes": active_patch.size_bytes,
            "formatted_size": active_patch.formatted_size,
            "md5": active_patch.md5,
            "sha256": active_patch.sha256,
            "release_notes": active_patch.release_notes,
            "created_at": active_patch.created_at.strftime("%Y-%m-%d %H:%M:%S") if active_patch.created_at else ""
        }


    @staticmethod
    def publish_patch(
        app_id: str,
        file_obj: UploadedFile | Any,
        version: str,
        target_version_code: int = 1,
        target_abi: str = "multi",
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

        # اعتبارسنجی بزرگ‌تر بودن نسخه پچ جدید نسبت به نسخه‌های قبلی همین اپلیکیشن
        validate_new_patch_version(app, version)

        with transaction.atomic():
            # در صورت انتشار به عنوان پچ فعال، پچ‌های قبلی همین اپ را آرشیو کن
            if activate:
                Patch.objects.filter(app=app, status='active').update(status='archived')

            # تشخیص یا تنظیم معماری هدف
            filename_lower = (file_obj.name if hasattr(file_obj, 'name') else '').lower()
            effective_abi = (target_abi or 'multi').strip().lower()
            if effective_abi == 'multi' and filename_lower:
                if 'x86_64' in filename_lower or 'emulator' in filename_lower:
                    effective_abi = 'x86_64'
                elif 'arm64' in filename_lower:
                    effective_abi = 'arm64-v8a'
                elif 'armeabi' in filename_lower:
                    effective_abi = 'armeabi-v7a'

            patch = Patch(
                app=app,
                version=version,
                target_version_code=int(target_version_code),
                target_abi=effective_abi,
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


    @staticmethod
    def check_ota_v1(
        app_id: str,
        base_release: Optional[str] = None,
        base_version_name: Optional[str] = None,
        base_build_number: Optional[int] = None,
        abi: Optional[str] = None,
        current_patch_version: Optional[str] = None,
        channel: Optional[str] = "stable",
        device_id: Optional[str] = None,
        host: Optional[str] = None,
        scheme: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        پیاده‌سازی استاندارد استعلام نسخه بر اساس معماری Shorebird-Grade (POST /api/v1/ota/check/)
        - بررسی ایزوله‌سازی Base Release
        - هدایت خودکار به استور در صورت قدیمی بودن بیلد (STORE_UPDATE_REQUIRED)
        - توزیع پچ هماهنگ با معماری پردازنده (Multi-ABI Architecture)
        """
        server_host = host or "localhost:8080"
        url_scheme = scheme or "http"
        app = App.objects.filter(Q(app_id=app_id) | Q(package_name=app_id), is_active=True).first()

        # استخراج شماره ساخت
        build_num = None
        if base_build_number is not None:
            try:
                build_num = int(base_build_number)
            except (ValueError, TypeError):
                pass

        # ۱. یافتن یا مطابقت Base Release (ایزوله به ازای همین اپلیکیشن)
        base_rel = None
        if base_release:
            base_rel = BaseRelease.objects.filter(app=app, release_name=base_release.strip()).first() if app else BaseRelease.objects.filter(release_name=base_release.strip()).first()
        if not base_rel and build_num is not None:
            base_rel = BaseRelease.objects.filter(app=app, build_number=build_num).first() if app else BaseRelease.objects.filter(build_number=build_num).first()

        # ۲. اولویت اول: بررسی وجود نسخه نصبی نیتیو جدیدتر (Direct APK یا Store Update)
        active_release = app.active_release if app else Release.objects.filter(status='active').first()
        latest_base = BaseRelease.objects.filter(app=app, is_active=True).order_by('-build_number').first() if app else BaseRelease.objects.filter(is_active=True).order_by('-build_number').first()

        target_build = None
        if active_release:
            target_build = active_release.version_code
        elif latest_base:
            target_build = latest_base.build_number

        if build_num is not None and target_build is not None and build_num < target_build:
            logger.info(f"[OTA/v1] Client on older build ({build_num} < {target_build}). Triggering native update.")
            if active_release and active_release.file:
                apk_url = f"{url_scheme}://{server_host}/releases/{app.app_id if app else 'app'}/{active_release.version_code}/{active_release.filename}"
                return {
                    "status": "PATCH_AVAILABLE",
                    "update_type": "native",
                    "has_update": True,
                    "patch": {
                        "version": active_release.version_name,
                        "download_url": apk_url,
                        "target_version_code": active_release.version_code,
                        "is_mandatory": active_release.is_force,
                        "is_force": active_release.is_force,
                        "size_bytes": active_release.size_bytes,
                        "md5": active_release.md5,
                        "change_log": active_release.release_notes or f"نسخه جدید {active_release.version_name}",
                        "release_notes": active_release.release_notes or f"نسخه جدید {active_release.version_name}",
                        "update_type": "native"
                    }
                }
            elif latest_base:
                return {
                    "status": "STORE_UPDATE_REQUIRED",
                    "store": {
                        "latest_version": latest_base.version_string,
                        "store_url": latest_base.store_url,
                        "web_url": latest_base.store_web_url,
                        "is_mandatory": True,
                        "message": f"نسخه جدید قرآن ({latest_base.version_string}) در کافه‌بازار منتشر شده است. لطفاً برنامه را به‌روزرسانی کنید."
                    }
                }

        # ۳. اولویت دوم: بررسی پچ سازگار با این Base Release (بر اساس اصل Base Release Isolation)
        query = Q(status='active')
        if channel:
            query &= (Q(channel=channel) | Q(channel='stable'))

        patches_qs = Patch.objects.none()
        if base_rel:
            patches_qs = base_rel.patches.filter(query).order_by('-patch_number', '-id')
        elif app and build_num is not None:
            patches_qs = app.patches.filter(query, target_version_code=build_num).order_by('-id')

        active_patch = patches_qs.first()

        # در صورت نبود پچ فعال برای این بیلد:
        if not active_patch:
            return {
                "status": "UP_TO_DATE",
                "message": "اپلیکیشن شما به‌روز است."
            }

        # ۴. بررسی تطابق با پچ نصب شده فعلی
        if current_patch_version:
            curr_clean = str(current_patch_version).strip()
            if curr_clean == active_patch.version.strip():
                return {
                    "status": "UP_TO_DATE",
                    "message": "اپلیکیشن شما مجهز به آخرین پچ است."
                }

        # ۵. انتخاب فایل هماهنگ با پردازنده کلاینت (ABI)
        client_abi = (abi or '').strip().lower()
        artifact = None
        if active_patch.artifacts.exists():
            if client_abi:
                artifact = active_patch.artifacts.filter(abi=client_abi).first()
            if not artifact:
                artifact = active_patch.artifacts.filter(abi='multi').first() or active_patch.artifacts.first()

        if artifact and artifact.file:
            media_prefix = getattr(settings, 'MEDIA_URL', '/media/')
            download_url = f"{url_scheme}://{server_host}{media_prefix}{artifact.file.name}"
            md5_val = artifact.md5
            size_val = artifact.file_size
        else:
            download_url = f"{url_scheme}://{server_host}/patches/{app.app_id if app else 'app'}/{active_patch.version}/{active_patch.filename}"
            md5_val = active_patch.md5
            size_val = active_patch.size_bytes

        # محاسبه دقیق target_version_code بر اساس معماری پردازنده کلاینت و شماره بیلد نیتیو
        effective_build = build_num or (base_rel.build_number if base_rel else 1)
        if client_abi == 'arm64-v8a':
            target_vc = 2000 + effective_build if effective_build < 1000 else effective_build
        elif client_abi == 'armeabi-v7a':
            target_vc = 1000 + effective_build if effective_build < 1000 else effective_build
        elif client_abi == 'x86_64':
            target_vc = effective_build if effective_build < 1000 else (effective_build % 1000)
        else:
            target_vc = active_patch.target_version_code or effective_build

        return {
            "status": "PATCH_AVAILABLE",
            "update_type": "patch",
            "has_update": True,
            "patch": {
                "version": active_patch.version,
                "download_url": download_url,
                "target_version_code": target_vc,
                "target_abi": client_abi or getattr(active_patch, 'target_abi', 'multi'),
                "md5": md5_val,
                "size_bytes": size_val,
                "is_mandatory": active_patch.is_mandatory or active_patch.is_force,
                "is_force": active_patch.is_mandatory or active_patch.is_force,
                "change_log": active_patch.change_log or active_patch.release_notes or f"به‌روزرسانی پچ نسخه {active_patch.version}",
                "release_notes": active_patch.release_notes or active_patch.change_log or f"به‌روزرسانی پچ نسخه {active_patch.version}",
                "update_type": "patch"
            }
        }

    @staticmethod
    def publish_patch_bundle(file_obj, channel: str = "stable") -> Patch:
        """
        پردازش خودکار فایل پکیج زیپ چندمعماری (Zero-Input Multi-ABI Upload)
        - استخراج manifest.json
        - ثبت BaseRelease و Patch
        - تفکیک خودکار و ذخیره فایل‌های arm64-v8a و armeabi-v7a و x86_64
        - محاسبه هش MD5 هر فایل به صورت خودکار
        """
        import zipfile
        from django.core.files.base import ContentFile

        if not zipfile.is_zipfile(file_obj):
            raise ValueError("فایل ارسالی یک فایل زیپ معتبر نیست.")

        file_obj.seek(0)
        with zipfile.ZipFile(file_obj, 'r') as zf:
            namelist = zf.namelist()
            manifest = {}
            if 'manifest.json' in namelist:
                with zf.open('manifest.json') as mf:
                    manifest = json.loads(mf.read().decode('utf-8'))

            app_id = manifest.get('app_id', 'quran_tafakor')
            version = manifest.get('version', '1.0.1')
            base_rel_name = manifest.get('base_release', '1.0.0+1')
            change_log = manifest.get('change_log', '')
            patch_channel = manifest.get('channel', channel) or 'stable'

            # استخراج شماره ساخت
            build_num = 1
            version_str = "1.0.0"
            if '+' in base_rel_name:
                parts = base_rel_name.split('+')
                version_str = parts[0]
                try:
                    build_num = int(parts[1])
                except ValueError:
                    pass

            app, _ = App.objects.get_or_create(
                app_id=app_id,
                defaults={"name": "قرآن و تفکر", "package_name": "com.qurantafakor.app"}
            )

            base_rel, _ = BaseRelease.objects.get_or_create(
                release_name=base_rel_name,
                defaults={
                    "app": app,
                    "build_number": build_num,
                    "version_string": version_str,
                    "is_active": True
                }
            )

            # آرشیو پچ‌های قبلی همین کانال و بیس
            Patch.objects.filter(base_release=base_rel, channel=patch_channel, status='active').update(status='archived')

            patch, _ = Patch.objects.get_or_create(
                app=app,
                base_release=base_rel,
                version=version,
                defaults={
                    "channel": patch_channel,
                    "status": "active",
                    "change_log": change_log,
                    "release_notes": change_log,
                    "target_version_code": build_num,
                    "target_abi": "multi"
                }
            )
            patch.status = 'active'
            patch.channel = patch_channel
            patch.target_abi = 'multi'
            patch.target_version_code = build_num
            patch.change_log = change_log
            patch.release_notes = change_log
            patch.save()

            # بررسی و استخراج فایل‌های هر معماری
            primary_artifact = None
            abis = ['arm64-v8a', 'armeabi-v7a', 'x86_64']
            for abi in abis:
                # الگوهای نام‌گذاری فایل درون زیپ
                candidate_names = [f"{abi}/patch.zip", f"{abi}/libapp.so", f"{abi}.zip"]
                matched_name = None
                for c in candidate_names:
                    if c in namelist:
                        matched_name = c
                        break

                if matched_name:
                    file_bytes = zf.read(matched_name)
                    hasher = hashlib.md5()
                    hasher.update(file_bytes)
                    md5_val = hasher.hexdigest()
                    size_val = len(file_bytes)

                    artifact, _ = PatchArtifact.objects.get_or_create(
                        patch=patch,
                        abi=abi,
                        defaults={"md5": md5_val, "file_size": size_val}
                    )
                    artifact.file.save(os.path.basename(matched_name), ContentFile(file_bytes), save=False)
                    artifact.md5 = md5_val
                    artifact.file_size = size_val
                    artifact.save()
                    if not primary_artifact or abi == 'arm64-v8a':
                        primary_artifact = artifact
                    logger.info(f"[OTA/Publish] Stored artifact {abi}: size={size_val}, md5={md5_val}")

            # در صورت خالی بودن فایل اصلی پچ، ست کردن با فایل آرتیفکت اصلی برای فال‌بک مطمئن
            if primary_artifact and primary_artifact.file:
                patch.file = primary_artifact.file
                patch.filename = os.path.basename(primary_artifact.file.name)
                patch.md5 = primary_artifact.md5
                patch.size_bytes = primary_artifact.file_size
                patch.save(update_fields=['file', 'filename', 'md5', 'size_bytes'])

            return patch

    @staticmethod
    def record_telemetry(app_id: str, patch_version: str, event: str, duration_ms: Optional[int] = None, device_id: Optional[str] = None):
        """ثبت گزارش رویداد تله‌متری OTA"""
        return TelemetryReport.objects.create(
            app_id=app_id,
            patch_version=patch_version,
            event=event,
            duration_ms=duration_ms,
            device_id=device_id or ""
        )


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
            "total_patches": Patch.objects.count(),
            "total_releases": Release.objects.count()
        }


class ReleaseService:
    """لایه سرویس مدیریت نسخه‌های نصبی نیتیو (فایل‌های کامل APK)"""

    @staticmethod
    def list_releases_for_app(app_id: str) -> List[Dict[str, Any]]:
        releases = Release.objects.filter(app__app_id=app_id).order_by('-version_code')
        result = []
        for r in releases:
            result.append({
                "id": r.id,
                "app_id": r.app.app_id,
                "version_name": r.version_name,
                "version_code": r.version_code,
                "status": r.status,
                "is_active": 1 if r.is_active else 0,
                "is_force": 1 if r.is_force else 0,
                "filename": r.filename,
                "size_bytes": r.size_bytes,
                "formatted_size": r.formatted_size,
                "download_count": r.download_count,
                "md5": r.md5,
                "sha256": r.sha256,
                "release_notes": r.release_notes,
                "created_at": r.created_at.strftime("%Y-%m-%d %H:%M:%S") if r.created_at else "",
            })
        return result

    @staticmethod
    def publish_release(
        app_id: str,
        file_obj: UploadedFile | Any,
        version_name: str,
        version_code: int,
        is_force: bool = False,
        activate: bool = True,
        release_notes: str = "",
        extra_metadata: Optional[Dict[str, Any]] = None
    ) -> Release:
        app = App.objects.filter(app_id=app_id).first()
        if not app:
            raise ValueError(f"اپلیکیشن '{app_id}' یافت نشد.")

        version_name = version_name.strip()
        if not version_name:
            raise ValueError("نام نسخه (version_name) نمی‌تواند خالی باشد.")

        try:
            vc = int(version_code)
            if vc <= 0:
                raise ValueError("کد بیلد نیتیو باید یک عدد مثبت باشد.")
        except (TypeError, ValueError):
            raise ValueError("کد بیلد نیتیو (version_code) باید یک عدد معتبر باشد.")

        # اعتبارسنجی بزرگ‌تر بودن version_code نسبت به نسخه‌های قبلی همین اپ
        existing = Release.objects.filter(app=app, version_code__gt=vc)
        if existing.exists():
            max_vc = max(r.version_code for r in existing)
            raise ValueError(
                f"کد بیلد نیتیو جدید ({vc}) نمی‌تواند کمتر از بالاترین نسخه ثبت‌شده ({max_vc}) باشد."
            )

        with transaction.atomic():
            if activate:
                Release.objects.filter(app=app, status='active').update(status='archived')

            # در صورتی که نسخه‌ای با همین شماره بیلد قبلاً ثبت شده باشد آرشیو می‌شود
            Release.objects.filter(app=app, version_code=vc).update(status='archived')

            release = Release(
                app=app,
                version_name=version_name,
                version_code=vc,
                status='active' if activate else 'archived',
                is_force=is_force,
                release_notes=release_notes.strip(),
                extra_metadata=extra_metadata or {}
            )
            release.file = file_obj
            release.filename = os.path.basename(file_obj.name) if hasattr(file_obj, 'name') else 'app-release.apk'
            release.save()

            # همگام‌سازی خودکار با مدل BaseRelease برای معماری استاندارد شوربرد
            base_rel_name = f"{version_name}+{vc}"
            base_rel, _ = BaseRelease.objects.update_or_create(
                release_name=base_rel_name,
                defaults={
                    'app': app,
                    'build_number': vc,
                    'version_string': version_name,
                    'is_active': activate
                }
            )
            if activate:
                BaseRelease.objects.filter(app=app).exclude(id=base_rel.id).update(is_active=False)

            logger.info(f"Published Native Release #{release.id} (v{version_name}, Build {vc}) for app {app.app_id}.")
            return release

    @staticmethod
    def rollback_to_release(app_id: str, release_id: int) -> bool:
        app = App.objects.filter(app_id=app_id).first()
        if not app:
            raise ValueError(f"اپلیکیشن '{app_id}' یافت نشد.")

        if release_id == 0:
            with transaction.atomic():
                Release.objects.filter(app=app, status='active').update(status='archived')
                remaining_base = BaseRelease.objects.filter(app=app).order_by('build_number').first()
                if remaining_base:
                    BaseRelease.objects.filter(app=app).exclude(id=remaining_base.id).update(is_active=False)
                    remaining_base.is_active = True
                    remaining_base.save(update_fields=['is_active'])
            logger.info(f"Deactivated all native releases for app '{app_id}'.")
            return True

        release = Release.objects.filter(id=release_id, app=app).first()
        if not release:
            raise ValueError(f"نسخه شماره #{release_id} یافت نشد.")

        with transaction.atomic():
            release.activate_and_rollback()
            base_rel_name = f"{release.version_name}+{release.version_code}"
            base_rel, _ = BaseRelease.objects.update_or_create(
                release_name=base_rel_name,
                defaults={
                    'app': app,
                    'build_number': release.version_code,
                    'version_string': release.version_name,
                    'is_active': True
                }
            )
            BaseRelease.objects.filter(app=app).exclude(id=base_rel.id).update(is_active=False)

        logger.info(f"Activated native release #{release_id} (Build {release.version_code}) for app '{app_id}'.")
        return True

    @staticmethod
    def toggle_force_release(release_id: int) -> bool:
        release = Release.objects.filter(id=release_id).first()
        if not release:
            raise ValueError(f"نسخه شماره #{release_id} یافت نشد.")

        release.is_force = not release.is_force
        release.save(update_fields=['is_force', 'updated_at'])
        logger.info(f"Toggled force policy for release #{release_id} to {release.is_force}")
        return release.is_force

    @staticmethod
    def delete_release(release_id: int) -> bool:
        release = Release.objects.filter(id=release_id).first()
        if not release:
            raise ValueError(f"نسخه شماره #{release_id} یافت نشد.")

        app = release.app
        vc = release.version_code
        rel_ver = f"{release.version_name} (Build {vc})"
        app_id = app.app_id

        with transaction.atomic():
            # ۱. حذف فایل باینری از دیسک
            try:
                if release.file and os.path.exists(release.file.path):
                    file_dir = os.path.dirname(release.file.path)
                    os.remove(release.file.path)
                    if os.path.exists(file_dir) and not os.listdir(file_dir):
                        os.rmdir(file_dir)
            except Exception as e:
                logger.warning(f"Could not remove release file from disk: {e}")

            # ۲. حذف رکورد ریلیز از دیتابیس
            release.delete()

            # ۳. همگام‌سازی و پاکسازی BaseRelease متناظر
            base_rel = BaseRelease.objects.filter(app=app, build_number=vc).first()
            if base_rel:
                if not base_rel.patches.exists():
                    base_rel.delete()
                else:
                    base_rel.is_active = False
                    base_rel.save(update_fields=['is_active'])

            # ۴. در صورت وجود نسخه قبلی، بالاترین نسخه پیشین را به عنوان نسخه فعال (active) بازگردانی کن
            prev_release = Release.objects.filter(app=app).order_by('-version_code').first()
            if prev_release:
                prev_release.status = 'active'
                prev_release.save(update_fields=['status', 'updated_at'])
                BaseRelease.objects.filter(app=app, build_number=prev_release.version_code).update(is_active=True)
                BaseRelease.objects.filter(app=app).exclude(build_number=prev_release.version_code).update(is_active=False)
            else:
                # اگر هیچ ریلیز نصبی دیگری نمانده، آخرین بیس رلیز باقی‌مانده را فعال کن
                remaining_base = BaseRelease.objects.filter(app=app).order_by('-build_number').first()
                if remaining_base:
                    remaining_base.is_active = True
                    remaining_base.save(update_fields=['is_active'])
                    BaseRelease.objects.filter(app=app).exclude(id=remaining_base.id).update(is_active=False)

        logger.info(f"Deleted native release #{release_id} ({rel_ver}) for app {app_id} and synchronized BaseRelease.")
        return True
