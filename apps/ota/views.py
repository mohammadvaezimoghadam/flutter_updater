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

from .services import AppService, PatchService, SystemService


class DashboardView(View):
    """رندر داشبورد کنترل پنل OTA با تمپلیت مدرن Persian Control Plane"""

    def get(self, request, *args, **kwargs):
        app_id = request.GET.get('app_id', 'quran_app')
        app = AppService.get_app_by_id(app_id) or AppService.list_apps_summary()
        current_app = AppService.get_app_by_id(app_id)
        if not current_app:
            from .models import App
            current_app = App.objects.first()

        active_patch = current_app.active_patch if current_app else None
        recent_patches = current_app.patches.all().order_by('-id')[:5] if current_app else []
        apps_list = AppService.list_apps_summary()
        status_data = SystemService.get_status()

        context = {
            'current_app': current_app,
            'active_patch': active_patch,
            'recent_patches': recent_patches,
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
            body = json.loads(request.body.decode('utf-8'))
            app_id = body.get('app_id', '').strip()
            name = body.get('name', '').strip()
            package_name = body.get('package_name', '').strip()
            description = body.get('description', '').strip()
            platform = body.get('platform', 'all').strip()

            if not app_id or not name or not package_name:
                return JsonResponse({"ok": False, "error": "تمامی فیلدهای الزامی را پر کنید."}, status=400)

            app = AppService.create_app(
                app_id=app_id,
                name=name,
                package_name=package_name,
                description=description,
                platform=platform
            )
            return JsonResponse({"ok": True, "app_id": app.app_id})
        except Exception as e:
            return JsonResponse({"ok": False, "error": str(e)}, status=400)


@method_decorator(csrf_exempt, name='dispatch')
class PatchesAPIView(View):
    """دریافت تاریخچه پچ‌های یک اپلیکیشن"""

    def get(self, request, *args, **kwargs):
        app_id = request.GET.get('app_id', 'quran_app')
        patches = PatchService.get_patches_for_app(app_id)
        return JsonResponse(patches, safe=False)


@method_decorator(csrf_exempt, name='dispatch')
class UploadPatchAPIView(View):
    """آپلود و انتشار باینری پچ جدید"""

    def post(self, request, *args, **kwargs):
        app_id = (request.POST.get('app_id') or request.GET.get('app_id') or 'quran_app').strip()
        version = (request.POST.get('version') or request.GET.get('version') or '1.0.0').strip()
        target_version_code = request.POST.get('target_version_code') or request.GET.get('target_version_code', 1)
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
        app_id = (
            request.GET.get('app_id') or 
            request.GET.get('package_name') or 
            request.GET.get('id') or 
            'quran_app'
        ).strip()
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

        content_type, _ = mimetypes.guess_type(full_path)
        response = FileResponse(open(full_path, 'rb'), content_type=content_type or 'application/octet-stream')
        response['Content-Length'] = os.path.getsize(full_path)
        response['Content-Disposition'] = f'attachment; filename="{os.path.basename(full_path)}"'
        return response
