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
from apps.factory.models import CompanyProfile, Machine, Sensor
from django.db.utils import OperationalError
from apps.factory.serializer import RequestFactorySerializer

# api ---
import logging
from urllib.parse import urlparse
import time
import datetime
import json
import numpy as np
import math
import scipy.signal
from gql import Client, client, gql
from gql.transport.requests import RequestsHTTPTransport
import requests
from scipy import stats
from opcua import ua, Client
from itertools import chain

serverIP = '25.9.7.151'
serverUrl = urlparse('http://{:s}:8000/graphql'.format(serverIP))

@login_required(login_url="/login/")
def index(request):
    company_info = None
    machine_info = None
    sensor_info = None

    try:
        user_id = request.session.get("userId")

        if user_id is None:
            views.login_view(request)

            return redirect("/")

        else:
            user_info = RequestSerializer.request_id_check(user_id)

            try:
                company_info = RequestFactorySerializer.request_company_id_check(user_info.get().company_fk_id)
                print(company_info)
                machine_info = RequestFactorySerializer.request_machine_id_check(company_info.get().company_id)
                print(company_info)
                sensor_info = RequestFactorySerializer.request_sensor_id_check(machine_info.get().machine_id)
                print(company_info)

                # mac_id = Sensor.objects.values_list('sensor_mac')
                # for mac_unit in mac_id:
                #     print(mac_unit)

            except CompanyProfile.DoesNotExist or Machine.DoesNotExist or Sensor.DoesNotExist or OperationalError:
                pass

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

            context = {'segment': 'index', 'user_info': user_info, 'company_info': company_info,
                       'machine_info': machine_info, 'sensor_info': sensor_info}
            html_template = loader.get_template('home/index.html')

            return HttpResponse(html_template.render(context, request))

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
        self.connect(
            serverUrl.geturl()
        )

    def __enter__(self):
        self.connect(
            serverUrl.geturl()
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
            serverUrl.geturl()
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
            return (values, dates, fRanges, numSamples, sampleRates)

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
    def get_init_data(serverUrl, mac_id, period):
        with GraphQLClient(serverUrl) as client:
            query_text = '''
                        mutation{
                          setMaxBeatPeriod(macId: "''' + mac_id + '''", period: ''' + str(period) + '''){
                            __typename
                            ... on GrapheneSetMaxBeatPeriodMutation {ok}
                          }
                        }
                        '''

        return client.execute_query(query_text)


def init(request):
    # serverIP = '25.9.7.151'
    # serverUrl = urlparse('http://{:s}:8000/graphql'.format(serverIP))

    mac_list = Sensor.objects.values_list('sensor_mac', flat=True)
    for mac_id in mac_list:
        print(mac_id)
        Initiation.get_init_data(serverUrl=serverUrl, mac_id=mac_id, period=120)

    return redirect("/")


def hpf_loop(valuesX, valuesY, valuesZ, fRangesX, fRangesY, fRangesZ, sampleRatesX, sampleRatesY, sampleRatesZ):
    transformed = []
    for (v, f, s) in list(zip([valuesX, valuesY, valuesZ], [fRangesX, fRangesY, fRangesZ],
                              [sampleRatesX, sampleRatesY, sampleRatesZ])):
        for i in range(len(v)):
            v[i] = [d / 512.0 * f[i] for d in v[i]]
            v[i] = HighPassFilter.perform_hpf_filtering(
                data=v[i],
                sampleRate=s[i],
                hpf=3
            )
        transformed.append(v)
    return transformed

def result_graph(request, sensor_tag):
    logging.basicConfig(level=logging.INFO)
    logging.getLogger("graphql").setLevel(logging.WARNING)

    serverIP = '25.9.7.151'
    serverUrl = urlparse('http://{:s}:8000/graphql'.format(serverIP))

    # sensor = Sensor.objects.filter(sensor_tag=sensor_tag)
    # mac_id = sensor.get().sensor_mac

    # replace xx.xx.xx.xx with the IP address of your server
    # serverIP = "25.3.15.233" #BKT
    # serverIP = '25.55.114.208'  # KPU
    # serverIP = '25.12.181.157' #SKT1
    # serverIP = '25.17.10.130' #SKT2

    # serverIP = '25.9.7.151'
    # serverUrl = urlparse('http://{:s}:8000/graphql'.format(serverIP))

    # replace xx:xx:xx:xx with your sensors macId
    # macId = '82:8e:2c:a3' #BKT
    # macId = 'c7:f0:3e:b4'  # KPU
    # macId='94:f3:9e:df' #SKT1
    # macId='05:92:6d:a7' #SKT2
    macId = '95:b0:30:c5'

    # change settings
    hpf = 6  # high pass filter (Hz)
    endtime = datetime.datetime.now() - datetime.timedelta(minutes=30)
    starttime = endtime - datetime.timedelta(minutes=10)
    endtime = endtime.isoformat()
    starttime = starttime.isoformat()
    timeZone = "Asia/Seoul"  # local time zone
    limit = 1000  # limit limits the number of returned measurements
    axisX = 'X'  # axis allows to select data from only 1 or multiple axes
    axisY = 'Y'  # axis allows to select data from only 1 or multiple axes
    axisZ = 'Z'  # axis allows to select data from only 1 or multiple axes


    (valuesX, datesX, fRangesX, numSamples, sampleRatesX) = DataAcquisition.get_sensor_data(
        serverUrl=serverUrl,
        macId=macId,
        starttime=starttime,
        endtime=endtime,
        limit=limit,
        axis=axisX
    )
    (valuesY, datesY, fRangesY, numSamples, sampleRatesY) = DataAcquisition.get_sensor_data(
        serverUrl=serverUrl,
        macId=macId,
        starttime=starttime,
        endtime=endtime,
        limit=limit,
        axis=axisY
    )
    (valuesZ, datesZ, fRangesZ, numSamples, sampleRatesZ) = DataAcquisition.get_sensor_data(
        serverUrl=serverUrl,
        macId=macId,
        starttime=starttime,
        endtime=endtime,
        limit=limit,
        axis=axisZ
    )
    (dateT, temperature) = DataAcquisition.get_temperature_data(
        serverUrl=serverUrl,
        macId=macId
    )

    RmsTimeValue = []  # stores XRms time value
    XRmsRawValue = []  # stores XRms raw value
    YRmsRawValue = []  # stores YRms raw value
    ZRmsRawValue = []  # stores ZRms raw value
    gKurtXRawValue = []  # stores XKurt raw value
    gKurtYRawValue = []  # stores YKurt raw value
    gKurtZRawValue = []  # stores ZKurt raw value
    boardTemperatureValue = []  # stores boardTemperature raw Value

    # convert vibration data to 'g' units
    for i in range(len(fRangesX)):
        valuesX[i] = [d / 512.0 * fRangesX[i] for d in valuesX[i]]
        valuesX[i] = HighPassFilter.perform_hpf_filtering(
            data=valuesX[i],
            sampleRate=sampleRatesX[i],
            hpf=hpf
        )

    for i in range(len(fRangesY)):
        valuesY[i] = [d / 512.0 * fRangesY[i] for d in valuesY[i]]
        valuesY[i] = HighPassFilter.perform_hpf_filtering(
            data=valuesY[i],
            sampleRate=sampleRatesY[i],
            hpf=hpf
        )

    for i in range(len(fRangesZ)):
        valuesZ[i] = [d / 512.0 * fRangesZ[i] for d in valuesZ[i]]

        valuesZ[i] = HighPassFilter.perform_hpf_filtering(
            data=valuesZ[i],
            sampleRate=sampleRatesZ[i],
            hpf=hpf
        )

    epochDatesX = []
    for date in datesX:
        try:
            d = round(datetime.datetime.strptime(date, "%Y-%m-%dT%H:%M:%S.%f+00:00").timestamp() * 1000)
        except:
            try:
                d = round(datetime.datetime.strptime(date, "%Y-%m-%dT%H:%M:%S+00:00").timestamp() * 1000)
            except:
                print("Error in date data format")

        epochDatesX.append(d)

    epochDatesY = []
    for date in datesY:
        try:
            d = round(datetime.datetime.strptime(date, "%Y-%m-%dT%H:%M:%S.%f+00:00").timestamp() * 1000)
        except:
            try:
                d = round(datetime.datetime.strptime(date, "%Y-%m-%dT%H:%M:%S+00:00").timestamp() * 1000)
            except:
                print("Error in date data format")
        epochDatesY.append(d)

    epochDatesZ = []
    for date in datesZ:
        try:
            d = round(datetime.datetime.strptime(date, "%Y-%m-%dT%H:%M:%S.%f+00:00").timestamp() * 1000)
        except:
            try:
                d = round(datetime.datetime.strptime(date, "%Y-%m-%dT%H:%M:%S+00:00").timestamp() * 1000)
            except:
                print("Error in date data format")
        epochDatesZ.append(d)


    for i in range(len(valuesX)):
        vals = np.array(valuesX[i])
        XRmsRawValue.append(np.sqrt(np.mean(vals ** 2)))
        gKurtXRawValue.append(stats.kurtosis(vals))
    for i in range(len(valuesY)):
        vals = np.array(valuesY[i])
        YRmsRawValue.append(np.sqrt(np.mean(vals ** 2)))
        gKurtYRawValue.append(stats.kurtosis(vals))
    for i in range(len(valuesZ)):
        vals = np.array(valuesZ[i])
        ZRmsRawValue.append(np.sqrt(np.mean(vals ** 2)))
        gKurtZRawValue.append(stats.kurtosis(vals))

    # with open(
    #         'C:/Users/user/Iqunet_reshenie_old_test/Reshenie_Old_wirevibsensor/BKT_reshenie_Vibration_PWR_data12.json',
    #         'w') as json_file:
    #     for i in range(len(epochDatesX)):
    #         data2 = [{"serviceId": "76", "deviceId": "reshenie1", "timestamp": epochDatesX[i],
    #                   "contents": {"XRms": XRmsRawValue[i], "gKurtX": gKurtXRawValue[i], "YRms": None, "gKurtY": None,
    #                                "ZRms": None, "gKurtZ": None, "BoradTemperature": None}}]
    #         json.dump(data2, json_file, indent=4)
    #
    #     for i in range(len(epochDatesY)):
    #         data2 = [{"serviceId": "76", "deviceId": "reshenie1", "timestamp": epochDatesY[i],
    #                   "contents": {"XRms": None, "gKurtX": None, "YRms": YRmsRawValue[i], "gKurtY": gKurtYRawValue[i],
    #                                "ZRms": None, "gKurtZ": None, "BoradTemperature": None}}]
    #         json.dump(data2, json_file, indent=4)
    #
    #     for i in range(len(epochDatesZ)):
    #         data2 = [{"serviceId": "76", "deviceId": "reshenie1", "timestamp": epochDatesZ[i],
    #                   "contents": {"XRms": None, "gKurtX": None, "YRms": None, "gKurtY": None, "ZRms": ZRmsRawValue[i],
    #                                "gKurtZ": gKurtZRawValue[i], "BoradTemperature": None}}]
    #         json.dump(data2, json_file, indent=4)

    data2 = [{"serviceId": "76", "deviceId": "reshenie1", "timestamp": dateT,
              "contents": {"XRms": None, "gKurtX": None, "YRms": None, "gKurtY": None, "ZRms": None, "gKurtZ": None,
                           "BoradTemperature": temperature}}]
    json.dumps(data2, indent=4)

    return JsonResponse({"serviceId": "76", "deviceId": "reshenie1", "timestamp": dateT,
                         "contents": {"XRms": None, "gKurtX": None, "YRms": None, "gKurtY": None, "ZRms": None,
                                      "gKurtZ": None,
                                      "BoradTemperature": temperature}}, status=201)

@login_required(login_url="/login/")
def pages(request):
    context = {}
    # All resource paths end in .html.
    # Pick out the html file name from the url. And load that template.
    try:

        load_template = request.path.split('/')[-1]

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
