from rest_framework.permissions import BasePermission

class IsPassenger(BasePermission):
    def has_permission(self, request, view):
        return hasattr(request.user, 'profile') and request.user.profile.role == 'passenger'

class IsOperatorOrAdmin(BasePermission):
    def has_permission(self, request, view):
        return hasattr(request.user, 'profile') and request.user.profile.role in ['driver', 'operator_admin', 'operator_staff']

class IsVerifiedOperator(BasePermission):
    def has_permission(self, request, view):
        return (hasattr(request.user, 'profile') and 
                request.user.profile.is_verified and 
                request.user.profile.role in ['driver', 'operator_admin'])
