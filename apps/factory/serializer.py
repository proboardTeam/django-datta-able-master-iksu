from rest_framework import serializers
from .models import CompanyProfile, Factory, Machine, Server, Sensor
from rest_framework.exceptions import ValidationError
from rest_framework.validators import UniqueTogetherValidator


class RequestCompanySerializer(serializers.ModelSerializer):
    class Meta:
        model = CompanyProfile
        fields = "__all__"
        validators = [
            UniqueTogetherValidator(
                queryset=CompanyProfile.objects.all(),
                fields="__all__"
            )
        ]


class RequestFactorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Factory
        fields = "__all__"
        validators = [
            UniqueTogetherValidator(
                queryset=Factory.objects.all(),
                fields="__all__"
            )
        ]


class RequestServerSerializer(serializers.ModelSerializer):
    class Meta:
        model = Server
        fields = "__all__"
        validators = [
            UniqueTogetherValidator(
                queryset=Server.objects.all(),
                fields="__all__"
            )
        ]


class RequestMachineSerializer(serializers.ModelSerializer):

    class Meta:
        model = Machine
        fields = "__all__"
        validators = [
            UniqueTogetherValidator(
                queryset=Machine.objects.all(),
                fields="__all__"
            )
        ]


class RequestSensorSerializer(serializers.ModelSerializer):
    class Meta:
        model = Sensor
        fields = ["sensor_id", "sensor_tag", "sensor_img", ]
        validators = [
            UniqueTogetherValidator(
                queryset=Sensor.objects.all(),
                fields="__all__"
            )
        ]


class RequestFactoryQuery:

    @staticmethod
    def get_factory_list(request):
        if request:
            response = Factory.objects.all()
            return response

        else:
            return


class RequestServerQuery:

    @staticmethod
    def get_server_list(request):
        if request:
            response = Server.objects.all()
            return response

        else:
            return


class RequestMachineQuery:

    @staticmethod
    def get_machine_list(request):
        if request:
            response = Machine.objects.all()
            return response

        else:
            return

    @staticmethod
    def get_machine_all_machine_name(request):
        if request:
            response = Machine.objects.values_list(request, flat=True).values()
            return response

        else:
            return

    @staticmethod
    def get_machine_by_id(request):
        if request:
            response = Machine.objects.filter(factory_fk_id=request)
            return response

        else:
            return


class RequestSensorQuery:

    @staticmethod
    def get_sensor_list(request):
        if request:
            response = Sensor.objects.all()
            return response

        else:
            return

    @staticmethod
    def get_sensor_all_sensor(request):

        if "sensor_tag" == request:
            return Sensor.objects.values_list(request, flat=True).values()

        elif "sensor_img" == request:
            return Sensor.objects.values_list(request, flat=True).values()

        else:
            return

    @staticmethod
    def get_sensor_all_sensor_img(request):

        if "sensor_img" == request:
            return Sensor.objects.values_list(request, flat=True).values()

        else:
            return

    @staticmethod
    def get_sensor_select_by_one(request):
        return Sensor.objects.get(sensor_id=request)


class RequestTotalSerializer(serializers.ModelSerializer):
    class Meta:
        model = CompanyProfile, Factory, Machine, Sensor

    @staticmethod
    def request_company_id_check(request):
        company_id = CompanyProfile.objects.filter(company_id=request)

        return company_id

    @staticmethod
    def request_company_id_check_one(request):
        company_id = CompanyProfile.objects.get(company_id=request)

        return company_id

    @staticmethod
    def request_machine_id_check_one(request):
        machine_id = Machine.objects.get(company_fk_id=request)

        return machine_id

    @staticmethod
    def request_machine_id_check(request):
        machine_id = Machine.objects.filter(company_fk_id=request)

        return machine_id

    @staticmethod
    def request_sensor_id_check_one(request):
        sensor_id = Sensor.objects.get(machine_fk_id=request)

        return sensor_id

    @staticmethod
    def request_sensor_id_check(request):
        sensor_id = Sensor.objects.filter(machine_fk_id=request)

        return sensor_id

    @staticmethod
    def request_sensor_all_from_company(request):
        sensor_id = Sensor.objects.filter(company_fk_id=request)

        return sensor_id

    @staticmethod
    def request_sensor_name_check(request):
        sensor_id = Sensor.objects.filter(sensor_tag=request)

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
