"""Bounded, approximate sign-in labels shared by staff and customer sessions."""
from datetime import timezone


def aware(value):
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def device_labels(user_agent):
    # Retain only fixed labels, never the original header or network address.
    value = user_agent[:512].lower()
    browser = "Edge" if "edg/" in value or "edga/" in value else "Firefox" if "firefox/" in value or "fxios/" in value else "Chrome" if "chrome/" in value or "crios/" in value else "Safari" if "safari/" in value else "Other browser or app"
    device = "iPhone or iPad" if "iphone" in value or "ipad" in value else "Android" if "android" in value else "Windows" if "windows" in value else "macOS" if "macintosh" in value or "mac os" in value else "Linux" if "linux" in value else "Unknown device"
    return browser, device
