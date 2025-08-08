from cryptography.fernet import Fernet, InvalidToken
from base64 import urlsafe_b64encode
from django.conf import settings
import hashlib
from django.core.exceptions import ValidationError


def generate_key_from_password(password):
    """비밀번호로부터 32바이트 키 생성 (보안 강화)"""
    if not password:
        raise ValidationError("암호화 키가 제공되지 않았습니다.")
    
    # 비밀번호 유효성 검사
    if len(password) < 4:
        raise ValidationError("암호화 키는 최소 4자 이상이어야 합니다.")
    
    try:
        # 보안 강화: 암호화 키를 생성할 때 UTF-8 인코딩 명시
        key = hashlib.sha256(password.encode('utf-8')).digest()
        return urlsafe_b64encode(key)
    except Exception as e:
        logger.error(f"키 생성 중 오류 발생: {e}")
        raise ValidationError("암호화 키 생성 중 오류가 발생했습니다.")

def encrypt_text(text, password):
    """문제 내용 암호화 (보안 강화)"""
    if not text:
        return None
    if not password:
        raise ValidationError("암호화 키가 제공되지 않았습니다.")
    
    try:
        key = generate_key_from_password(password)
        f = Fernet(key)
        # 명시적 UTF-8 인코딩으로 안전하게 처리
        encrypted_text = f.encrypt(text.encode('utf-8'))
        return encrypted_text.decode('utf-8')
    except ValidationError:
        raise
    except Exception as e:
        raise ValidationError("암호화 처리 중 오류가 발생했습니다.")

def decrypt_text(encrypted_text, password):
    """문제 내용 복호화 (보안 강화)"""
    if not encrypted_text:
        return None
    if not password:
        raise ValidationError("복호화 키가 제공되지 않았습니다.")
    
    try:
        key = generate_key_from_password(password)
        f = Fernet(key)
        decrypted_text = f.decrypt(encrypted_text.encode('utf-8'))
        return decrypted_text.decode('utf-8')
    except InvalidToken:
        raise ValidationError("잘못된 복호화 키입니다.")
    except ValidationError:
        raise
    except Exception as e:
        raise ValidationError("복호화 처리 중 오류가 발생했습니다.")