from PySide6.QtWebEngineCore import QWebEngineUrlRequestInterceptor


class SSOInterceptor(QWebEngineUrlRequestInterceptor):
    """Injects OAuth Bearer tokens into API requests to Google/Microsoft services.

    Only targets known API endpoint domains — web login pages (accounts.google.com,
    login.microsoftonline.com) use session cookies, not Bearer tokens, so
    injecting there does nothing and may break requests.
    """

    GOOGLE_API_DOMAINS = ("www.googleapis.com", "people.googleapis.com",
                          "oauth2.googleapis.com")
    MICROSOFT_API_DOMAINS = ("graph.microsoft.com", "api.onedrive.com")

    def __init__(self, get_token):
        super().__init__()
        self._get_token = get_token

    def interceptRequest(self, info):
        url = info.requestUrl().toString().lower()
        if any(d in url for d in self.GOOGLE_API_DOMAINS):
            token = self._get_token('google')
            if token:
                info.setHttpHeader(b"Authorization",
                                   f"Bearer {token}".encode())
        elif any(d in url for d in self.MICROSOFT_API_DOMAINS):
            token = self._get_token('microsoft')
            if token:
                info.setHttpHeader(b"Authorization",
                                   f"Bearer {token}".encode())
