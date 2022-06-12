from django import template
from apps.factory.models import CompanyProfile, CompanyType, Factory, Machine, Sensor
import datetime

register = template.Library()


@register.simple_tag
def company_list():
    company = CompanyProfile.objects.exclude(company_id=1)
    # for i in company:
    #     print(i.company_id)
    return company


@register.simple_tag
def get_company_icon_url(view_point):
    company_type = CompanyType.objects.get(company_type_fk__company_id=view_point)
    company_type_img_url = company_type.company_type_img.url[6:]
    print(f'company_type: {company_type_img_url}')

    return company_type_img_url


@register.simple_tag
def factory_name_select_by_type(company_results_key):
    factory = Factory.objects.get(company_fk=company_results_key)
    return factory


@register.simple_tag
def factory_data_view_point(view_point):
    factory = {}
    factories = Factory.objects.filter(company_fk=view_point).values_list("factory_name", "factory_img")
    factories = dict(factories)
    for factory_name, factory_img_url in factories.items():
        factory_img_url = factory_img_url[5:]
        factory |= {factory_name: factory_img_url}
        print(f'factory: {factory}')
    return factory


@register.simple_tag
def machine_data_view_point(view_point):
    machine = {}
    machines = Machine.objects.filter(factory_fk__company_fk__company_id=view_point).values_list("machine_name", "machine_img")
    machines = dict(machines)

    for machine_name, machine_img_url in machines.items():
        machine_img_url = machine_img_url[5:]
        machine |= {machine_name: machine_img_url}
        print(f'machine: {machine}')

    return machine


@register.simple_tag
def sensor_img_view_point(view_point):
    sensor = {}
    sensors = Sensor.objects.filter(factory_fk__company_fk__company_id=view_point).values_list("sensor_tag", "sensor_img")
    sensors = dict(sensors)

    for sensor_name, sensor_img_url in sensors.items():
        sensor_img_url = sensor_img_url[5:]
        sensor |= {sensor_name: sensor_img_url}
        print(f'sensor: {sensor}')

    return sensor


@register.simple_tag
def sensor_data_view_point(view_point):
    sensor = {}
    sensors = Sensor.objects.filter(factory_fk__company_fk__company_id=view_point).values_list("sensor_id", "sensor_tag")
    sensors = dict(sensors)

    # for sensor_id, sensor_tag in sensors.items():
    #     sensor |= {sensor_id: sensor_tag}
    #     print(f'sensor: {sensor}')
    print(f'sensors: {sensors}')
    return sensors


@register.simple_tag
def sensor_init_data(sensor_id):
    sensor = Sensor.objects.get(sensor_id=sensor_id)
    try:
        sensor_img_url = sensor.sensor_img.url[5:]
    except ValueError:
        sensor_img_url = ''
    board_temperature = 0
    start_time_str = datetime.datetime.now().strftime("%Y년 %m월 %d일 %H시 %M분 %S초")

    s_results = {
        'sensor_id': sensor.sensor_id,
        'sensor_tag': sensor.sensor_tag,
        'sensor_url': sensor_img_url,
        'BarPlot_RMS_XYZ_Values': [],
        'BarPlot_Kurtosis_XYZ_Values': [],
        'BarPlot_XYZ_Time': [],
        'XYZBackgroundColor': ['#3e95cd'],
        'XYZBorderColor': ['#3e95cd'],
        'my_board_temperature': board_temperature,
        'BarPlot_Board_Time': [],
        'BarPlot_Board_Temperature_BackColor': ['#3e95cd'],
        'BarPlot_Board_Temperature_BorderColor': ['#3e95cd'],
        'Measurement_Start_Time': start_time_str,
    }

    return s_results
