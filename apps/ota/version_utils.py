# apps/ota/version_utils.py
import re
from typing import Optional
from packaging.version import parse as parse_version, InvalidVersion


def normalize_version(version_str: str) -> str:
    """حذف کاراکترهای اضافی و پیشوند v از شماره نسخه"""
    if not version_str:
        return ""
    v = str(version_str).strip()
    if v.lower().startswith('v'):
        v = v[1:].strip()
    return v


def _fallback_version_tuple(v_clean: str):
    """
    تجزیه شماره نسخه به توکن‌های عددی و متنی برای مقایسه دقیق نسخه‌های غیر استاندارد
    مثال: '1.0.0-patch.2' -> (1, 0, 0, 'patch', 2)
    """
    parts = re.split(r'[-.+_]', v_clean)
    parsed = []
    for p in parts:
        if not p:
            continue
        if p.isdigit():
            parsed.append((0, int(p)))
        else:
            subparts = re.split(r'(\d+)', p)
            for sp in subparts:
                if not sp:
                    continue
                if sp.isdigit():
                    parsed.append((0, int(sp)))
                else:
                    parsed.append((1, sp))
    return tuple(parsed)


def compare_versions(v1: str, v2: str) -> int:
    """
    مقایسه هوشمند دو رشته نسخه (SemVer، اعداد صحیح، یا نسخه‌های ترکیبی):
    خروجی:
       1 : اگر v1 > v2
      -1 : اگر v1 < v2
       0 : اگر v1 == v2
    """
    n1 = normalize_version(v1)
    n2 = normalize_version(v2)

    if n1 == n2:
        return 0
    if not n1:
        return -1
    if not n2:
        return 1

    # ۱. استفاده از موتور استاندارد packaging.version (پشتیبانی کامل SemVer و PEP 440)
    try:
        pv1 = parse_version(n1)
        pv2 = parse_version(n2)
        if pv1 > pv2:
            return 1
        elif pv1 < pv2:
            return -1
        else:
            return 0
    except InvalidVersion:
        pass

    # ۲. فال‌بک به تفکیک عددی و توکنی
    try:
        t1 = _fallback_version_tuple(n1)
        t2 = _fallback_version_tuple(n2)
        if t1 > t2:
            return 1
        elif t1 < t2:
            return -1
        else:
            return 0
    except Exception:
        pass

    # ۳. فال‌بک نهایی
    return 1 if n1 > n2 else -1


def is_version_greater(new_v: str, old_v: str) -> bool:
    """آیا نسخه جدید اکیداً بزرگ‌تر از نسخه قبلی است؟"""
    return compare_versions(new_v, old_v) > 0


def get_highest_patch_version(app) -> Optional[str]:
    """یافتن بالاترین نسخه ثبت‌شده در تمامی پچ‌های یک اپلیکیشن"""
    patches = app.patches.all()
    if not patches.exists():
        return None

    highest = None
    for p in patches:
        if highest is None:
            highest = p.version
        elif is_version_greater(p.version, highest):
            highest = p.version
    return highest


def validate_new_patch_version(app, new_version: str) -> None:
    """
    اعتبارسنجی اجباری بزرگ‌تر بودن نسخه پچ جدید نسبت به آخرین نسخه ثبت‌شده برای همین اپلیکیشن
    """
    new_version_clean = normalize_version(new_version)
    if not new_version_clean:
        raise ValueError("شماره نسخه پچ نمی‌تواند خالی باشد.")

    highest = get_highest_patch_version(app)
    if highest is not None:
        comp = compare_versions(new_version, highest)
        if comp < 0:
            raise ValueError(
                f"نسخه پچ جدید (v{new_version}) نمی‌تواند از آخرین نسخه ثبت‌شده (v{highest}) کوچک‌تر باشد."
            )
        elif comp == 0:
            raise ValueError(
                f"نسخه پچ (v{new_version}) قبلاً برای این اپلیکیشن ثبت شده است. لطفاً نسخه بالاتری ثبت نمایید."
            )
