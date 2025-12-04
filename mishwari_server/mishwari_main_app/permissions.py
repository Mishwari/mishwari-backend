from rest_framework.permissions import BasePermission
from rest_framework.response import Response
from django.core.cache import cache
from functools import wraps

def require_transaction_auth(view_func):
    """Decorator for sensitive operations requiring step-up auth"""
    @wraps(view_func)
    def wrapper(self, request, *args, **kwargs):
        from rest_framework import status as http_status
        
        transaction_token = request.headers.get('X-Transaction-Token')
        
        if not transaction_token:
            return Response({
                'error': 'REQUIRE_AUTH',
                'message': 'This action requires additional authentication'
            }, status=http_status.HTTP_403_FORBIDDEN)
        
        cached_token = cache.get(f'transaction_{request.user.id}')
        if transaction_token != cached_token:
            return Response({'error': 'Invalid or expired transaction token'}, status=http_status.HTTP_403_FORBIDDEN)
        
        # Consume token (one-time use)
        cache.delete(f'transaction_{request.user.id}')
        
        return view_func(self, request, *args, **kwargs)
    return wrapper

class IsPassenger(BasePermission):
    def has_permission(self, request, view):
        return hasattr(request.user, 'profile') and request.user.profile.role == 'passenger'

class IsOperatorOrAdmin(BasePermission):
    def has_permission(self, request, view):
        has_profile = hasattr(request.user, 'profile')
        print(f'[PERMISSION] User: {request.user.username}, Has profile: {has_profile}')
        if has_profile:
            role = request.user.profile.role
            print(f'[PERMISSION] Role: {role}, Allowed: {role in ["driver", "operator_admin", "operator_staff"]}')
            return role in ['driver', 'operator_admin', 'operator_staff']
        return False

class IsVerifiedOperator(BasePermission):
    def has_permission(self, request, view):
        return (hasattr(request.user, 'profile') and 
                request.user.profile.is_verified and 
                request.user.profile.role in ['driver', 'operator_admin'])

class IsAuthenticatedOrPartial(BasePermission):
    """Allow access for authenticated users including those with partial status (no profile yet)"""
    def has_permission(self, request, view):
        return request.user and request.user.is_authenticated
