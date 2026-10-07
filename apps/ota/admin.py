from django.contrib import admin
from .models import App, Patch


@admin.register(App)
class AppAdmin(admin.ModelAdmin):
    list_display = ('name', 'app_id', 'package_name', 'platform', 'is_active', 'total_patches_badge', 'created_at')
    list_filter = ('platform', 'is_active')
    search_fields = ('name', 'app_id', 'package_name')
    readonly_fields = ('created_at', 'updated_at')

    def total_patches_badge(self, obj):
        return f"{obj.total_patches} نسخه"
    total_patches_badge.short_description = "کل پچ‌ها"


@admin.register(Patch)
class PatchAdmin(admin.ModelAdmin):
    list_display = ('version', 'app', 'target_version_code', 'status', 'is_force', 'formatted_size', 'md5', 'created_at')
    list_filter = ('app', 'status', 'is_force')
    search_fields = ('version', 'app__name', 'app__app_id', 'md5', 'release_notes')
    readonly_fields = ('size_bytes', 'md5', 'sha256', 'created_at', 'updated_at')
    actions = ['activate_selected_patches']

    def activate_selected_patches(self, request, queryset):
        for patch in queryset:
            patch.activate_and_rollback()
        self.message_user(request, "پچ(های) انتخاب‌شده فعال شدند.")
    activate_selected_patches.short_description = "فعال‌سازی و رول‌بک به پچ‌های انتخاب‌شده"
