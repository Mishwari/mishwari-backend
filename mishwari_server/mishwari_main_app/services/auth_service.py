"""Authentication service - OTP, Firebase, password logic"""

import os
from django.core.cache import cache
from django.utils.crypto import get_random_string
from django.utils import timezone
from django.contrib.auth.models import User
from datetime import timedelta

from ..models import Profile, OTPAttempt, DriverInvitation, Driver
from ..utils.constants import UserRole, BusinessRules
from ..utils.cache_keys import CacheKeys
from ..utils.firebase_auth import verify_firebase_token
from ..utils.twilio_otp import send_otp_via_twilio


class AuthService:
    """Service for authentication operations"""
    
    def request_otp(self, mobile_number):
        """Request OTP with rate limiting"""
        attempt, _ = OTPAttempt.objects.get_or_create(mobile_number=mobile_number)
        
        if attempt.blocked_until and timezone.now() < attempt.blocked_until:
            return {'success': False, 'error': 'Too many requests', 'status_code': 429}
        
        if attempt.attempt_count >= BusinessRules.OTP_MAX_ATTEMPTS:
            attempt.blocked_until = timezone.now() + timedelta(minutes=BusinessRules.OTP_BLOCK_MINUTES)
            attempt.save()
            return {'success': False, 'error': 'Too many requests', 'status_code': 429}
        
        otp_code = get_random_string(length=6, allowed_chars='0123456789')
        cache.set(CacheKeys.otp(mobile_number), otp_code, timeout=BusinessRules.OTP_EXPIRY_SECONDS)
        
        attempt.attempt_count += 1
        attempt.save()
        
        requires_password = self._check_password_required(mobile_number)
        result = send_otp_via_twilio(mobile_number, otp_code)
        
        return {
            'success': result['status'] == 'success',
            'message': result.get('message', 'OTP sent'),
            'otp_code': otp_code if result['status'] != 'success' else None,
            'requires_password': requires_password
        }
    
    def verify_otp(self, mobile_number, otp_code, password=None):
        """Verify OTP and create/login user"""
        cached_otp = cache.get(CacheKeys.otp(mobile_number))
        emergency_code = os.getenv('EMERGENCY_OTP_CODE', None)
        
        if not cached_otp:
            return {'success': False, 'error': 'OTP expired or not found'}
        
        if otp_code != emergency_code and otp_code != cached_otp:
            return {'success': False, 'error': 'Invalid or expired OTP'}
        
        pending_invitation = DriverInvitation.objects.filter(
            mobile_number=mobile_number,
            status='pending',
            expires_at__gt=timezone.now()
        ).first()
        
        user, created = User.objects.get_or_create(
            username=mobile_number,
            defaults={'email': f'{mobile_number}@temp.mishwari.com'}
        )
        
        profile, _ = Profile.objects.get_or_create(
            user=user,
            defaults={
                'mobile_number': mobile_number,
                'role': UserRole.INVITED_DRIVER if pending_invitation else UserRole.PASSENGER
            }
        )
        
        if pending_invitation:
            Driver.objects.get_or_create(
                user=user,
                defaults={
                    'profile': profile,
                    'driver_rating': BusinessRules.DEFAULT_DRIVER_RATING,
                    'operator': pending_invitation.operator
                }
            )
        
        if not created and profile.role == UserRole.OPERATOR_ADMIN and user.has_usable_password():
            if not password:
                return {'success': False, 'error': 'Password required'}
            if not user.check_password(password):
                return {'success': False, 'error': 'Invalid password'}
        
        cache.delete(CacheKeys.otp(mobile_number))
        self._clear_otp_attempts(mobile_number)
        
        return {'success': True, 'user': user}
    
    def verify_firebase_token(self, firebase_token, password=None):
        """Verify Firebase token and create/login user"""
        try:
            token_data = verify_firebase_token(firebase_token)
            mobile_number = token_data['phone_number']
            
            pending_invitation = DriverInvitation.objects.filter(
                mobile_number=mobile_number,
                status='pending',
                expires_at__gt=timezone.now()
            ).first()
            
            user, created = User.objects.get_or_create(
                username=mobile_number,
                defaults={'email': f'{mobile_number}@temp.mishwari.com'}
            )
            
            profile, _ = Profile.objects.get_or_create(
                user=user,
                defaults={
                    'mobile_number': mobile_number,
                    'role': UserRole.INVITED_DRIVER if pending_invitation else UserRole.PASSENGER
                }
            )
            
            if pending_invitation:
                Driver.objects.get_or_create(
                    user=user,
                    defaults={
                        'profile': profile,
                        'driver_rating': BusinessRules.DEFAULT_DRIVER_RATING,
                        'operator': pending_invitation.operator
                    }
                )
            
            if not created and profile.role == UserRole.OPERATOR_ADMIN and user.has_usable_password():
                if not password:
                    return {'success': False, 'error': 'Password required'}
                if not user.check_password(password):
                    return {'success': False, 'error': 'Invalid password'}
            
            self._clear_otp_attempts(mobile_number)
            return {'success': True, 'user': user}
            
        except ValueError as e:
            return {'success': False, 'error': str(e)}
    
    def generate_transaction_token(self, user):
        """Generate short-lived transaction token for sensitive operations"""
        transaction_token = get_random_string(32)
        cache.set(
            CacheKeys.transaction_token(user.id), 
            transaction_token, 
            timeout=BusinessRules.TRANSACTION_TOKEN_EXPIRY_SECONDS
        )
        return transaction_token
    
    def verify_transaction_token(self, user, token):
        """Verify transaction token"""
        cached_token = cache.get(CacheKeys.transaction_token(user.id))
        return token == cached_token
    
    def _check_password_required(self, mobile_number):
        """Check if password is required for login"""
        try:
            user = User.objects.get(username=mobile_number)
            profile = Profile.objects.get(user=user)
            return profile.role == UserRole.OPERATOR_ADMIN and user.has_usable_password()
        except (User.DoesNotExist, Profile.DoesNotExist):
            return False
    
    def _clear_otp_attempts(self, mobile_number):
        """Clear OTP attempts after successful login"""
        try:
            attempt = OTPAttempt.objects.get(mobile_number=mobile_number)
            attempt.attempt_count = 0
            attempt.blocked_until = None
            attempt.save()
        except OTPAttempt.DoesNotExist:
            pass
