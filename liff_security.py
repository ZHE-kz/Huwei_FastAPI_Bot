def protect_profile_headers(path: str, headers) -> None:
    if path.startswith("/api/") or path in {"/profile", "/profile/"}:
        headers["Cache-Control"] = "private, no-store"
        headers["Pragma"] = "no-cache"
    if path.startswith("/api/") or path.startswith("/profile"):
        headers["X-Content-Type-Options"] = "nosniff"
        headers["Referrer-Policy"] = "no-referrer"
        headers["Permissions-Policy"] = "camera=(), microphone=()"
