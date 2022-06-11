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


