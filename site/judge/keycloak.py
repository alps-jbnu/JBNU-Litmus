import requests

from django.conf import settings
import json
import jwt
from social_core.exceptions import AuthTokenError
from social_core.exceptions import AuthException 
from django.contrib.sessions.backends.base import SessionBase

def save_keycloak_tokens(backend, user, response, *args, **kwargs):
    """
    Keycloak 로그인 후 Access Token, Refresh Token을 Django 세션에 저장하는 함수
    """
    if backend.name != "keycloak":
        return

    try:
        # Keycloak에서 받은 토큰 데이터
        access_token = response.get("access_token")
        refresh_token = response.get("refresh_token")
        refresh_expires_in = response.get("refresh_expires_in", 86400)  # 기본값 24시간

        if not access_token or not refresh_token:
            raise AuthException(backend, "Keycloak access_token 또는 refresh_token이 없음.")

        # Django 세션에 저장 (DB)
        session: SessionBase = backend.strategy.request.session
        session["keycloak_access_token"] = access_token
        session["keycloak_refresh_token"] = refresh_token
        session.set_expiry(refresh_expires_in)

    except Exception as e:
        raise AuthException(backend, f"Keycloak 토큰 저장 실패: {str(e)}")


def keycloak_logout(refresh_token):
    """ Keycloak에서 Refresh Token을 사용하여 로그아웃 """
    logout_url = f"https://{settings.SOCIAL_AUTH_KEYCLOAK_DOMAIN}/realms/{settings.SOCIAL_AUTH_KEYCLOAK_REALM}/protocol/openid-connect/logout"

    data = {
        "client_id": settings.SOCIAL_AUTH_KEYCLOAK_KEY,
        "client_secret": settings.SOCIAL_AUTH_KEYCLOAK_SECRET,
        "refresh_token": refresh_token
    }
    
    headers = {"Content-Type": "application/x-www-form-urlencoded"}

    try:
        response = requests.post(logout_url, data=data, headers=headers, verify=False)
        if response.status_code == 204:
            return True
        else:
            return False
    except Exception as e:
        return False
