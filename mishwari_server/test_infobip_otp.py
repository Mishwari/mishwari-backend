import os
import requests
from dotenv import load_dotenv

load_dotenv()

# Dynamic: request.data.get('mobile_number')
phone_number = "201503100429"

# Dynamic: get_random_string(length=4, allowed_chars='0123456789')
otp_code = "1234"

# Dynamic: os.getenv('INFOBIP_BASE_URL')
base_url = os.getenv('INFOBIP_BASE_URL')

# Dynamic: os.getenv('INFOBIP_API_KEY')
api_key = os.getenv('INFOBIP_API_KEY')

# Dynamic: os.getenv('INFOBIP_WHATSAPP_SENDER')
whatsapp_sender = os.getenv('INFOBIP_WHATSAPP_SENDER')

print(f"Sending WhatsApp to: {phone_number}")

try:
    url = f"https://{base_url}/whatsapp/1/message/text"
    
    headers = {
        "Authorization": f"App {api_key}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "from": whatsapp_sender,
        "to": phone_number,
        "content": {
            "text": f"Your Mishwari verification code is: {otp_code}"
        }
    }
    
    response = requests.post(url, json=payload, headers=headers)
    
    if response.status_code == 200:
        data = response.json()
        message_id = data.get('messages', [{}])[0].get('messageId')
        print(f"✓ Success! Message ID: {message_id}")
    else:
        print(f"✗ Error: Status {response.status_code}")
        print(f"Body: {response.text}")
        
except Exception as e:
    print(f"✗ Error: {e}")
