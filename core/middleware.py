class SecurityHeadersMiddleware:
    """Apply conservative browser security headers without external packages."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        from django.conf import settings

        response = self.get_response(request)
        if settings.CONTENT_SECURITY_POLICY:
            response.setdefault("Content-Security-Policy", settings.CONTENT_SECURITY_POLICY)
        if settings.PERMISSIONS_POLICY:
            response.setdefault("Permissions-Policy", settings.PERMISSIONS_POLICY)
        return response
