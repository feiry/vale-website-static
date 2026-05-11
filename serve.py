#!/usr/bin/env python3
"""Local dev server that auto-detects MIME types for extensionless files."""

import http.server
import mimetypes
import subprocess
import sys
from pathlib import Path


class SmartHandler(http.server.SimpleHTTPRequestHandler):
    def guess_type(self, path):
        """path here is a filesystem path (from SimpleHTTPRequestHandler)."""
        # Try standard lookup first
        mime, _ = mimetypes.guess_type(path)
        if mime and mime != "application/octet-stream":
            return mime

        # For extensionless or UUID-suffixed files, detect from content
        fpath = Path(path)
        if fpath.is_file():
            try:
                result = subprocess.run(
                    ["file", "--brief", "--mime-type", str(fpath)],
                    capture_output=True, text=True, timeout=2,
                )
                detected = result.stdout.strip()
                if detected and "/" in detected:
                    return detected
            except Exception:
                pass

        # Fallback: check if any path component has a known image extension
        # e.g. /documents/.../image.png/<uuid> → image/png
        for part in fpath.parts:
            ext_mime, _ = mimetypes.guess_type(part)
            if ext_mime and ext_mime.startswith(("image/", "application/pdf")):
                return ext_mime

        return mime or "application/octet-stream"


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
    bind = sys.argv[2] if len(sys.argv) > 2 else "0.0.0.0"

    server = http.server.HTTPServer((bind, port), SmartHandler)
    print(f"Serving at http://{bind}:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
