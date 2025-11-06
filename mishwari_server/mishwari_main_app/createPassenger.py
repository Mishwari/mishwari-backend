import random
from rest_framework import serializers
from .models import Passenger,BookingPassenger


def create(self, validated_data):
    print('create data: ', validated_data)
    initial_passengers_data = self.initial_data.get('passengers', [])
    print('initial_passengers_data: ', initial_passengers_data)
    user = self.context['request'].user  # Ensure this matches the user making the request

    # Ensure 'user' is not in validated_data
    validated_data.pop('user', None)

    # Remove passengers from validated_data
    validated_data.pop('passengers', [])

    # Create the booking instance without passengers
    booking = Booking.objects.create(**validated_data, user=user)

    # Retrieve available seats for the trip
    available_seats = list(Seat.objects.filter(trip=booking.trip, is_booked=False))
    random.shuffle(available_seats)  # Randomize the list of available seats

    # Assign each passenger a random seat
    for passenger_info in initial_passengers_data:
        passenger_id = passenger_info.get('id')
        print("\npassenger_id:", passenger_id)
        if passenger_id is None:
            print("\nCreating new passenger:", passenger_info)
            passenger = Passenger.objects.create(user=user, **passenger_info)
        else:
            print("\nUpdating existing passenger:", passenger_info)
            # Remove 'id' from the dictionary to avoid conflicts
            passenger_info.pop('id', None)
            passenger, _ = Passenger.objects.update_or_create(id=passenger_id, defaults={**passenger_info, 'user': user})

        if available_seats:
            selected_seat = available_seats.pop()
            selected_seat.is_booked = True
            selected_seat.save()
            BookingPassenger.objects.create(booking=booking, passenger=passenger, seat=selected_seat)
        else:
            raise serializers.ValidationError("Not enough seats available.")

    return booking



from rest_framework.exceptions import ValidationError
from .payment_gateway import PaymentGateway
from wallet.models import Wallet, Transaction

class WalletPaymentGateway(PaymentGateway):
    def initiate_payment(self, booking_details):
        user = booking_details['user']
        trip = booking_details['trip']
        amount = booking_details['amount']
        wallet = Wallet.objects.get(user=user)

        print("Wallet payment initiated")
        print("Amount:", amount)
        print("Wallet balance:", wallet.balance)

        if wallet.balance < amount:
            print("Insufficient wallet balance")
            raise ValidationError('Insufficient wallet balance')

        with transaction.atomic():
            wallet.balance -= amount
            wallet.save()

            # Create a transaction record
            Transaction.objects.create(
                wallet=wallet,
                transaction_type='debit',
                amount=amount,
                description=f'Payment for trip {trip.id}'
            )

        return "Wallet payment successful"

    def handle_webhook(self, request):
        # Logic to handle wallet payment webhook
        pass
