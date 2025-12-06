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

from ..models import Profile, BusOperator, Driver, OTPAttempt, DriverInvitation
from datetime import timedelta
from twilio.rest import Client
from ..utils.firebase_auth import verify_firebase_token 




class MobileLoginView(viewsets.ViewSet):
    
    permission_classes = [AllowAny]

    # disabling DRF’s default authentication to allow mobile based token to be used
    authentication_classes = []
    
    @action(detail=False, methods=['post'], url_path='request-otp')
    def request_otp(self, request):
        mobile_number = request.data.get('mobile_number')
        
        # Check rate limiting with OTPAttempt
        attempt, _ = OTPAttempt.objects.get_or_create(mobile_number=mobile_number)
        if attempt.blocked_until and timezone.now() < attempt.blocked_until:
            return Response({'error': 'Too many requests'}, status=status.HTTP_429_TOO_MANY_REQUESTS)
        
        if attempt.attempt_count >= 3:
            attempt.blocked_until = timezone.now() + timedelta(minutes=30)
            attempt.save()
            return Response({'error': 'Too many requests'}, status=status.HTTP_429_TOO_MANY_REQUESTS)
        
        otp_code = get_random_string(length=6, allowed_chars='0123456789')
        
        # Store OTP in cache (1 min expiry)
        cache.set(f'otp_{mobile_number}', otp_code, timeout=60)
        
        attempt.attempt_count += 1
        attempt.save()
        
        print(f'sending otp {otp_code} to mobile {mobile_number}')
        
        # Check if user has password (only operator_admin should have password)
        requires_password = False
        try:
            user = User.objects.get(username=mobile_number)
            profile = Profile.objects.get(user=user)
            has_password = user.has_usable_password()
            print(f'[OTP REQUEST] User {mobile_number} - role: {profile.role}, has_usable_password: {has_password}')
            # Only require password for operator_admin with usable password
            if profile.role == 'operator_admin' and has_password:
                requires_password = True
        except (User.DoesNotExist, Profile.DoesNotExist):
            print(f'[OTP REQUEST] User {mobile_number} - does not exist')
            pass
        
        result = self.send_otp_via_infobip(mobile_number, otp_code)
        if result['status'] == 'success':
            return Response({
                'message': 'OTP sent successfully via SMS',
                'requires_password': requires_password
            }, status=status.HTTP_200_OK)
        else:
            print(f"SMS error: {result['message']}")
            return Response({
                'message': f"OTP: {otp_code} (SMS failed: {result['message']})",
                'requires_password': requires_password
            }, status=status.HTTP_200_OK)
        

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
    

    @action(detail=False, methods=['post'], url_path='check-password-required')
    def check_password_required(self, request):
        """Check if password is required for login without generating OTP"""
        mobile_number = request.data.get('mobile_number')
        
        requires_password = False
        try:
            user = User.objects.get(username=mobile_number)
            profile = Profile.objects.get(user=user)
            if profile.role == 'operator_admin' and user.has_usable_password():
                requires_password = True
        except (User.DoesNotExist, Profile.DoesNotExist):
            pass
        
        return Response({'requires_password': requires_password}, status=status.HTTP_200_OK)
    
    @action(detail=False, methods=['post'], url_path='verify-firebase-otp')
    def verify_firebase_otp(self, request):
        firebase_token = request.data.get('firebase_token')
        
        if not firebase_token:
            return Response({'error': 'Firebase token required'}, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            # Verify Firebase token and extract phone number
            token_data = verify_firebase_token(firebase_token)
            mobile_number = token_data['phone_number']
            
            # Create or get user
            user, created = User.objects.get_or_create(
                username=mobile_number,
                defaults={'email': f'{mobile_number}@temp.mishwari.com'}
            )
            
            # Create or get profile
            profile, _ = Profile.objects.get_or_create(
                user=user,
                defaults={
                    'mobile_number': mobile_number,
                    'role': 'passenger'
                }
            )
            
            # Check password requirement for operator_admin
            has_password = user.has_usable_password()
            if not created and profile.role == 'operator_admin' and has_password:
                password = request.data.get('password')
                if not password:
                    return Response({'error': 'Password required'}, status=status.HTTP_400_BAD_REQUEST)
                if not user.check_password(password):
                    return Response({'error': 'Invalid password'}, status=status.HTTP_401_UNAUTHORIZED)
            
            # Clear OTP attempts
            try:
                attempt = OTPAttempt.objects.get(mobile_number=mobile_number)
                attempt.attempt_count = 0
                attempt.blocked_until = None
                attempt.save()
            except OTPAttempt.DoesNotExist:
                pass
            
            tokens = self.get_tokens_for_user(user)
            return Response({
                "message": "Login successful",
                "tokens": tokens
            }, status=status.HTTP_200_OK)
            
        except ValueError as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return Response({'error': 'Verification failed'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    @action(detail=False, methods=['patch'], url_path='verify-otp')
    def verify_otp(self, request):
        mobile_number = request.data.get('mobile_number')
        otp_code = request.data.get('otp_code')
        password = request.data.get('password')  # Optional password for operator_admin
        
        # Get OTP from cache
        cached_otp = cache.get(f'otp_{mobile_number}')
        if not cached_otp:
            return Response({'error': 'OTP expired or not found'}, status=status.HTTP_404_NOT_FOUND)
        
        emergency_code = os.getenv('EMERGENCY_OTP_CODE', None)
        
        if otp_code == emergency_code or otp_code == cached_otp:
            # Create user with phone as username
            user, created = User.objects.get_or_create(
                username=mobile_number,
                defaults={'email': f'{mobile_number}@temp.mishwari.com'}
            )
            
            # Create empty profile (full_name is None)
            profile, _ = Profile.objects.get_or_create(
                user=user,
                defaults={
                    'mobile_number': mobile_number,
                    'role': 'passenger'
                }
            )
            
            # Check if user has password (only operator_admin should require password)
            has_password = user.has_usable_password()
            print(f'[VERIFY OTP] User {mobile_number} - created: {created}, role: {profile.role}, has_usable_password: {has_password}')
            if not created and profile.role == 'operator_admin' and has_password:
                if not password:
                    return Response({'error': 'Password required'}, status=status.HTTP_400_BAD_REQUEST)
                
                # Verify password
                if not user.check_password(password):
                    return Response({'error': 'Invalid password'}, status=status.HTTP_401_UNAUTHORIZED)
            
            # All validations passed - clear OTP and reset attempts
            cache.delete(f'otp_{mobile_number}')
            try:
                attempt = OTPAttempt.objects.get(mobile_number=mobile_number)
                attempt.attempt_count = 0
                attempt.blocked_until = None
                attempt.save()
            except OTPAttempt.DoesNotExist:
                pass
            
            tokens = self.get_tokens_for_user(user)
            return Response({
                "message": "Login successful",
                "tokens": tokens
            }, status=status.HTTP_200_OK)
        
        return Response({"error": "Invalid or expired OTP"}, status=status.HTTP_400_BAD_REQUEST)                                                       
    

    @action(detail=False, methods=['post'], url_path='verify-transaction', permission_classes=[IsAuthenticated], authentication_classes=[JWTAuthentication])
    def verify_transaction(self, request):
        """Verify password for sensitive operations (operator_admin only)"""
        credential = request.data.get('credential')
        profile = request.user.profile
        
        if profile.role != 'operator_admin':
            return Response({'error': 'Not authorized'}, status=status.HTTP_403_FORBIDDEN)
        
        if not request.user.check_password(credential):
            return Response({'error': 'Invalid password'}, status=status.HTTP_403_FORBIDDEN)
        
        # Generate short-lived transaction token (5 minutes)
        transaction_token = get_random_string(32)
        cache.set(f'transaction_{request.user.id}', transaction_token, timeout=300)
        
        return Response({'transaction_token': transaction_token}, status=status.HTTP_200_OK)
    
    @action(detail=False, methods=['post'], url_path='change-mobile', permission_classes=[IsAuthenticated], authentication_classes=[JWTAuthentication])
    def change_mobile(self, request):
        """Change mobile number with OTP or Firebase verification"""
        new_mobile = request.data.get('new_mobile')
        otp_code = request.data.get('otp_code')
        password = request.data.get('password')
        firebase_token = request.data.get('firebase_token')
        
        profile = request.user.profile
        
        # Verify password for operator_admin
        if profile.role == 'operator_admin':
            if not password or not request.user.check_password(password):
                return Response({'error': 'Invalid password'}, status=status.HTTP_401_UNAUTHORIZED)
        
        # Verify Firebase token or OTP
        if firebase_token:
            try:
                token_data = verify_firebase_token(firebase_token)
                verified_mobile = token_data['phone_number']
                if verified_mobile != new_mobile:
                    return Response({'error': 'Mobile number mismatch'}, status=status.HTTP_400_BAD_REQUEST)
            except ValueError as e:
                return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        else:
            cached_otp = cache.get(f'otp_{new_mobile}')
            emergency_code = os.getenv('EMERGENCY_OTP_CODE', None)
            
            if not (otp_code == emergency_code or otp_code == cached_otp):
                return Response({'error': 'Invalid or expired OTP'}, status=status.HTTP_400_BAD_REQUEST)
        
        # Check if new mobile already exists
        if User.objects.filter(username=new_mobile).exclude(id=request.user.id).exists():
            return Response({'error': 'Mobile number already in use'}, status=status.HTTP_400_BAD_REQUEST)
        
        # Update mobile number
        old_mobile = profile.mobile_number
        request.user.username = new_mobile
        request.user.save()
        profile.mobile_number = new_mobile
        profile.save()
        
        # Clear OTP if used
        if not firebase_token:
            cache.delete(f'otp_{new_mobile}')
        
        print(f'[MOBILE CHANGE] User {request.user.id} changed mobile from {old_mobile} to {new_mobile}')
        
        return Response({'message': 'Mobile number updated successfully'}, status=status.HTTP_200_OK)
    
    @action(detail = False, methods = ['GET'], url_path='profile')
    def profile_detail(self,request):
        user = User.objects.get(user=request.user)
    
    @action(detail=False, methods=['get'], url_path='validate-invite')
    def validate_invite(self, request):
        """Validate invitation code (before OTP)"""
        invite_code = request.query_params.get('code')
        
        try:
            invitation = DriverInvitation.objects.get(invite_code=invite_code)
            
            if invitation.status != 'pending':
                return Response({'error': 'Invitation already used or cancelled'}, status=status.HTTP_400_BAD_REQUEST)
            
            if timezone.now() > invitation.expires_at:
                invitation.status = 'expired'
                invitation.save()
                return Response({'error': 'Invitation expired'}, status=status.HTTP_400_BAD_REQUEST)
            
            return Response({
                'valid': True,
                'operator_name': invitation.operator.name,
                'mobile_number': invitation.mobile_number
            })
        except DriverInvitation.DoesNotExist:
            return Response({'error': 'Invalid invitation code'}, status=status.HTTP_404_NOT_FOUND)
    
    @action(detail=False, methods=['post'], url_path='accept-invite', permission_classes=[IsAuthenticated], authentication_classes=[JWTAuthentication])
    def accept_invite(self, request):
        """Accept driver invitation (after OTP verification)"""
        invite_code = request.data.get('invite_code')
        
        try:
            invitation = DriverInvitation.objects.get(invite_code=invite_code, status='pending')
            
            if timezone.now() > invitation.expires_at:
                invitation.status = 'expired'
                invitation.save()
                return Response({'error': 'Invitation expired'}, status=status.HTTP_400_BAD_REQUEST)
            
            user = request.user
            profile = user.profile
            
            if profile.mobile_number != invitation.mobile_number:
                return Response({'error': 'Mobile number mismatch'}, status=status.HTTP_400_BAD_REQUEST)
            
            # Update profile
            profile.full_name = request.data.get('full_name')
            profile.role = 'driver'
            profile.save()
            
            # Update user email
            email = request.data.get('email')
            if email:
                user.email = email
                user.save()
            
            # Create Driver record
            driver = Driver.objects.create(
                user=user,
                profile=profile,
                national_id=request.data.get('national_id', ''),
                driver_license=request.data.get('driver_license', ''),
                driver_rating=5.0,
                operator=invitation.operator
            )
            
            # Mark invitation as accepted
            invitation.status = 'accepted'
            invitation.accepted_at = timezone.now()
            invitation.accepted_by = user
            invitation.save()
            
            return Response({
                'message': 'Successfully joined fleet',
                'driver_id': driver.id,
                'operator_name': invitation.operator.name,
                'profile': ProfileSerializer(profile).data
            })
            
        except DriverInvitation.DoesNotExist:
            return Response({'error': 'Invalid invitation code'}, status=status.HTTP_404_NOT_FOUND)
    
    @action(detail=False, methods=['post'], url_path='complete-profile', permission_classes=[IsAuthenticated], authentication_classes=[JWTAuthentication])
    def complete_profile(self, request):
        user = request.user
        profile = user.profile
        
        # Update profile fields
        profile.full_name = request.data.get('full_name', profile.full_name)
        profile.gender = request.data.get('gender', profile.gender)
        profile.birth_date = request.data.get('birth_date', profile.birth_date)
        profile.address = request.data.get('address', profile.address)
        
        # Handle operator registration
        role = request.data.get('role')
        if role and role in ['driver', 'operator_admin']:
            # Check if user already has a driver record (from invitation)
            existing_driver = Driver.objects.filter(user=user).first()
            
            if existing_driver:
                print(f'[REGISTRATION] User already has Driver record from invitation, skipping operator creation')
                profile.role = 'driver'
            else:
                profile.role = role
                
                # Require password for operator_admin
                if role == 'operator_admin':
                    password = request.data.get('password')
                    if not password or len(password) < 8:
                        return Response({'error': 'Password required (min 8 characters)'}, status=status.HTTP_400_BAD_REQUEST)
                    user.set_password(password)
                    user.save()
                
                print(f'[REGISTRATION] Creating operator for role: {role}')
                
                # Create operator if needed
                operator = BusOperator.objects.filter(platform_user=user).first()
                if not operator:
                    operator = BusOperator.objects.create(
                        name=profile.full_name or user.username,
                        contact_info=profile.mobile_number,
                        uses_own_system=False,
                        platform_user=user
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
        
        profile.save()
        
        # Update user email (replace temp email)
        email = request.data.get('email')
        if email:
            user.email = email
            user.save()
        
        return Response({
            "message": "Profile updated successfully",
            "profile": ProfileSerializer(profile).data
        }, status=status.HTTP_200_OK)
        


    

    def get_tokens_for_user(self, user):
        refresh = RefreshToken.for_user(user)
        return {
            'refresh': str(refresh),
            'access': str(refresh.access_token)
        }
        

    

    

class ProfileView(viewsets.ModelViewSet):
    serializer_class = ProfileSerializer
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
            
            # Get operator info and metrics
            operator_metrics = None
            operator_name = None
            is_standalone = False
            if profile.role in ['driver', 'operator_admin']:
                try:
                    driver = Driver.objects.get(user=request.user)
                    operator_name = driver.operator.name
                    # Check if driver owns the operator (standalone) or works for another operator (invited)
                    is_standalone = driver.operator.platform_user == request.user
                    operator_metrics = {
                        'is_suspended': driver.operator.metrics.is_suspended if hasattr(driver.operator, 'metrics') else False,
                        'health_score': driver.operator.metrics.health_score if hasattr(driver.operator, 'metrics') else 100,
                    }
                except Driver.DoesNotExist:
                    # For operator_admin without Driver record, get operator from BusOperator
                    if profile.role == 'operator_admin':
                        try:
                            operator = BusOperator.objects.get(platform_user=request.user)
                            operator_name = operator.name
                            is_standalone = True
                            operator_metrics = {
                                'is_suspended': operator.metrics.is_suspended if hasattr(operator, 'metrics') else False,
                                'health_score': operator.metrics.health_score if hasattr(operator, 'metrics') else 100,
                            }
                        except BusOperator.DoesNotExist:
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
                'operator_name': operator_name,
                'is_standalone': is_standalone,
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