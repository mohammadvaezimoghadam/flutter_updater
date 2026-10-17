import json
from django.test import TestCase, Client
from django.core.files.uploadedfile import SimpleUploadedFile
from apps.ota.models import App, BaseRelease, Patch, Release
from apps.ota.services import PatchService, ReleaseService


class OtaLifecycleTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.app = App.objects.create(
            name="Quran Tafakor",
            app_id="quran_tafakor",
            package_name="com.qurantafakor.app",
            is_active=True
        )

    def test_native_apk_priority_over_current_patch(self):
        """
        تست باگ اصلی گزارش‌شده توسط کاربر:
        کاربر روی بیلد ۱ است و پچ فعال 1.0.14 را نصب دارد.
        فایل نصبی جدید APK بیلد ۲ روی سرور منتشر شده است.
        سرور باید حتماً آپدیت نیتیو (فایل نصبی بیلد ۲) را به کاربر برگرداند نه UP_TO_DATE!
        """
        base_v1 = BaseRelease.objects.create(
            app=self.app,
            release_name="1.0.0+1",
            build_number=1,
            version_string="1.0.0",
            is_active=False
        )
        Patch.objects.create(
            app=self.app,
            base_release=base_v1,
            version="1.0.14",
            patch_number=14,
            status="active"
        )

        dummy_apk = SimpleUploadedFile("app-release.apk", b"PKtestapkpayload", content_type="application/vnd.android.package-archive")
        ReleaseService.publish_release(
            app_id="quran_tafakor",
            file_obj=dummy_apk,
            version_name="1.0.1",
            version_code=2,
            activate=True,
            release_notes="نسخه جدید ۱.۰.۱"
        )

        # استعلام کلاینت
        res = PatchService.check_ota_v1(
            app_id="quran_tafakor",
            base_release="1.0.0+1",
            base_build_number=1,
            current_patch_version="1.0.14"
        )

        self.assertEqual(res["status"], "PATCH_AVAILABLE")
        self.assertEqual(res["update_type"], "native")
        self.assertTrue(res["has_update"])
        self.assertEqual(res["patch"]["version"], "1.0.1")
        self.assertEqual(res["patch"]["target_version_code"], 2)
        self.assertIn("/releases/quran_tafakor/2/", res["patch"]["download_url"])

    def test_client_on_latest_build_is_up_to_date_when_no_patch(self):
        """
        کاربر APK بیلد ۲ را نصب کرده است.
        سرور هنوز هیچ پچی برای بیلد ۲ منتشر نکرده است.
        سرور باید وضعیت UP_TO_DATE برگرداند.
        """
        dummy_apk = SimpleUploadedFile("app-release.apk", b"PKtestapkpayload", content_type="application/vnd.android.package-archive")
        ReleaseService.publish_release(
            app_id="quran_tafakor",
            file_obj=dummy_apk,
            version_name="1.0.1",
            version_code=2,
            activate=True
        )

        res = PatchService.check_ota_v1(
            app_id="quran_tafakor",
            base_release="1.0.1+2",
            base_build_number=2,
            current_patch_version=""
        )

        self.assertEqual(res["status"], "UP_TO_DATE")

    def test_patch_delivery_when_builds_match(self):
        """
        کاربر روی بیلد ۱ است و پچ قدیمی 1.0.13 دارد.
        پچ جدید 1.0.14 برای بیلد ۱ فعال است و نسخه نصبی جدیدی هم نیامده است.
        سرور باید پچ دارت 1.0.14 را ارسال کند.
        """
        base_v1 = BaseRelease.objects.create(
            app=self.app,
            release_name="1.0.0+1",
            build_number=1,
            version_string="1.0.0",
            is_active=True
        )
        Patch.objects.create(
            app=self.app,
            base_release=base_v1,
            version="1.0.14",
            patch_number=14,
            status="active",
            filename="patch.zip"
        )

        res = PatchService.check_ota_v1(
            app_id="quran_tafakor",
            base_release="1.0.0+1",
            base_build_number=1,
            current_patch_version="1.0.13"
        )

        self.assertEqual(res["status"], "PATCH_AVAILABLE")
        self.assertEqual(res["update_type"], "patch")
        self.assertEqual(res["patch"]["version"], "1.0.14")

    def test_store_update_fallback_when_no_direct_apk_file(self):
        """
        بیلد ۲ در استور فعال است ولی فایل APK مستقیم در سرور آپلود نشده است.
        سرور باید به درستی STORE_UPDATE_REQUIRED برگرداند.
        """
        BaseRelease.objects.create(
            app=self.app,
            release_name="1.0.1+2",
            build_number=2,
            version_string="1.0.1",
            is_active=True
        )

        res = PatchService.check_ota_v1(
            app_id="quran_tafakor",
            base_release="1.0.0+1",
            base_build_number=1,
            current_patch_version=""
        )

        self.assertEqual(res["status"], "STORE_UPDATE_REQUIRED")
        self.assertEqual(res["store"]["latest_version"], "1.0.1")

    def test_publish_release_calculates_hashes_and_syncs_baserelease(self):
        """
        بررسی محاسبه خودکار MD5 و سایز بایت‌ها و ساخت رکورد BaseRelease
        """
        payload = b"SampleAPKContentForTestingMd5"
        dummy_apk = SimpleUploadedFile("app-release.apk", payload, content_type="application/vnd.android.package-archive")

        release = ReleaseService.publish_release(
            app_id="quran_tafakor",
            file_obj=dummy_apk,
            version_name="1.0.2",
            version_code=3,
            activate=True
        )

        self.assertEqual(release.size_bytes, len(payload))
        self.assertTrue(len(release.md5) > 0)
        self.assertTrue(len(release.sha256) > 0)

        # بررسی سینک شدن با BaseRelease
        base_rel = BaseRelease.objects.filter(release_name="1.0.2+3").first()
        self.assertIsNotNone(base_rel)
        self.assertEqual(base_rel.build_number, 3)
        self.assertTrue(base_rel.is_active)

    def test_reuploading_same_version_code_replaces_cleanly(self):
        """
        اگر توسعه‌دهنده بیلد ۲ را مجدداً آپلود کند،
        سیستم رکورد قبلی را آرشیو و فایل جدید را جایگزین می‌کند.
        """
        apk1 = SimpleUploadedFile("app-release.apk", b"APK_OLD_CONTENT", content_type="application/vnd.android.package-archive")
        r1 = ReleaseService.publish_release(
            app_id="quran_tafakor",
            file_obj=apk1,
            version_name="1.0.1",
            version_code=2,
            activate=True
        )

        apk2 = SimpleUploadedFile("app-release.apk", b"APK_NEW_CONTENT_FIXED", content_type="application/vnd.android.package-archive")
        r2 = ReleaseService.publish_release(
            app_id="quran_tafakor",
            file_obj=apk2,
            version_name="1.0.1",
            version_code=2,
            activate=True
        )

        r1.refresh_from_db()
        self.assertEqual(r1.status, "archived")
        self.assertEqual(r2.status, "active")
        self.assertEqual(self.app.active_release.id, r2.id)

    def test_http_api_v1_ota_check_endpoint(self):
        """
        تست سطح HTTP اندپوینت POST /api/v1/ota/check/ شبیه‌ساز درخواست دقیق کلاینت فلاتر
        """
        dummy_apk = SimpleUploadedFile("app-release.apk", b"PKtestapkpayload", content_type="application/vnd.android.package-archive")
        ReleaseService.publish_release(
            app_id="quran_tafakor",
            file_obj=dummy_apk,
            version_name="1.0.1",
            version_code=2,
            activate=True,
            release_notes="نسخه جدید ۱.۰.۱"
        )

        payload = {
            "app_id": "quran_tafakor",
            "base_release": "1.0.0+1",
            "base_version_name": "1.0.0",
            "base_build_number": 1,
            "abi": "arm64-v8a",
            "current_patch_version": "1.0.14",
            "channel": "stable",
            "device_id": "test_device_123"
        }

        response = self.client.post(
            "/api/v1/ota/check/",
            data=json.dumps(payload),
            content_type="application/json"
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], "PATCH_AVAILABLE")
        self.assertEqual(data["update_type"], "native")
        self.assertEqual(data["patch"]["version"], "1.0.1")
        self.assertEqual(data["patch"]["target_version_code"], 2)
