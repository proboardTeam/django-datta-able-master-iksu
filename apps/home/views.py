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
import schedule
import pytz

serverIP = '25.9.7.151'
# serverIP = '25.52.52.52'
# serverIP = '25.58.137.19'
# serverIP = '25.105.77.110'

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
                # print(company_info)
                machine_info = RequestFactorySerializer.request_machine_id_check(company_info.get().company_id)
                # print(company_info)
                sensor_info = RequestFactorySerializer.request_sensor_id_check(machine_info.get().machine_id)
                # print(company_info)

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
    mac_list = Sensor.objects.values_list('sensor_mac', flat=True)
    for mac_id in mac_list:
        # print(mac_id)
        Initiation.get_init_data(serverUrl=serverUrl, mac_id=mac_id, period=120)

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

    if x_flag == 1 and y_flag == z_flag == 0:
        for (v, f, s) in list(zip([x_valid], [x_range_valid], [x_sample_valid])):

            # print(f'len(f) = {len(f)}')

            for i in range(len(f)):
                try:
                    v[i] = [d / 512.0 * f[i] for d in v[i]]
                    v[i] = HighPassFilter.perform_hpf_filtering(
                        data=v[i],
                        sampleRate=s[i],
                        hpf=6
                    )
                    transformed.extend(v)

                except TypeError:
                    transformed.extend(v)

        return transformed

    elif y_flag == 1 and x_flag == z_flag == 0:
        for (v, f, s) in list(zip([y_valid], [y_range_valid], [y_sample_valid])):

            # print(f'len(f) = {len(f)}')

            for i in range(len(f)):
                try:
                    v[i] = [d / 512.0 * f[i] for d in v[i]]
                    v[i] = HighPassFilter.perform_hpf_filtering(
                        data=v[i],
                        sampleRate=s[i],
                        hpf=6
                    )
                    transformed.extend(v)

                except TypeError:
                    transformed.extend(v)

        return transformed

    elif z_flag == 1 and x_flag == y_flag:
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
                    transformed.extend(v)

                except TypeError:
                    transformed.extend(v)

        return transformed

    elif x_flag == y_flag == z_flag == 1:
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
                    transformed.extend(v)

                except TypeError:
                    transformed.extend(v)

        return transformed

    else:
        return None


def rms(ndarray):
    return np.sqrt(np.mean(ndarray ** 2))


# request,
def result_json(sensor_tag):
    logging.basicConfig(level=logging.INFO)
    logging.getLogger("graphql").setLevel(logging.WARNING)

    # sensor = Sensor.objects.filter(sensor_tag=sensor_tag)
    # mac_id = sensor.get().sensor_mac

    # replace xx.xx.xx.xx with the IP address of your server
    # serverIP = "25.3.15.233" #BKT
    # serverIP = '25.55.114.208'  # KPU
    # serverIP = '25.12.181.157' #SKT1
    # serverIP = '25.17.10.130' #SKT2

    # serverIP = '25.9.7.151'
    # serverUrl = urlparse('http://{:s}:8000/graphql'.format(serverIP))

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

    # end_time_stamp_str = datetime.datetime.fromtimestamp(endtime).strftime("%Y-%m-%dT%H:%M:%S.%f+00:00")
    # start_time_stamp_str = datetime.datetime.fromtimestamp(starttime).strftime("%Y-%m-%dT%H:%M:%S.%f+00:00")

    end_time_stamp_str = "2022-03-25"
    start_time_stamp_str = "2022-03-24"


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

    epoch_dates_x = []
    i = 0
    for date in datesX:
        try:
            # d = round(datetime.datetime.strptime(date, "%Y-%m-%dT%H:%M:%S.%f+00:00").timestamp() * 1000)
            d = datetime.datetime.strptime(date, "%Y-%m-%dT%H:%M:%S.%f+00:00").timestamp()
            epoch_dates_x.append(d)

            val_x = np.array(values_x[i])
            XRmsRawValue.append(rms(val_x))
            gKurtXRawValue.append(stats.kurtosis(val_x))
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

            val_y = np.array(values_y[i])
            YRmsRawValue.append(rms(val_y))
            gKurtYRawValue.append(stats.kurtosis(val_y))
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

    print(f'x : {len(epoch_dates_x)}, y : {len(epoch_dates_y)}, z : {len(epoch_dates_z)}')

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

        # x_time_converter = datetime.datetime.fromtimestamp(epoch_dates_x[i]).strftime(
        #     "%Y-%m-%d %H:%M:%S.%f+00:00")
        # epoch_dates_x_timeline.append(x_time_converter)
        epoch_dates_x_timeline.append(epoch_dates_x[i])
        json_results = json.dumps(data_x, indent=4)
        json_x_datas.extend(json.loads(json_results))

    for json_data in json_x_datas:
        x_rms_contents.append(json_data['contents']['XRms'])
        x_kurt_contents.append(json_data['contents']['gKurtX'])
        x_board_temperatures.append(json_data['contents']['BoardTemperature'])

    print(f'x_rms_contents: {x_rms_contents}')
    print(f'x_kurt_contents: {x_kurt_contents}')
    print(f'x_board_temperatures: {x_board_temperatures}')
    print(f'epoch_dates_x_timeline: {epoch_dates_x_timeline}')

    print("=====================================================================================")

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

        # y_time_converter = datetime.datetime.fromtimestamp(epoch_dates_y[i]).strftime(
        #     "%Y-%m-%d %H:%M:%S.%f+00:00")
        # epoch_dates_y_timeline.append(y_time_converter)
        epoch_dates_y_timeline.append(epoch_dates_y[i])
        json_results = json.dumps(data_y, indent=4)
        json_y_datas.extend(json.loads(json_results))

    for json_data in json_y_datas:
        y_rms_contents.append(json_data['contents']['YRms'])
        y_kurt_contents.append(json_data['contents']['gKurtY'])
        y_board_temperatures.append(json_data['contents']['BoardTemperature'])

    print(f'y_rms_contents: {y_rms_contents}')
    print(f'y_kurt_contents: {y_kurt_contents}')
    print(f'y_board_temperatures: {y_board_temperatures}')
    print(f'epoch_dates_y_timeline: {epoch_dates_y_timeline}')

    print("=====================================================================================")

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

        # z_time_converter = datetime.datetime.fromtimestamp(epoch_dates_z[i]).strftime(
        #     "%Y-%m-%d %H:%M:%S.%f+00:00")
        # epoch_dates_z_timeline.append(z_time_converter)
        epoch_dates_z_timeline.append(epoch_dates_z[i])
        json_results = json.dumps(data_z, indent=4)
        json_z_datas.extend(json.loads(json_results))

    for json_data in json_z_datas:
        z_rms_contents.append(json_data['contents']['ZRms'])
        z_kurt_contents.append(json_data['contents']['gKurtZ'])
        z_board_temperatures.append(json_data['contents']['BoardTemperature'])

    print(f'z_rms_contents: {z_rms_contents}')
    print(f'z_kurt_contents: {z_kurt_contents}')
    print(f'z_board_temperatures: {z_board_temperatures}')
    print(f'epoch_dates_z_timeline: {epoch_dates_z_timeline}')

    print("=====================================================================================")

    return [x_rms_contents, y_rms_contents, z_rms_contents], [x_kurt_contents, y_kurt_contents, z_kurt_contents], \
           [x_board_temperatures, y_board_temperatures, z_board_temperatures], \
           [epoch_dates_x_timeline, epoch_dates_y_timeline, epoch_dates_z_timeline], \
           [x_flag, y_flag, z_flag]

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


def show_graph(request, sensor_tag):
    x, y, z, xyz = 0, 1, 2, 3

    # RMS (rms acceleration; rms 가속도 : 일정 시간 동안의 가속도 제곱의 평균의 제곱근
    my_rms, my_kurtosis, my_board_temperatures, my_time, flags = result_json(sensor_tag)

    # you can change graph parameters
    acceleration_x = []
    acceleration_y = []
    acceleration_z = []
    acceleration_xyz = []

    bar_plot_x = []
    bar_plot_y = []
    bar_plot_z = []
    bar_plot_xyz = []

    bar_plot_x_rms_values = []
    bar_plot_y_rms_values = []
    bar_plot_z_rms_values = []
    bar_plot_xyz_rms_values = []

    bar_plot_x_kurtosis_values = []
    bar_plot_y_kurtosis_values = []
    bar_plot_z_kurtosis_values = []
    bar_plot_xyz_kurtosis_values = []

    bar_plot_x_board_temperatures = []
    bar_plot_y_board_temperatures = []
    bar_plot_z_board_temperatures = []
    bar_plot_xyz_board_temperatures = []

    bar_plot_x_time = []
    bar_plot_y_time = []
    bar_plot_z_time = []
    bar_plot_xyz_time = []

    background_color = []
    border_color = []

    if flags[x] == 1 and flags[y] == flags[z]:
        date_list_x = []
        base_time = my_time[x][0]
        for i in range(len(my_time[x])):
            date_list_x.append(my_time[x][i] - base_time)

        bar_plot_x_rms_values = my_rms[x]
        bar_plot_x_kurtosis_values = my_kurtosis[x]
        bar_plot_x_board_temperatures = my_board_temperatures[x]
        bar_plot_x_time = date_list_x

        x_step_size = 0
        for i in range(1, len(bar_plot_x_time)):
            acceleration_x.append(x_step_size)
            background_color.append('#3e95cd')
            border_color.append('#3e95cd')
            x_step_size += 0.5

    elif flags[y] == 1 and flags[x] == flags[z]:
        date_list_y = []
        base_time = my_time[y][0]
        for i in range(len(my_time[y])):
            date_list_y.append(my_time[y][i] - base_time)

        bar_plot_y_rms_values = my_rms[y]
        bar_plot_y_kurtosis_values = my_kurtosis[y]
        bar_plot_y_board_temperatures = my_board_temperatures[y]
        bar_plot_y_time = date_list_y

        y_step_size = 0
        for i in range(1, len(bar_plot_y_time)):
            acceleration_y.append(y_step_size)
            background_color.append('#3e95cd')
            border_color.append('#3e95cd')
            y_step_size += 0.5

    elif flags[z] == 1 and flags[x] == flags[y]:
        date_list_z = [0, ]
        base_time = my_time[z][0]
        for i in range(1, len(my_time[z])):
            date_list_z.append(my_time[z][i] - base_time)

        print(f'date_list_z: {date_list_z}')
        bar_plot_z_rms_values = my_rms[z]
        bar_plot_z_kurtosis_values = my_kurtosis[z]
        bar_plot_z_board_temperatures = my_board_temperatures[z]
        bar_plot_z_time = date_list_z

        z_step_size = 0
        for i in range(len(bar_plot_z_rms_values)):
            acceleration_z.append(z_step_size)
            background_color.append('#3e95cd')
            border_color.append('#3e95cd')
            z_step_size += 0.5

    elif flags[x] == flags[y] == flags[z] == 1:
        date_list = []

        plot_x_pairs = dict(zip(my_time[x], my_rms[x]))
        plot_y_pairs = dict(zip(my_time[y], my_rms[y]))
        plot_z_pairs = dict(zip(my_time[z], my_rms[z]))

        # dictionary 형태로 update
        plot_y_pairs.update(plot_x_pairs)
        plot_z_pairs.update(plot_y_pairs)

        # 최종 결과 기준 key 값으로 정렬
        results = dict(sorted(plot_z_pairs.items()))
        time_list = list(results.keys())
        base_time = time_list[0]
        
        # rms 값은 value 배열에 저장
        value_list = list(results.values())
        
        # 시간을 빼주고 다른 배열에 저장
        for i in range(1, len(results)):
            date_list.append(time_list[i] - base_time)    
        
        bar_plot_xyz_rms_values = value_list
        bar_plot_xyz_kurtosis_values = my_kurtosis[x] + my_kurtosis[y] + my_kurtosis[z]
        bar_plot_xyz_board_temperatures = my_board_temperatures[x] + my_board_temperatures[y] + my_board_temperatures[z]
        bar_plot_xyz_time = date_list

        xyz_step_size = 0.5
        for i in range(len(results)):
            acceleration_xyz.append(xyz_step_size)
            background_color.append('#3e95cd')
            border_color.append('#3e95cd')
            xyz_step_size += 0.5

    context = {
        'Acceleration_X': acceleration_x,
        'Acceleration_Y': acceleration_y,
        'Acceleration_Z': acceleration_z,
        'Acceleration_XYZ': acceleration_xyz,
        'BarPlot_X': bar_plot_x,
        'BarPlot_Y': bar_plot_y,
        'BarPlot_Z': bar_plot_z,
        'BarPlot_XYZ': bar_plot_xyz,
        'BarPlot_X_RMS_Values': bar_plot_x_rms_values,
        'BarPlot_Y_RMS_Values': bar_plot_y_rms_values,
        'BarPlot_Z_RMS_Values': bar_plot_z_rms_values,
        'BarPlot_XYZ_RMS_Values': bar_plot_xyz_rms_values,
        'BarPlot_X_Kurtosis_Values': bar_plot_x_kurtosis_values,
        'BarPlot_Y_Kurtosis_Values': bar_plot_y_kurtosis_values,
        'BarPlot_Z_Kurtosis_Values': bar_plot_z_kurtosis_values,
        'BarPlot_XYZ_Kurtosis_Values': bar_plot_xyz_kurtosis_values,
        'BarPlot_X_Board_Temperatures': bar_plot_x_board_temperatures,
        'BarPlot_Y_Board_Temperatures': bar_plot_y_board_temperatures,
        'BarPlot_z_board_temperatures': bar_plot_z_board_temperatures,
        'BarPlot_xyz_board_temperatures': bar_plot_xyz_board_temperatures,
        'BarPlot_X_time': bar_plot_x_time,
        'BarPlot_Y_time': bar_plot_y_time,
        'BarPlot_Z_time': bar_plot_z_time,
        'BarPlot_XYZ_time': bar_plot_xyz_time,
        'backgroundColor': background_color,
        'borderColor': border_color,
    }

    # schedule.every(60).seconds.do(result_json)

    # while request:
    #     schedule.run_pending()
    #     time.sleep(1)

    return render(request, 'home/show-graph.html', {'context': context})


def other_data(request):

    return render(request, 'home/show-graph.html', {'context': context})


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
