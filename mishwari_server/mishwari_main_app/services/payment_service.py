"""Payment service - orchestrates payment gateways"""

from ..payment_gateways.stripe_payment_gateway import StripePaymentGateway
from ..payment_gateways.wallet_payment_gateway import WalletPaymentGateway
from ..utils.constants import PaymentMethod


class PaymentService:
    """Service for payment operations"""
    
    def process_payment(self, booking, payment_method):
        """Process payment for booking"""
        if payment_method == PaymentMethod.STRIPE:
            gateway = StripePaymentGateway()
            payment_url = gateway.initiate_payment({
                'user': booking.user,
                'trip': booking.trip,
                'amount': booking.total_fare,
                'booking_id': booking.id
            })
            return {'success': True, 'payment_url': payment_url, 'requires_redirect': True}
        
        elif payment_method == PaymentMethod.WALLET:
            gateway = WalletPaymentGateway()
            gateway.initiate_payment({
                'user': booking.user,
                'trip': booking.trip,
                'amount': booking.total_fare,
                'booking_id': booking.id
            })
            booking.is_paid = True
            booking.save()
            return {'success': True, 'requires_redirect': False}
        
        elif payment_method == PaymentMethod.CASH:
            return {'success': True, 'requires_redirect': False}
        
        else:
            raise ValueError(f'Unsupported payment method: {payment_method}')
