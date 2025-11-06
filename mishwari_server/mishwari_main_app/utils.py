# utils.py

import requests
from django.conf import settings

def send_otp_via_fast2sms(mobile_number, otp_code):
    url = "https://www.fast2sms.com/dev/bulkV2"
    
    querystring = {
        "authorization": settings.FAST2SMS_API_KEY,
        "numbers": mobile_number,

        # # if quick
        # "message": f"كود التحقق لمشواري هو: {otp_code}",
        # "language": "arabic",
        # "route": "q",
        #######################
        # if normal
        "variables_values":f"{otp_code}",
        "route":"otp",
    }
    
    headers = {
        'cache-control': "no-cache"
    }

    response = requests.request("GET", url, headers=headers, params=querystring)
    
    # Log the response for debugging
    print(response.json())
    print(response.status_code)
    
    return response