# apps/ota/urls.py
from django.urls import path, re_path
from .views import (
    DashboardView,
    StatusAPIView,
    AppsAPIView,
    PatchesAPIView,
    UploadPatchAPIView,
    ActivatePatchAPIView,
    ToggleForceAPIView,
    DeletePatchAPIView,
    CheckUpdateAPIView,
    DownloadPatchView,
)

app_name = 'ota'

urlpatterns = [
    # صفحات وب داشبورد
    path('', DashboardView.as_view(), name='dashboard'),
    path('dashboard', DashboardView.as_view(), name='dashboard_tab'),
    path('publisher', DashboardView.as_view(), name='publisher_tab'),
    path('rollback', DashboardView.as_view(), name='rollback_tab'),
    path('apps', DashboardView.as_view(), name='apps_tab'),

    # اندپوینت‌های کلاینت فلاتر
    path('check', CheckUpdateAPIView.as_view(), name='check_update'),
    re_path(r'^patches/(?P<rel_path>.*)$', DownloadPatchView.as_view(), name='download_patch'),

    # اندپوینت‌های REST API کنترل پنل
    path('api/status', StatusAPIView.as_view(), name='api_status'),
    path('api/apps', AppsAPIView.as_view(), name='api_apps'),
    path('api/patches', PatchesAPIView.as_view(), name='api_patches'),
    path('api/patches/upload', UploadPatchAPIView.as_view(), name='api_upload_patch'),
    path('api/patches/activate', ActivatePatchAPIView.as_view(), name='api_activate_patch'),
    path('api/patches/toggle_force', ToggleForceAPIView.as_view(), name='api_toggle_force'),
    path('api/patches/delete', DeletePatchAPIView.as_view(), name='api_delete_patch'),
]
