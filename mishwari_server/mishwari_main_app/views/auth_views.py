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
from ..services.google_identity_proxy import GoogleIdentityProxyService 




class MobileLoginView(viewsets.ViewSet):
    
    permission_classes = [AllowAny]

    # disabling DRF’s default authentication to allow mobile based token to be used
    authentication_classes = []
    
    @action(detail=False, methods=['post'], url_path='request-otp')
    def request_otp(self, request):
        mobile_number = request.data.get('mobile_number')
        recaptcha_token = request.data.get('recaptcha_token')
        use_firebase = request.data.get('use_firebase', True)
        
        # Check rate limiting with OTPAttempt
        attempt, _ = OTPAttempt.objects.get_or_create(mobile_number=mobile_number)
        if attempt.blocked_until and timezone.now() < attempt.blocked_until:
            return Response({'error': 'Too many requests'}, status=status.HTTP_429_TOO_MANY_REQUESTS)
        
        if attempt.attempt_count >= 50:
            attempt.blocked_until = timezone.now() + timedelta(minutes=30)
            attempt.save()
            return Response({'error': 'Too many requests'}, status=status.HTTP_429_TOO_MANY_REQUESTS)
        
        # Check if user has password (only operator_admin should have password)
        requires_password = False
        try:
            user = User.objects.get(username=mobile_number)
            profile = Profile.objects.get(user=user)
            has_password = user.has_usable_password()
            print(f'[OTP REQUEST] User {mobile_number} - role: {profile.role}, has_usable_password: {has_password}')
            if profile.role == 'operator_admin' and has_password:
                requires_password = True
        except (User.DoesNotExist, Profile.DoesNotExist):
            print(f'[OTP REQUEST] User {mobile_number} - does not exist')
            pass
        
        # Try Firebase proxy first if recaptcha token provided
        if use_firebase and recaptcha_token:
            print(f'[OTP REQUEST] Attempting Firebase proxy for {mobile_number}')
            firebase_result = GoogleIdentityProxyService.send_otp(mobile_number, recaptcha_token)
            
            if firebase_result['success']:
                attempt.attempt_count += 1
                attempt.save()
                
                # Store session_info in cache for verification
                cache.set(f'firebase_session_{mobile_number}', firebase_result['session_info'], timeout=300)
                
                print(f'[OTP REQUEST] Firebase proxy success for {mobile_number}')
                return Response({
                    'message': 'OTP sent successfully via Firebase',
                    'method': 'firebase',
                    'session_info': firebase_result['session_info'],
                    'requires_password': requires_password
                }, status=status.HTTP_200_OK)
            else:
                print(f'[OTP REQUEST] Firebase proxy failed: {firebase_result.get("error")}, falling back to SMS')
        
        # Fallback to SMS
        otp_code = get_random_string(length=6, allowed_chars='0123456789')
        cache.set(f'otp_{mobile_number}', otp_code, timeout=60)
        attempt.attempt_count += 1
        attempt.save()
        
        print(f'[OTP REQUEST] Sending SMS OTP {otp_code} to {mobile_number}')
        result = self.send_otp_via_infobip(mobile_number, otp_code)
        
        if result['status'] == 'success':
            return Response({
                'message': 'OTP sent successfully via SMS',
                'method': 'sms',
                'requires_password': requires_password
            }, status=status.HTTP_200_OK)
        else:
            print(f"SMS error: {result['message']}")
            return Response({
                'message': f"OTP: {otp_code} (SMS failed: {result['message']})",
                'method': 'sms',
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
    

    @action(detail=False, methods=['patch'], url_path='verify-otp')
    def verify_otp(self, request):
        mobile_number = request.data.get('mobile_number')
        otp_code = request.data.get('otp_code')
        password = request.data.get('password')
        session_info = request.data.get('session_info')
        method = request.data.get('method', 'sms')
        
        # Check emergency code first (works for both Firebase and SMS)
        emergency_code = os.getenv('EMERGENCY_OTP_CODE', None)
        if emergency_code and otp_code == emergency_code:
            print(f'[VERIFY OTP] Emergency code used for {mobile_number}')
        elif method == 'firebase' and session_info:
            # Verify via Firebase proxy
            print(f'[VERIFY OTP] Verifying Firebase OTP for session')
            firebase_result = GoogleIdentityProxyService.verify_otp(session_info, otp_code)
            
            if not firebase_result['success']:
                print(f'[VERIFY OTP] Firebase verification failed: {firebase_result.get("error")}')
                return Response({
                    'error': 'INVALID_OTP',
                    'message': firebase_result['message']
                }, status=status.HTTP_400_BAD_REQUEST)
            
            mobile_number = firebase_result['phone_number']
            print(f'[VERIFY OTP] Firebase verification success for {mobile_number}')
        else:
            # Verify via SMS
            cached_otp = cache.get(f'otp_{mobile_number}')
            if not cached_otp:
                return Response({'error': 'OTP expired or not found'}, status=status.HTTP_404_NOT_FOUND)
            
            if otp_code != cached_otp:
                return Response({"error": "Invalid or expired OTP"}, status=status.HTTP_400_BAD_REQUEST)
            
            print(f'[VERIFY OTP] SMS verification success for {mobile_number}')
        
        # Common verification logic for both methods
        if True:
            # Check if user has pending invitation
            pending_invitation = DriverInvitation.objects.filter(
                mobile_number=mobile_number,
                status='pending',
                expires_at__gt=timezone.now()
            ).first()
            
            # Smart app_type detection: if pending invitation exists, default to driver
            app_type = request.data.get('app_type')
            if not app_type:
                app_type = 'driver' if pending_invitation else 'passenger'
            print(f'[SMS] Detected app_type={app_type}, has_invitation={bool(pending_invitation)}')
            
            # Create user with phone as username
            user, created = User.objects.get_or_create(
                username=mobile_number,
                defaults={'email': f'{mobile_number}@temp.mishwari.com'}
            )
            
            # Create profile with appropriate role
            # For new users, set role based on app_type to avoid immediate blocking
            default_role = 'passenger'
            if pending_invitation:
                default_role = 'invited_driver'
            elif app_type == 'driver':
                default_role = 'standalone_driver'  # Will be finalized in complete_profile
            
            profile, _ = Profile.objects.get_or_create(
                user=user,
                defaults={
                    'mobile_number': mobile_number,
                    'role': default_role
                }
            )
            
            # Validate app access based on role
            print(f'[SMS] app_type={app_type}, role={profile.role}, created={created}')
            if app_type == 'passenger' and profile.role in ['standalone_driver', 'invited_driver', 'operator_admin']:
                print(f'[SMS] BLOCKING driver in passenger app')
                return Response({
                    'error': 'WRONG_APP',
                    'message': 'هذا الحساب مخصص للسائقين. يرجى استخدام تطبيق السائقين للدخول.'
                }, status=status.HTTP_403_FORBIDDEN)
            
            if app_type == 'driver' and profile.role == 'passenger':
                print(f'[SMS] BLOCKING passenger in driver app')
                return Response({
                    'error': 'WRONG_APP',
                    'message': 'هذا الحساب مخصص للركاب. يرجى استخدام تطبيق الركاب للدخول.'
                }, status=status.HTTP_403_FORBIDDEN)
            
            # Create Driver record immediately if pending invitation exists
            if pending_invitation:
                Driver.objects.get_or_create(
                    user=user,
                    defaults={
                        'profile': profile,
                        'driver_rating': 5.0,
                        'operator': pending_invitation.operator
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
            if method == 'sms':
                cache.delete(f'otp_{mobile_number}')
            else:
                cache.delete(f'firebase_session_{mobile_number}')
            
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
    
    @action(detail=False, methods=['post'], url_path='change-password', permission_classes=[IsAuthenticated], authentication_classes=[JWTAuthentication])
    def change_password(self, request):
        """Change password for operator_admin"""
        current_password = request.data.get('current_password')
        new_password = request.data.get('new_password')
        
        profile = request.user.profile
        
        if profile.role != 'operator_admin':
            return Response({'error': 'Only operator_admin can change password'}, status=status.HTTP_403_FORBIDDEN)
        
        if not current_password or not new_password:
            return Response({'error': 'Current and new password required'}, status=status.HTTP_400_BAD_REQUEST)
        
        if not request.user.check_password(current_password):
            return Response({'error': 'Current password is incorrect'}, status=status.HTTP_401_UNAUTHORIZED)
        
        if len(new_password) < 8:
            return Response({'error': 'New password must be at least 8 characters'}, status=status.HTTP_400_BAD_REQUEST)
        
        request.user.set_password(new_password)
        request.user.save()
        
        print(f'[PASSWORD CHANGE] User {request.user.id} changed password successfully')
        
        return Response({'message': 'Password updated successfully'}, status=status.HTTP_200_OK)
    
    @action(detail=False, methods=['post'], url_path='change-mobile', permission_classes=[IsAuthenticated], authentication_classes=[JWTAuthentication])
    def change_mobile(self, request):
        """Change mobile number with OTP verification"""
        new_mobile = request.data.get('new_mobile')
        otp_code = request.data.get('otp_code')
        password = request.data.get('password')
        
        profile = request.user.profile
        
        # Verify password for operator_admin
        if profile.role == 'operator_admin':
            if not password or not request.user.check_password(password):
                return Response({'error': 'Invalid password'}, status=status.HTTP_401_UNAUTHORIZED)
        
        # Verify OTP
        cached_otp = cache.get(f'otp_{new_mobile}')
        emergency_code = os.getenv('EMERGENCY_OTP_CODE', None)
        
        if not (otp_code == emergency_code or otp_code == cached_otp):
            return Response({'error': 'Invalid or expired OTP'}, status=status.HTTP_400_BAD_REQUEST)
        
        # Check if new mobile already exists
        if User.objects.filter(username=new_mobile).exclude(id=request.user.id).exists():
            return Response({'error': 'Mobile number already in use'}, status=status.HTTP_400_BAD_REQUEST)
        
        # Check if new mobile has pending invitation (warn but allow)
        pending_invitation = DriverInvitation.objects.filter(
            mobile_number=new_mobile,
            status='pending',
            expires_at__gt=timezone.now()
        ).first()
        if pending_invitation:
            print(f'[MOBILE CHANGE] Warning: New mobile {new_mobile} has pending invitation from {pending_invitation.operator.name}')
        
        # Update mobile number
        old_mobile = profile.mobile_number
        request.user.username = new_mobile
        request.user.save()
        profile.mobile_number = new_mobile
        profile.save()
        
        # Clear OTP
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
        """Complete invited driver profile (Driver record already created during OTP)"""
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
            
            # Update profile details (keep role as 'invited_driver')
            profile.full_name = request.data.get('full_name')
            # Don't change role - it's already 'invited_driver'
            profile.save()
            
            # Update user email
            email = request.data.get('email')
            if email:
                user.email = email
                user.save()
            
            # Update Driver record (already created during OTP verification)
            driver = Driver.objects.get(user=user)
            driver.national_id = request.data.get('national_id', '')
            driver.driver_license = request.data.get('driver_license', '')
            driver.save()
            
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
        except Driver.DoesNotExist:
            return Response({'error': 'Driver record not found'}, status=status.HTTP_400_BAD_REQUEST)
    
    @action(detail=False, methods=['post'], url_path='complete-profile', permission_classes=[IsAuthenticated], authentication_classes=[JWTAuthentication])
    def complete_profile(self, request):
        from ..models import CityList
        user = request.user
        profile = user.profile
        
        # Extract fields from request
        operator_name = request.data.get('operator_name')
        operator_contact = request.data.get('operator_contact')
        operational_regions = request.data.get('operational_regions')
        driver_license = request.data.get('driver_license')
        national_id = request.data.get('national_id')
        role = request.data.get('role')
        
        # Handle initial operator registration FIRST
        if role and role in ['driver', 'operator_admin']:
            existing_driver = Driver.objects.filter(user=user).first()
            
            if existing_driver:
                # User already has Driver record (invited driver)
                profile.role = 'invited_driver'
            else:
                # New standalone driver or operator_admin
                if role == 'driver':
                    profile.role = 'standalone_driver'
                else:
                    profile.role = 'operator_admin'
                
                # Create operator for standalone users
                if role == 'operator_admin':
                    password = request.data.get('password')
                    if not password or len(password) < 8:
                        return Response({'error': 'Password required (min 8 characters)'}, status=status.HTTP_400_BAD_REQUEST)
                    user.set_password(password)
                    user.save()
                
                operator = BusOperator.objects.filter(platform_user=user).first()
                if not operator:
                    operator = BusOperator.objects.create(
                        name=operator_name or request.data.get('full_name') or user.username,
                        contact_info=operator_contact or profile.mobile_number,
                        uses_own_system=False,
                        platform_user=user
                    )
                    if operational_regions:
                        cities = CityList.objects.filter(city__in=operational_regions)
                        operator.operational_regions.set(cities)
                
                if role == 'driver':
                    Driver.objects.create(
                        user=user,
                        profile=profile,
                        driver_rating=5.0,
                        operator=operator,
                        driver_license=driver_license or '',
                        national_id=national_id or ''
                    )
        
        # Update profile fields
        profile.full_name = request.data.get('full_name', profile.full_name)
        profile.gender = request.data.get('gender', profile.gender)
        profile.birth_date = request.data.get('birth_date', profile.birth_date)
        profile.address = request.data.get('address', profile.address)
        profile.save()
        
        # Update user email
        email = request.data.get('email')
        if email:
            user.email = email
            user.save()
        
        # Update operator details if standalone (for existing operators)
        if operator_name or operator_contact or operational_regions is not None:
            try:
                driver = Driver.objects.get(user=user)
                if driver.operator.platform_user == user:
                    if operator_name:
                        driver.operator.name = operator_name
                    if operator_contact:
                        driver.operator.contact_info = operator_contact
                    if operational_regions is not None:
                        cities = CityList.objects.filter(city__in=operational_regions)
                        driver.operator.operational_regions.set(cities)
                    driver.operator.save()
            except Driver.DoesNotExist:
                if profile.role == 'operator_admin':
                    try:
                        operator = BusOperator.objects.get(platform_user=user)
                        if operator_name:
                            operator.name = operator_name
                        if operator_contact:
                            operator.contact_info = operator_contact
                        if operational_regions is not None:
                            cities = CityList.objects.filter(city__in=operational_regions)
                            operator.operational_regions.set(cities)
                        operator.save()
                    except BusOperator.DoesNotExist:
                        pass
        
        # Update driver details (allow all drivers to update their own info)
        if driver_license or national_id:
            try:
                driver = Driver.objects.get(user=user)
                if driver_license:
                    driver.driver_license = driver_license
                if national_id:
                    driver.national_id = national_id
                driver.save()
            except Driver.DoesNotExist:
                pass
        
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
            is_standalone = profile.role in ['standalone_driver', 'operator_admin']
            if profile.role in ['standalone_driver', 'invited_driver', 'operator_admin']:
                try:
                    driver = Driver.objects.get(user=request.user)
                    operator_name = driver.operator.name
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
                            operator_metrics = {
                                'is_suspended': operator.metrics.is_suspended if hasattr(operator, 'metrics') else False,
                                'health_score': operator.metrics.health_score if hasattr(operator, 'metrics') else 100,
                            }
                        except BusOperator.DoesNotExist:
                            pass
            
            # Check for pending invitation code
            pending_invitation_code = None
            if profile.role == 'invited_driver' and not profile.full_name:
                try:
                    driver = Driver.objects.get(user=request.user)
                    invitation = DriverInvitation.objects.filter(
                        mobile_number=profile.mobile_number,
                        operator=driver.operator
                    ).order_by('-created_at').first()
                    if invitation:
                        pending_invitation_code = invitation.invite_code
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
                'operator_name': operator_name,
                'is_standalone': is_standalone,
                'operator_metrics': operator_metrics,
                'pending_invitation_code': pending_invitation_code
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