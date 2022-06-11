import time
import datetime
import json
import numpy as np
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlparse

from django.http import JsonResponse

from apps.factory.serializer import RequestTotalSerializer
from apps.graph.statistics import HighPassFilter
from apps.protocol.graphql import DataAcquisition, get_draw_data_by_graphql, gql_process
from apps.protocol.opc_ua import get_draw_data_by_opcua, opcua_process


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
