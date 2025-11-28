from rest_framework.permissions import BasePermission

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
