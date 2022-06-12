from django.db import models


# Create your models here.
class CompanyType(models.Model):
    company_type_id = models.AutoField(auto_created=True, primary_key=True, serialize=False)
    company_type_name = models.CharField(max_length=200)
    company_type_img = models.FileField(upload_to="apps/static/assets/media/images/company_type", blank=True, null=True)


class CompanyProfile(models.Model):
    company_id = models.AutoField(auto_created=True, primary_key=True, serialize=False)
    company_name = models.CharField(max_length=200)
    company_type_fk = models.ForeignKey(CompanyType, related_name="company_type_fk", blank=True, null=True,
                                        on_delete=models.CASCADE)


class Factory(models.Model):
    factory_id = models.AutoField(auto_created=True, primary_key=True, serialize=False)
    factory_name = models.CharField(max_length=200)
    factory_address = models.CharField(max_length=200)
    factory_img = models.ImageField(upload_to="apps/static/assets/media/images/factory", blank=True, null=True)
    company_fk = models.ForeignKey(CompanyProfile, related_name="factory_company_fk", blank=True, null=True,
                                   on_delete=models.CASCADE)


class Server(models.Model):
    server_id = models.AutoField(auto_created=True, primary_key=True, serialize=False)
    server_name = models.CharField(max_length=200)
    factory_fk = models.ForeignKey(Factory, related_name="server_company_fk", blank=True, null=True,
                                   on_delete=models.CASCADE)


class MachineType(models.Model):
    machine_type_id = models.AutoField(auto_created=True, primary_key=True, serialize=False)
    machine_type_name = models.CharField(max_length=200)


class Machine(models.Model):
    machine_id = models.AutoField(auto_created=True, primary_key=True, serialize=False)
    machine_name = models.CharField(max_length=200)
    machine_img = models.ImageField(upload_to="apps/static/assets/media/images/machine", blank=True, null=True)
    factory_fk = models.ForeignKey(Factory, related_name="machine_factory_fk", blank=True, null=True,
                                   on_delete=models.CASCADE)
    machine_type_fk = models.ForeignKey(MachineType, related_name="machine_type_fk", blank=True, null=True,
                                on_delete=models.CASCADE)


class Sensor(models.Model):
    sensor_id = models.AutoField(auto_created=True, primary_key=True, serialize=False)
    sensor_parent = models.CharField(max_length=200)
    sensor_mac = models.CharField(max_length=200)
    sensor_tag = models.CharField(max_length=200)
    sensor_img = models.ImageField(upload_to="apps/static/assets/media/images/sensor", blank=True, null=True)

    server_fk = models.ForeignKey(Server, related_name="sensor_server_fk", blank=True, null=True,
                                  on_delete=models.CASCADE)
    machine_fk = models.ForeignKey(Machine, related_name="sensor_machine_fk", blank=True, null=True,
                                   on_delete=models.CASCADE)
    factory_fk = models.ForeignKey(Factory, related_name="sensor_factory_fk", blank=True, null=True,
                                   on_delete=models.CASCADE)

# from django.db import models
#
#
# # Create your models here.
# # 회사 정보
# class CompanyProfile(models.Model):
#     company_id = models.AutoField(auto_created=True, primary_key=True, serialize=False)
#     company_name = models.CharField(max_length=200)
#
#
# # 회사(현장) 유형
# class CompanyType(models.Model):
#     company_type_id = models.AutoField(auto_created=True, primary_key=True, serialize=False)
#     company_type_name = models.CharField(max_length=200)
#     company_type_img = models.FileField(upload_to="apps/static/assets/media/images/company_type", blank=True, null=True)
#     company_fk = models.ForeignKey(CompanyProfile, related_name="company_type_company_fk", blank=True, null=True,
#                                    on_delete=models.CASCADE)
#
#
# # 현장
# class Factory(models.Model):
#     factory_id = models.AutoField(auto_created=True, primary_key=True, serialize=False)
#     factory_name = models.CharField(max_length=200)
#     factory_address = models.CharField(max_length=200)
#     factory_img = models.ImageField(upload_to="apps/static/assets/media/images/factory", blank=True, null=True)
#     company_fk = models.ForeignKey(CompanyProfile, related_name="factory_company_fk", blank=True, null=True,
#                                    on_delete=models.CASCADE)
#
#
# # 서버
# class Server(models.Model):
#     server_id = models.AutoField(auto_created=True, primary_key=True, serialize=False)
#     server_ip = models.CharField(max_length=200)
#     server_name = models.CharField(max_length=200)
#     factory_fk = models.ForeignKey(Factory, related_name="server_company_fk", blank=True, null=True,
#                                    on_delete=models.CASCADE)
#
#
# # 설비
# class Machine(models.Model):
#     machine_id = models.AutoField(auto_created=True, primary_key=True, serialize=False)
#     machine_name = models.CharField(max_length=200)
#     machine_img = models.ImageField(upload_to="apps/static/assets/media/images/machine", blank=True, null=True)
#     factory_fk = models.ForeignKey(Factory, related_name="machine_factory_fk", blank=True, null=True,
#
#                                    on_delete=models.CASCADE)
#
#
# # 설비 유형
# class MachineType(models.Model):
#     machine_type_id = models.AutoField(auto_created=True, primary_key=True, serialize=False)
#     machine_type_name = models.CharField(max_length=200)
#     machine_fk = models.ForeignKey(Machine, related_name="machine_type_machine_fk", blank=True, null=True,
#                                    on_delete=models.CASCADE)
#
#
# # 센서
# class Sensor(models.Model):
#     sensor_id = models.AutoField(auto_created=True, primary_key=True, serialize=False)
#     sensor_parent = models.CharField(max_length=200)
#     sensor_mac = models.CharField(max_length=200)
#     sensor_tag = models.CharField(max_length=200)
#     sensor_img = models.ImageField(upload_to="apps/static/assets/media/images/sensor", blank=True, null=True)
#
#     server_fk = models.ForeignKey(Server, related_name="sensor_server_fk", blank=True, null=True,
#                                   on_delete=models.CASCADE)
#     machine_fk = models.ForeignKey(Machine, related_name="sensor_machine_fk", blank=True, null=True,
#                                    on_delete=models.CASCADE)
#     factory_fk = models.ForeignKey(Factory, related_name="sensor_factory_fk", blank=True, null=True,
#                                    on_delete=models.CASCADE)
#
#
# # 센서 유형
# class SensorType(models.Model):
#     sensor_type_id = models.AutoField(auto_created=True, primary_key=True, serialize=False)
#
#     # 센서 일련 번호
#     sensor_type_model_no = models.CharField(max_length=200)
#     sensor_type_model_name = models.CharField(max_length=200)
#     sensor_brand_name = models.CharField(max_length=200)
#
#     sensor_fk = models.ForeignKey(Sensor, related_name="sensor_type_sensor_fk", blank=True, null=True,
#                                   on_delete=models.CASCADE)
#
#
# class SensorSetting(models.Model):
#     sensor_setting_id = models.AutoField(auto_created=True, primary_key=True, serialize=False)
#     sensor_fk = models.ForeignKey(Sensor, related_name="sensor_setting_sensor_fk", blank=True, null=True,
#                                   on_delete=models.CASCADE)
#
#
# class SensorOption(models.Model):
#     sensor_option_id = models.AutoField(auto_created=True, primary_key=True, serialize=False)
#     sensor_option_units = models.IntegerField(blank=True, null=True)
#     sensor_option_value = models.IntegerField(blank=True, null=True)
#     sensor_option_name = models.CharField(max_length=200)
#     sensor_setting_fk = models.ForeignKey(SensorSetting, related_name="sensor_option_sensor_setting_fk", blank=True,
#                                           null=True,
#                                           on_delete=models.CASCADE)
#
#
# # 데이터 특징; ex) 진동, 전류
# class Feature(models.Model):
#     feature_id = models.AutoField(auto_created=True, primary_key=True, serialize=False)
#     feature_name = models.CharField(max_length=200)
#     sensor_fk = models.ForeignKey(Sensor, related_name="feature_sensor_fk", blank=True, null=True,
#                                   on_delete=models.CASCADE)
#
#
# # 수집할 데이터 종류(RMS, Voltage, ...)
# class MeasurementType(models.Model):
#     measurement_id = models.AutoField(auto_created=True, primary_key=True, serialize=False)
#     measurement_name = models.CharField(max_length=200)
#
#     # 센서 ID, tag, type
#     sensor_type_fk = models.ForeignKey(SensorType, related_name="measurement_type_sensor_type_fk", blank=True,
#                                        null=True,
#                                        on_delete=models.CASCADE)
#     feature_fk = models.ForeignKey(Feature, related_name="measurement_type_feature_fk", blank=True, null=True,
#                                    on_delete=models.CASCADE)
#
#
# # 수집할 데이터 설정(RMS -> [g], Voltage -> [v], ...)
# class MeasurementOption(models.Model):
#     measurement_option_id = models.AutoField(auto_created=True, primary_key=True, serialize=False)
#     measurement_name = models.CharField(max_length=200)
#     measurement_unit = models.CharField(max_length=200)
#     measurement_range = models.CharField(max_length=200)
#
#     # type
#     sensor_type_fk = models.ForeignKey(SensorType, related_name="measurement_type_sensor_type_fk", blank=True,
#                                        null=True,
#                                        on_delete=models.CASCADE)
#
#     # Vibration, Amper, Proximity, ...
#     feature_fk = models.ForeignKey(Feature, related_name="measurement_type_feature_fk", blank=True, null=True,
#                                    on_delete=models.CASCADE)
#
#     # RMS, Voltage, Hall_fields, ...
#     measurement_type_fk = models.ForeignKey(MeasurementType, related_name="measurement_option_measurement_type_fk",
#                                             blank=True,
#                                             null=True,
#                                             on_delete=models.CASCADE)
#
#
# class TimeSeriesData(models.Model):
#     timeseries_data_id = models.AutoField(auto_created=True, primary_key=True, serialize=False)
#     timeseries_time = models.TimeField(blank=True, null=True)
#     timeseries_data = models.FloatField(blank=True, null=True)
#
#     # 센서 id, tag, type
#     sensor_type_fk = models.ForeignKey(SensorType, related_name="measurement_type_sensor_type_fk", blank=True,
#                                        null=True,
#                                        on_delete=models.CASCADE)
#
#     # Vibration, Amper, Proximity, ...
#     feature_fk = models.ForeignKey(Feature, related_name="measurement_type_feature_fk", blank=True, null=True,
#                                    on_delete=models.CASCADE)
#
#     # RMS, Voltage, Hall_fields, ...
#     measurement_type_fk = models.ForeignKey(MeasurementType, related_name="measurement_option_measurement_type_fk",
#                                             blank=True,
#                                             null=True,
#                                             on_delete=models.CASCADE)

