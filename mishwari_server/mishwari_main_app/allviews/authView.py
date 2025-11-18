from rest_framework.response import Response
from rest_framework import status
from rest_framework import viewsets,status
from rest_framework.views import APIView
import os


from django.utils.crypto import get_random_string
from django.utils import timezone

from rest_framework_simplejwt.tokens import RefreshToken, UntypedToken
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError
from rest_framework_simplejwt.authentication import JWTAuthentication


from rest_framework.permissions import IsAuthenticated, AllowAny,IsAdminUser
from rest_framework.generics import get_object_or_404

from django.contrib.auth.models import User
from ..serializers import  ProfileCompletionSerializer, ProfileSerializer
import random
import requests
from django.http import JsonResponse
from django.views import View
from rest_framework.decorators import action
from django.core.cache import cache

from ..models import Profile, TemporaryMobileVerification, BusOperator, Driver
from twilio.rest import Client 




class MobileLoginView(viewsets.ViewSet):
    
    permission_classes = [AllowAny]

    # disabling DRF’s default authentication to allow mobile based token to be used
    authentication_classes = []
    
    @action(detail=False, methods=['post'], url_path='request-otp')
    def request_otp(self, request):
        mobile_number = request.data.get('mobile_number')

        if not self.is_phone_blocked(mobile_number):
            return Response({'error': 'Phone number is blocked'}, status=status.HTTP_403_FORBIDDEN)

        if not self.can_request_otp(mobile_number):
            return Response({'error': 'Too many requests, Try again later'}, status=status.HTTP_429_TOO_MANY_REQUESTS)
        
        otp_code = get_random_string(length=4, allowed_chars='0123456789')

        verification, created = TemporaryMobileVerification.objects.update_or_create(
            mobile_number=mobile_number,
            defaults={
                'otp_code': otp_code,
                'is_verified': False,
                'otp_sent_at': timezone.now() # NECESSARY
            }
        )

        print(f'sending otp {otp_code} to mobile {mobile_number}')
        
        result = self.send_otp_via_infobip(mobile_number, otp_code)
        if result['status'] == 'success':
            return Response({'message': 'OTP sent successfully via SMS'}, status=status.HTTP_200_OK)
        else:
            print(f"Twilio error: {result['message']}")
            return Response({'message': f"OTP: {otp_code} (SMS failed: {result['message']})"}, status=status.HTTP_200_OK)
        

    def send_otp_via_twilio(self, phone_number, otp_code):
        try:
            account_sid = os.getenv('TWILIO_ACCOUNT_SID')
            auth_token = os.getenv('TWILIO_AUTH_TOKEN')
            twilio_phone_number = os.getenv('TWILIO_PHONE_NUMBER')

            print(f"Twilio config check - SID: {bool(account_sid)}, Token: {bool(auth_token)}, Phone: {bool(twilio_phone_number)}")

            if not all([account_sid, auth_token, twilio_phone_number]):
                return {"status": "error", "message": "Twilio credentials not configured"}

            if not phone_number.startswith('+'):
                phone_number = '+' + phone_number

            print(f"Sending to: {phone_number}")
            client = Client(account_sid, auth_token)
            message = client.messages.create(
                body=f"Your OTP code is {otp_code}",
                from_=twilio_phone_number,
                to=phone_number
            )
            print(f"Message sent successfully: {message.sid}")
            return {"status": "success", "sid": message.sid}
        except Exception as e:
            print(f"Twilio exception: {str(e)}")
            import traceback
            traceback.print_exc()
            return {"status": "error", "message": str(e)}

    def send_otp_via_infobip(self, phone_number, otp_code):
        try:
            api_key = os.getenv('INFOBIP_API_KEY')
            base_url = os.getenv('INFOBIP_BASE_URL')
            sender = os.getenv('INFOBIP_SENDER', 'InfoSMS')

            if not all([api_key, base_url]):
                return {"status": "error", "message": "Infobip credentials not configured"}

            if not base_url.startswith('http'):
                base_url = 'https://' + base_url

            if not phone_number.startswith('+'):
                phone_number = '+' + phone_number

            url = f"{base_url}/sms/2/text/advanced"
            headers = {
                "Authorization": f"App {api_key}",
                "Content-Type": "application/json"
            }
            payload = {
                "messages": [{
                    "from": sender,
                    "destinations": [{"to": phone_number}],
                    "text": f"Your OTP code is {otp_code}"
                }]
            }

            response = requests.post(url, json=payload, headers=headers)
            print(f"Infobip response status: {response.status_code}")
            print(f"Infobip response: {response.text}")
            if response.status_code == 200:
                return {"status": "success", "response": response.json()}
            else:
                return {"status": "error", "message": response.text}
        except Exception as e:
            return {"status": "error", "message": str(e)}
        
    def send_whatsapp_message(self, phone_number, otp_code):
        # Failed due to Facebook aprroval delay
        url = "https://graph.facebook.com/v20.0/392655450602043/messages"
        WHATSAPP_SECRET_KEY = os.getenv('WHATSAPP_SECRET_KEY')
        print("tokrn",WHATSAPP_SECRET_KEY)
        headers = {
            # 60 days permanent for Husni
            "Authorization": f"Bearer {WHATSAPP_SECRET_KEY}",

            "Content-Type": "application/json"
        }
        data = {
        "messaging_product": "whatsapp",
        "to": phone_number,
        "type": "template",
        # "text": {
        #     "body": "Test message",
        # }
        "template": {
            "name": "mishwari_login",  # Replace with your actual template name
            "language": {"code": "ar"},  # Replace with the appropriate language code
            "components": [
                {
                    "type": "body",
                    "parameters": [
                        {
                            "type": "text",
                            "text": otp_code  # The OTP code variable
                        }
                    ]
                },
                {
                    "type": "button",
                    "sub_type": "url",
                    "index": "0",
                    "parameters": [
                    {
                        "type": "text",
                        "text": otp_code
                    }
                    ]
                }
            ]
        }
    }
        response = requests.post(url, json=data, headers=headers)
        print(response.json())
        return response
    

    @action(detail=False, methods=['patch'], url_path='verify-otp')
    def verify_otp(self, request):
        mobile_number = request.data.get('mobile_number')
        otp_code = request.data.get('otp_code')
        
        try:
            verification = TemporaryMobileVerification.objects.get(mobile_number=mobile_number)
 
            print('Verification', verification.otp_is_valid())
        except TemporaryMobileVerification.DoesNotExist:
            return Response({'error': 'Mobile number not found'}, status=status.HTTP_404_NOT_FOUND)
        

        if verification.otp_code == otp_code and verification.otp_is_valid(): # otp validity 10 min from models
            print('received otp ',otp_code)
            verification.is_verified = True
            verification.attempts = 0 
            verification.save()

            try:
                user = User.objects.get(profile__mobile_number=mobile_number)
                tokens = self.get_tokens_for_user(user)
                return Response({
                    "message": "Login successful.",
                    "user_status": "complete",
                    "tokens": tokens
                }, status=status.HTTP_200_OK)
            
            except User.DoesNotExist:
                print('does not exist')
                tokens = self.get_temporary_token_for_mobile(mobile_number)
                return Response({
                    "message": "Mobile number verified, proceed to complete registration.",
                    "user_status": "partial",
                    "tokens": tokens
                }, status=status.HTTP_200_OK)
            
        return Response({"error": "Invalid or expired OTP."}, status=status.HTTP_400_BAD_REQUEST)                                                       
    

    @action(detail = False, methods = ['GET'], url_path='profile')
    def profile_detail(self,request):
        user = User.objects.get(user=request.user)
    
    @action(detail=False, methods=['post'], url_path='complete-profile')
    def complete_profile(self, request):
        # token_mobile_number = request.user.token.get('mobile_number') # did not work since token has to be linked with user id 

        # self.authentication_classes = []

        auth_header = request.headers.get('Authorization')
        if not auth_header or not auth_header.startswith('Bearer '):
            return Response({"error": "No token provided"}, status=status.HTTP_401_UNAUTHORIZED)
        
        token_str = auth_header.split(' ')[1]

        try: 
            token = UntypedToken(token_str)
            token_mobile_number = token.get('mobile_number', None) # case 1: if mobile based token
            user_id = token.get('user_id', None) # case 2: if user based token

            # if not token_mobile_number:
            #     return Response({"error": "Invalid token. No mobile number found"}, status=status.HTTP_401_UNAUTHORIZED)

            # if only mobile verified without
            if token_mobile_number:


                if 'mobile_number' in request.data:
                    return Response({"error" : "Mobile number can not be changed during profile completing after verification."}, status=status.HTTP_400_BAD_REQUEST)
                
                serializer = ProfileCompletionSerializer(data=request.data, context={'mobile_number': token_mobile_number}) # NOTE trigger create since no instance provided 
                if serializer.is_valid():
                    profile = serializer.save()
                    user = profile.user
                    
                    # Handle operator registration
                    role = request.data.get('role', 'passenger')
                    print(f'[REGISTRATION] Creating operator for role: {role}')
                    if role in ['driver', 'operator_admin']:
                        # Auto-create operator with platform_user link
                        operator = BusOperator.objects.create(
                            name=profile.full_name or user.username,
                            contact_info=profile.mobile_number,
                            uses_own_system=False,
                            platform_user=user  # Direct link to platform user
                        )
                        print(f'[REGISTRATION] Created BusOperator ID: {operator.id}, platform_user: {user.username}')
                        
                        # For individual drivers, also create Driver record
                        if role == 'driver':
                            driver = Driver.objects.create(
                                user=user,
                                profile=profile,
                                driver_rating=5.0,
                                operator=operator
                            )
                            print(f'[REGISTRATION] Created Driver ID: {driver.id} for user: {user.username}')
                    
                    tokens = self.get_tokens_for_user(user)
                    return Response({
                        "message": "Profile created successfully.",
                        "tokens": tokens,
                        'purpose':'create'}, status=status.HTTP_201_CREATED
                        )
                
                return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
            
            # if exist user and profile
            elif user_id:
                try:
                    user = User.objects.get(id=user_id) # raise user exception if user is not available
                    profile = user.profile # raise profile exception if profile is not available
                    serializer = ProfileCompletionSerializer(profile, data=request.data, partial=True) # NOTE trigger update method since "profile" instance provided
                    print('user_based update',request.data)
                    tokens = self.get_tokens_for_user(user)
                    if serializer.is_valid():
                        serializer.save()
                        return Response({"message": "Profile updated successfully.",
                        "tokens": tokens,
                        'purpose':'edit'}, status=status.HTTP_200_OK)
                    
                    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
                
                except User.DoesNotExist:
                    return Response({"error": "User not found."}, status=status.HTTP_404_NOT_FOUND)
                
                except Profile.DoesNotExist:
                    return Response({"error": "Profile not found."}, status=status.HTTP_404_NOT_FOUND)
                
            else:
                return Response({"error": "Invalid token. No valid identification found"}, status=status.HTTP_401_UNAUTHORIZED)
                
        except  (InvalidToken, TokenError) as e:

            return Response({"error": f"Invalid or expired token: {str(e)}"}, status=status.HTTP_401_UNAUTHORIZED)
        


    

    def get_tokens_for_user(self, user):
        refresh = RefreshToken.for_user(user)
        return {
            'refresh': str(refresh),
            'access': str(refresh.access_token)
        }
        

    
    def get_temporary_token_for_mobile(self, mobile_number):
        print('test')
        refresh = RefreshToken()
        refresh['mobile_number'] = mobile_number # number becomes part of the token's data
        return {
            'refresh': str(refresh),
            'access': str(refresh.access_token)
        }
    
    def is_phone_blocked(self, mobile_number):
        number, created = TemporaryMobileVerification.objects.get_or_create(mobile_number=mobile_number)
        if created:
            return True
        if number.attempts > 6:
            return False
        
        number.attempts+=1
        number.save()
        return True
    
    def can_request_otp(self, mobile_number):
        request_count = cache.get(f'otp_request_count_{mobile_number}', 0)
        
        
        if request_count >= 3:
            return False
        
        cache.set(f'otp_request_count_{mobile_number}', request_count + 1, timeout = 30) # Waiting time
        return True
    

class ProfileView(viewsets.ModelViewSet):
    serializer_class = ProfileCompletionSerializer
    permission_classes = [IsAuthenticated]
    authentication_classes = [JWTAuthentication]

    # def get_queryset(self):
    #     # This line gets the user ID from the JWT token and returns the corresponding user
    #     return Profile.objects.filter(user=self.request.user.id)
    
    def list(self, request, *args, **kwargs):
        wallet = get_object_or_404(Profile, user=self.request.user)
        serializer = self.get_serializer(wallet)
        return Response(serializer.data, status=status.HTTP_200_OK)
    
    @action(detail=False, methods=['get'], url_path='me')
    def get_current_user(self, request):
        """Get current user with verification status for state revalidation"""
        try:
            profile = Profile.objects.get(user=request.user)
            
            # Get operator metrics if user is operator
            operator_metrics = None
            if profile.role in ['driver', 'operator_admin']:
                try:
                    driver = Driver.objects.get(user=request.user)
                    operator_metrics = {
                        'is_suspended': driver.operator.metrics.is_suspended if hasattr(driver.operator, 'metrics') else False,
                        'health_score': driver.operator.metrics.health_score if hasattr(driver.operator, 'metrics') else 100,
                    }
                except Driver.DoesNotExist:
                    pass
            
            return Response({
                'id': request.user.id,
                'username': request.user.username,
                'email': request.user.email,
                'profile': {
                    'id': profile.id,
                    'mobile_number': profile.mobile_number,
                    'full_name': profile.full_name,
                    'role': profile.role,
                    'is_verified': profile.is_verified,
                    'gender': profile.gender,
                    'birth_date': profile.birth_date,
                },
                'operator_metrics': operator_metrics
            }, status=status.HTTP_200_OK)
        except Profile.DoesNotExist:
            return Response({'error': 'Profile not found'}, status=status.HTTP_404_NOT_FOUND)
    
    def get_permissions(self):
        if self.request.method in ['GET']:
            return [IsAuthenticated()]
        return [IsAdminUser()]
    

class whatsapp_webhook(APIView):
    def post(self, request):
        data = request.data
        
        # Check if the webhook is related to message delivery
        if 'statuses' in data:
            for status_data in data['statuses']:
                message_status = status_data.get('status')
                recipient_phone = status_data.get('recipient_id')

                # Log message status
                print(f"Message to {recipient_phone} has status: {message_status}")

                # You can implement further logic here, such as marking OTP as delivered, etc.

        return Response({"message": "Webhook received"}, status=status.HTTP_200_OK)

    def get(self, request):
        """
        This GET method is usually called by Facebook/WhatsApp when validating the webhook.
        """
        hub_mode = request.GET.get('hub.mode')
        hub_challenge = request.GET.get('hub.challenge')
        hub_verify_token = request.GET.get('hub.verify_token')

        if hub_mode == 'subscribe' and hub_verify_token == 'YOUR_VERIFY_TOKEN':
            return Response(hub_challenge, status=status.HTTP_200_OK)

        return Response({"error": "Invalid verification token"}, status=status.HTTP_400_BAD_REQUEST)