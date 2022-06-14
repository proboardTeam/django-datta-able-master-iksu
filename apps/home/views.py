# -*- encoding: utf-8 -*-
"""
Copyright (c) 2019 - present AppSeed.us
"""
import json

from django import template
from django.http import HttpResponse, HttpResponseRedirect, JsonResponse
from django.template import loader
from django.urls import reverse
from django.shortcuts import render, redirect
from django.views.generic import TemplateView

from apps.authentication.serializer import RequestSerializer
from apps.authentication import views
from apps.factory.models import CompanyProfile, CompanyType, Factory, Server, Machine, MachineType, Sensor
from django.db.utils import OperationalError
from django.contrib.auth.decorators import login_required
from django.utils.decorators import method_decorator

# api ---
import datetime

# 폴더가 한글, 한자 등 영어 외 문자로 계정 폴더 사용 시 주의 : temp 폴더 경로 변경할 것
import requests


@method_decorator(login_required, name="dispatch")
class Index(TemplateView):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    # 처음 화면
    def get(self, request, *args, **kwargs):
        try:
            # del request.session["userId"]
            user_id = request.session.get("userId")

            if user_id is None:
                views.login_view(request)

                return redirect("/")

            else:
                user_info = RequestSerializer.request_id_check(user_id)
                user = RequestSerializer.request_id_check_one(user_id)
                username = user.username
                # print(f'user name : {user.username}')

                start_time_str = datetime.datetime.now().strftime("%Y년 %m월 %d일 %H시 %M분 %S초")

                def sensor_func(m_id):
                    sensor_func_results = []
                    try:
                        sensor_names = Sensor.objects.filter(machine_fk=m_id).values("sensor_id", "sensor_tag")

                        for sensor_name in sensor_names:
                            sensor_id = sensor_name['sensor_id']
                            sensor_name_unit = sensor_name['sensor_tag']
                            sensor = Sensor.objects.get(sensor_id=sensor_id)
                            sensor_img_url = sensor.sensor_img.url[5:]
                            board_temp = 0
                            # s_results.update({
                            #     sensor_id: {
                            #         'sensor_id': sensor_id,
                            #         'sensor_tag': sensor_name_unit,
                            #         'sensor_url': sensor_img_url,
                            #         'BarPlot_XYZ_RMS_Values': [],
                            #         'BarPlot_XYZ_Kurtosis_Values': [],
                            #         'BarPlot_XYZ_Time': [],
                            #         'XYZBackgroundColor': ['#3e95cd'],
                            #         'XYZBorderColor': ['#3e95cd'],
                            #         'my_board_temperature': board_temperature,
                            #         'BarPlot_Board_Time': [],
                            #         'BarPlot_Board_Temperature_BackColor': ['#3e95cd'],
                            #         'BarPlot_Board_Temperature_BorderColor': ['#3e95cd'],
                            #         'Measurement_Start_Time': start_time_str,
                            #     }
                            # })
                            s_results = {
                                'sensor_id': sensor_id,
                                'sensor_tag': sensor_name_unit,
                                'sensor_url': sensor_img_url,
                                'BarPlot_RMS_XYZ_Values': [],
                                'BarPlot_Kurtosis_XYZ_Values': [],
                                'BarPlot_XYZ_Time': [],
                                'XYZBackgroundColor': ['#3e95cd'],
                                'XYZBorderColor': ['#3e95cd'],
                                'my_board_temperature': board_temp,
                                'BarPlot_Board_Time': [],
                                'BarPlot_Board_Temperature_BackColor': ['#3e95cd'],
                                'BarPlot_Board_Temperature_BorderColor': ['#3e95cd'],
                                'Measurement_Start_Time': start_time_str,
                            }

                            sensor_func_results.append(s_results)
                            print(f'센서 ID {sensor_id} : 센서 결과 {s_results}')

                    except Sensor.DoesNotExist or ValueError:
                        board_temp = 0
                        # s_results.update({
                        #     sensor_id: {
                        #         'sensor_id': sensor_id,
                        #         'sensor_tag': sensor_name_unit,
                        #         'sensor_url': sensor_img_url,
                        #         'BarPlot_XYZ_RMS_Values': [],
                        #         'BarPlot_XYZ_Kurtosis_Values': [],
                        #         'BarPlot_XYZ_Time': [],
                        #         'XYZBackgroundColor': ['#3e95cd'],
                        #         'XYZBorderColor': ['#3e95cd'],
                        #         'my_board_temperature': board_temperature,
                        #         'BarPlot_Board_Time': [],
                        #         'BarPlot_Board_Temperature_BackColor': ['#3e95cd'],
                        #         'BarPlot_Board_Temperature_BorderColor': ['#3e95cd'],
                        #         'Measurement_Start_Time': start_time_str,
                        #     }
                        # })
                        s_results = {
                            'sensor_id': 0,
                            'sensor_tag': '',
                            'sensor_url': '',
                            'BarPlot_RMS_XYZ_Values': [],
                            'BarPlot_Kurtosis_XYZ_Values': [],
                            'BarPlot_XYZ_Time': [],
                            'XYZBackgroundColor': ['#3e95cd'],
                            'XYZBorderColor': ['#3e95cd'],
                            'my_board_temperature': board_temp,
                            'BarPlot_Board_Time': [],
                            'BarPlot_Board_Temperature_BackColor': ['#3e95cd'],
                            'BarPlot_Board_Temperature_BorderColor': ['#3e95cd'],
                            'Measurement_Start_Time': start_time_str,
                        }

                        sensor_func_results.append(s_results)

                    return sensor_func_results

                def machine_func(f_id):
                    machine_func_results = []
                    machine_pending = 0

                    try:
                        machines = Machine.objects.filter(factory_fk=f_id).values("machine_id", "machine_name")

                        for machine in machines:
                            machine_id = machine['machine_id']
                            machine_name = machine['machine_name']
                            machine_get = Machine.objects.get(machine_id=machine_id)

                            machine_img_url = machine_get.machine_img.url[5:]

                            machine_type = MachineType.objects.get(machine_type_id=machine_get.machine_type_fk_id)
                            # m_results.update({
                            #     machine_id: {
                            #         'machine_id': machine_id,
                            #         'machine_name': machine_name,
                            #         'machine_img_url': machine_img_url,
                            #         'machine_type_name': machine_type.machine_type_name,
                            #         'sensor_results': sensor_func(machine_id, sensor_results),
                            #     }
                            # })
                            # m_results.append([
                            #     {
                            #         'machine_id': machine_id,
                            #         'machine_name': machine_name,
                            #         'machine_img_url': machine_img_url,
                            #         'machine_type_name': machine_type.machine_type_name,
                            #         'sensor_results': sensor_func(machine_id, sensor_results),
                            #      }
                            # ])
                            m_results = {
                                'machine_id': machine_id,
                                'machine_name': machine_name,
                                'machine_img_url': machine_img_url,
                                'machine_type_name': machine_type.machine_type_name,
                                'sensor_results': sensor_func(machine_id),
                            }

                            machine_func_results.append(m_results)
                            print(f'설비 ID {machine_id} : 설비 결과 {machine_func_results}')

                    except Machine.DoesNotExist or ValueError:
                        m_results = {
                            'machine_id': 0,
                            'machine_name': '',
                            'machine_img_url': '',
                            'machine_type_name': '',
                            'sensor_results': sensor_func(0),
                        }

                        machine_func_results.append(m_results)

                    return machine_func_results

                def factory_func(c_id):
                    factory_func_results = []

                    try:
                        factories = Factory.objects.filter(company_fk=c_id).values_list("factory_id", "factory_name")
                        factories = dict(factories)
                        for factory_id, factory_name in factories.items():

                            factory_get = Factory.objects.get(factory_id=factory_id)
                            factory_img_url = factory_get.factory_img.url[5:]

                            f_results = {
                                'factory_id': factory_id,
                                'factory_name': factory_name,
                                'factory_img_url': factory_img_url,
                                'machine_results': machine_func(factory_id), }

                            factory_func_results.append(f_results)
                            print(f'현장 ID {factory_id} : 현장 결과 {factory_func_results}')

                    except Factory.DoesNotExist or ValueError:
                        f_results = {
                            'factory_id': 0,
                            'factory_name': '',
                            'factory_img_url': '',
                            'machine_results': machine_func(0), }

                        factory_func_results.append(f_results)

                        # f_results.update({
                        #     factory_id: {
                        #         'factory_id': factory_id,
                        #         'factory_name': factory_name,
                        #         'factory_img_url': factory_img_url,
                        #         'machine_results': machine_func(factory_id, machine_results),
                        #     }
                        # })
                        # f_results.append([
                        #     {
                        #         'factory_id': factory_id,
                        #         'factory_name': factory_name,
                        #         'factory_img_url': factory_img_url,
                        #         'machine_results': machine_func(factory_id, machine_results),
                        #     }
                        # ])

                    return factory_func_results

                def company_func(result_id):
                    company_func_results = []

                    try:
                        company_get = CompanyProfile.objects.get(company_id=result_id)
                        company_type = CompanyType.objects.get(company_type_id=company_get.company_type_fk_id)
                        company_type_img_url = company_type.company_type_img.url[5:]

                        c_results = {
                            'company_id': company_get.company_id,
                            'company_name': company_get.company_name,
                            'company_type_img_url': company_type_img_url,
                            'factory_results': factory_func(company_get.company_id), }

                        company_func_results.append(c_results)
                        print(f'회사 ID {company_get.company_id} : 회사 조회 결과 {c_results}')

                    except CompanyProfile.DoesNotExist or ValueError:

                        c_results = {
                            'company_id': 0,
                            'company_name': '',
                            'company_type_img_url': '',
                            'factory_results': factory_func(0), }

                        company_func_results.append(c_results)

                    # c_results.update({
                    #     company_get.company_id: {
                    #         'company_id': company_get.company_id,
                    #         'company_name': company_get.company_name,
                    #         'company_type_img_url': company_type_img_url,
                    #         'factory_results': factory_func(company_get.company_id, factory_results),
                    #     }
                    # })
                    # c_results.append([
                    #     {
                    #         'company_id': company_get.company_id,
                    #         'company_name': company_get.company_name,
                    #         'company_type_img_url': company_type_img_url,
                    #         'factory_results': factory_func(company_get.company_id, factory_results),
                    #     }
                    # ])

                    return company_func_results

                def result_func():
                    results_array = []
                    view_points = []

                    try:
                        companies = CompanyProfile.objects.exclude(company_id=1).values_list("company_id", "company_name")
                        companies = dict(companies)
                        print('companies : ', companies)

                        try:
                            for company_id, company_name in companies.items():
                                print('try .. ')
                                # print(f'company_id {company_id}')
                                # print(f'company_name {company_name}')

                                # q_results.update({
                                #     company_id: {
                                #         'company_results': company_func(company_id, company_results),
                                #     }
                                # })

                                # q_results.append([
                                #     {
                                #         'company_results': company_func(company_id, company_results),
                                #     }
                                # ])
                                print('company_id : ', company_id)
                                view_points.append(company_id)
                                q_results = {'company_results': company_func(view_points[0]), }
                                results_array.append(q_results)

                                return results_array, view_points[0]

                        except TypeError:
                            q_results = {'company_results': company_func([0, ]), }
                            results_array.append(q_results)

                            return results_array, [0, ]

                    except CompanyProfile.DoesNotExist or IndexError:
                        q_results = {'company_results': company_func(0), }
                        results_array.append(q_results)

                        return results_array, [0, ]

                if username == "리쉐니에":

                    # company_info = RequestTotalSerializer.request_company_id_check_one(user_info.get().company_fk_id)
                    # print(f'회사명 : {company_info.company_name}')
                    # company_name = company_info.company_name
                    # company_type = CompanyType.objects.get(company_type_id=company_info.company_type_fk_id)
                    try:
                        (results, view_point) = result_func()
                    except TypeError:
                        results = []
                        view_point = 0

                    contents = {
                        'segment': 'index',
                        'username': username,
                        'view_point': view_point,
                        'results': results,
                    }
                    print(f"쿼리 조회 결과 {contents}")

                    return render(request, 'home/index.html', {'contents': contents})

                else:
                    board_temperature = 0
                    sensor_other_results = {}
                    machine_other_results = {}
                    factory_other_results = {}
                    company_other_results = {}
                    sensor_other_results.update({
                        0: {
                            'sensor_id': '',
                            'sensor_tag': '',
                            'sensor_url': '',
                            'BarPlot_XYZ_RMS_Values': [],
                            'BarPlot_XYZ_Kurtosis_Values': [],
                            'BarPlot_XYZ_Time': [],
                            'XYZBackgroundColor': ['#3e95cd'],
                            'XYZBorderColor': ['#3e95cd'],
                            'my_board_temperature': board_temperature,
                            'BarPlot_Board_Time': [],
                            'BarPlot_Board_Temperature_BackColor': ['#3e95cd'],
                            'BarPlot_Board_Temperature_BorderColor': ['#3e95cd'],
                            'Measurement_Start_Time': start_time_str,
                        }
                    })

                    machine_other_results.update({
                        0: {
                            'machine_id': 0,
                            'machine_name': '',
                            'machine_img_url': '',
                            'machine_type_name': '',
                            'sensor_results': sensor_other_results,
                        }
                    })

                    factory_other_results.update({
                        0: {
                            'factory_id': 0,
                            'factory_name': '',
                            'factory_img_url': '',
                            'machine_results': machine_other_results,
                        }
                    })

                    company_other_results.update({
                        0: {
                            'company_id': 0,
                            'company_name': '',
                            'company_type_img_url': '',
                            'factory_results': factory_other_results,
                        }
                    })

                    contents = {
                        'segment': 'index',
                        'username': username,
                        'results': company_other_results
                    }

                    html_template = loader.get_template('home/index.html')

                    return HttpResponse(html_template.render(contents, request))

        # 기타 데이터가 잘못된 경우
        except KeyError:
            views.login_view(request)

            return redirect("/")

    # 섹션 이동 시 화면 구성
    def post(self, request, *args, **kwargs):
        try:
            # del request.session["userId"]
            user_id = request.session.get("userId")

            if user_id is None:
                views.login_view(request)

                return redirect("/")

            else:
                user = RequestSerializer.request_id_check_one(user_id)
                username = user.username

                start_time_str = datetime.datetime.now().strftime("%Y년 %m월 %d일 %H시 %M분 %S초")

                def sensor_func(m_id):
                    sensor_func_results = []

                    try:
                        sensor_names = Sensor.objects.filter(machine_fk=m_id).values("sensor_id", "sensor_tag")

                        for sensor_name in sensor_names:
                            sensor_id = sensor_name['sensor_id']
                            sensor_name_unit = sensor_name['sensor_tag']
                            sensor = Sensor.objects.get(sensor_id=sensor_id)
                            sensor_img_url = sensor.sensor_img.url[5:]
                            board_temperature = 0

                            s_results = {
                                'sensor_id': sensor_id,
                                'sensor_tag': sensor_name_unit,
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

                            sensor_func_results.append(s_results)
                            print(f'센서 ID {sensor_id} : 센서 결과 {s_results}')

                    except Sensor.DoesNotExist or ValueError:
                        s_results = {
                            'sensor_id': 0,
                            'sensor_tag': '',
                            'sensor_url': '',
                            'BarPlot_RMS_XYZ_Values': [],
                            'BarPlot_Kurtosis_XYZ_Values': [],
                            'BarPlot_XYZ_Time': [],
                            'XYZBackgroundColor': ['#3e95cd'],
                            'XYZBorderColor': ['#3e95cd'],
                            'my_board_temperature': 0,
                            'BarPlot_Board_Time': [],
                            'BarPlot_Board_Temperature_BackColor': ['#3e95cd'],
                            'BarPlot_Board_Temperature_BorderColor': ['#3e95cd'],
                            'Measurement_Start_Time': start_time_str,
                        }

                        sensor_func_results.append(s_results)

                    return sensor_func_results

                def machine_func(f_id):
                    machine_func_results = []

                    try:
                        machines = Machine.objects.filter(factory_fk=f_id).values("machine_id", "machine_name")

                        for machine in machines:
                            machine_id = machine['machine_id']
                            machine_name = machine['machine_name']
                            machine_get = Machine.objects.get(machine_id=machine_id)
                            machine_img_url = machine_get.machine_img.url[5:]


                            machine_type = MachineType.objects.get(machine_type_id=machine_get.machine_type_fk_id)

                            m_results = {
                                'machine_id': machine_id,
                                'machine_name': machine_name,
                                'machine_img_url': machine_img_url,
                                'machine_type_name': machine_type.machine_type_name,
                                'sensor_results': sensor_func(machine_id),
                            }

                            machine_func_results.append(m_results)
                            print(f'설비 ID {machine_id} : 설비 결과 {machine_func_results}')

                    except Machine.DoesNotExist or ValueError:
                        m_results = {
                            'machine_id': 0,
                            'machine_name': '',
                            'machine_img_url': '',
                            'machine_type_name': '',
                            'sensor_results': sensor_func(0),
                        }

                        machine_func_results.append(m_results)

                    return machine_func_results

                def factory_func(c_id):
                    factory_func_results = []

                    try:
                        factories = Factory.objects.filter(company_fk=c_id).values_list("factory_id", "factory_name")
                        factories = dict(factories)
                        for factory_id, factory_name in factories.items():

                            factory_get = Factory.objects.get(factory_id=factory_id)
                            factory_img_url = factory_get.factory_img.url[5:]

                            f_results = {
                                'factory_id': factory_id,
                                'factory_name': factory_name,
                                'factory_img_url': factory_img_url,
                                'machine_results': machine_func(factory_id), }

                            factory_func_results.append(f_results)
                            print(f'현장 ID {factory_id} : 현장 결과 {factory_func_results}')

                    except Factory.DoesNotExist or ValueError:
                        f_results = {
                            'factory_id': 0,
                            'factory_name': '',
                            'factory_img_url': '',
                            'machine_results': machine_func(0), }

                        factory_func_results.append(f_results)

                    return factory_func_results

                def company_func(result_id):
                    company_func_results = []
                    try:
                        company_get = CompanyProfile.objects.get(company_id=result_id)
                        company_type = CompanyType.objects.get(company_type_id=company_get.company_type_fk_id)
                        company_type_img_url = company_type.company_type_img.url[5:]

                        c_results = {
                            'company_id': company_get.company_id,
                            'company_name': company_get.company_name,
                            'company_type_img_url': company_type_img_url,
                            'factory_results': factory_func(company_get.company_id), }

                        company_func_results.append(c_results)
                        print(f'회사 ID {company_get.company_id} : 회사 조회 결과 {c_results}')

                    except CompanyProfile.DoesNotExist or ValueError:
                        c_results = {
                            'company_id': 0,
                            'company_name': '',
                            'company_type_img_url': '',
                            'factory_results': factory_func(0), }

                        company_func_results.append(c_results)

                    return company_func_results

                def result_func(q_results, c_id):
                    results_array = []

                    q_results = {'company_results': company_func(c_id), }
                    results_array.append(q_results)

                    return results_array, c_id

                if username == "리쉐니에":

                    section_move = 1
                    query_results = {}
                    (results, view_point) = result_func(query_results, request.POST['company_id'])
                    viewer = {
                        'segment': 'index',
                        'username': username,
                        'view_point': view_point,
                        'results': results,
                        'section_move': section_move,
                    }
                    print(f"쿼리 조회 결과 {viewer}")

                    return render(request, 'home/index.html', {'viewer': viewer})

                else:
                    sensor_other_results = []
                    machine_other_results = []
                    factory_other_results = []
                    company_other_results = []
                    sensor_other_results.append([
                        {
                            'sensor_id': '',
                            'sensor_tag': '',
                            'sensor_url': '',
                            'BarPlot_XYZ_RMS_Values': [],
                            'BarPlot_XYZ_Kurtosis_Values': [],
                            'BarPlot_XYZ_Time': [],
                            'XYZBackgroundColor': ['#3e95cd'],
                            'XYZBorderColor': ['#3e95cd'],
                            'my_board_temperature': [],
                            'BarPlot_Board_Time': [],
                            'BarPlot_Board_Temperature_BackColor': ['#3e95cd'],
                            'BarPlot_Board_Temperature_BorderColor': ['#3e95cd'],
                            'Measurement_Start_Time': start_time_str,
                        }
                    ])

                    machine_other_results.append([
                        {
                            'machine_id': 0,
                            'machine_name': '',
                            'machine_img_url': '',
                            'machine_type_name': '',
                            'sensor_results': sensor_other_results,
                        }
                    ])

                    factory_other_results.append([
                        {
                            'factory_id': 0,
                            'factory_name': '',
                            'factory_img_url': '',
                            'machine_results': machine_other_results,
                        }
                    ])

                    company_other_results.append([
                        {
                            'company_id': 0,
                            'company_name': '',
                            'company_type_img_url': '',
                            'factory_results': factory_other_results,
                        }
                    ])

                    section_move = 0
                    query_results = {}
                    (results, view_point) = result_func(query_results, request.POST['company_id'])
                    contents = {
                        'segment': 'index',
                        'username': username,
                        'view_point': view_point,
                        'results': results,
                        'section_move': section_move,
                    }

                    html_template = loader.get_template('home/index.html')

                    return HttpResponse(html_template.render(contents, request))

        # 기타 데이터가 잘못된 경우
        except KeyError:

            return redirect("/")


@login_required(login_url="/login/")
def pages(request):
    context = {}
    # All resource paths end in .html.
    # Pick out the html file name from the url. And load that template.
    try:

        load_template = request.path.split('/')[-1]

        # 1. core의 url.py에 해당 코드 없이 /home/admin 링크를 걸면 이동 가능
        # admin.site.index_template = 'admin/custom.html'
        # admin.autodiscover()

        # 2. templates/admin 경로의 custom.html 삭제해도 이동 가능

        if load_template == 'admin':
            return HttpResponseRedirect(reverse('admin:index'))
        context['segment'] = load_template

        html_template = loader.get_template('home/' + load_template)
        return HttpResponse(html_template.render(context, request))

    except template.TemplateDoesNotExist:

        html_template = loader.get_template('home/page-404.html')
        return HttpResponse(html_template.render(context, request))

    except requests.exceptions.HTTPError:
        html_template = loader.get_template('home/page-500.html')
        return HttpResponse(html_template.render(context, request))
