"""User-related serializers"""
from rest_framework import serializers
from django.contrib.auth.models import User
from ..models import Profile, Driver, BusOperator, CityList


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ["id", "username", "email", "first_name", "last_name"]


class ProfileSerializer(serializers.ModelSerializer):
    user = UserSerializer(read_only=True)
    is_standalone = serializers.SerializerMethodField()
    operator_name = serializers.SerializerMethodField()
    operator_contact = serializers.SerializerMethodField()
    operational_regions = serializers.SerializerMethodField()
    driver_license = serializers.SerializerMethodField()
    national_id = serializers.SerializerMethodField()
    pending_invitation_code = serializers.SerializerMethodField()
    
    class Meta:
        model = Profile
        fields = ['id', 'user', 'mobile_number', 'full_name', 'birth_date', 'gender', 'address', 'role', 'is_verified', 'is_standalone', 'operator_name', 'operator_contact', 'operational_regions', 'driver_license', 'national_id', 'pending_invitation_code']
    
    def get_is_standalone(self, obj):
        return obj.role in ['standalone_driver', 'operator_admin']
    
    def get_operator_name(self, obj):
        if obj.role in ['standalone_driver', 'invited_driver', 'operator_admin']:
            try:
                driver = Driver.objects.get(user=obj.user)
                return driver.operator.name
            except Driver.DoesNotExist:
                if obj.role == 'operator_admin':
                    try:
                        operator = BusOperator.objects.get(platform_user=obj.user)
                        return operator.name
                    except BusOperator.DoesNotExist:
                        pass
        return None
    
    def get_operator_contact(self, obj):
        if obj.role in ['standalone_driver', 'invited_driver', 'operator_admin']:
            try:
                driver = Driver.objects.get(user=obj.user)
                return driver.operator.contact_info
            except Driver.DoesNotExist:
                if obj.role == 'operator_admin':
                    try:
                        operator = BusOperator.objects.get(platform_user=obj.user)
                        return operator.contact_info
                    except BusOperator.DoesNotExist:
                        pass
        return None
    
    def get_driver_license(self, obj):
        if obj.role in ['standalone_driver', 'invited_driver', 'operator_admin']:
            try:
                driver = Driver.objects.get(user=obj.user)
                return driver.driver_license
            except Driver.DoesNotExist:
                pass
        return None
    
    def get_national_id(self, obj):
        if obj.role in ['standalone_driver', 'invited_driver', 'operator_admin']:
            try:
                driver = Driver.objects.get(user=obj.user)
                return driver.national_id
            except Driver.DoesNotExist:
                pass
        return None
    
    def get_operational_regions(self, obj):
        if obj.role in ['standalone_driver', 'invited_driver', 'operator_admin']:
            try:
                driver = Driver.objects.get(user=obj.user)
                return list(driver.operator.operational_regions.values_list('city', flat=True))
            except Driver.DoesNotExist:
                if obj.role == 'operator_admin':
                    try:
                        operator = BusOperator.objects.get(platform_user=obj.user)
                        return list(operator.operational_regions.values_list('city', flat=True))
                    except BusOperator.DoesNotExist:
                        pass
        return []
    
    def get_pending_invitation_code(self, obj):
        from ..models import DriverInvitation
        
        if obj.role == 'invited_driver' and not obj.full_name:
            try:
                driver = Driver.objects.get(user=obj.user)
                invitation = DriverInvitation.objects.filter(
                    mobile_number=obj.mobile_number,
                    operator=driver.operator
                ).order_by('-created_at').first()
                if invitation:
                    return invitation.invite_code
            except Driver.DoesNotExist:
                pass
        return None


class ProfileCompletionSerializer(serializers.ModelSerializer):
    username = serializers.CharField(write_only=True, required=False)
    email = serializers.EmailField(write_only=True, required=True)
    user = UserSerializer(read_only=True)
    
    class Meta:
        model = Profile
        fields = ['user', 'username', 'full_name', 'birth_date', 'gender', 'address', 'email', 'role']
        extra_kwargs = {'full_name': {'required': True}}

    def create(self, validated_data):
        username = validated_data.pop('username', None)
        email = validated_data.pop('email', None)
        mobile_number = self.context.get('mobile_number', None)

        if not username:
            username = mobile_number
        
        if not username:
            raise serializers.ValidationError({'message': 'Mobile number is required for profile creation'})
        
        user = User.objects.create_user(username=username, email=email)
        profile = Profile.objects.create(user=user, mobile_number=mobile_number, **validated_data)
        
        return profile

    def update(self, instance, validated_data):
        user = instance.user
        username = validated_data.get('username', user.username)
        email = validated_data.get('email', user.email)
        user.username = username
        user.email = email
        user.save()

        instance.full_name = validated_data.get('full_name', instance.full_name)
        instance.birth_date = validated_data.get('birth_date', instance.birth_date)
        instance.gender = validated_data.get('gender', instance.gender)
        instance.save()
        
        operator_name = validated_data.get('operator_name')
        operator_contact = validated_data.get('operator_contact')
        operational_regions = validated_data.get('operational_regions')
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
                if instance.role == 'operator_admin':
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
        
        driver_license = validated_data.get('driver_license')
        national_id = validated_data.get('national_id')
        if driver_license or national_id:
            try:
                driver = Driver.objects.get(user=user)
                if driver.operator.platform_user == user:
                    if driver_license:
                        driver.driver_license = driver_license
                    if national_id:
                        driver.national_id = national_id
                    driver.save()
            except Driver.DoesNotExist:
                pass
        
        return instance
