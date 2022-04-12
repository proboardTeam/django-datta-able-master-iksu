from django.db import models


# Create your models here.
class CompanyProfile(models.Model):
    company_id = models.AutoField(auto_created=True, primary_key=True, serialize=False)
    company_name = models.CharField(max_length=200)
    # company_numbering = models.IntegerField()
    user_fk = models.ForeignKey("authentication.UserProfile", blank=True, null=True, related_name="userprofile",
                                on_delete=models.CASCADE)
    # machine_fk = models.ForeignKey(Machine, related_name="machine", blank=True, null=True, on_delete=models.CASCADE)
    # sensor_fk = models.ForeignKey(Sensor, related_name="machine_sensor_fk", blank=True, null=True, on_delete=models.CASCADE)


class Machine(models.Model):
    machine_id = models.AutoField(auto_created=True, primary_key=True, serialize=False)
    machine_name = models.CharField(max_length=200)
    # sensor_fk = models.ForeignKey(Sensor, blank=True, null=True, related_name="sensor", on_delete=models.CASCADE)
    company_fk = models.ForeignKey(CompanyProfile, related_name="machine", blank=True, null=True, on_delete=models.CASCADE)


class Sensor(models.Model):
    # user = models.OneToOneField(AbstractUser, on_delete=models.CASCADE)
    # sensor_parent = 0 : base_station | sensor_parent != 0 : other
    sensor_id = models.AutoField(auto_created=True, primary_key=True, serialize=False)
    sensor_parent = models.CharField(max_length=200)
    sensor_mac = models.CharField(max_length=200)
    sensor_tag = models.CharField(max_length=200)
    machine_fk = models.ForeignKey(Machine, related_name="sensor_machine_fk", blank=True, null=True, on_delete=models.CASCADE)

