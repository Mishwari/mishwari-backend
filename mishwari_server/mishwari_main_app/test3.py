from django.utils.crypto import get_random_string

otp_code = get_random_string(length=6, allowed_chars='0123456789')

print(otp_code)