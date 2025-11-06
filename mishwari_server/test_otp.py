import os
from dotenv import load_dotenv
from twilio.rest import Client

load_dotenv()

# Dynamic: request.data.get('mobile_number')
phone_number = "+201503100429"

# Dynamic: get_random_string(length=4, allowed_chars='0123456789')
otp_code = "1234"

# Dynamic: os.getenv('TWILIO_ACCOUNT_SID')
account_sid = os.getenv('TWILIO_ACCOUNT_SID')

# Dynamic: os.getenv('TWILIO_AUTH_TOKEN')
auth_token = os.getenv('TWILIO_AUTH_TOKEN')

# Dynamic: os.getenv('TWILIO_PHONE_NUMBER')
twilio_phone_number = os.getenv('TWILIO_PHONE_NUMBER')

print(f"Sending to: {phone_number}")

try:
    client = Client(account_sid, auth_token)
    message = client.messages.create(
        body=f"Your Mishwari verification code is: {otp_code}",
        from_=twilio_phone_number,
        to=phone_number
    )
    print(f"✓ Success! SID: {message.sid}, Status: {message.status}")
except Exception as e:
    print(f"✗ Error: {e}")
