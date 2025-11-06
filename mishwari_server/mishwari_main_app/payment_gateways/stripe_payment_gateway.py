import stripe
from django.http import JsonResponse
from django.conf import settings
from ..models import Booking


# from .payment_gateway import PaymentGateway


class StripePaymentGateway:

    @staticmethod
    def initiate_payment( booking_details):
        stripe.api_key = settings.STRIPE_SECRET_KEY # random token by Tabnine

        session = stripe.checkout.Session.create(
            payment_method_types=['card'],
            line_items=[
                {
                    'price_data': {
                        'currency': 'sar',
                        'unit_amount': int(booking_details['amount'] * 100), 
                        # multiply by no of passengers or add total_price field on booking
                        'product_data': {
                            'name': f'Booking {booking_details["booking_id"]}',
                        },
                    },
                    'quantity': 1,
                }
            ],
            mode='payment',
            
            metadata={"booking_id":booking_details["booking_id"]},
            success_url='http://localhost:3000/checkout/success?session_id={CHECKOUT_SESSION_ID}',
            cancel_url='http://localhost:3000/checkout/cancel',
            customer_email='husni.abad@gmail.com',
            
        )

        return session.url
    

    # def handle_webhook(self, request):
    #     payload = request.body
    #     sig_header = request.META['HTTP_STRIPE_SIGNATURE']
    #     endpoint_secret = settings.STRIPE_WEBHOOK_SECRET

    #     try:
    #         event = stripe.Webhook.construct_event(
    #             payload, sig_header, endpoint_secret
    #         )
    #     except ValueError as e:
    #         # Invalid payload
    #         return JsonResponse({'error':str(e)},status=400)
    #     except stripe.error.SignatureVerificationError as e:
    #         # Invalid signature
    #         return JsonResponse({'error':str(e)},status=400)
        
    #     if event['type'] == 'checkout.session.completed':
    #         session = event['data']['object']
    #         booking_id = session['metadata']['booking_id']
    #         # self.

    #     return {'booking_id':booking_id, 'status':'success'}
    
    # def update_booking_status(self, booking_id, status):
    #     try:
    #         booking = Booking.objects.get(id=booking_id)
    #         booking.is_paid = status # boolean
    #         booking.status = 'active' if status else 'pending'
    #         booking.save()

    #     except Booking.DoesNotExist:
    #         pass

        

        #     booking = get_object_or_404(Booking, id=booking_id)
        #     booking.is_paid = True
        #     booking.status = 'active'
        #     booking.save()
            
        # return JsonResponse({'status':'success'}, status=200)
