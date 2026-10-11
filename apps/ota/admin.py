from django.contrib import admin
from .models import App, Patch, Release, BaseRelease, PatchArtifact, TelemetryReport


@admin.register(App)
class AppAdmin(admin.ModelAdmin):
    list_display = ('name', 'app_id', 'package_name', 'platform', 'is_active', 'total_patches_badge', 'total_releases_badge', 'created_at')
    list_filter = ('platform', 'is_active')
    search_fields = ('name', 'app_id', 'package_name')
    readonly_fields = ('created_at', 'updated_at')

    def total_patches_badge(self, obj):
        return f"{obj.total_patches} پچ"
    total_patches_badge.short_description = "کل پچ‌ها"

    def total_releases_badge(self, obj):
        return f"{obj.total_releases} نسخه APK"
    total_releases_badge.short_description = "کل نسخه‌های نصبی"


@admin.register(BaseRelease)
class BaseReleaseAdmin(admin.ModelAdmin):
    list_display = ('release_name', 'version_string', 'build_number', 'is_active', 'store_url', 'created_at')
    list_filter = ('is_active', 'app')
    search_fields = ('release_name', 'version_string', 'build_number')
    readonly_fields = ('created_at',)


class PatchArtifactInline(admin.TabularInline):
    model = PatchArtifact
    extra = 0
    readonly_fields = ('file_size', 'md5', 'download_count', 'created_at')


@admin.register(Patch)
class PatchAdmin(admin.ModelAdmin):
    list_display = ('version', 'base_release', 'channel', 'target_version_code', 'status', 'is_mandatory', 'formatted_size', 'download_count', 'created_at')
    list_filter = ('channel', 'status', 'is_mandatory', 'is_force', 'app')
    search_fields = ('version', 'base_release__release_name', 'md5', 'change_log', 'release_notes')
    readonly_fields = ('size_bytes', 'md5', 'sha256', 'download_count', 'created_at', 'updated_at')
    inlines = [PatchArtifactInline]
    actions = ['activate_selected_patches']

    def activate_selected_patches(self, request, queryset):
        for patch in queryset:
            patch.activate_and_rollback()
        self.message_user(request, "پچ(های) انتخاب‌شده فعال شدند.")
    activate_selected_patches.short_description = "فعال‌سازی و رول‌بک به پچ‌های انتخاب‌شده"


@admin.register(PatchArtifact)
class PatchArtifactAdmin(admin.ModelAdmin):
    list_display = ('patch', 'abi', 'file_size', 'md5', 'download_count', 'created_at')
    list_filter = ('abi', 'patch__channel')
    search_fields = ('patch__version', 'md5')
    readonly_fields = ('created_at',)


@admin.register(TelemetryReport)
class TelemetryReportAdmin(admin.ModelAdmin):
    list_display = ('app_id', 'patch_version', 'event', 'duration_ms', 'device_id', 'created_at')
    list_filter = ('event', 'app_id', 'created_at')
    search_fields = ('app_id', 'patch_version', 'device_id')
    readonly_fields = ('created_at',)


@admin.register(Release)
class ReleaseAdmin(admin.ModelAdmin):
    list_display = ('version_name', 'version_code', 'app', 'status', 'is_force', 'formatted_size', 'download_count', 'md5', 'created_at')
    list_filter = ('app', 'status', 'is_force')
    search_fields = ('version_name', 'version_code', 'app__name', 'app__app_id', 'md5', 'release_notes')
    readonly_fields = ('size_bytes', 'md5', 'sha256', 'download_count', 'created_at', 'updated_at')
    actions = ['activate_selected_releases']

    def activate_selected_releases(self, request, queryset):
        for release in queryset:
            release.activate_and_rollback()
        self.message_user(request, "نسخه(های) انتخاب‌شده فعال شدند.")
    activate_selected_releases.short_description = "فعال‌سازی و رول‌بک به نسخه‌های انتخاب‌شده"
