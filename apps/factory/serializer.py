from rest_framework import serializers
from .models import CompanyProfile, Machine, Sensor
from rest_framework.exceptions import ValidationError


class RequestFactorySerializer(serializers.ModelSerializer):
    class Meta:
        model = CompanyProfile
        fields = ('company_id', 'company_name')

    @staticmethod
    def request_company_id_check(request):
        company_id = CompanyProfile.objects.filter(company_id=request)

        return company_id

    @staticmethod
    def request_machine_id_check(request):
        machine_id = Machine.objects.filter(company_fk_id=request)

        return machine_id

    @staticmethod
    def request_sensor_id_check(request):
        sensor_id = Sensor.objects.filter(machine_fk_id=request)

        return sensor_id

    @staticmethod
    def request_create(**request):
        response = CompanyProfile.save(**request)
        return response

    @staticmethod
    def request_delete(request):
        info = CompanyProfile.objects.get(company_name=request)
        info.delete()

    # @staticmethod
    # def request_update(response, **request):
    #     user_id = request.get('id')
    #     UserProfile.objects.filter(id=user_id).update(request.get(''))
