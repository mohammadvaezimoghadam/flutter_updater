# apps/ota/views.py
from __future__ import annotations

import os
import json
import mimetypes
from django.conf import settings
from django.http import JsonResponse, HttpResponse, FileResponse, Http404
from django.shortcuts import render
from django.views import View
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from django.core.files.base import ContentFile

from .services import AppService, PatchService, SystemService, ReleaseService


class DashboardView(View):
    """رندر داشبورد کنترل پنل OTA با تمپلیت مدرن Persian Control Plane"""

    def get(self, request, *args, **kwargs):
        apps_list = AppService.list_apps_summary()
        app_id = request.GET.get('app_id')
        current_app = None
        if app_id:
            current_app = AppService.get_app_by_id(app_id.strip())
        if not current_app and apps_list:
            current_app = AppService.get_app_by_id(apps_list[0]['app_id'])
        if not current_app:
            from .models import App
            current_app = App.objects.first()

        active_patch = current_app.active_patch if current_app else None
        recent_patches = current_app.patches.all().order_by('-id')[:5] if current_app else []
        active_release = current_app.active_release if current_app else None
        recent_releases = current_app.releases.all().order_by('-version_code')[:5] if current_app else []
        apps_list = AppService.list_apps_summary()
        status_data = SystemService.get_status()

        context = {
            'current_app': current_app,
            'active_patch': active_patch,
            'recent_patches': recent_patches,
            'active_release': active_release,
            'recent_releases': recent_releases,
            'apps_list': apps_list,
            'status_data': status_data,
            'server_host': status_data.get('ips', ['127.0.0.1'])[0] if status_data.get('ips') else '127.0.0.1',

            'server_port': status_data.get('port', 8080),
        }
        return render(request, "ota/dashboard.html", context)


@method_decorator(csrf_exempt, name='dispatch')
class StatusAPIView(View):
    """استعلام وضعیت سرور و آدرس‌های هاست فعال"""

    def get(self, request, *args, **kwargs):
        status_data = SystemService.get_status()
        return JsonResponse(status_data)


@method_decorator(csrf_exempt, name='dispatch')
class AppsAPIView(View):
    """دریافت لیست اپلیکیشن‌ها و ثبت اپ جدید"""

    def get(self, request, *args, **kwargs):
        apps = AppService.list_apps_summary()
        return JsonResponse(apps, safe=False)

    def post(self, request, *args, **kwargs):
        try:
            if request.content_type and 'multipart/form-data' in request.content_type:
                app_id = request.POST.get('app_id', '').strip()
                name = request.POST.get('name', '').strip()
                package_name = request.POST.get('package_name', '').strip()
                description = request.POST.get('description', '').strip()
                platform = request.POST.get('platform', 'all').strip()
                icon_file = request.FILES.get('icon')
            else:
                body = json.loads(request.body.decode('utf-8')) if request.body else {}
                app_id = body.get('app_id', '').strip()
                name = body.get('name', '').strip()
                package_name = body.get('package_name', '').strip()
                description = body.get('description', '').strip()
                platform = body.get('platform', 'all').strip()
                icon_file = None

            if not app_id or not name or not package_name:
                return JsonResponse({"ok": False, "error": "تمامی فیلدهای الزامی را پر کنید."}, status=400)

            app = AppService.create_app(
                app_id=app_id,
                name=name,
                package_name=package_name,
                description=description,
                platform=platform,
                icon_file=icon_file
            )
            return JsonResponse({"ok": True, "app_id": app.app_id, "icon_url": app.icon_url})
        except Exception as e:
            return JsonResponse({"ok": False, "error": str(e)}, status=400)

    def delete(self, request, *args, **kwargs):
        try:
            body = json.loads(request.body.decode('utf-8')) if request.body else {}
            app_id = (body.get('app_id') or request.GET.get('app_id') or '').strip()
            if not app_id:
                return JsonResponse({"ok": False, "error": "شناسه برنامه (app_id) الزامی است."}, status=400)
            AppService.delete_app(app_id)
            return JsonResponse({"ok": True, "message": f"برنامه '{app_id}' با موفقیت حذف گردید."})
        except Exception as e:
            return JsonResponse({"ok": False, "error": str(e)}, status=400)


@method_decorator(csrf_exempt, name='dispatch')
class UpdateAppAPIView(View):
    """ویرایش اطلاعات و آیکون یک اپلیکیشن"""

    def post(self, request, *args, **kwargs):
        try:
            if request.content_type and 'multipart/form-data' in request.content_type:
                app_id = request.POST.get('app_id', '').strip()
                name = request.POST.get('name')
                package_name = request.POST.get('package_name')
                description = request.POST.get('description')
                platform = request.POST.get('platform')
                icon_file = request.FILES.get('icon')
            else:
                body = json.loads(request.body.decode('utf-8')) if request.body else {}
                app_id = body.get('app_id', '').strip()
                name = body.get('name')
                package_name = body.get('package_name')
                description = body.get('description')
                platform = body.get('platform')
                icon_file = None

            if not app_id:
                return JsonResponse({"ok": False, "error": "شناسه برنامه (app_id) الزامی است."}, status=400)

            app = AppService.update_app(
                app_id=app_id,
                name=name,
                package_name=package_name,
                description=description,
                platform=platform,
                icon_file=icon_file
            )
            return JsonResponse({
                "ok": True,
                "app_id": app.app_id,
                "name": app.name,
                "icon_url": app.icon_url,
                "message": f"اطلاعات برنامه '{app.name}' با موفقیت به‌روزرسانی شد."
            })
        except Exception as e:
            return JsonResponse({"ok": False, "error": str(e)}, status=400)


@method_decorator(csrf_exempt, name='dispatch')
class DeleteAppAPIView(View):
    """حذف کامل یک اپلیکیشن"""

    def post(self, request, *args, **kwargs):
        try:
            body = json.loads(request.body.decode('utf-8')) if request.body else {}
            app_id = (body.get('app_id') or request.POST.get('app_id') or request.GET.get('app_id') or '').strip()
            if not app_id:
                return JsonResponse({"ok": False, "error": "شناسه برنامه (app_id) الزامی است."}, status=400)
            AppService.delete_app(app_id)
            return JsonResponse({"ok": True, "message": f"برنامه '{app_id}' با موفقیت حذف گردید."})
        except Exception as e:
            return JsonResponse({"ok": False, "error": str(e)}, status=400)


@method_decorator(csrf_exempt, name='dispatch')
class PatchesAPIView(View):
    """دریافت تاریخچه پچ‌های یک اپلیکیشن"""

    def get(self, request, *args, **kwargs):
        app_id = request.GET.get('app_id')
        if not app_id:
            return JsonResponse([], safe=False)
        patches = PatchService.get_patches_for_app(app_id.strip())
        return JsonResponse(patches, safe=False)


@method_decorator(csrf_exempt, name='dispatch')
class UploadPatchAPIView(View):
    """آپلود و انتشار باینری پچ جدید"""

    def post(self, request, *args, **kwargs):
        app_id = (request.POST.get('app_id') or request.GET.get('app_id') or '').strip()
        if not app_id:
            return JsonResponse({"ok": False, "error": "شناسه برنامه (app_id) الزامی است."}, status=400)
        version = (request.POST.get('version') or request.GET.get('version') or '').strip()
        if not version:
            return JsonResponse({"ok": False, "error": "شماره نسخه پچ الزامی است."}, status=400)
        target_version_code = request.POST.get('target_version_code') or request.GET.get('target_version_code', 1)
        target_abi = (request.POST.get('target_abi') or request.GET.get('target_abi') or 'multi').strip()
        is_force = (request.POST.get('is_force') or request.GET.get('is_force', '0')) in ['1', 'true', True]
        activate = (request.POST.get('activate') or request.GET.get('activate', '1')) in ['1', 'true', True]
        release_notes = request.POST.get('notes') or request.GET.get('notes', '')
        filename = request.POST.get('filename') or request.GET.get('filename', 'patch.zip')


        # بررسی نحوه ارسال فایل (Multipart FormData یا Binary Body)
        file_obj = None
        if request.FILES.get('file'):
            file_obj = request.FILES['file']
        elif request.FILES.get('patch'):
            file_obj = request.FILES['patch']
        else:
            try:
                content_len = int(request.META.get('CONTENT_LENGTH') or 0)
                if content_len > 0 and len(request.body) > 0:
                    file_obj = ContentFile(request.body, name=filename)
            except Exception as e:
                return JsonResponse({"ok": False, "error": f"خطا در خواندن فایل آپلود شده: {e}"}, status=400)

        if not file_obj:
            return JsonResponse({"ok": False, "error": "هیچ فایل پچی ارسال نشده است."}, status=400)

        try:
            patch = PatchService.publish_patch(
                app_id=app_id,
                file_obj=file_obj,
                version=version,
                target_version_code=int(target_version_code),
                target_abi=target_abi,
                is_force=is_force,
                activate=activate,
                release_notes=release_notes
            )
            return JsonResponse({
                "ok": True,
                "patch_id": patch.id,
                "version": patch.version,
                "size_bytes": patch.size_bytes,
                "md5": patch.md5
            })
        except Exception as e:
            return JsonResponse({"ok": False, "error": str(e)}, status=500)


@method_decorator(csrf_exempt, name='dispatch')
class ActivatePatchAPIView(View):
    """فعال‌سازی و رول‌بک ایمن به یک نسخه از پچ"""

    def post(self, request, *args, **kwargs):
        try:
            body = json.loads(request.body.decode('utf-8'))
            app_id = body.get('app_id')
            patch_id = int(body.get('patch_id', 0))

            if not app_id:
                return JsonResponse({"ok": False, "error": "شناسه برنامه (app_id) الزامی است."}, status=400)

            PatchService.rollback_to_patch(app_id, patch_id)
            return JsonResponse({"ok": True})
        except Exception as e:
            return JsonResponse({"ok": False, "error": str(e)}, status=400)


@method_decorator(csrf_exempt, name='dispatch')
class ToggleForceAPIView(View):
    """تغییر وضعیت سیاست اجباری بودن پچ"""

    def post(self, request, *args, **kwargs):
        try:
            body = json.loads(request.body.decode('utf-8'))
            patch_id = int(body.get('patch_id', 0))
            is_force = PatchService.toggle_force_policy(patch_id)
            return JsonResponse({"ok": True, "is_force": is_force})
        except Exception as e:
            return JsonResponse({"ok": False, "error": str(e)}, status=400)


@method_decorator(csrf_exempt, name='dispatch')
class DeletePatchAPIView(View):
    """حذف دائم پچ و فایل آن"""

    def post(self, request, *args, **kwargs):
        try:
            body = json.loads(request.body.decode('utf-8'))
            patch_id = int(body.get('patch_id', 0))
            PatchService.delete_patch(patch_id)
            return JsonResponse({"ok": True})
        except Exception as e:
            return JsonResponse({"ok": False, "error": str(e)}, status=400)


class CheckUpdateAPIView(View):
    """اندپوینت استعلام به‌روزرسانی برای کلاینت‌های فلاتر"""

    def get(self, request, *args, **kwargs):
        raw_app_id = (
            request.GET.get('app_id') or 
            request.GET.get('package_name') or 
            request.GET.get('id')
        )
        if not raw_app_id or not str(raw_app_id).strip():
            return JsonResponse({
                "ok": False,
                "has_update": False,
                "error": "شناسه برنامه (app_id یا package_name) الزامی است."
            }, status=400)

        app_id = str(raw_app_id).strip()
        version_code = (
            request.GET.get('app_version_code') or 
            request.GET.get('version_code') or 
            request.GET.get('build_number')
        )
        current_patch = (
            request.GET.get('current_patch') or 
            request.GET.get('patch_version') or 
            request.GET.get('current_version')
        )

        host = request.get_host()
        scheme = "https" if request.is_secure() or request.headers.get("x-forwarded-proto") == "https" else "http"

        print(f"[CheckUpdate/API] Request from {request.META.get('REMOTE_ADDR')}: app_id='{app_id}', version_code='{version_code}', current_patch='{current_patch}'")
        update_info = PatchService.check_update(
            app_id=app_id,
            version_code=version_code,
            current_patch=current_patch,
            host=host,
            scheme=scheme
        )
        print(f"[CheckUpdate/API] Response: has_update={update_info.get('has_update')}, version={update_info.get('version')}, force={update_info.get('is_force')}")
        return JsonResponse(update_info)


class DownloadPatchView(View):
    """دانلود مستقیم و استریمی فایل باینری پچ"""

    def get(self, request, rel_path, *args, **kwargs):
        media_root = str(settings.MEDIA_ROOT)
        full_path = os.path.normpath(os.path.join(media_root, rel_path))

        # پیشگیری از Directory Traversal
        if not full_path.startswith(media_root) or not os.path.isfile(full_path):
            raise Http404("فایل پچ یافت نشد.")

        # افزایش شمارنده تعداد دانلود پچ
        try:
            from django.db.models import F
            from .models import Patch
            parts = rel_path.strip('/').split('/')
            if len(parts) >= 2:
                Patch.objects.filter(app__app_id=parts[0], version=parts[1]).update(download_count=F('download_count') + 1)
        except Exception:
            pass

        content_type, _ = mimetypes.guess_type(full_path)
        response = FileResponse(open(full_path, 'rb'), content_type=content_type or 'application/octet-stream')
        response['Content-Length'] = os.path.getsize(full_path)
        response['Content-Disposition'] = f'attachment; filename="{os.path.basename(full_path)}"'
        return response


class DownloadReleaseView(View):
    """دانلود مستقیم و استریمی فایل باینری نصبی نیتیو (APK)"""

    def get(self, request, rel_path, *args, **kwargs):
        releases_root = str(getattr(settings, 'RELEASES_ROOT', settings.BASE_DIR / 'releases'))
        full_path = os.path.normpath(os.path.join(releases_root, rel_path))

        # پیشگیری از Directory Traversal
        if not full_path.startswith(releases_root) or not os.path.isfile(full_path):
            raise Http404("فایل نصبی یافت نشد.")

        # افزایش شمارنده تعداد دانلود نسخه
        try:
            from django.db.models import F
            from .models import Release
            parts = rel_path.strip('/').split('/')
            if len(parts) >= 2:
                Release.objects.filter(app__app_id=parts[0], version_code=int(parts[1])).update(download_count=F('download_count') + 1)
        except Exception:
            pass

        content_type, _ = mimetypes.guess_type(full_path)
        response = FileResponse(open(full_path, 'rb'), content_type=content_type or 'application/vnd.android.package-archive')
        response['Content-Length'] = os.path.getsize(full_path)
        response['Content-Disposition'] = f'attachment; filename="{os.path.basename(full_path)}"'
        return response


@method_decorator(csrf_exempt, name='dispatch')
class ReleasesAPIView(View):
    """دریافت تاریخچه نسخه‌های نصبی نیتیو یک اپلیکیشن"""

    def get(self, request, *args, **kwargs):
        app_id = request.GET.get('app_id')
        if not app_id:
            return JsonResponse([], safe=False)
        releases = ReleaseService.list_releases_for_app(app_id.strip())
        return JsonResponse(releases, safe=False)


@method_decorator(csrf_exempt, name='dispatch')
class UploadReleaseAPIView(View):
    """آپلود و انتشار فایل نصبی نیتیو جدید (APK)"""

    def post(self, request, *args, **kwargs):
        app_id = (request.POST.get('app_id') or request.GET.get('app_id') or '').strip()
        if not app_id:
            return JsonResponse({"ok": False, "error": "شناسه برنامه (app_id) الزامی است."}, status=400)

        version_name = (request.POST.get('version_name') or request.GET.get('version_name') or '').strip()
        version_code = request.POST.get('version_code') or request.GET.get('version_code')
        if not version_name or not version_code:
            return JsonResponse({"ok": False, "error": "نام نسخه (version_name) و کد بیلد نیتیو (version_code) الزامی هستند."}, status=400)

        is_force = (request.POST.get('is_force') or request.GET.get('is_force', '0')) in ['1', 'true', True]
        activate = (request.POST.get('activate') or request.GET.get('activate', '1')) in ['1', 'true', True]
        release_notes = request.POST.get('notes') or request.GET.get('notes', '')
        filename = request.POST.get('filename') or request.GET.get('filename', 'app-release.apk')

        file_obj = None
        if request.FILES.get('file'):
            file_obj = request.FILES['file']
        elif request.FILES.get('apk'):
            file_obj = request.FILES['apk']
        else:
            try:
                content_len = int(request.META.get('CONTENT_LENGTH') or 0)
                if content_len > 0 and len(request.body) > 0:
                    file_obj = ContentFile(request.body, name=filename)
            except Exception as e:
                return JsonResponse({"ok": False, "error": f"خطا در خواندن فایل آپلود شده: {e}"}, status=400)

        if not file_obj:
            return JsonResponse({"ok": False, "error": "هیچ فایل نصبی (APK) ارسال نشده است."}, status=400)

        try:
            release = ReleaseService.publish_release(
                app_id=app_id,
                file_obj=file_obj,
                version_name=version_name,
                version_code=int(version_code),
                is_force=is_force,
                activate=activate,
                release_notes=release_notes
            )
            return JsonResponse({
                "ok": True,
                "release_id": release.id,
                "version_name": release.version_name,
                "version_code": release.version_code,
                "size_bytes": release.size_bytes,
                "md5": release.md5
            })
        except Exception as e:
            return JsonResponse({"ok": False, "error": str(e)}, status=400)


@method_decorator(csrf_exempt, name='dispatch')
class ActivateReleaseAPIView(View):
    """فعال‌سازی یا رول‌بک نسخه نصبی نیتیو"""

    def post(self, request, *args, **kwargs):
        try:
            body = json.loads(request.body.decode('utf-8'))
            app_id = body.get('app_id')
            release_id = int(body.get('release_id', 0))

            if not app_id:
                return JsonResponse({"ok": False, "error": "شناسه برنامه (app_id) الزامی است."}, status=400)

            ReleaseService.rollback_to_release(app_id, release_id)
            return JsonResponse({"ok": True})
        except Exception as e:
            return JsonResponse({"ok": False, "error": str(e)}, status=400)


@method_decorator(csrf_exempt, name='dispatch')
class ToggleForceReleaseAPIView(View):
    """تغییر سیاست ارتقای اجباری نسخه نصبی"""

    def post(self, request, *args, **kwargs):
        try:
            body = json.loads(request.body.decode('utf-8'))
            release_id = int(body.get('release_id', 0))
            is_force = ReleaseService.toggle_force_release(release_id)
            return JsonResponse({"ok": True, "is_force": is_force})
        except Exception as e:
            return JsonResponse({"ok": False, "error": str(e)}, status=400)


@method_decorator(csrf_exempt, name='dispatch')
class DeleteReleaseAPIView(View):
    """حذف دائم نسخه نصبی نیتیو و فایل باینری آن"""

    def post(self, request, *args, **kwargs):
        try:
            body = json.loads(request.body.decode('utf-8'))
            release_id = int(body.get('release_id', 0))
            ReleaseService.delete_release(release_id)
            return JsonResponse({"ok": True})
        except Exception as e:
            return JsonResponse({"ok": False, "error": str(e)}, status=400)




@method_decorator(csrf_exempt, name='dispatch')
class OtaCheckV1APIView(View):
    """
    اندپوینت استاندارد استعلام OTA کلاینت بر اساس معماری سیستم دیزاین
    POST /api/v1/ota/check/
    """

    def post(self, request, *args, **kwargs):
        try:
            body = json.loads(request.body.decode('utf-8'))
        except Exception:
            body = request.POST.dict()

        app_id = (body.get('app_id') or body.get('package_name') or 'quran_tafakor').strip()
        base_release = body.get('base_release')
        base_version_name = body.get('base_version_name')
        base_build_number = body.get('base_build_number')
        abi = body.get('abi')
        current_patch_version = body.get('current_patch_version')
        channel = body.get('channel') or 'stable'
        device_id = body.get('device_id')

        host = request.get_host()
        scheme = "https" if request.is_secure() or request.headers.get("x-forwarded-proto") == "https" else "http"

        print(f"[OTA/v1/Check] Request: app='{app_id}', base='{base_release}', build={base_build_number}, abi='{abi}', current_patch='{current_patch_version}', channel='{channel}'")

        res_data = PatchService.check_ota_v1(
            app_id=app_id,
            base_release=base_release,
            base_version_name=base_version_name,
            base_build_number=base_build_number,
            abi=abi,
            current_patch_version=current_patch_version,
            channel=channel,
            device_id=device_id,
            host=host,
            scheme=scheme
        )
        print(f"[OTA/v1/Check] Response: status={res_data.get('status')}")
        return JsonResponse(res_data)


@method_decorator(csrf_exempt, name='dispatch')
class OtaReportV1APIView(View):
    """
    اندپوینت ثبت رویداد و تله‌متری کلاینت OTA
    POST /api/v1/ota/report/
    """

    def post(self, request, *args, **kwargs):
        try:
            body = json.loads(request.body.decode('utf-8'))
        except Exception:
            body = request.POST.dict()

        app_id = body.get('app_id') or 'quran_tafakor'
        patch_version = body.get('patch_version') or ''
        event = body.get('event') or 'UNKNOWN'
        duration_ms = body.get('duration_ms')
        device_id = body.get('device_id')

        print(f"📊 [OTA/Report] app='{app_id}', patch='{patch_version}', event='{event}', duration={duration_ms}ms, device='{device_id}'")

        try:
            PatchService.record_telemetry(
                app_id=app_id,
                patch_version=patch_version,
                event=event,
                duration_ms=int(duration_ms) if duration_ms is not None else None,
                device_id=device_id
            )
            return JsonResponse({"ok": True})
        except Exception as e:
            return JsonResponse({"ok": False, "error": str(e)}, status=500)


@method_decorator(csrf_exempt, name='dispatch')
class OtaPublishV1APIView(View):
    """
    اندپوینت انتشار اتوماتیک بسته پچ چندمعماری (CLI Tool Publish)
    POST /api/v1/ota/publish/
    """

    def post(self, request, *args, **kwargs):
        file_obj = request.FILES.get('file') or request.FILES.get('bundle')
        channel = request.POST.get('channel', 'stable')

        if not file_obj:
            return JsonResponse({"ok": False, "error": "فایل بسته پچ (patch_bundle.zip) یافت نشد."}, status=400)

        try:
            patch = PatchService.publish_patch_bundle(file_obj, channel=channel)
            artifacts_info = [
                {"abi": a.abi, "md5": a.md5, "size_bytes": a.file_size}
                for a in patch.artifacts.all()
            ]
            return JsonResponse({
                "ok": True,
                "version": patch.version,
                "channel": patch.channel,
                "base_release": patch.base_release.release_name if patch.base_release else None,
                "artifacts": artifacts_info
            })
        except Exception as e:
            return JsonResponse({"ok": False, "error": str(e)}, status=500)
