from django.db import transaction

from rest_framework.exceptions import ValidationError

from .payment_gateway import PaymentGateway
from wallet.models import Wallet, WalletTransaction



class WalletPaymentGateway(PaymentGateway):
    def initiate_payment(self,booking_details):
        user = booking_details['user']
        trip = booking_details['trip']
        amount = booking_details['amount']  # Ensure the trip price is properly set
        # payment_method = booking_details['payment_method']
        wallet = Wallet.objects.get(user=user)

        if wallet.balance <= amount:
            raise ValidationError('insufficient wallet balance')
        
        with transaction.atomic():
            wallet.balance -= amount
            wallet.save()
            # booking_details.status = 'active' # if booking.data

            WalletTransaction.objects.create(
                amount=amount,
                wallet=wallet,
                transaction_type='debit',
            )


        return "wallet_payment_success"

    def handle_webhook(self, request):
        # Logic to handle wallet payment webhook
        pass