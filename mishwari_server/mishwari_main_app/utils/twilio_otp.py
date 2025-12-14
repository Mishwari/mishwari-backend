"""Twilio OTP utility"""
import os
from twilio.rest import Client


def send_otp_via_twilio(phone_number, otp_code):
    """Send OTP via Twilio SMS"""
    try:
        account_sid = os.getenv('TWILIO_ACCOUNT_SID')
        auth_token = os.getenv('TWILIO_AUTH_TOKEN')
        twilio_phone_number = os.getenv('TWILIO_PHONE_NUMBER')
        
        if not all([account_sid, auth_token, twilio_phone_number]):
            return {"status": "error", "message": "Twilio credentials not configured"}
        
        if not phone_number.startswith('+'):
            phone_number = '+' + phone_number
        
        client = Client(account_sid, auth_token)
        message = client.messages.create(
            body=f"Your OTP code is {otp_code}",
            from_=twilio_phone_number,
            to=phone_number
        )
        
        return {"status": "success", "sid": message.sid}
    except Exception as e:
        return {"status": "error", "message": str(e)}
