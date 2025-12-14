"""Tests for auth service"""

from django.test import TestCase
from django.core.cache import cache
from ..services.auth_service import AuthService
from ..utils.cache_keys import CacheKeys


class AuthServiceTest(TestCase):
    def setUp(self):
        self.service = AuthService()
        self.mobile = '1234567890'
        cache.clear()
    
    def test_request_otp_success(self):
        result = self.service.request_otp(self.mobile)
        self.assertTrue('otp_code' in result or result.get('success'))
    
    def test_verify_otp_invalid(self):
        result = self.service.verify_otp(self.mobile, '000000')
        self.assertFalse(result['success'])
        self.assertIn('error', result)
    
    def test_verify_otp_success(self):
        cache.set(CacheKeys.otp(self.mobile), '123456', timeout=60)
        result = self.service.verify_otp(self.mobile, '123456')
        self.assertTrue(result['success'])
        self.assertIn('user', result)
