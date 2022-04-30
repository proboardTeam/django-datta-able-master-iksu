import json
import time
from django import template
from apps.home.opcua_view import gql_process, opcua_process
from concurrent.futures import ThreadPoolExecutor
from django.shortcuts import HttpResponse, render
from django.http import JsonResponse

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
