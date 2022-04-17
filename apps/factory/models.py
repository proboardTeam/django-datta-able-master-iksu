from django.db import models


# Create your models here.
class CompanyProfile(models.Model):
    company_id = models.AutoField(auto_created=True, primary_key=True, serialize=False)
    company_name = models.CharField(max_length=200)


class Machine(models.Model):
    machine_id = models.AutoField(auto_created=True, primary_key=True, serialize=False)
    machine_name = models.CharField(max_length=200)
    company_fk = models.ForeignKey(CompanyProfile, related_name="machine", blank=True, null=True, on_delete=models.CASCADE)


class Sensor(models.Model):
    sensor_id = models.AutoField(auto_created=True, primary_key=True, serialize=False)
    sensor_parent = models.CharField(max_length=200)
    sensor_mac = models.CharField(max_length=200)
    sensor_tag = models.CharField(max_length=200)
    machine_fk = models.ForeignKey(Machine, related_name="sensor_machine_fk", blank=True, null=True, on_delete=models.CASCADE)

