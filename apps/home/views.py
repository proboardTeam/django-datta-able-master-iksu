# -*- encoding: utf-8 -*-
"""
Copyright (c) 2019 - present AppSeed.us
"""

import sys
import os

from django import template
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, HttpResponseRedirect, JsonResponse
from django.template import loader
from django.urls import reverse
from django.shortcuts import render, redirect
from apps.authentication.serializer import RequestSerializer
from apps.authentication import views, forms, models
from apps.factory.models import CompanyProfile, Server, Machine, Sensor
from django.db.utils import OperationalError
from apps.factory.serializer import RequestFactorySerializer
from concurrent.futures import ThreadPoolExecutor
from django.views import View
from django.core import serializers

# api ---
import logging
from urllib.parse import urlparse
import time
import datetime
import json
import numpy as np
import math

# 폴더가 한글, 한자 등 영어 외 문자로 계정 폴더 사용 시 주의 : temp 폴더 경로 변경할 것
import scipy.signal
from gql import Client, client, gql
from gql.transport.requests import RequestsHTTPTransport
import requests
from scipy import stats
import schedule
import pytz

# serverIP = '25.9.7.151'
# serverIP = '25.52.52.52'
# serverIP = '25.58.137.19'
# serverIP = '25.105.77.110'

# serverUrl = urlparse('http://{:s}:8000/graphql'.format(serverIP))


@login_required(login_url="/login/")
def index(request):
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
            print(f'user name : {user.username}')

            try:
                company_info = RequestFactorySerializer.request_company_id_check_one(user_info.get().company_fk_id)
                print(f'회사명 : {company_info.company_name}')
                company_name = company_info.company_name
                request.session["companyName"] = company_name

                server = Server.objects.get(company_fk_id=company_info.company_id)
                print(f'server IP : {server.server_name}')
                request.session["serverIP"] = server.server_name

                machine_list = RequestFactorySerializer.request_machine_id_check(company_info.company_id)
                machine_names = list(machine_list.values_list('machine_name', flat=True).values())
                machine_names = list(m['machine_name'] for m in machine_names)
                machine_company_fk = machine_list.values_list('company_fk_id', flat=True)
                print(f'machine_names : {machine_names}')

                sensor_info = RequestFactorySerializer.request_sensor_all_from_company(machine_company_fk[0])
                sensor_tags = list(sensor_info.values_list("sensor_tag", flat=True).values())
                sensor_tags = list(s['sensor_tag'] for s in sensor_tags)
                print(f'sensor_tags : {sensor_tags}')
                # mac_id = Sensor.objects.values_list('sensor_mac')
                # for mac_unit in mac_id:
                #     print(mac_unit)

                if sensor_tags:
                    my_rms, my_kurtosis, my_time, flags, start_time, board_temperature = result_json(request, sensor_tags[0])

                    if not my_rms or not my_kurtosis or not my_time or not flags or start_time is None or board_temperature is None:
                        contents = {'segment': 'index', 'username': username, 'company_name': company_name,
                                    'machine_names': machine_names, 'sensor_tags': sensor_tags,
                                    'BarPlot_XYZ_RMS_Values': [],
                                    'BarPlot_XYZ_Kurtosis_Values': [],
                                    'BarPlot_XYZ_Time': [],
                                    'XYZBackgroundColor': [],
                                    'XYZBorderColor': [],
                                    'my_board_temperature': 0}

                        return render(request, 'home/index.html', {'contents': contents})

                    print(f'board_temperature = {board_temperature}')
                    # print(user_info)
                    # user_tuple = models.UserProfile.objects.values_list('id', 'username')
                    # print(user_tuple)

                    # if company_info is True:
                    #     print(company_info.get().company_id)

                    # print(info2)
                    # test = models.UserProfile.objects.get(id=user_id)
                    # print(test)
                    # print(test.id)
                    # print(test.username)
                    # print(test.company)

                    x, y, z = 0, 1, 2
                    print(f'my_rms length : {len(my_rms)}, my_time[x] length : {len(my_time[x])}')

                    # you can change graph parameters
                    (bar_plot_xyz_time, bar_plot_xyz_rms_values, bar_plot_xyz_kurtosis_values, xyz_background_color,
                     xyz_border_color) = ShowGraph.xyz_define(
                        start_time=start_time, x_time=my_time[x], y_time=my_time[y], z_time=my_time[z],
                        x_rms=my_rms[x], y_rms=my_rms[y], z_rms=my_rms[z],
                        x_kurtosis=my_kurtosis[x], y_kurtosis=my_kurtosis[y], z_kurtosis=my_kurtosis[z]
                    )

                    contents = {'segment': 'index', 'username': username, 'company_name': company_name,
                                'machine_names': machine_names, 'sensor_tags': sensor_tags,
                                'BarPlot_XYZ_RMS_Values': bar_plot_xyz_rms_values,
                                'BarPlot_XYZ_Kurtosis_Values': bar_plot_xyz_kurtosis_values,
                                'BarPlot_XYZ_Time': bar_plot_xyz_time,
                                'XYZBackgroundColor': xyz_background_color,
                                'XYZBorderColor': xyz_border_color,
                                'my_board_temperature': board_temperature}

                    # html_template = loader.get_template('home/index.html')
                    #
                    # return HttpResponse(html_template.render(contents, request))

                    return render(request, 'home/index.html', {'contents': contents})

                else:
                    contents = {'segment': 'index', 'username': username, 'company_name': company_name,
                                'machine_names': machine_names, 'sensor_tags': [],
                                'BarPlot_XYZ_RMS_Values': [],
                                'BarPlot_XYZ_Kurtosis_Values': [],
                                'BarPlot_XYZ_Time': [],
                                'XYZBackgroundColor': [],
                                'XYZBorderColor': [],
                                'my_board_temperature': 0}

                    html_template = loader.get_template('home/index.html')

                    return HttpResponse(html_template.render(contents, request))

            except CompanyProfile.DoesNotExist or Machine.DoesNotExist or Sensor.DoesNotExist or OperationalError:
                html_template = loader.get_template('home/index.html')
                contents = {'segment': 'index', 'username': username, 'company_name': [],
                            'machine_names': [], 'sensor_tags': [],
                            'BarPlot_XYZ_RMS_Values': [],
                            'BarPlot_XYZ_Kurtosis_Values': [],
                            'BarPlot_XYZ_Time': [],
                            'XYZBackgroundColor': [],
                            'XYZBorderColor': [],
                            'my_board_temperature': 0}
                return HttpResponse(html_template.render(contents, request))

    except KeyError:
        views.login_view(request)

        return redirect("/")


# ---
class HighPassFilter(object):
    @staticmethod
    def get_highpass_coefficients(lowcut, sampleRate, order=5):
        nyq = 0.5 * sampleRate
        low = lowcut / nyq
        b, a = scipy.signal.butter(order, [low], btype='highpass')
        return b, a

    @staticmethod
    def run_highpass_filter(data, lowcut, sampleRate, order=5):
        if lowcut >= sampleRate / 2.0:
            return data * 0.0
        b, a = HighPassFilter.get_highpass_coefficients(lowcut, sampleRate, order=order)
        y = scipy.signal.filtfilt(b, a, data, padtype='even')
        return y

    @staticmethod
    def perform_hpf_filtering(data, sampleRate, hpf=3):
        if hpf == 0:
            return data
        data[0:6] = data[13:7:-1]  # skip compressor settling
        data = HighPassFilter.run_highpass_filter(
            data=data,
            lowcut=3,
            sampleRate=sampleRate,
            order=1,
        )
        data = HighPassFilter.run_highpass_filter(
            data=data,
            lowcut=int(hpf),
            sampleRate=sampleRate,
            order=2,
        )
        return data


class FourierTransform(object):

    @staticmethod
    def perform_fft_windowed(signal, fs, winSize, nOverlap, window, detrend=True, mode='lin'):
        assert (nOverlap < winSize)
        assert (mode in ('magnitudeRMS', 'magnitudePeak', 'lin', 'log'))

        # Compose window and calculate 'coherent gain scale factor'
        w = scipy.signal.get_window(window, winSize)
        # http://www.bores.com/courses/advanced/windows/files/windows.pdf
        # Bores signal processing: "FFT window functions: Limits on FFT analysis"
        # F. J. Harris, "On the use of windows for harmonic analysis with the
        # discrete Fourier transform," in Proceedings of the IEEE, vol. 66, no. 1,
        # pp. 51-83, Jan. 1978.
        coherentGainScaleFactor = np.sum(w) / winSize

        # Zero-pad signal if smaller than window
        padding = len(w) - len(signal)
        if padding > 0:
            signal = np.pad(signal, (0, padding), 'constant')

        # Number of windows
        k = int(np.fix((len(signal) - nOverlap) / (len(w) - nOverlap)))

        # Calculate psd
        j = 0
        spec = np.zeros(len(w))
        for i in range(0, k):
            segment = signal[j:j + len(w)]
            if detrend is True:
                segment = scipy.signal.detrend(segment)
            winData = segment * w
            # Calculate FFT, divide by sqrt(N) for power conservation,
            # and another sqrt(N) for RMS amplitude spectrum.
            fftData = np.fft.fft(winData, len(w)) / len(w)
            sqAbsFFT = abs(fftData / coherentGainScaleFactor) ** 2
            spec = spec + sqAbsFFT
            j = j + len(w) - nOverlap

        # Scale for number of windows
        spec = spec / k

        # If signal is not complex, select first half
        if len(np.where(np.iscomplex(signal))[0]) == 0:
            stop = int(math.ceil(len(w) / 2.0))
            # Multiply by 2, except for DC and fmax. It is asserted that N is even.
            spec[1:stop - 1] = 2 * spec[1:stop - 1]
        else:
            stop = len(w)
        spec = spec[0:stop]
        freq = np.round(float(fs) / len(w) * np.arange(0, stop), 2)

        if mode == 'lin':  # Linear Power spectrum
            return (spec, freq)
        elif mode == 'log':  # Log Power spectrum
            return (10. * np.log10(spec), freq)
        elif mode == 'magnitudeRMS':  # RMS Magnitude spectrum
            return (np.sqrt(spec), freq)
        elif mode == 'magnitudePeak':  # Peak Magnitude spectrum
            return (np.sqrt(2. * spec), freq)


class GraphQLClient(object):
    CONNECT_TIMEOUT = 15  # [sec]
    RETRY_DELAY = 10  # [sec]
    MAX_RETRIES = 3  # [-]

    class Decorators(object):
        @staticmethod
        def autoConnectingClient(wrappedMethod):
            def wrapper(obj, *args, **kwargs):
                for retry in range(GraphQLClient.MAX_RETRIES):
                    try:
                        return wrappedMethod(obj, *args, **kwargs)
                    except Exception:
                        pass
                    try:
                        obj._logger.warning(
                            '(Re)connecting to GraphQL service.'
                        )
                        obj.reconnect()
                    except ConnectionRefusedError:
                        obj._logger.warn(
                            'Connection refused. Retry in 10s.'.format(
                                GraphQLClient.RETRY_DELAY
                            )
                        )
                        time.sleep(GraphQLClient.RETRY_DELAY)
                else:  # So the exception is exposed.
                    obj.reconnect()
                    return wrappedMethod(obj, *args, **kwargs)

            return wrapper

    def __init__(self, serverUrl):
        self._logger = logging.getLogger(self.__class__.__name__)
        self.serverUrl = serverUrl
        self.connect(
            serverUrl.geturl()
        )

    def __enter__(self):
        self.connect(
            self.serverUrl.geturl()
        )
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self._client = None

    def connect(self, url):
        host = url.split('//')[1].split('/')[0]
        request = requests.get(url,
                               headers={
                                   'Host': str(host),
                                   'Accept': 'text/html',
                               }
                               )
        request.raise_for_status()
        csrf = request.cookies['csrftoken']
        self._client = Client(
            transport=RequestsHTTPTransport(url=url,
                                            cookies={"csrftoken": csrf},
                                            headers={'x-csrftoken': csrf}
                                            ),
            fetch_schema_from_transport=True
        )

    def disconnect(self):
        self._client = None

    def reconnect(self):
        self.disconnect()
        self.connect(
            self.serverUrl.geturl()
        )

    @Decorators.autoConnectingClient
    def execute_query(self, querytext):
        query = gql(querytext)
        return self._client.execute(query)


class DataAcquisition(object):
    LOGGER = logging.getLogger('DataAcquisition')

    @staticmethod
    def get_sensor_data(serverUrl, macId, starttime, endtime, limit, axis):
        with GraphQLClient(serverUrl) as client:
            querytext = '''
			{ deviceManager { device(macId:"''' + macId + '''") {
                __typename
                ... on GrapheneVibrationCombo {vibrationTimestampHistory(start:"''' + str(
                starttime) + '''", end:"''' + str(endtime) + '''", limit:''' + str(limit) + ''', axis:"''' + axis + '''")}
            }}}
            '''
            result = client.execute_query(querytext)
            times = \
                result['deviceManager']['device']['vibrationTimestampHistory']

            dates, values, fRanges, numSamples, sampleRates = ([], [], [], [], [])
            # print(result['deviceManager']['device'])
            # print(times)
            for t in times:
                result = DataAcquisition.get_sensor_measurement(
                    client,
                    macId,
                    t
                )
                # print(result)
                dates.append(t)
                deviceData = result['deviceManager']['device']
                values.append(
                    deviceData['vibrationArray']['rawSamples']
                )

                fRanges.append(
                    deviceData['vibrationArray']['formatRange']
                )
                numSamples.append(
                    deviceData['vibrationArray']['numSamples']
                )
                sampleRates.append(
                    deviceData['vibrationArray']['sampleRate']
                )
                # print(deviceData)
                # print(len(values[0]))
                # print(deviceData['vibrationArray'])

            # valuesX, valuesY, valuesZ, fRangesX, fRangesY, fRangesZ, sampleRatesX, sampleRatesY, sampleRatesZ, hpf=3
            if axis == "X":
                # print(f'values={values}, fRangesX={fRanges}, sampleRatesX={sampleRates}')
                hpf_value = hpf_loop(hpf=6, valuesX=values, fRangesX=fRanges, sampleRatesX=sampleRates)
            elif axis == "Y":
                hpf_value = hpf_loop(hpf=6, valuesY=values, fRangesY=fRanges, sampleRatesY=sampleRates)
            elif axis == "Z":
                hpf_value = hpf_loop(hpf=6, valuesZ=values, fRangesZ=fRanges, sampleRatesZ=sampleRates)
            elif axis == "XYZ":
                hpf_value = hpf_loop(hpf=6, valuesXYZ=values, fRangesXYZ=fRanges, sampleRatesXYZ=sampleRates)

            return hpf_value, dates
            # return (values, dates, fRanges, numSamples, sampleRates)

    @staticmethod
    def get_sensor_measurement(client, macId, isoDate):
        querytext = '''
        { deviceManager { device(macId:"''' + macId + '''") {
        __typename
        ... on GrapheneVibrationCombo { vibrationArray(isoDate: "''' + isoDate + '''") {
        numSamples rawSamples sampleRate formatRange axis }}
        }}}
        '''
        return client.execute_query(querytext)

    @staticmethod
    # def get_temperature_data(serverUrl, macId, timeZone):
    def get_temperature_data(serverUrl, macId):
        with GraphQLClient(serverUrl) as client:
            result = DataAcquisition.get_temperature_measurement(
                client,
                macId
            )
            date = round(datetime.datetime.now().timestamp() * 1000)
            deviceData = result['deviceManager']['device']
            temperature = deviceData['temperature']
            return (date, temperature)

    @staticmethod
    def get_temperature_measurement(client, macId):
        querytext = '''
        { deviceManager { device(macId:"''' + macId + '''") {
        __typename
        ... on GrapheneVibrationCombo { temperature }
        }}}
        '''
        return client.execute_query(querytext)


class Initiation(object):

    @staticmethod
    def get_init_wakeup(server_url, mac_id, period):
        with GraphQLClient(server_url) as user:
            query_text = '''
                        mutation{
                          setMaxBeatPeriod(macId: "''' + mac_id + '''", period: ''' + str(period) + '''){
                            __typename
                            ... on GrapheneSetMaxBeatPeriodMutation {ok}
                          }
                        }
                        '''

        return user.execute_query(query_text)

    @staticmethod
    def reboot_sensor(server_url, mac_id):
        with GraphQLClient(server_url) as user:
            query_text = '''
                mutation {
                    reboot(macId:"''' + mac_id + '''"){
                        ok
                        }
                    }
                '''
            return user.execute_query(query_text)

    @staticmethod
    def set_sample_rate(server_url, mac_id, sample_rate):
        with GraphQLClient(server_url) as user:
            query_text = '''
                mutation {
                    setSampleRate(macId:"''' + mac_id + '''",sampleRate:''' + str(sample_rate) + '''){
                        ok
                        }
                    }
                '''
            return user.execute_query(query_text)

    @staticmethod
    def set_num_samples(server_url, mac_id, num_samples):
        with GraphQLClient(server_url) as user:
            query_text = '''
                mutation {
                    setNumSamples(numSamples:''' + str(num_samples) + ''',macId:"''' + mac_id + '''"){
                        ok
                        }
                    }
                '''
            return user.execute_query(query_text)

    @staticmethod
    def start_vibration_measurement(server_url, mac_id, hpf, prefetch, sample_rate, format_range, threshold, axis,
                                    num_samples):
        with GraphQLClient(server_url) as user:
            query_text = '''
                mutation {
                    vibrationRunSetup(hpf:''' + str(hpf) + ''',prefetch:''' + str(prefetch) + ''',sampleRate:''' + str(
                sample_rate) + ''',formatRange:''' + str(format_range) + ''',threshold:''' + str(
                threshold) + ''',axis:"''' + axis + '''", numSamples:''' + str(num_samples) + ''', macId:"''' + mac_id + '''"){
                        ok
                        }
                    }
                '''
            return user.execute_query(query_text)

    @staticmethod
    def set_queue_enabled(server_url, mac_id, enabled):
        with GraphQLClient(server_url) as user:
            query_text = '''
                mutation {
                    setQueueEnabled(enabled:''' + enabled + ''',macId: "''' + mac_id + '''"){
                        ok
                        }
                    }
                '''
            return user.execute_query(query_text)

    @staticmethod
    def set_queue_interval(server_url, mac_id, capture):
        with GraphQLClient(server_url) as user:
            query_text = '''
                mutation {
                    setQueueInterval(interval:''' + str(capture) + ''',macId: "''' + mac_id + '''"){
                        ok
                        }
                    }
                '''
            return user.execute_query(query_text)

    @staticmethod
    def set_tilt_guard_roll(server_url, degrees, mac_id):
        with GraphQLClient(server_url) as user:
            query_text = '''
                mutation {
                    setTiltGuardRoll(degrees:''' + str(degrees) + ''',macId: "''' + mac_id + '''"){
                        ok
                        }
                    }
                '''
            return user.execute_query(query_text)


def init(request):
    mac_list = Sensor.objects.values_list('sensor_mac', flat=True)

    serverIP = request.session.get("serverIP")
    serverUrl = urlparse('http://{:s}:8000/graphql'.format(serverIP))

    for mac_id in mac_list:
        # print(mac_id)
        Initiation.reboot_sensor(server_url=serverUrl, mac_id=mac_id)
        Initiation.get_init_wakeup(server_url=serverUrl, mac_id=mac_id, period=120)
        # Initiation.set_tilt_guard_roll(server_url=serverUrl, degrees=60, mac_id="5e:54:8a:8a")

    return redirect("/")


# transformed = data => rms | kurtosis
# valuesX, valuesY, valuesZ, fRangesX, fRangesY, fRangesZ, sampleRatesX, sampleRatesY, sampleRatesZ, hpf=3
def hpf_loop(**data):
    transformed = []
    x_valid = data.get('valuesX')
    y_valid = data.get('valuesY')
    z_valid = data.get('valuesZ')
    x_range_valid = data.get('fRangesX')
    y_range_valid = data.get('fRangesY')
    z_range_valid = data.get('fRangesZ')
    x_sample_valid = data.get('sampleRatesX')
    y_sample_valid = data.get('sampleRatesY')
    z_sample_valid = data.get('sampleRatesZ')

    x_flag = y_flag = z_flag = 1
    if x_valid is None or not x_valid or len(x_valid) == 0:
        x_flag = 0
    if y_valid is None or not y_valid or len(y_valid) == 0:
        y_flag = 0
    if z_valid is None or not z_valid or len(z_valid) == 0:
        z_flag = 0

    if x_flag == 1:
        v = x_valid
        f = x_range_valid
        s = x_sample_valid

        for i in range(len(f)):
            v[i] = [d / 512.0 * f[i] for d in v[i]]
            v[i] = HighPassFilter.perform_hpf_filtering(
                data=v[i],
                sampleRate=s[i],
                hpf=6
            )
            transformed.append(v[i])
            # print(f'transformed : {transformed}')

        # print(f'transformed done : {transformed}')
        return transformed

    if y_flag == 1:
        v = y_valid
        f = y_range_valid
        s = y_sample_valid

        # print(f'len(f) = {len(f)}')

        for i in range(len(f)):
            v[i] = [d / 512.0 * f[i] for d in v[i]]
            v[i] = HighPassFilter.perform_hpf_filtering(
                data=v[i],
                sampleRate=s[i],
                hpf=6
            )
            transformed.append(v[i])
            # print(f'y_transformed : {transformed}')

        return transformed

    if z_flag == 1:
        for (v, f, s) in list(zip([z_valid], [z_range_valid], [z_sample_valid])):

            # print(f'len(f) = {len(f)}')

            for i in range(len(f)):
                try:
                    v[i] = [d / 512.0 * f[i] for d in v[i]]
                    v[i] = HighPassFilter.perform_hpf_filtering(
                        data=v[i],
                        sampleRate=s[i],
                        hpf=6
                    )
                    transformed.append(v[i])

                except TypeError:
                    transformed.append(v[i])

        return transformed

    if x_flag == y_flag == z_flag == 1:
        for (v, f, s) in list(zip([x_valid, y_valid, z_valid], [x_range_valid, y_range_valid, z_range_valid],
                                  [x_sample_valid, y_sample_valid, z_sample_valid])):

            # print(f'len(f) = {len(f)}')

            for i in range(len(f)):
                try:
                    v[i] = [d / 512.0 * f[i] for d in v[i]]
                    v[i] = HighPassFilter.perform_hpf_filtering(
                        data=v[i],
                        sampleRate=s[i],
                        hpf=6
                    )
                    transformed.append(v[i])

                except TypeError:
                    transformed.append(v[i])

        return transformed

    else:
        return None


def rms(ndarray):
    return np.sqrt(np.mean(ndarray ** 2))


# request,
def result_json(request, sensor_tag):
    start_proc = time.time()

    logging.basicConfig(level=logging.INFO)
    logging.getLogger("graphql").setLevel(logging.WARNING)

    # sensor = Sensor.objects.filter(sensor_tag=sensor_tag)
    # mac_id = sensor.get().sensor_mac

    # replace xx.xx.xx.xx with the IP address of your server
    # serverIP = "25.3.15.233" #BKT
    # serverIP = '25.55.114.208'  # KPU
    # serverIP = '25.12.181.157' #SKT1
    # serverIP = '25.17.10.130' #SKT2
    serverIP = request.session.get("serverIP")
    serverUrl = urlparse('http://{:s}:8000/graphql'.format(serverIP))

    sensor = RequestFactorySerializer.request_sensor_name_check(sensor_tag)

    # replace xx:xx:xx:xx with your sensors macId
    # macId = '82:8e:2c:a3' #BKT
    # macId = 'c7:f0:3e:b4'  # KPU
    # macId='94:f3:9e:df' #SKT1
    # macId='05:92:6d:a7' #SKT2
    mac_id = sensor.get().sensor_mac

    # change settings
    hpf = 6  # high pass filter (Hz)
    # endtime = datetime.datetime.now() - datetime.timedelta(minutes=30)
    # starttime = endtime - datetime.timedelta(minutes=10)

    # endtime = datetime.datetime.now() - datetime.timedelta(hours=9)
    # starttime = endtime - datetime.timedelta(hours=12)

    # endtime = endtime.isoformat()
    # starttime = starttime.isoformat()

    endtime = time.time() - 3600 * 48
    starttime = endtime - 3600 * 48

    end_time_stamp_str = datetime.datetime.fromtimestamp(endtime).strftime("%Y-%m-%dT%H:%M:%S.%f+00:00")
    start_time_stamp_str = datetime.datetime.fromtimestamp(starttime).strftime("%Y-%m-%dT%H:%M:%S.%f+00:00")

    # start_time_stamp_str = "2022-04-25T00:00:00"
    # end_time_stamp_str = "2022-04-25T23:59:59"

    print(f'start time = {start_time_stamp_str}, end time = {end_time_stamp_str}')

    # endtime = "2022-04-12"
    # starttime = "2022-04-13"

    timeZone = "Asia/Seoul"  # local time zone
    limit = 1000  # limit limits the number of returned measurements
    axisX = 'X'  # axis allows to select data from only 1 or multiple axes
    axisY = 'Y'  # axis allows to select data from only 1 or multiple axes
    axisZ = 'Z'  # axis allows to select data from only 1 or multiple axes
    axis_xyz = 'XYZ'

    # (valuesX, datesX, fRangesX, numSamples, sampleRatesX) = DataAcquisition.get_sensor_data(
    #     serverUrl=serverUrl,
    #     macId=mac_id,
    #     starttime=start_time_stamp_str,
    #     endtime=end_time_stamp_str,
    #     limit=limit,
    #     axis=axisX
    # )
    # (valuesY, datesY, fRangesY, numSamples, sampleRatesY) = DataAcquisition.get_sensor_data(
    #     serverUrl=serverUrl,
    #     macId=mac_id,
    #     starttime=start_time_stamp_str,
    #     endtime=end_time_stamp_str,
    #     limit=limit,
    #     axis=axisY
    # )
    # (valuesZ, datesZ, fRangesZ, numSamples, sampleRatesZ) = DataAcquisition.get_sensor_data(
    #     serverUrl=serverUrl,
    #     macId=mac_id,
    #     starttime=start_time_stamp_str,
    #     endtime=end_time_stamp_str,
    #     limit=limit,
    #     axis=axisZ
    # )

    RmsTimeValue = []  # stores XRms time value
    XRmsRawValue = []  # stores XRms raw value
    YRmsRawValue = []  # stores YRms raw value
    ZRmsRawValue = []  # stores ZRms raw value

    gKurtXRawValue = []  # stores XKurt raw value
    gKurtYRawValue = []  # stores YKurt raw value
    gKurtZRawValue = []  # stores ZKurt raw value

    boardTemperatureValue = []  # stores boardTemperature raw Value

    # values = data
    (values_x, datesX) = DataAcquisition.get_sensor_data(
        serverUrl=serverUrl,
        macId=mac_id,
        starttime=start_time_stamp_str,
        endtime=end_time_stamp_str,
        limit=limit,
        axis=axisX
    )

    if not values_x or not datesX:
        return [], [], \
               [], \
               [], None, None

    epoch_dates_x = []
    i = 0
    for date in datesX:
        try:
            # d = round(datetime.datetime.strptime(date, "%Y-%m-%dT%H:%M:%S.%f+00:00").timestamp() * 1000)
            d = datetime.datetime.strptime(date, "%Y-%m-%dT%H:%M:%S.%f+00:00").timestamp()
            epoch_dates_x.append(d)

            # val_x = np.array(values_x[i])
            XRmsRawValue.append(rms(values_x[i]))
            gKurtXRawValue.append(stats.kurtosis(values_x[i]))
            i += 1

        except TypeError or IndexError or ValueError:
            try:
                # d = round(datetime.datetime.strptime(date, "%Y-%m-%dT%H:%M:%S.%f+00:00").timestamp() * 1000)
                d = datetime.datetime.strptime(date, "%Y-%m-%dT%H:%M:%S.%f+00:00").timestamp()
                epoch_dates_x.append(d)

                XRmsRawValue.append(None)
                gKurtXRawValue.append(None)
                i += 1

            except TypeError or IndexError or ValueError:
                print("Error in date data format")

    # print(f"x_val_length : {len(values_x)}, x_date_length : {len(datesX)}")
    # print(f"x_val : {values_x}")
    # print(f"x_rms : {XRmsRawValue}, x_kurtosis : {gKurtXRawValue}")

    (values_y, datesY) = DataAcquisition.get_sensor_data(
        serverUrl=serverUrl,
        macId=mac_id,
        starttime=start_time_stamp_str,
        endtime=end_time_stamp_str,
        limit=limit,
        axis=axisY
    )

    epoch_dates_y = []
    i = 0
    for date in datesY:
        try:
            # d = round(datetime.datetime.strptime(date, "%Y-%m-%dT%H:%M:%S.%f+00:00").timestamp() * 1000)
            d = datetime.datetime.strptime(date, "%Y-%m-%dT%H:%M:%S.%f+00:00").timestamp()
            epoch_dates_y.append(d)

            # val_y = np.array(values_y[i])
            YRmsRawValue.append(rms(values_y[i]))
            gKurtYRawValue.append(stats.kurtosis(values_y[i]))
            i += 1

        except TypeError or IndexError or ValueError:
            try:
                # d = round(datetime.datetime.strptime(date, "%Y-%m-%dT%H:%M:%S.%f+00:00").timestamp() * 1000)
                d = datetime.datetime.strptime(date, "%Y-%m-%dT%H:%M:%S.%f+00:00").timestamp()
                epoch_dates_y.append(d)

                YRmsRawValue.append(None)
                gKurtYRawValue.append(None)
                i += 1

            except TypeError or IndexError or ValueError:
                print("Error in date data format")

    (values_z, datesZ) = DataAcquisition.get_sensor_data(
        serverUrl=serverUrl,
        macId=mac_id,
        starttime=start_time_stamp_str,
        endtime=end_time_stamp_str,
        limit=limit,
        axis=axisZ
    )

    epoch_dates_z = []
    i = 0
    for date in datesZ:
        try:
            # d = round(datetime.datetime.strptime(date, "%Y-%m-%dT%H:%M:%S.%f+00:00").timestamp() * 1000)
            d = datetime.datetime.strptime(date, "%Y-%m-%dT%H:%M:%S.%f+00:00").timestamp()
            epoch_dates_z.append(d)

            val_z = np.array(values_z[i])
            ZRmsRawValue.append(rms(val_z))
            gKurtZRawValue.append(stats.kurtosis(val_z))
            i += 1

        except TypeError or IndexError or ValueError:
            try:
                # d = round(datetime.datetime.strptime(date, "%Y-%m-%dT%H:%M:%S.%f+00:00").timestamp() * 1000)
                d = datetime.datetime.strptime(date, "%Y-%m-%dT%H:%M:%S.%f+00:00").timestamp()
                epoch_dates_z.append(d)

                ZRmsRawValue.append(None)
                gKurtZRawValue.append(None)
                i += 1

            except TypeError or IndexError or ValueError:
                print("Error in date data format")

    # (values_xyz, dates_xyz) = DataAcquisition.get_sensor_data(
    #     serverUrl=serverUrl,
    #     macId=mac_id,
    #     starttime=start_time_stamp_str,
    #     endtime=end_time_stamp_str,
    #     limit=limit,
    #     axis=axis_xyz
    # )

    print(f'x length : {len(epoch_dates_x)}, y length : {len(epoch_dates_y)}, z length : {len(epoch_dates_z)}')

    epoch_dates_length = 0
    if (len(epoch_dates_x) > len(epoch_dates_y)) and (len(epoch_dates_x) > len(epoch_dates_z)):
        epoch_dates_length = len(epoch_dates_x)

    elif (len(epoch_dates_y) > len(epoch_dates_x)) and (len(epoch_dates_y) > len(epoch_dates_z)):
        epoch_dates_length = len(epoch_dates_y)

    elif (len(epoch_dates_z) > len(epoch_dates_x)) and (len(epoch_dates_z) > len(epoch_dates_y)):
        epoch_dates_length = len(epoch_dates_z)

    (dateT, temperature) = DataAcquisition.get_temperature_data(
        serverUrl=serverUrl,
        macId=mac_id
    )

    # convert vibration data to 'g' units
    # for i in range(len(fRangesX)):
    #     valuesX[i] = [d / 512.0 * fRangesX[i] for d in valuesX[i]]
    #     valuesX[i] = HighPassFilter.perform_hpf_filtering(
    #         data=valuesX[i],
    #         sampleRate=sampleRatesX[i],
    #         hpf=hpf
    #     )
    #
    # for i in range(len(fRangesY)):
    #     valuesY[i] = [d / 512.0 * fRangesY[i] for d in valuesY[i]]
    #     valuesY[i] = HighPassFilter.perform_hpf_filtering(
    #         data=valuesY[i],
    #         sampleRate=sampleRatesY[i],
    #         hpf=hpf
    #     )
    #
    # for i in range(len(fRangesZ)):
    #     valuesZ[i] = [d / 512.0 * fRangesZ[i] for d in valuesZ[i]]
    #
    #     valuesZ[i] = HighPassFilter.perform_hpf_filtering(
    #         data=valuesZ[i],
    #         sampleRate=sampleRatesZ[i],
    #         hpf=hpf
    #     )

    # for i in range(len(valuesX)):
    #     vals = np.array(valuesX[i])
    #     XRmsRawValue.append(np.sqrt(np.mean(vals ** 2)))
    #     gKurtXRawValue.append(stats.kurtosis(vals))
    # for i in range(len(valuesY)):
    #     vals = np.array(valuesY[i])
    #     YRmsRawValue.append(np.sqrt(np.mean(vals ** 2)))
    #     gKurtYRawValue.append(stats.kurtosis(vals))
    # for i in range(len(valuesZ)):
    #     vals = np.array(valuesZ[i])
    #     ZRmsRawValue.append(np.sqrt(np.mean(vals ** 2)))
    #     gKurtZRawValue.append(stats.kurtosis(vals))

    x_flag = y_flag = z_flag = 1
    if len(epoch_dates_x) == 0:
        x_flag = 0
    if len(epoch_dates_y) == 0:
        y_flag = 0
    if len(epoch_dates_z) == 0:
        z_flag = 0

    # with open(
    #         'C:/Users/user/Iqunet_reshenie_old_test/Reshenie_Old_wirevibsensor/BKT_reshenie_Vibration_PWR_data12.json',
    #         'w') as json_file:
    #     for i in range(len(epoch_dates_x)):
    #         data2 = [{"serviceId": "76", "deviceId": "reshenie1", "timestamp": epoch_dates_x[i],
    #                   "contents": {"XRms": XRmsRawValue[i], "gKurtX": gKurtXRawValue[i], "YRms": None, "gKurtY": None,
    #                                "ZRms": None, "gKurtZ": None, "BoradTemperature": None}}]
    #         json.dump(data2, json_file, indent=4)
    #
    #     for i in range(len(epoch_dates_y)):
    #         data2 = [{"serviceId": "76", "deviceId": "reshenie1", "timestamp": epoch_dates_y[i],
    #                   "contents": {"XRms": None, "gKurtX": None, "YRms": YRmsRawValue[i], "gKurtY": gKurtYRawValue[i],
    #                                "ZRms": None, "gKurtZ": None, "BoradTemperature": None}}]
    #         json.dump(data2, json_file, indent=4)
    #
    #     for i in range(len(epoch_dates_z)):
    #         data2 = [{"serviceId": "76", "deviceId": "reshenie1", "timestamp": epoch_dates_z[i],
    #                   "contents": {"XRms": None, "gKurtX": None, "YRms": None, "gKurtY": None, "ZRms": ZRmsRawValue[i],
    #                                "gKurtZ": gKurtZRawValue[i], "BoradTemperature": None}}]
    #         json.dump(data2, json_file, indent=4)

    # convert vibration data to 'g' units and plot data
    # franges = fRangesX | Y | Z = formatRange
    # for i in range(len(fRangesX)):
    #     valuesX[i] = [d / 512.0 * fRangesX[i] for d in valuesX[i]]
    #
    # for i in range(len(fRangesY)):
    #     valuesY[i] = [d / 512.0 * fRangesY[i] for d in valuesY[i]]
    #
    # for i in range(len(fRangesZ)):
    #     valuesZ[i] = [d / 512.0 * fRangesZ[i] for d in valuesZ[i]]

    # plt.figure()
    # plt.plot(values[i])
    # plt.title(str(dates[i]))

    # json_results = None
    # for i in range(len(epoch_dates_x)):
    #     data2 = [{"serviceId": "76", "deviceId": "reshenie1", "timestamp": epoch_dates_x[i],
    #               "contents": {"XRms": XRmsRawValue[i], "gKurtX": gKurtXRawValue[i], "YRms": None, "gKurtY": None,
    #                            "ZRms": None, "gKurtZ": None, "BoradTemperature": temperature}}]
    #     json_results = json.dumps(data2, indent=4)
    #     json_datas = json.loads(json_results)
    #     for json_data in json_datas:
    #         print(json_data['contents']['XRms'])
    #     print("=====================================================================================")
    #
    # for i in range(len(epoch_dates_y)):
    #     data2 = [{"serviceId": "76", "deviceId": "reshenie1", "timestamp": epoch_dates_y[i],
    #               "contents": {"XRms": None, "gKurtX": None, "YRms": YRmsRawValue[i], "gKurtY": gKurtYRawValue[i],
    #                            "ZRms": None, "gKurtZ": None, "BoradTemperature": None}}]
    #     json_results = json.dumps(data2, indent=4)
    #     json_datas = json.loads(json_results)
    #     for json_data in json_datas:
    #         print(json_data['contents']['YRms'])
    #     print("=====================================================================================")
    #
    # for i in range(len(epoch_dates_z)):
    #     data2 = [{"serviceId": "76", "deviceId": "reshenie1", "timestamp": epoch_dates_z[i],
    #               "contents": {"XRms": None, "gKurtX": None, "YRms": None, "gKurtY": None, "ZRms": ZRmsRawValue[i],
    #                            "gKurtZ": gKurtZRawValue[i], "BoradTemperature": None}}]
    #     json_results = json.dumps(data2, indent=4)
    #     json_datas = json.loads(json_results)
    #     for json_data in json_datas:
    #         print(json_data['contents']['ZRms'])
    #     print("=====================================================================================")

    base_time = time.mktime(datetime.datetime.strptime(start_time_stamp_str, "%Y-%m-%dT%H:%M:%S.%f+00:00").timetuple())
    print(f"start base time : {base_time}")

    # inner repeat
    epoch_dates_x_timeline = []
    json_x_datas = []

    # outer repeat

    x_rms_contents = []
    x_kurt_contents = []

    for i in range(len(epoch_dates_x)):
        data_x = [{"serviceId": "76", "deviceId": "reshenie1", "timestamp": epoch_dates_x[i],
                   "contents": {"XRms": XRmsRawValue[i], "gKurtX": gKurtXRawValue[i],
                                "YRms": None, "gKurtY": None,
                                "ZRms": None, "gKurtZ": None,
                                "BoardTemperature": temperature}}]

        # x_time_converter = datetime.datetime.fromtimestamp(epoch_dates_x[i]).strftime(
        #     "%Y-%m-%d %H:%M:%S.%f+00:00")
        # epoch_dates_x_timeline.append(x_time_converter)
        epoch_dates_x_timeline.append(epoch_dates_x[i])
        json_results = json.dumps(data_x, indent=4)
        json_x_datas.extend(json.loads(json_results))

    for json_data in json_x_datas:
        x_rms_contents.append(json_data['contents']['XRms'])
        x_kurt_contents.append(json_data['contents']['gKurtX'])

    # print(f'x_rms_contents: {x_rms_contents}')
    # print(f'x_kurt_contents: {x_kurt_contents}')
    # print(f'x_board_temperatures: {x_board_temperatures}')
    # print(f'epoch_dates_x_timeline: {epoch_dates_x_timeline}')
    #
    # print("=====================================================================================")

    epoch_dates_y_timeline = []
    json_y_datas = []
    y_rms_contents = []
    y_kurt_contents = []
    for i in range(len(epoch_dates_y)):
        data_y = [{"serviceId": "76", "deviceId": "reshenie1", "timestamp": epoch_dates_y[i],
                   "contents": {"XRms": None, "gKurtX": None,
                                "YRms": YRmsRawValue[i], "gKurtY": gKurtYRawValue[i],
                                "ZRms": None, "gKurtZ": None,
                                "BoardTemperature": temperature}}]

        # y_time_converter = datetime.datetime.fromtimestamp(epoch_dates_y[i]).strftime(
        #     "%Y-%m-%d %H:%M:%S.%f+00:00")
        # epoch_dates_y_timeline.append(y_time_converter)
        epoch_dates_y_timeline.append(epoch_dates_y[i])
        json_results = json.dumps(data_y, indent=4)
        json_y_datas.extend(json.loads(json_results))

    for json_data in json_y_datas:
        y_rms_contents.append(json_data['contents']['YRms'])
        y_kurt_contents.append(json_data['contents']['gKurtY'])

    # print(f'y_rms_contents: {y_rms_contents}')
    # print(f'y_kurt_contents: {y_kurt_contents}')
    # print(f'y_board_temperatures: {y_board_temperatures}')
    # print(f'epoch_dates_y_timeline: {epoch_dates_y_timeline}')
    #
    # print("=====================================================================================")

    epoch_dates_z_timeline = []
    json_z_datas = []
    z_rms_contents = []
    z_kurt_contents = []
    for i in range(len(epoch_dates_z)):
        data_z = [{"serviceId": "76", "deviceId": "reshenie1", "timestamp": epoch_dates_z[i],
                   "contents": {"XRms": None, "gKurtX": None,
                                "YRms": None, "gKurtY": None,
                                "ZRms": ZRmsRawValue[i], "gKurtZ": gKurtZRawValue[i],
                                "BoardTemperature": temperature}}]

        # z_time_converter = datetime.datetime.fromtimestamp(epoch_dates_z[i]).strftime(
        #     "%Y-%m-%d %H:%M:%S.%f+00:00")
        # epoch_dates_z_timeline.append(z_time_converter)
        epoch_dates_z_timeline.append(epoch_dates_z[i])
        json_results = json.dumps(data_z, indent=4)
        json_z_datas.extend(json.loads(json_results))

    for json_data in json_z_datas:
        z_rms_contents.append(json_data['contents']['ZRms'])
        z_kurt_contents.append(json_data['contents']['gKurtZ'])

    end_proc = time.time() - start_proc
    print(f"graphql process time : {end_proc}")

    # print(f'z_rms_contents: {z_rms_contents}')
    # print(f'z_kurt_contents: {z_kurt_contents}')
    # print(f'z_board_temperatures: {z_board_temperatures}')
    # print(f'epoch_dates_z_timeline: {epoch_dates_z_timeline}')
    #
    # print("=====================================================================================")

    json_t_datas = []
    board_temperature = None
    data_t = [{"serviceId": "76", "deviceId": "reshenie1", "timestamp": dateT,
               "contents": {"XRms": None, "gKurtX": None,
                            "YRms": None, "gKurtY": None,
                            "ZRms": None, "gKurtZ": None,
                            "BoradTemperature": temperature}}]
    json_results = json.dumps(data_t, indent=4)
    json_t_datas.extend(json.loads(json_results))

    for json_data in json_t_datas:
        board_temperature = json_data['contents']['BoradTemperature']

    return [x_rms_contents, y_rms_contents, z_rms_contents], [x_kurt_contents, y_kurt_contents, z_kurt_contents], \
           [epoch_dates_x_timeline, epoch_dates_y_timeline, epoch_dates_z_timeline], \
           [x_flag, y_flag, z_flag], base_time, board_temperature

    # data2 = [{"serviceId": "76", "deviceId": "reshenie1", "timestamp": dateT,
    #                      "contents": {"XRms": None, "gKurtX": None,
    #                                   "YRms": None, "gKurtY": None,
    #                                   "ZRms": None, "gKurtZ": None,
    #                                   "BoradTemperature": temperature}}]
    # json_results = json.dumps(data2, indent=4)

    # if x_flag == 1 and y_flag == z_flag:
    #
    #     return x_rms_contents, x_kurt_contents, x_board_temperatures, epoch_dates_x_timeline, x_flag, y_flag, z_flag
    #     # return JsonResponse({'RMS': x_rms_contents, 'Kurtosis': x_kurt_contents, 'nowTime': epoch_dates_x_timeline},
    #     #                     status=201)
    #
    # elif y_flag == 1 and x_flag == z_flag:
    #
    #     return y_rms_contents, y_kurt_contents, y_board_temperatures, epoch_dates_y_timeline, x_flag, y_flag, z_flag
    #     # return JsonResponse({'RMS': y_rms_contents, 'Kurtosis': y_kurt_contents, 'nowTime': epoch_dates_y_timeline},
    #     #                     status=201)
    #
    # elif z_flag == 1 and x_flag == y_flag:
    #
    #     return z_rms_contents, z_kurt_contents, z_board_temperatures, epoch_dates_z_timeline, x_flag, y_flag, z_flag
    #     # return JsonResponse({'RMS': z_rms_contents, 'Kurtosis': z_kurt_contents, 'nowTime': epoch_dates_z_timeline},
    #     #                     status=201)

    # return JsonResponse({"serviceId": "76", "deviceId": "reshenie1", "timestamp": dateT,
    #                      "contents": {"XRms": None, "gKurtX": None,
    #                                   "YRms": None, "gKurtY": None,
    #                                   "ZRms": None, "gKurtZ": None,
    #                                   "BoradTemperature": temperature}}, status=201)


class ShowGraph(View):

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

    def get(self, request, *args, **kwargs):
        x, y, z, xyz = 0, 1, 2, 3

        # RMS (rms acceleration; rms 가속도 : 일정 시간 동안의 가속도 제곱의 평균의 제곱근
        request.session['sensor_tag'] = kwargs['sensor_tag']
        sensor_tag = request.session.get('sensor_tag')
        my_rms, my_kurtosis, my_time, flags, start_time, my_board_temperature = result_json(kwargs['sensor_tag'])
        start_time_str = datetime.datetime.fromtimestamp(start_time).strftime("%Y년 %m월 %d일 %H시 %M분 %S초")
        print(f'my_rms[x] length : {len(my_rms[x])}, my_time[x] length : {len(my_time[x])}')
        print(f'my_rms[y] length : {len(my_rms[y])}, my_time[y] length : {len(my_time[y])}, my_time : {my_time[y]}')
        print(f'my_rms[z] length : {len(my_rms[z])}, my_time[z] length : {len(my_time[z])}')
        print(f'my_board_temperature : {my_board_temperature}')

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
            'sensor_tag': sensor_tag
        }

        # schedule.every(60).seconds.do(result_json)

        # while request:
        #     schedule.run_pending()
        #     time.sleep(1)

        return render(request, 'home/show-graph.html', {'context': context})


class OtherDataGraph(View):
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

    def get(self, request, *args, **kwargs):
        x, y, z, xyz = 0, 1, 2, 3

        # RMS (rms acceleration; rms 가속도 : 일정 시간 동안의 가속도 제곱의 평균의 제곱근
        my_rms, my_kurtosis, my_time, flags, start_time, my_board_temperature = result_json(kwargs['sensor_tag'])
        start_time_str = datetime.datetime.fromtimestamp(start_time).strftime("%Y년 %m월 %d일 %H시 %M분 %S초")
        print(f'my_rms[x] length : {len(my_rms[x])}, my_time[x] length : {len(my_time[x])}')
        print(f'my_rms[y] length : {len(my_rms[y])}, my_time[y] length : {len(my_time[y])}, my_time : {my_time[y]}')
        print(f'my_rms[z] length : {len(my_rms[z])}, my_time[z] length : {len(my_time[z])}')

        # you can change graph parameters
        (bar_plot_x_rms_values, bar_plot_x_kurtosis_values, bar_plot_x_time,
         x_background_color, x_border_color) = self.x_define(start_time, my_time[x], my_rms[x], my_kurtosis[x])
        (bar_plot_y_rms_values, bar_plot_y_kurtosis_values, bar_plot_y_time,
         y_background_color, y_border_color) = self.y_define(start_time, my_time[y], my_rms[y], my_kurtosis[y], )
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

        return render(request, 'home/other-data.html', {'context': context})


def test(request):
    total_count = 100
    total_count1 = 101
    total_count2 = 102

    # you can change graph parameters
    country_names = ['temp', 'humid', 'PM2.5', 'PM10', 'TVOC']
    country_names1 = ['total', 'humid', 'weather', 'PM2.5', 'PM10']
    country_names2 = ['11', '12', '13', '14', '15', '16', '17']

    bar_plot_values = []

    bar_plot_values1 = []

    bar_plot_values2_1 = []
    bar_plot_values2_2 = []
    bar_plot_values2_3 = []
    bar_plot_values2_4 = []
    bar_plot_values2_5 = []

    context = {'totalCount': total_count, 'countryNames': country_names, 'Bar_Plot_Values': bar_plot_values,
               'totalCount1': total_count1, 'countryNames1': country_names1, 'Bar_Plot_Values1': bar_plot_values1,
               'totalCount2': total_count2, 'countryNames2': country_names2,
               'Bar_Plot_Values2_1': bar_plot_values2_1, 'Bar_Plot_Values2_2': bar_plot_values2_2,
               'Bar_Plot_Values2_3': bar_plot_values2_3, 'Bar_Plot_Values2_4': bar_plot_values2_4,
               'Bar_Plot_Values2_5': bar_plot_values2_5}

    return render(request, 'tester/index.html', context)


def gql_process(request, sensor_tag):
    time.sleep(1)

    start_proc = time.time()

    logging.basicConfig(level=logging.INFO)
    logging.getLogger("graphql").setLevel(logging.WARNING)

    # replace xx.xx.xx.xx with the IP address of your server
    # serverIP = "25.3.15.233" #BKT
    # serverIP = '25.55.114.208'  # KPU
    # serverIP = '25.12.181.157' #SKT1
    # serverIP = '25.17.10.130' #SKT2
    # serverIP = '25.9.7.151'
    serverIP = request.session.get("serverIP")
    serverUrl = urlparse('http://{:s}:8000/graphql'.format(serverIP))

    sensor = RequestFactorySerializer.request_sensor_name_check(sensor_tag)

    # replace xx:xx:xx:xx with your sensors macId
    # macId = '82:8e:2c:a3' #BKT
    # macId = 'c7:f0:3e:b4'  # KPU
    # macId='94:f3:9e:df' #SKT1
    # macId='05:92:6d:a7' #SKT2
    mac_id = sensor.get().sensor_mac

    # change settings
    hpf = 6  # high pass filter (Hz)
    # endtime = datetime.datetime.now() - datetime.timedelta(minutes=30)
    # starttime = endtime - datetime.timedelta(minutes=10)

    # endtime = datetime.datetime.now() - datetime.timedelta(hours=9)
    # starttime = endtime - datetime.timedelta(hours=12)

    # endtime = endtime.isoformat()
    # starttime = starttime.isoformat()

    # endtime = "2022-04-12"
    # starttime = "2022-04-13"

    endtime = time.time() - 3600 * 48
    starttime = endtime - 3600 * 48

    end_time_stamp_str = datetime.datetime.fromtimestamp(endtime).strftime("%Y-%m-%dT%H:%M:%S.%f+00:00")
    start_time_stamp_str = datetime.datetime.fromtimestamp(starttime).strftime("%Y-%m-%dT%H:%M:%S.%f+00:00")

    # start_time_stamp_str = "2022-04-19"
    # end_time_stamp_str = "2022-04-20"

    # start_time_stamp_str = "2022-03-23"
    # end_time_stamp_str = "2022-03-25"

    timeZone = "Asia/Seoul"  # local time zone
    limit = 1000  # limit limits the number of returned measurements
    axisX = 'X'  # axis allows to select data from only 1 or multiple axes
    axisY = 'Y'  # axis allows to select data from only 1 or multiple axes
    axisZ = 'Z'  # axis allows to select data from only 1 or multiple axes

    RmsTimeValue = []  # stores XRms time value
    XRmsRawValue = []  # stores XRms raw value
    YRmsRawValue = []  # stores YRms raw value
    ZRmsRawValue = []  # stores ZRms raw value
    gKurtXRawValue = []  # stores XKurt raw value
    gKurtYRawValue = []  # stores YKurt raw value
    gKurtZRawValue = []  # stores ZKurt raw value
    boardTemperatureValue = []  # stores boardTemperature raw Value

    # values = data
    (values_x, datesX) = DataAcquisition.get_sensor_data(
        serverUrl=serverUrl,
        macId=mac_id,
        starttime=start_time_stamp_str,
        endtime=end_time_stamp_str,
        limit=limit,
        axis=axisX
    )

    epoch_dates_x = []
    i = 0
    for date in datesX:
        try:
            d = datetime.datetime.strptime(date, "%Y-%m-%dT%H:%M:%S.%f+00:00").timestamp()
            epoch_dates_x.append(d)

            XRmsRawValue.append(rms(values_x[i]))
            gKurtXRawValue.append(stats.kurtosis(values_x[i]))
            i += 1

        except TypeError or IndexError or ValueError:
            try:
                d = datetime.datetime.strptime(date, "%Y-%m-%dT%H:%M:%S.%f+00:00").timestamp()
                epoch_dates_x.append(d)

                XRmsRawValue.append(None)
                gKurtXRawValue.append(None)
                i += 1

            except TypeError or IndexError or ValueError:
                print("Error in date data format")

    (values_y, datesY) = DataAcquisition.get_sensor_data(
        serverUrl=serverUrl,
        macId=mac_id,
        starttime=start_time_stamp_str,
        endtime=end_time_stamp_str,
        limit=limit,
        axis=axisY
    )

    epoch_dates_y = []
    i = 0
    for date in datesY:
        try:
            d = datetime.datetime.strptime(date, "%Y-%m-%dT%H:%M:%S.%f+00:00").timestamp()
            epoch_dates_y.append(d)

            YRmsRawValue.append(rms(values_y[i]))
            gKurtYRawValue.append(stats.kurtosis(values_y[i]))
            i += 1

        except TypeError or IndexError or ValueError:
            try:
                d = datetime.datetime.strptime(date, "%Y-%m-%dT%H:%M:%S.%f+00:00").timestamp()
                epoch_dates_y.append(d)

                YRmsRawValue.append(None)
                gKurtYRawValue.append(None)
                i += 1

            except TypeError or IndexError or ValueError:
                print("Error in date data format")

    (values_z, datesZ) = DataAcquisition.get_sensor_data(
        serverUrl=serverUrl,
        macId=mac_id,
        starttime=start_time_stamp_str,
        endtime=end_time_stamp_str,
        limit=limit,
        axis=axisZ
    )

    epoch_dates_z = []
    i = 0
    for date in datesZ:
        try:
            d = datetime.datetime.strptime(date, "%Y-%m-%dT%H:%M:%S.%f+00:00").timestamp()
            epoch_dates_z.append(d)

            val_z = np.array(values_z[i])
            ZRmsRawValue.append(rms(val_z))
            gKurtZRawValue.append(stats.kurtosis(val_z))
            i += 1

        except TypeError or IndexError or ValueError:
            try:
                d = datetime.datetime.strptime(date, "%Y-%m-%dT%H:%M:%S.%f+00:00").timestamp()
                epoch_dates_z.append(d)

                ZRmsRawValue.append(None)
                gKurtZRawValue.append(None)
                i += 1

            except TypeError or IndexError or ValueError:
                print("Error in date data format")

    (dateT, temperature) = DataAcquisition.get_temperature_data(
        serverUrl=serverUrl,
        macId=mac_id
    )

    base_time = time.mktime(datetime.datetime.strptime(start_time_stamp_str, "%Y-%m-%d").timetuple())
    print(f"start base time : {base_time}")

    # inner repeat
    epoch_dates_x_timeline = []
    json_x_datas = []

    # outer repeat

    x_rms_contents = []
    x_kurt_contents = []
    x_board_temperatures = []

    for i in range(len(epoch_dates_x)):
        data_x = [{"serviceId": "76", "deviceId": "reshenie1", "timestamp": epoch_dates_x[i],
                   "contents": {"XRms": XRmsRawValue[i], "gKurtX": gKurtXRawValue[i],
                                "YRms": None, "gKurtY": None,
                                "ZRms": None, "gKurtZ": None,
                                "BoardTemperature": temperature}}]

        epoch_dates_x_timeline.append(epoch_dates_x[i])
        json_results = json.dumps(data_x, indent=4)
        json_x_datas.extend(json.loads(json_results))

    for json_data in json_x_datas:
        x_rms_contents.append(json_data['contents']['XRms'])
        x_kurt_contents.append(json_data['contents']['gKurtX'])
        x_board_temperatures.append(json_data['contents']['BoardTemperature'])

    epoch_dates_y_timeline = []
    json_y_datas = []
    y_rms_contents = []
    y_kurt_contents = []
    y_board_temperatures = []
    for i in range(len(epoch_dates_y)):
        data_y = [{"serviceId": "76", "deviceId": "reshenie1", "timestamp": epoch_dates_y[i],
                   "contents": {"XRms": None, "gKurtX": None,
                                "YRms": YRmsRawValue[i], "gKurtY": gKurtYRawValue[i],
                                "ZRms": None, "gKurtZ": None,
                                "BoardTemperature": temperature}}]

        epoch_dates_y_timeline.append(epoch_dates_y[i])
        json_results = json.dumps(data_y, indent=4)
        json_y_datas.extend(json.loads(json_results))

    for json_data in json_y_datas:
        y_rms_contents.append(json_data['contents']['YRms'])
        y_kurt_contents.append(json_data['contents']['gKurtY'])
        y_board_temperatures.append(json_data['contents']['BoardTemperature'])

    epoch_dates_z_timeline = []
    json_z_datas = []
    z_rms_contents = []
    z_kurt_contents = []
    z_board_temperatures = []
    for i in range(len(epoch_dates_z)):
        data_z = [{"serviceId": "76", "deviceId": "reshenie1", "timestamp": epoch_dates_z[i],
                   "contents": {"XRms": None, "gKurtX": None,
                                "YRms": None, "gKurtY": None,
                                "ZRms": ZRmsRawValue[i], "gKurtZ": gKurtZRawValue[i],
                                "BoardTemperature": temperature}}]

        epoch_dates_z_timeline.append(epoch_dates_z[i])
        json_results = json.dumps(data_z, indent=4)
        json_z_datas.extend(json.loads(json_results))

    for json_data in json_z_datas:
        z_rms_contents.append(json_data['contents']['ZRms'])
        z_kurt_contents.append(json_data['contents']['gKurtZ'])
        z_board_temperatures.append(json_data['contents']['BoardTemperature'])

    end_proc = time.time() - start_proc
    print(f"graphql process time : {end_proc}")

    return end_proc


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

        # 2. admin 폴더의 custom.html 삭제해도 이동 가능

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
