from rest_framework import serializers
from .models import UserProfile, UserProfileManager
from apps.factory.serializer import RequestFactorySerializer
from rest_framework.exceptions import ValidationError


class RequestSerializer(serializers.ModelSerializer):
    objects = UserProfileManager()

    class Meta:
        model = UserProfile
        fields = ('id', 'username', 'email', 'company_fk')

    @staticmethod
    def request_id_check_one(request):
        info = UserProfile.objects.get(id=request)
        return info

    @staticmethod
    def request_id_check(request):
        info = UserProfile.objects.filter(id=request)
        return info

    @staticmethod
    def request_name_check(request):
        info = UserProfile.objects.get(username=request)

        return info.id

    @staticmethod
    def request_company_username_check(request):
        info = UserProfile.objects.get(company_fk_id=request)
        response = RequestSerializer(data=info)

        if response.is_valid():
            return response.data
        else:
            raise ValidationError()

    @staticmethod
    def request_company_check(request):
        info = RequestFactorySerializer.request_company_id_check(request)

        return info


    @staticmethod
    def request_create(**request):
        response = UserProfile.objects.create_user(**request)

        return response

    @staticmethod
    def request_super_create(**request):
        print(request)
        response = UserProfile.objects.create_superuser(**request)

        return response

    @staticmethod
    def request_delete(request):
        info = UserProfile.objects.get(username=request)
        info.delete()

    # @staticmethod
    # def request_update(response, **request):
    #     user_id = request.get('id')
    #     UserProfile.objects.filter(id=user_id).update(request.get(''))
