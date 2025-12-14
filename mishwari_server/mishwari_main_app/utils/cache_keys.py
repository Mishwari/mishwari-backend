"""Centralized cache key patterns"""

class CacheKeys:
    """Cache key generators for consistent naming"""
    
    @staticmethod
    def otp(mobile_number):
        return f'otp:{mobile_number}'
    
    @staticmethod
    def route_session(user_id):
        return f'routes_{user_id}'
    
    @staticmethod
    def route_start_city(user_id):
        return f'start_city_{user_id}'
    
    @staticmethod
    def route_end_city(user_id):
        return f'end_city_{user_id}'
    
    @staticmethod
    def route_close_cities(user_id):
        return f'close_cities_{user_id}'
    
    @staticmethod
    def route_new_route(user_id):
        return f'new_route_{user_id}'
    
    @staticmethod
    def route_summary(user_id):
        return f'route_summary_{user_id}'
    
    @staticmethod
    def transaction_token(user_id):
        return f'transaction:token:{user_id}'
    
    @staticmethod
    def otp_attempts(mobile_number):
        return f'otp:attempts:{mobile_number}'
