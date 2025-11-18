"""Utility functions for operator management"""
from .models import BusOperator, Driver


def get_operator_for_user(user):
    """
    Get BusOperator for platform trip creators (driver or operator_admin).
    
    Args:
        user: Django User instance
        
    Returns:
        BusOperator instance
        
    Raises:
        ValueError: If user is not a trip creator or operator not found
    """
    profile = user.profile
    
    if profile.role == 'driver':
        try:
            driver = Driver.objects.select_related('operator').get(user=user)
            return driver.operator
        except Driver.DoesNotExist:
            raise ValueError(f"Driver record not found for user {user.username}")
    
    elif profile.role == 'operator_admin':
        # Use platform_user FK for direct lookup
        operator = BusOperator.objects.filter(platform_user=user).first()
        if not operator:
            raise ValueError(f"Operator not found for user {user.username}")
        return operator
    
    raise ValueError(f"User {user.username} is not a trip creator (role: {profile.role})")
