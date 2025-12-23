import os
import requests
from typing import Dict

class GoogleIdentityProxyService:
    """Proxy service for Google Identity Toolkit REST API"""
    
    FIREBASE_API_KEY = os.getenv('FIREBASE_WEB_API_KEY')
    VERIFY_CODE_URL = f"https://identitytoolkit.googleapis.com/v1/accounts:sendVerificationCode?key={FIREBASE_API_KEY}"
    SIGN_IN_URL = f"https://identitytoolkit.googleapis.com/v1/accounts:signInWithPhoneNumber?key={FIREBASE_API_KEY}"
    
    @classmethod
    def send_otp(cls, phone_number: str, recaptcha_token: str) -> Dict:
        """Send OTP via Google Identity Toolkit"""
        if not phone_number.startswith('+'):
            phone_number = '+' + phone_number
            
        payload = {
            "phoneNumber": phone_number,
            "recaptchaToken": recaptcha_token
        }
        
        try:
            response = requests.post(cls.VERIFY_CODE_URL, json=payload, timeout=10)
            response.raise_for_status()
            data = response.json()
            return {
                'success': True,
                'session_info': data.get('sessionInfo')
            }
        except requests.exceptions.RequestException as e:
            error_msg = str(e)
            if hasattr(e, 'response') and e.response is not None:
                try:
                    error_data = e.response.json()
                    error_msg = error_data.get('error', {}).get('message', error_msg)
                except:
                    pass
            return {
                'success': False,
                'error': error_msg,
                'message': 'Failed to send OTP via Firebase'
            }
    
    @classmethod
    def verify_otp(cls, session_info: str, code: str) -> Dict:
        """Verify OTP via Google Identity Toolkit"""
        payload = {
            "sessionInfo": session_info,
            "code": code
        }
        
        try:
            response = requests.post(cls.SIGN_IN_URL, json=payload, timeout=10)
            response.raise_for_status()
            data = response.json()
            
            phone_number = data.get('phoneNumber', '')
            if phone_number.startswith('+'):
                phone_number = phone_number[1:]
                
            return {
                'success': True,
                'phone_number': phone_number,
                'id_token': data.get('idToken'),
                'refresh_token': data.get('refreshToken')
            }
        except requests.exceptions.RequestException as e:
            error_msg = str(e)
            if hasattr(e, 'response') and e.response is not None:
                try:
                    error_data = e.response.json()
                    error_msg = error_data.get('error', {}).get('message', error_msg)
                except:
                    pass
            return {
                'success': False,
                'error': error_msg,
                'message': 'Invalid or expired OTP'
            }
