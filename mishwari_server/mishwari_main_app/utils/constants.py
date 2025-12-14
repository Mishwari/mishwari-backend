"""Centralized constants and business rules"""

class UserRole:
    PASSENGER = 'passenger'
    STANDALONE_DRIVER = 'standalone_driver'
    INVITED_DRIVER = 'invited_driver'
    OPERATOR_ADMIN = 'operator_admin'
    
    CHOICES = [
        (PASSENGER, 'Passenger'),
        (STANDALONE_DRIVER, 'Standalone Driver'),
        (INVITED_DRIVER, 'Invited Driver'),
        (OPERATOR_ADMIN, 'Operator Admin'),
    ]

class TripStatus:
    DRAFT = 'draft'
    PUBLISHED = 'published'
    ACTIVE = 'active'
    COMPLETED = 'completed'
    CANCELLED = 'cancelled'
    
    CHOICES = [
        (DRAFT, 'Draft'),
        (PUBLISHED, 'Published'),
        (ACTIVE, 'Active'),
        (COMPLETED, 'Completed'),
        (CANCELLED, 'Cancelled'),
    ]

class TripType:
    SCHEDULED = 'scheduled'
    FLEXIBLE = 'flexible'
    
    CHOICES = [
        (SCHEDULED, 'Fixed Schedule'),
        (FLEXIBLE, 'Flexible Window'),
    ]

class BookingStatus:
    CONFIRMED = 'confirmed'
    PENDING = 'pending'
    CANCELLED = 'cancelled'
    COMPLETED = 'completed'
    
    CHOICES = [
        (CONFIRMED, 'Confirmed'),
        (PENDING, 'Pending'),
        (CANCELLED, 'Cancelled'),
        (COMPLETED, 'Completed'),
    ]

class PaymentMethod:
    CASH = 'cash'
    WALLET = 'wallet'
    STRIPE = 'stripe'
    
    CHOICES = [
        (CASH, 'Cash'),
        (WALLET, 'Wallet'),
        (STRIPE, 'Stripe'),
    ]

class BookingSource:
    PLATFORM = 'platform'
    PHYSICAL = 'physical'
    EXTERNAL_API = 'external_api'
    
    CHOICES = [
        (PLATFORM, 'Platform (Web/App)'),
        (PHYSICAL, 'Physical (By Operator)'),
        (EXTERNAL_API, 'External API Partner'),
    ]

class InvitationStatus:
    PENDING = 'pending'
    ACCEPTED = 'accepted'
    EXPIRED = 'expired'
    CANCELLED = 'cancelled'
    
    CHOICES = [
        (PENDING, 'Pending'),
        (ACCEPTED, 'Accepted'),
        (EXPIRED, 'Expired'),
        (CANCELLED, 'Cancelled'),
    ]

class UpgradeStatus:
    PENDING = 'pending'
    APPROVED = 'approved'
    REJECTED = 'rejected'
    
    CHOICES = [
        (PENDING, 'Pending Review'),
        (APPROVED, 'Approved'),
        (REJECTED, 'Rejected'),
    ]

class Gender:
    MALE = 'male'
    FEMALE = 'female'
    
    CHOICES = [
        (MALE, 'male'),
        (FEMALE, 'female'),
    ]

class BusinessRules:
    """Business rules and limits"""
    STANDALONE_DRIVER_BUS_LIMIT = 1
    STANDALONE_DRIVER_TRIP_LIMIT = 2
    OTP_EXPIRY_SECONDS = 60
    OTP_MAX_ATTEMPTS = 3
    OTP_BLOCK_MINUTES = 30
    INVITATION_EXPIRY_DAYS = 7
    TRANSACTION_TOKEN_EXPIRY_SECONDS = 300
    PROXIMITY_KM = 2.0
    DEFAULT_PRICE_PER_KM = 50.00
    DEFAULT_DRIVER_RATING = 5.0
    DEFAULT_OPERATOR_HEALTH_SCORE = 100
    DEFAULT_PAYOUT_HOLD_HOURS = 24
