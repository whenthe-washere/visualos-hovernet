import os
import json
import secrets
import hashlib
import base64
import time
import webbrowser
from urllib.parse import urlencode, parse_qs, urlparse
from http.server import HTTPServer, BaseHTTPRequestHandler
import threading
import requests
from pathlib import Path


class OAuthCallbackHandler(BaseHTTPRequestHandler):
    """HTTP handler for OAuth redirect callback with per-instance state validation."""

    def __init__(self, expected_state, *args, **kwargs):
        self.expected_state = expected_state
        super().__init__(*args, **kwargs)

    def do_GET(self):
        parsed_url = urlparse(self.path)
        query_params = parse_qs(parsed_url.query)
        received_state = query_params.get('state', [None])[0]

        if not received_state or received_state != self.expected_state:
            self.server.auth_error = "Invalid state parameter (possible CSRF attack)."
            status = 400
            response = "<html><body><h1>Security Error</h1><p>Invalid state token.</p></body></html>"
        elif 'code' in query_params:
            self.server.auth_code = query_params['code'][0]
            status = 200
            response = "<html><body><h1>Authorization successful!</h1><p>You can close this window.</p></body></html>"
        elif 'error' in query_params:
            self.server.auth_error = query_params.get('error_description', ['Unknown error'])[0]
            status = 400
            response = f"<html><body><h1>Authorization failed</h1><p>{self.server.auth_error}</p></body></html>"
        else:
            self.server.auth_error = "No authorization code received."
            status = 400
            response = "<html><body><h1>Authorization failed</h1></body></html>"

        self.send_response(status)
        self.send_header('Content-type', 'text/html')
        self.end_headers()
        self.wfile.write(response.encode())

    def log_message(self, format, *args):
        pass


class OAuthManager:
    """Handles PKCE-secured OAuth2 flows for Google and Microsoft."""

    GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
    GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
    GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v1/userinfo"

    MICROSOFT_AUTH_URL = "https://login.microsoftonline.com/common/oauth2/v2.0/authorize"
    MICROSOFT_TOKEN_URL = "https://login.microsoftonline.com/common/oauth2/v2.0/token"
    MICROSOFT_USERINFO_URL = "https://graph.microsoft.com/v1.0/me"

    def __init__(self):
        self.config_dir = Path(os.path.expanduser('~')) / '.hovernet' / 'auth'
        self.config_dir.mkdir(parents=True, exist_ok=True)
        self.google_token_file = self.config_dir / 'google_token.json'
        self.microsoft_token_file = self.config_dir / 'microsoft_token.json'

    def _generate_pkce(self):
        code_verifier = base64.urlsafe_b64encode(secrets.token_bytes(32)).decode('utf-8').rstrip('=')
        code_challenge = base64.urlsafe_b64encode(
            hashlib.sha256(code_verifier.encode()).digest()
        ).decode('utf-8').rstrip('=')
        return code_verifier, code_challenge

    def _save_token(self, provider, token_data):
        token_file = self.google_token_file if provider == 'google' else self.microsoft_token_file
        with open(token_file, 'w') as f:
            json.dump(token_data, f)

    def _load_token(self, provider):
        token_file = self.google_token_file if provider == 'google' else self.microsoft_token_file
        if token_file.exists():
            try:
                with open(token_file, 'r') as f:
                    return json.load(f)
            except Exception:
                return None
        return None

    def _refresh_token(self, provider, refresh_token, client_id, client_secret=None):
        token_url = self.GOOGLE_TOKEN_URL if provider == 'google' else self.MICROSOFT_TOKEN_URL
        data = {
            'client_id': client_id,
            'refresh_token': refresh_token,
            'grant_type': 'refresh_token'
        }
        if client_secret:
            data['client_secret'] = client_secret

        try:
            response = requests.post(token_url, data=data, timeout=10)
            response.raise_for_status()
            new_token = response.json()
            new_token['refresh_token'] = refresh_token
            new_token['client_id'] = client_id
            if client_secret:
                new_token['client_secret'] = client_secret
            self._save_token(provider, new_token)
            return new_token
        except Exception:
            return None

    def authenticate_google(self, client_id, client_secret=None, redirect_uri=None,
                            scope=None, process_events=None):
        code_verifier, code_challenge = self._generate_pkce()
        state = secrets.token_urlsafe(32)

        if redirect_uri:
            effective_redirect = redirect_uri
            parsed = urlparse(redirect_uri)
            bind_port = parsed.port if parsed.port else 80
            server = HTTPServer(('127.0.0.1', bind_port), None)
        else:
            server = HTTPServer(('127.0.0.1', 8888), None)
            effective_redirect = "http://localhost:8888/callback"

        effective_scope = scope or 'openid email profile https://www.googleapis.com/auth/drive.file'
        params = {
            'client_id': client_id,
            'redirect_uri': effective_redirect,
            'response_type': 'code',
            'scope': effective_scope,
            'code_challenge': code_challenge,
            'code_challenge_method': 'S256',
            'state': state,
            'access_type': 'offline',
            'prompt': 'consent'
        }
        auth_url = f"{self.GOOGLE_AUTH_URL}?{urlencode(params)}"
        return self._run_oauth_flow(server, auth_url, state, client_id, client_secret,
                                    code_verifier, effective_redirect, 'google',
                                    process_events=process_events)

    def authenticate_microsoft(self, client_id, client_secret=None, redirect_uri=None,
                               scope=None, process_events=None):
        code_verifier, code_challenge = self._generate_pkce()
        state = secrets.token_urlsafe(32)

        if redirect_uri:
            effective_redirect = redirect_uri
            parsed = urlparse(redirect_uri)
            bind_port = parsed.port if parsed.port else 80
            server = HTTPServer(('127.0.0.1', bind_port), None)
        else:
            server = HTTPServer(('127.0.0.1', 8888), None)
            effective_redirect = "http://localhost:8888/callback"

        effective_scope = scope or 'openid email profile offline_access User.Read Files.ReadWrite Files.ReadWrite.AppFolder'
        params = {
            'client_id': client_id,
            'redirect_uri': effective_redirect,
            'response_type': 'code',
            'scope': effective_scope,
            'code_challenge': code_challenge,
            'code_challenge_method': 'S256',
            'state': state,
        }
        auth_url = f"{self.MICROSOFT_AUTH_URL}?{urlencode(params)}"
        return self._run_oauth_flow(server, auth_url, state, client_id, client_secret,
                                    code_verifier, effective_redirect, 'microsoft')

    def _run_oauth_flow(self, server, auth_url, state, client_id, client_secret,
                        code_verifier, redirect_uri, provider, process_events=None):
        server.auth_code = None
        server.auth_error = None

        def handler_factory(*args, **kwargs):
            return OAuthCallbackHandler(state, *args, **kwargs)

        server.RequestHandlerClass = handler_factory
        server_thread = threading.Thread(target=server.handle_request, daemon=True)
        server_thread.start()

        try:
            webbrowser.open(auth_url)
            deadline = time.time() + 60
            while server_thread.is_alive() and time.time() < deadline:
                server_thread.join(timeout=0.05)
                if process_events:
                    process_events()
                if getattr(server, 'auth_error', None):
                    server.server_close()
                    return {'error': server.auth_error}

            if getattr(server, 'auth_error', None):
                return {'error': server.auth_error}

            auth_code = getattr(server, 'auth_code', None)
            if not auth_code:
                return {'error': 'Authorization timed out or code not received'}

            return self._exchange_code_for_token(
                provider, auth_code, client_id, client_secret,
                code_verifier, redirect_uri
            )
        finally:
            server.server_close()

    def _exchange_code_for_token(self, provider, code, client_id, client_secret,
                                 code_verifier, redirect_uri):
        token_url = self.GOOGLE_TOKEN_URL if provider == 'google' else self.MICROSOFT_TOKEN_URL
        data = {
            'code': code,
            'client_id': client_id,
            'redirect_uri': redirect_uri,
            'grant_type': 'authorization_code',
            'code_verifier': code_verifier
        }
        if client_secret:
            data['client_secret'] = client_secret

        try:
            response = requests.post(token_url, data=data, timeout=10)
            response.raise_for_status()
            token_data = response.json()
            token_data['client_id'] = client_id
            if client_secret:
                token_data['client_secret'] = client_secret
            self._save_token(provider, token_data)
            return token_data
        except requests.HTTPError as e:
            try:
                return {'error': response.json().get('error_description') or response.text}
            except Exception:
                return {'error': str(e)}
        except Exception as e:
            return {'error': str(e)}

    def get_user_info(self, provider):
        token_data = self._load_token(provider)
        if not token_data:
            return None

        user_url = self.GOOGLE_USERINFO_URL if provider == 'google' else self.MICROSOFT_USERINFO_URL
        headers = {'Authorization': f"Bearer {token_data['access_token']}"}

        try:
            response = requests.get(user_url, headers=headers, timeout=10)
            if response.status_code == 401 and token_data.get('refresh_token'):
                token_data = self._refresh_token(
                    provider,
                    token_data['refresh_token'],
                    token_data.get('client_id'),
                    token_data.get('client_secret')
                )
                if not token_data:
                    return None
                headers = {'Authorization': f"Bearer {token_data['access_token']}"}
                response = requests.get(user_url, headers=headers, timeout=10)
            response.raise_for_status()
            return response.json()
        except Exception:
            return None

    def get_google_user_info(self):
        return self.get_user_info('google')

    def get_microsoft_user_info(self):
        return self.get_user_info('microsoft')

    def is_google_authenticated(self):
        return self._load_token('google') is not None

    def is_microsoft_authenticated(self):
        return self._load_token('microsoft') is not None

    def logout_google(self):
        if self.google_token_file.exists():
            self.google_token_file.unlink()

    def logout_microsoft(self):
        if self.microsoft_token_file.exists():
            self.microsoft_token_file.unlink()

    def upload_to_google_drive(self, file_path, filename, folder_id=None):
        token_data = self._load_token('google')
        if not token_data:
            return {'error': 'Not authenticated with Google'}
        access_token = token_data.get('access_token')
        try:
            headers = {'Authorization': f'Bearer {access_token}'}
            with open(file_path, 'rb') as f:
                resp = requests.post(
                    'https://www.googleapis.com/upload/drive/v3/files?uploadType=media',
                    headers=headers, data=f, timeout=120
                )
            resp.raise_for_status()
            file_id = resp.json().get('id')
            if folder_id:
                patch = requests.patch(
                    f'https://www.googleapis.com/drive/v3/files/{file_id}',
                    headers=headers, params={'addParents': folder_id, 'removeParents': 'root'},
                    timeout=120
                )
                patch.raise_for_status()
            return {'success': True, 'file_id': file_id, 'filename': filename}
        except Exception as e:
            return {'error': str(e)}

    def list_google_drive_folders(self, parent_id=None):
        token_data = self._load_token('google')
        if not token_data:
            return {'error': 'Not authenticated with Google'}
        access_token = token_data.get('access_token')
        try:
            parent = 'root' if parent_id is None else parent_id
            q = f"'{parent}' in parents and mimeType='application/vnd.google-apps.folder' and trashed=false"
            headers = {'Authorization': f'Bearer {access_token}'}
            params = {'q': q, 'fields': 'files(id,name)', 'pageSize': 300}
            resp = requests.get('https://www.googleapis.com/drive/v3/files',
                                headers=headers, params=params, timeout=30)
            resp.raise_for_status()
            files = resp.json().get('files', [])
            return {'success': True, 'folders': [{'id': f['id'], 'name': f['name']} for f in files]}
        except Exception as e:
            return {'error': str(e)}

    def upload_to_onedrive(self, file_path, filename, folder_id=None):
        token_data = self._load_token('microsoft')
        if not token_data:
            return {'error': 'Not authenticated with Microsoft'}
        access_token = token_data.get('access_token')
        try:
            from urllib.parse import quote
            safe_name = quote(filename)
            headers = {'Authorization': f'Bearer {access_token}',
                       'Content-Type': 'application/octet-stream'}
            if folder_id:
                url = f'https://graph.microsoft.com/v1.0/me/drive/items/{folder_id}:/{safe_name}:/content'
            else:
                url = f'https://graph.microsoft.com/v1.0/me/drive/root:/{safe_name}:/content'
            with open(file_path, 'rb') as f:
                resp = requests.put(url, headers=headers, data=f, timeout=120)
            resp.raise_for_status()
            return {'success': True, 'filename': filename}
        except Exception as e:
            return {'error': str(e)}

    def list_onedrive_folders(self, parent_id=None):
        token_data = self._load_token('microsoft')
        if not token_data:
            return {'error': 'Not authenticated with Microsoft'}
        access_token = token_data.get('access_token')
        try:
            if parent_id is None:
                url = 'https://graph.microsoft.com/v1.0/me/drive/root/children'
            else:
                url = f'https://graph.microsoft.com/v1.0/me/drive/items/{parent_id}/children'
            headers = {'Authorization': f'Bearer {access_token}'}
            params = {'$filter': 'folder ne null', '$select': 'id,name', '$top': 200}
            resp = requests.get(url, headers=headers, params=params, timeout=30)
            resp.raise_for_status()
            items = resp.json().get('value', [])
            return {'success': True, 'folders': [{'id': it['id'], 'name': it['name']} for it in items]}
        except Exception as e:
            return {'error': str(e)}
