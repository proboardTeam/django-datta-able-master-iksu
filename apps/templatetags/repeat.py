import json
import time
from django import template
from apps.home.opcua_view import gql_process, opcua_process
from concurrent.futures import ThreadPoolExecutor
from django.shortcuts import HttpResponse, render
from django.http import JsonResponse
from django.views import View
import datetime
from apps.home import views

register = template.Library()


@register.filter
def protocol_repeat(request, sensor_tag):

    start_time = time.time()
    with ThreadPoolExecutor(max_workers=2) as TPE:
        gql_future = TPE.submit(gql_process, sensor_tag)

        opcua_future = TPE.submit(opcua_process, sensor_tag)

    # gql_future = gql_process(sensor_tag)
    # opcua_future = opcua_process(sensor_tag)

    end_time = time.time() - start_time

    # print(f'gql_future : {gql_future.result()}')
    # print(f'opcua_future : {opcua_future.result()}')

    # return JsonResponse({'gql_future': gql_future.result(), 'opcua_future': opcua_future.result(),
    #                      'current process time': end_time}, status=201)

    # return JsonResponse({'gql_future': gql_future, 'opcua_future': opcua_future,  'current process time': end_time},
    #                     status=201)

    info = {
        'gql_result': gql_future.result(),
        'opcua_result': opcua_future.result(),
        'current_running_time': end_time,
    }

    return JsonResponse({'info': info}, status=201)
    # return render(request, 'home/compare.html', {'info': info})
    # return info


@register.filter
class JsonGraph(View):

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    @staticmethod
    def x_define(start, x_time, rms, kurtosis):
        date_list_x, background_color, border_color = [], [], []
        # d = datetime.datetime.fromtimestamp(x_time[0]).strftime("%Y년 %m월 %d일 %H시 %M분 %S초")
        # date_list_x.append(d)

        if x_time:
            for i in range(len(x_time)):
                d = datetime.datetime.fromtimestamp(x_time[i]).strftime("%H시 %M분 %S.%f초")
                # date_list_x.append(x_time[i] - start)
                date_list_x.append(d)

        else:
            return [], [], [], background_color, border_color

        print(f'date_list_x: {date_list_x}')
        bar_plot_x_rms_values = rms
        bar_plot_x_kurtosis_values = kurtosis
        bar_plot_x_time = date_list_x

        x_step_size = 0
        for i in range(len(x_time)):
            background_color.append('#3e95cd')
            border_color.append('#3e95cd')
            x_step_size += 0.5

        return bar_plot_x_rms_values, bar_plot_x_kurtosis_values, bar_plot_x_time, background_color, border_color

    @staticmethod
    def y_define(start, y_time, rms, kurtosis):
        date_list_y, background_color, border_color = [], [], []

        if y_time:
            for i in range(len(y_time)):
                # date_list_y.append(y_time[i] - start)
                d = datetime.datetime.fromtimestamp(y_time[i]).strftime("%H시 %M분 %S.%f초")
                print(f'converter_time_y: {d}')
                date_list_y.append(d)

        else:
            return [], [], [], background_color, border_color

        print(f'date_list_y: {date_list_y}')
        bar_plot_y_rms_values = rms
        bar_plot_y_kurtosis_values = kurtosis
        bar_plot_y_time = date_list_y

        for i in range(len(y_time)):
            background_color.append('#3e95cd')
            border_color.append('#3e95cd')

        return bar_plot_y_rms_values, bar_plot_y_kurtosis_values, bar_plot_y_time, background_color, border_color

    @staticmethod
    def z_define(start, z_time, rms, kurtosis):
        date_list_z, background_color, border_color = [], [], []

        if z_time:
            for i in range(len(z_time)):
                # date_list_z.append(z_time[i] - start)
                d = datetime.datetime.fromtimestamp(z_time[i]).strftime("%H시 %M분 %S.%f초")
                date_list_z.append(d)

        else:
            return [], [], [], background_color, border_color

        print(f'date_list_z: {date_list_z}')
        bar_plot_z_rms_values = rms
        bar_plot_z_kurtosis_values = kurtosis
        bar_plot_z_time = date_list_z

        for i in range(len(z_time)):
            background_color.append('#3e95cd')
            border_color.append('#3e95cd')

        return bar_plot_z_rms_values, bar_plot_z_kurtosis_values, bar_plot_z_time, background_color, border_color

    @staticmethod
    def xyz_define(**kwargs):
        xyz_rms_date_list, xyz_kurtosis_date_list, background_color, border_color = [], [], [], []

        plot_x_rms_pairs = dict(zip(kwargs.get('x_time'), kwargs.get('x_rms')))
        plot_y_rms_pairs = dict(zip(kwargs.get('y_time'), kwargs.get('y_rms')))
        plot_z_rms_pairs = dict(zip(kwargs.get('z_time'), kwargs.get('z_rms')))

        plot_x_kurtosis_pairs = dict(zip(kwargs.get('x_time'), kwargs.get('x_kurtosis')))
        plot_y_kurtosis_pairs = dict(zip(kwargs.get('y_time'), kwargs.get('y_kurtosis')))
        plot_z_kurtosis_pairs = dict(zip(kwargs.get('z_time'), kwargs.get('z_kurtosis')))

        # dictionary 형태로 update
        plot_y_rms_pairs.update(plot_x_rms_pairs)
        plot_z_rms_pairs.update(plot_y_rms_pairs)

        plot_y_kurtosis_pairs.update(plot_x_kurtosis_pairs)
        plot_z_kurtosis_pairs.update(plot_y_kurtosis_pairs)

        # 최종 결과 기준 key 값으로 정렬
        xyz_rms_results = dict(sorted(plot_z_rms_pairs.items()))
        xyz_kurtosis_results = dict(sorted(plot_z_kurtosis_pairs.items()))
        print(f"dictionary result: {xyz_rms_results}")

        xyz_rms_time_list = list(xyz_rms_results.keys())
        xyz_kurtosis_time_list = list(xyz_kurtosis_results.keys())

        # rms 값은 value 배열에 저장
        xyz_rms_value_list = list(xyz_rms_results.values())
        xyz_kurtosis_value_list = list(xyz_kurtosis_results.values())

        # 시간을 빼주고 다른 배열에 저장
        for i in range(len(xyz_rms_results)):
            xyz_rms_date_list.append(xyz_rms_time_list[i] - kwargs.get('start_time'))

        for i in range(len(xyz_rms_results)):
            xyz_kurtosis_date_list.append(xyz_kurtosis_time_list[i] - kwargs.get('start_time'))

        print(f"xyz result time : {xyz_rms_date_list}")

        bar_plot_xyz_rms_values = xyz_rms_value_list
        bar_plot_xyz_kurtosis_values = xyz_kurtosis_value_list

        bar_plot_xyz_time = xyz_rms_date_list

        for i in range(len(xyz_rms_time_list)):
            background_color.append('#3e95cd')
            border_color.append('#3e95cd')

        return bar_plot_xyz_time, bar_plot_xyz_rms_values, bar_plot_xyz_kurtosis_values, background_color, border_color

    def post(self, request, *args, **kwargs):
        x, y, z, xyz = 0, 1, 2, 3

        # RMS (rms acceleration; rms 가속도 : 일정 시간 동안의 가속도 제곱의 평균의 제곱근
        # my_rms, my_kurtosis, my_time, flags, start_time, my_board_temperatures = views.result_json(kwargs['sensor_tag'])
        my_rms, my_kurtosis, my_time, flags, start_time, my_board_temperature = views.result_json(request.POST['sensor_tag'])
        start_time_str = datetime.datetime.fromtimestamp(start_time).strftime("%Y년 %m월 %d일 %H시 %M분 %S초")
        print(f'my_rms[x] length : {len(my_rms[x])}, my_time[x] length : {len(my_time[x])}')
        print(f'my_rms[y] length : {len(my_rms[y])}, my_time[y] length : {len(my_time[y])}, my_time : {my_time[y]}')
        print(f'my_rms[z] length : {len(my_rms[z])}, my_time[z] length : {len(my_time[z])}')

        # you can change graph parameters
        (bar_plot_x_rms_values, bar_plot_x_kurtosis_values, bar_plot_x_time,
         x_background_color, x_border_color) = self.x_define(start_time, my_time[x], my_rms[x], my_kurtosis[x])
        (bar_plot_y_rms_values, bar_plot_y_kurtosis_values, bar_plot_y_time,
         y_background_color, y_border_color) = self.y_define(start_time, my_time[y], my_rms[y], my_kurtosis[y])
        (bar_plot_z_rms_values, bar_plot_z_kurtosis_values, bar_plot_z_time,
         z_background_color, z_border_color) = self.z_define(start_time, my_time[z], my_rms[z], my_kurtosis[z])
        (bar_plot_xyz_time, bar_plot_xyz_rms_values, bar_plot_xyz_kurtosis_values, xyz_background_color,
         xyz_border_color) = self.xyz_define(
            start_time=start_time, x_time=my_time[x], y_time=my_time[y], z_time=my_time[z],
            x_rms=my_rms[x], y_rms=my_rms[y], z_rms=my_rms[z],
            x_kurtosis=my_kurtosis[x], y_kurtosis=my_kurtosis[y], z_kurtosis=my_kurtosis[z]
        )

        context = {
            'Measurement_Start_Time': start_time_str,
            'BarPlot_X_RMS_Values': bar_plot_x_rms_values,
            'BarPlot_Y_RMS_Values': bar_plot_y_rms_values,
            'BarPlot_Z_RMS_Values': bar_plot_z_rms_values,
            'BarPlot_XYZ_RMS_Values': bar_plot_xyz_rms_values,
            'BarPlot_X_Kurtosis_Values': bar_plot_x_kurtosis_values,
            'BarPlot_Y_Kurtosis_Values': bar_plot_y_kurtosis_values,
            'BarPlot_Z_Kurtosis_Values': bar_plot_z_kurtosis_values,
            'BarPlot_XYZ_Kurtosis_Values': bar_plot_xyz_kurtosis_values,
            'BarPlot_Board_Temperature': my_board_temperature,
            'BarPlot_X_Time': bar_plot_x_time,
            'BarPlot_Y_Time': bar_plot_y_time,
            'BarPlot_Z_Time': bar_plot_z_time,
            'BarPlot_XYZ_Time': bar_plot_xyz_time,
            'XBackgroundColor': x_background_color,
            'XBorderColor': x_border_color,
            'YBackgroundColor': y_background_color,
            'YBorderColor': y_border_color,
            'ZBackgroundColor': z_background_color,
            'ZBorderColor': z_border_color,
            'XYZBackgroundColor': xyz_background_color,
            'XYZBorderColor': xyz_border_color,
        }

        # schedule.every(60).seconds.do(result_json)

        # while request:
        #     schedule.run_pending()
        #     time.sleep(1)

        return JsonResponse({'context': context}, status=201)
