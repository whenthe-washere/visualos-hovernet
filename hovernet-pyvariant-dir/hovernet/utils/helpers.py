import os
import random
from urllib.parse import quote_plus

def normalize_input(text):
    text = (text or "").strip()
    if not text:
        return "https://www.google.com"

    # Already a fully qualified URL — pass straight through
    if text.startswith(("http://", "https://", "file://", "ftp://")):
        return text

    # Internal browser URIs — never search these
    if text == "hovernet:settings":
        return "hovernet://settings"
    if text == "hovernet:history":
        return "hovernet://history"
    if text.startswith(("about:", "chrome:", "edge:", "data:", "hovernet:")):
        return text

    # localhost or local IPs (with optional port/path)
    import re
    if re.match(r'^localhost(:\d+)?(/.*)?$', text) or \
       re.match(r'^127\.\d+\.\d+\.\d+(:\d+)?(/.*)?$', text) or \
       re.match(r'^192\.168\.\d+\.\d+(:\d+)?(/.*)?$', text):
        return "http://" + text

    # Has spaces → definitely a search query
    if " " in text:
        return "https://www.google.com/search?q=" + quote_plus(text)

    # Looks like a domain: has a dot, no spaces, and a valid-ish TLD
    if re.match(r'^(www\.)?[a-zA-Z0-9\-]+(\.[a-zA-Z]{2,})+(/.*)?$', text):
        return "https://" + text

    # Everything else → search
    return "https://www.google.com/search?q=" + quote_plus(text)

def format_size(bytes_val):
    if bytes_val <= 0:
        return "?"
    for unit in ("B", "KB", "MB", "GB"):
        if bytes_val < 1024:
            return f"{bytes_val:.1f} {unit}"
        bytes_val /= 1024
    return f"{bytes_val:.1f} GB"
