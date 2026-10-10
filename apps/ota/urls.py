# apps/ota/urls.py
from django.urls import path, re_path
from .views import (
    DashboardView,
    StatusAPIView,
    AppsAPIView,
    UpdateAppAPIView,
    DeleteAppAPIView,
    PatchesAPIView,
    UploadPatchAPIView,
    ActivatePatchAPIView,
    ToggleForceAPIView,
    DeletePatchAPIView,
    CheckUpdateAPIView,
    DownloadPatchView,
    DownloadReleaseView,
    ReleasesAPIView,
    UploadReleaseAPIView,
    ActivateReleaseAPIView,
    ToggleForceReleaseAPIView,
    DeleteReleaseAPIView,
)

app_name = 'ota'

urlpatterns = [
    # صفحات وب داشبورد
    path('', DashboardView.as_view(), name='dashboard'),
    path('dashboard', DashboardView.as_view(), name='dashboard_tab'),
    path('publisher', DashboardView.as_view(), name='publisher_tab'),
    path('rollback', DashboardView.as_view(), name='rollback_tab'),
    path('apps', DashboardView.as_view(), name='apps_tab'),

    # اندپوینت‌های وضعیت سرور
    path('api/status', StatusAPIView.as_view(), name='api_status'),
    path('status', StatusAPIView.as_view(), name='status'),

    # اندپوینت‌های کلاینت فلاتر
    path('check', CheckUpdateAPIView.as_view(), name='check_update'),
    re_path(r'^patches/(?P<rel_path>.*)$', DownloadPatchView.as_view(), name='download_patch'),
    re_path(r'^releases/(?P<rel_path>.*)$', DownloadReleaseView.as_view(), name='download_release'),

    # اندپوینت‌های REST API برنامه‌ها
    path('api/apps', AppsAPIView.as_view(), name='api_apps'),
    path('api/apps/update', UpdateAppAPIView.as_view(), name='api_update_app'),
    path('api/apps/delete', DeleteAppAPIView.as_view(), name='api_delete_app'),
    path('api/patches', PatchesAPIView.as_view(), name='api_patches'),
    path('api/patches/upload', UploadPatchAPIView.as_view(), name='api_upload_patch'),
    path('api/patches/activate', ActivatePatchAPIView.as_view(), name='api_activate_patch'),
    path('api/patches/toggle_force', ToggleForceAPIView.as_view(), name='api_toggle_force'),
    path('api/patches/delete', DeletePatchAPIView.as_view(), name='api_delete_patch'),

    # اندپوینت‌های REST API ریلیزهای نیتیو APK
    path('api/releases', ReleasesAPIView.as_view(), name='api_releases'),
    path('api/releases/upload', UploadReleaseAPIView.as_view(), name='api_upload_release'),
    path('api/releases/activate', ActivateReleaseAPIView.as_view(), name='api_activate_release'),
    path('api/releases/toggle_force', ToggleForceReleaseAPIView.as_view(), name='api_toggle_force_release'),
    path('api/releases/delete', DeleteReleaseAPIView.as_view(), name='api_delete_release'),
]
