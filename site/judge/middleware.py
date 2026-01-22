import base64
import secrets
import hmac
import re
import struct
import secrets
from urllib.parse import quote

from django.conf import settings
from django.contrib.auth.models import User
from django.http import HttpResponse, HttpResponseRedirect
from django.urls import Resolver404, resolve, reverse
from django.utils.encoding import force_bytes
from requests.exceptions import HTTPError

from django.utils.deprecation import MiddlewareMixin
from django.contrib.auth import login
from django.contrib.auth import logout
from django.shortcuts import redirect
from urllib.parse import urlencode
import requests

from keycloak import KeycloakOpenIDConnection
from datetime import datetime, timedelta
from django.contrib import messages
import jwt
import logging

class ShortCircuitMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        try:
            callback, args, kwargs = resolve(request.path_info, getattr(request, 'urlconf', None))
        except Resolver404:
            callback, args, kwargs = None, None, None

        if getattr(callback, 'short_circuit_middleware', False):
            return callback(request, *args, **kwargs)
        return self.get_response(request)


class DMOJLoginMiddleware(object):
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.user.is_authenticated:
            profile = request.profile = request.user.profile
            logout_path = reverse('home')
            login_2fa_path = reverse('login_2fa')
            webauthn_path = reverse('webauthn_assert')
            change_password_path = reverse('password_change')
            change_password_done_path = reverse('password_change_done')
            has_2fa = profile.is_totp_enabled or profile.is_webauthn_enabled
            if (has_2fa and not request.session.get('2fa_passed', False) and
                    request.path not in (login_2fa_path, logout_path, webauthn_path) and
                    not request.path.startswith(settings.STATIC_URL)):
                return HttpResponseRedirect(login_2fa_path + '?next=' + quote(request.get_full_path()))
            elif (request.session.get('password_pwned', False) and
                    request.path not in (change_password_path, change_password_done_path,
                                         login_2fa_path, logout_path) and
                    not request.path.startswith(settings.STATIC_URL)):
                return HttpResponseRedirect(change_password_path + '?next=' + quote(request.get_full_path()))
        else:
            request.profile = None
        return self.get_response(request)


class DMOJImpersonationMiddleware(object):
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.user.is_impersonate:
            request.no_profile_update = True
            request.profile = request.user.profile
        return self.get_response(request)


class ContestMiddleware(object):
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        profile = request.profile
        if profile:
            profile.update_contest()
            request.participation = profile.current_contest
            request.in_contest = request.participation is not None
        else:
            request.in_contest = False
            request.participation = None
        return self.get_response(request)


class APIMiddleware(object):
    header_pattern = re.compile('^Bearer ([a-zA-Z0-9_-]{48})$')

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        full_token = request.META.get('HTTP_AUTHORIZATION', '')
        if not full_token:
            return self.get_response(request)

        token = self.header_pattern.match(full_token)
        if not token:
            return HttpResponse('Invalid authorization header', status=400)
        if request.path.startswith(reverse('admin:index')):
            return HttpResponse('Admin inaccessible', status=403)

        try:
            id, secret = struct.unpack('>I32s', base64.urlsafe_b64decode(token.group(1)))
            request.user = User.objects.get(id=id)

            # User hasn't generated a token
            if not request.user.profile.api_token:
                raise HTTPError()

            # Token comparison
            digest = hmac.new(force_bytes(settings.SECRET_KEY), msg=secret, digestmod='sha256').hexdigest()
            if not hmac.compare_digest(digest, request.user.profile.api_token):
                raise HTTPError()

            request._cached_user = request.user
            request.csrf_processing_done = True
            request.session['2fa_passed'] = True
        except (User.DoesNotExist, HTTPError):
            response = HttpResponse('Invalid token')
            response['WWW-Authenticate'] = 'Bearer realm="API"'
            response.status_code = 401
            return response
        return self.get_response(request)


class KeycloakSSOMiddleware(MiddlewareMixin):
    """
    Keycloak SSO 세션을 유지 및 확인하는 미들웨어
    """

    def process_request(self, request):
        """ 
        사용자가 인증되었는지 확인하고, 세션이 만료되었으면 로그아웃 또는 갱신
        최고 관리자 및 스태프 이외의 사용자는 키클락 세션이 없는 경우 자동 로그아웃 됨 - 일반 로그인 불가능
        최고 관리자 및 스태프는 확인하지 않음
        """
        if request.user.is_authenticated and not (request.user.is_superuser or request.user.is_staff):
            self.check_sso_session(request)

    def check_sso_session(self, request):
        """ Keycloak Access Token이 유효한지 확인 후 만료되면 갱신 또는 로그아웃"""
        access_token = request.session.get("keycloak_access_token")
        refresh_token = request.session.get("keycloak_refresh_token")

        if not access_token:
            self.logout_user(request)
            return

        # Refresh Token 유효성 검사
        if not self.is_refresh_token_valid_api(refresh_token):
            self.logout_user(request)
            return

        try:
            # 요청마다 새로운 Keycloak Connection 객체 생성
            server_url = settings.SOCIAL_AUTH_KEYCLOAK_DOMAIN
            if not server_url.startswith("http"):
                server_url = "https://" + server_url

            request.keycloak_connection = KeycloakOpenIDConnection(
                server_url=server_url,
                realm_name=settings.SOCIAL_AUTH_KEYCLOAK_REALM,
                client_id=settings.SOCIAL_AUTH_KEYCLOAK_KEY,
                client_secret_key=settings.SOCIAL_AUTH_KEYCLOAK_SECRET,
                token={
                    "access_token": access_token,
                    "refresh_token": refresh_token,
                    "expires_in": 300  
                },
            )

            # Access Token 디코딩 (서명 검증 없이 확인)
            decoded_token = jwt.decode(access_token, options={"verify_signature": False})
            exp_time = decoded_token.get("exp", 0)

            utc_now = datetime.utcnow()
            kst_now = utc_now + timedelta(hours=9)
            current_time = int(kst_now.timestamp())

            # Access Token 만료 - refresh_access_token을 통해 재발급
            if current_time >= exp_time:

                # Access Token 갱신 시도
                new_access_token = self.refresh_access_token(request)

                if new_access_token:
                    # 세션 업데이트 (각 사용자의 새로운 토큰 저장)
                    request.session["keycloak_access_token"] = new_access_token
                    request.session["keycloak_refresh_token"] = refresh_token
                else:
                    self.logout_user(request)

        except jwt.DecodeError as e: # WT DecodeError 발생 - 토큰이 잘못되었거나 손상됨
            self.logout_user(request)
        except Exception as e: # 예상치 못한 오류 발생
            self.logout_user(request)

    def is_refresh_token_valid_api(self, refresh_token):
        """ Keycloak API를 사용하여 Refresh Token이 유효한지 확인 """
        introspection_url = f"https://{settings.SOCIAL_AUTH_KEYCLOAK_DOMAIN}/realms/{settings.SOCIAL_AUTH_KEYCLOAK_REALM}/protocol/openid-connect/token/introspect"
        data = {
            "token": refresh_token,
            "client_id": settings.SOCIAL_AUTH_KEYCLOAK_KEY,
            "client_secret": settings.SOCIAL_AUTH_KEYCLOAK_SECRET
        }
        headers = {
            "Content-Type": "application/x-www-form-urlencoded"
        }

        try:
            response = requests.post(introspection_url, data=data, headers=headers, verify=False)
            response_data = response.json()

            return response_data.get("active", False)  # active가 True면 유효
        except Exception as e:
            return False

    def refresh_access_token(self, request):
        """ Access Token을 갱신하는 함수 """
        try:
            request.keycloak_connection.refresh_token()
            new_access_token = request.keycloak_connection.token.get("access_token")

            if new_access_token:
                return new_access_token
            else:
                return None
        except Exception as e:
            return None

    def logout_user(self, request):
        """ 사용자를 로그아웃하고 세션을 삭제하는 함수 """
        messages.error(request, "세션이 만료되어 자동 로그아웃되었습니다.")  # 🔹 메시지 저장
        logout(request)
        request.session.flush()

class SimpleCSPMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response
        self.csp_value = getattr(
            settings,
            'CSP_HEADER_VALUE',
            "default-src 'self'; "
            "script-src 'self' 'nonce-{nonce}' 'strict-dynamic' https: cdnjs.cloudflare.com ajax.googleapis.com; "
            "style-src 'self' 'unsafe-inline' cdnjs.cloudflare.com maxcdn.bootstrapcdn.com; "
            "font-src 'self' maxcdn.bootstrapcdn.com cdnjs.cloudflare.com; "
            "img-src 'self' data: www.gravatar.com gravatar.com; "
            "frame-ancestors 'none'; "
            "object-src 'none'; "
            "require-trusted-types-for 'script'; "
            "trusted-types *",
        )
        self.csp_report_only_value = getattr(settings, 'CSP_REPORT_ONLY_VALUE', '')

    def __call__(self, request):
        request.csp_nonce = secrets.token_urlsafe(16)
        response = self.get_response(request)
        if '{nonce}' in self.csp_value:
            csp_value = self.csp_value.format(nonce=request.csp_nonce)
        else:
            csp_value = self.csp_value
        response['Content-Security-Policy'] = csp_value
        if self.csp_report_only_value:
            if '{nonce}' in self.csp_report_only_value:
                csp_ro_value = self.csp_report_only_value.format(nonce=request.csp_nonce)
            else:
                csp_ro_value = self.csp_report_only_value
            response['Content-Security-Policy-Report-Only'] = csp_ro_value
        # Inject nonce into script tags (inline and external) for HTML responses.
        content_type = response.get('Content-Type', '')
        if (not response.streaming and 'text/html' in content_type and hasattr(response, 'content')):
            try:
                content = response.content
                if isinstance(content, bytes):
                    pattern = re.compile(br'<script(?![^>]*\bnonce=)([^>]*)>')
                    replacement = br'<script nonce="' + request.csp_nonce.encode() + br'"\1>'
                    new_content = pattern.sub(replacement, content)
                    if new_content != content:
                        response.content = new_content
                        if response.has_header('Content-Length'):
                            response['Content-Length'] = str(len(response.content))
                else:
                    pattern = re.compile(r'<script(?![^>]*\bnonce=)([^>]*)>')
                    replacement = r'<script nonce="' + request.csp_nonce + r'"\1>'
                    new_content = pattern.sub(replacement, content)
                    if new_content != content:
                        response.content = new_content
                        if response.has_header('Content-Length'):
                            response['Content-Length'] = str(len(response.content))
            except Exception:
                # If anything goes wrong, leave the response unchanged.
                pass
        return response
    
class NoCacheMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        
        # 민감한 경로에 대해 캐시 방지 헤더 추가
        sensitive_paths = [
            '/accounts/login/',
            '/accounts/register/',
            '/accounts/password/',
            '/term/',
            '/admin/',
            '/profile/',
            '/manifest.json',
        ]
        
        for path in sensitive_paths:
            if request.path.startswith(path) or request.path == path:
                from django.utils.cache import add_never_cache_headers
                add_never_cache_headers(response)
                response['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
                response['Pragma'] = 'no-cache'
                response['Expires'] = '0'
                break
                
        return response
