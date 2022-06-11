import scipy.signal

from apps.home import opcua_view
from concurrent.futures import ThreadPoolExecutor

from django import template
from django.http import JsonResponse
from django.shortcuts import render, redirect
from apps.factory.models import Server, Sensor
from apps.factory.serializer import RequestTotalSerializer
from django.views import View

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

# 1. templatetags 라는 폴더를 만들어 template tag 를 custom 가능
# 2. register = template.Library() <- 자신이 만든 template tag 등록
# 3. {% load repeat %} <-- html 등 프론트앤드 단에서 django에서 지원하는 것이 아닌 자신이 만든 template tag를 쓸 수 있음
register = template.Library()


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
    def get_sensor_data(server_url, mac_id, start_time, end_time, limit, axis, hpf):
        with GraphQLClient(server_url) as client:
            querytext = '''
			{ deviceManager { device(macId:"''' + mac_id + '''") {
                __typename
                ... on GrapheneVibrationCombo {vibrationTimestampHistory(start:"''' + str(
                start_time) + '''", end:"''' + str(end_time) + '''", limit:''' + str(limit) + ''', axis:"''' + axis + '''")}
            }}}
            '''
            result = client.execute_query(querytext)
            times = \
                result['deviceManager']['device']['vibrationTimestampHistory']

            dates, values, f_ranges, num_samples, sample_rates = ([], [], [], [], [])
            # print(result['deviceManager']['device'])
            # print(times)
            for t in times:
                result = DataAcquisition.get_sensor_measurement(
                    client,
                    mac_id,
                    t
                )
                # print(result)
                dates.append(t)
                device_data = result['deviceManager']['device']
                values.append(
                    device_data['vibrationArray']['rawSamples']
                )

                f_ranges.append(
                    device_data['vibrationArray']['formatRange']
                )
                num_samples.append(
                    device_data['vibrationArray']['numSamples']
                )
                sample_rates.append(
                    device_data['vibrationArray']['sampleRate']
                )
                # print(deviceData)
                # print(len(values[0]))
                # print(deviceData['vibrationArray'])

            # valuesX, valuesY, valuesZ, fRangesX, fRangesY, fRangesZ, sampleRatesX, sampleRatesY, sampleRatesZ, hpf=3
            if axis == "X":
                # print(f'values={values}, fRangesX={fRanges}, sampleRatesX={sampleRates}')
                hpf_value = hpf_loop(hpf=hpf, valuesX=values, fRangesX=f_ranges, sampleRatesX=sample_rates)
            elif axis == "Y":
                hpf_value = hpf_loop(hpf=hpf, valuesY=values, fRangesY=f_ranges, sampleRatesY=sample_rates)
            elif axis == "Z":
                hpf_value = hpf_loop(hpf=hpf, valuesZ=values, fRangesZ=f_ranges, sampleRatesZ=sample_rates)
            elif axis == "XYZ":
                hpf_value = hpf_loop(hpf=hpf, valuesXYZ=values, fRangesXYZ=f_ranges, sampleRatesXYZ=sample_rates)

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
    def get_temperature_data(server_url, mac_id):
        with GraphQLClient(server_url) as client:
            result = DataAcquisition.get_temperature_measurement(
                client,
                mac_id
            )
            date = (datetime.datetime.now().timestamp())
            device_data = result['deviceManager']['device']
            temperature = device_data['temperature']
            return date, temperature

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


@register.filter
class JsonGraph(View):

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        # change settings
        self.hpf = 6  # high pass filter (Hz)

        self.end_time = time.time() - 3600
        self.start_time = self.end_time - 3600 * 24

        self.end_time_stamp_str = datetime.datetime.fromtimestamp(self.end_time).strftime("%Y-%m-%dT%H:%M:%S+00:00")
        self.start_time_stamp_str = datetime.datetime.fromtimestamp(self.start_time).strftime("%Y-%m-%dT%H:%M:%S+00:00")
        self.kor_start_time_stamp_str = datetime.datetime.fromtimestamp(self.start_time).strftime(
            "%Y년 %m월 %d일 %H시 %M분 %S초")

        self.time_zone = "Asia/Seoul"  # local time zone
        self.limit = 1000  # limit limits the number of returned measurements
        self.axis_x = 'X'  # axis allows to select data from only 1 or multiple axes
        self.axis_y = 'Y'  # axis allows to select data from only 1 or multiple axes
        self.axis_z = 'Z'  # axis allows to select data from only 1 or multiple axes

    def define_t(self, server_url, mac_id):

        (dateT, temperature) = DataAcquisition.get_temperature_data(
            server_url=server_url,
            mac_id=mac_id
        )

        json_t_datas = []
        epoch_dates_t_timeline = []
        board_temperature = None
        data_t = [{"serviceId": "76", "deviceId": "reshenie1", "timestamp": dateT,
                   "contents": {"XRms": None, "gKurtX": None,
                                "YRms": None, "gKurtY": None,
                                "ZRms": None, "gKurtZ": None,
                                "BoradTemperature": temperature}}]
        json_results = json.dumps(data_t, indent=4)
        json_t_datas.extend(json.loads(json_results))
        date_t_timeline = datetime.datetime.fromtimestamp(dateT).strftime("%Y년 %m월 %d일 %H시 %M분 %S초")
        epoch_dates_t_timeline.append(date_t_timeline)

        for json_data in json_t_datas:
            board_temperature = json_data['contents']['BoradTemperature']

        if board_temperature is None:
            board_temperature = 0

        print(f'mac_id: {mac_id}, epoch_dates_t_timeline: {epoch_dates_t_timeline}, board_temperature: {board_temperature} \n')

        return epoch_dates_t_timeline, board_temperature

    def define_x(self, server_url, mac_id):
        background_color, border_color = [], []
        # d = datetime.datetime.fromtimestamp(x_time[0]).strftime("%Y년 %m월 %d일 %H시 %M분 %S초")
        # date_list_x.append(d)

        # values = data
        (values_x, dates_x) = DataAcquisition.get_sensor_data(
            server_url=server_url,
            mac_id=mac_id,
            start_time=self.start_time_stamp_str,
            end_time=self.end_time_stamp_str,
            limit=self.limit,
            axis=self.axis_x,
            hpf=self.hpf,
        )

        # inner repeat
        epoch_dates_x_timeline = []
        json_x_datas = []

        # outer repeat
        rms_x_contents = []
        kurt_x_contents = []

        i = 0
        for date in dates_x:
            if not values_x or not dates_x:
                break

            try:
                # d = round(datetime.datetime.strptime(date, "%Y-%m-%dT%H:%M:%S.%f+00:00").timestamp() * 1000)
                d = datetime.datetime.strptime(date, "%Y-%m-%dT%H:%M:%S.%f+00:00").timestamp()
                data_x = [{"serviceId": "76", "deviceId": "reshenie1", "timestamp": d,
                           "contents": {"XRms": rms(values_x[i]), "gKurtX": stats.kurtosis(values_x[i]),
                                        "YRms": None, "gKurtY": None,
                                        "ZRms": None, "gKurtZ": None}}]

                epoch_dates_x_timeline.append(d - self.start_time)
                json_results = json.dumps(data_x, indent=4)
                json_x_datas.extend(json.loads(json_results))

                # d = datetime.datetime.fromtimestamp(x_time[i]).strftime("%H시 %M분 %S.%f초")
                # date_list_x.append(d)

                background_color.append('#3e95cd')
                border_color.append('#3e95cd')

                i += 1

            except ValueError or IndexError:
                try:
                    # d = round(datetime.datetime.strptime(date, "%Y-%m-%dT%H:%M:%S.%f+00:00").timestamp() * 1000)
                    d = datetime.datetime.strptime(date, "%Y-%m-%dT%H:%M:%S+00:00").timestamp()
                    data_x = [{"serviceId": "76", "deviceId": "reshenie1", "timestamp": d,
                               "contents": {"XRms": rms(values_x[i]), "gKurtX": stats.kurtosis(values_x[i]),
                                            "YRms": None, "gKurtY": None,
                                            "ZRms": None, "gKurtZ": None}
                               }]

                    epoch_dates_x_timeline.append(d - self.start_time)
                    json_results = json.dumps(data_x, indent=4)
                    json_x_datas.extend(json.loads(json_results))

                    # d = datetime.datetime.fromtimestamp(x_time[i]).strftime("%H시 %M분 %S.%f초")
                    # date_list_x.append(d)

                    background_color.append('#3e95cd')
                    border_color.append('#3e95cd')

                    i += 1

                except ValueError or IndexError:
                    print("Error in date data format")

                    return [], [], [], background_color, border_color

        for json_data in json_x_datas:
            rms_x_contents.append(json_data['contents']['XRms'])
            kurt_x_contents.append(json_data['contents']['gKurtX'])

        print(f'mac_id: {mac_id}')
        print(f'epoch_dates_x_timeline: {epoch_dates_x_timeline}')
        print(f'rms_x_contents: {rms_x_contents}')
        print(f'kurt_x_contents: {kurt_x_contents}')

        return rms_x_contents, kurt_x_contents, epoch_dates_x_timeline, background_color, border_color

    def define_y(self, server_url, mac_id):
        background_color, border_color = [], []
        # d = datetime.datetime.fromtimestamp(x_time[0]).strftime("%Y년 %m월 %d일 %H시 %M분 %S초")
        # date_list_x.append(d)

        # values = data
        (values_y, dates_y) = DataAcquisition.get_sensor_data(
            server_url=server_url,
            mac_id=mac_id,
            start_time=self.start_time_stamp_str,
            end_time=self.end_time_stamp_str,
            limit=self.limit,
            axis=self.axis_y,
            hpf=self.hpf,
        )

        # inner repeat
        epoch_dates_y_timeline = []
        json_y_datas = []

        # outer repeat
        rms_y_contents = []
        kurt_y_contents = []

        i = 0
        for date in dates_y:
            if not values_y or not dates_y:
                break

            try:
                # d = round(datetime.datetime.strptime(date, "%Y-%m-%dT%H:%M:%S.%f+00:00").timestamp() * 1000)
                d = datetime.datetime.strptime(date, "%Y-%m-%dT%H:%M:%S.%f+00:00").timestamp()
                data_y = [{"serviceId": "76", "deviceId": "reshenie1", "timestamp": d,
                           "contents": {"XRms": None, "gKurtX": None,
                                        "YRms": rms(values_y[i]), "gKurtY": stats.kurtosis(values_y[i]),
                                        "ZRms": None, "gKurtZ": None}
                           }]

                epoch_dates_y_timeline.append(d - self.start_time)
                json_results = json.dumps(data_y, indent=4)
                json_y_datas.extend(json.loads(json_results))

                # d = datetime.datetime.fromtimestamp(x_time[i]).strftime("%H시 %M분 %S.%f초")
                # date_list_x.append(d)

                background_color.append('#3e95cd')
                border_color.append('#3e95cd')

                i += 1

            except ValueError or IndexError:
                try:
                    # d = round(datetime.datetime.strptime(date, "%Y-%m-%dT%H:%M:%S.%f+00:00").timestamp() * 1000)
                    d = datetime.datetime.strptime(date, "%Y-%m-%dT%H:%M:%S+00:00").timestamp()
                    data_y = [{"serviceId": "76", "deviceId": "reshenie1", "timestamp": d,
                               "contents": {"XRms": None, "gKurtX": None,
                                            "YRms": rms(values_y[i]), "gKurtY": stats.kurtosis(values_y[i]),
                                            "ZRms": None, "gKurtZ": None}
                               }]

                    epoch_dates_y_timeline.append(d - self.start_time)
                    json_results = json.dumps(data_y, indent=4)
                    json_y_datas.extend(json.loads(json_results))

                    # d = datetime.datetime.fromtimestamp(x_time[i]).strftime("%H시 %M분 %S.%f초")
                    # date_list_x.append(d)

                    background_color.append('#3e95cd')
                    border_color.append('#3e95cd')

                    i += 1

                except ValueError or IndexError:
                    print("Error in date data format")

                    return [], [], [], background_color, border_color

        for json_data in json_y_datas:
            rms_y_contents.append(json_data['contents']['YRms'])
            kurt_y_contents.append(json_data['contents']['gKurtY'])

        print(f'mac_id: {mac_id}')
        print(f'epoch_dates_y_timeline: {epoch_dates_y_timeline}')
        print(f'rms_y_contents: {rms_y_contents}')
        print(f'kurt_y_contents: {kurt_y_contents}')

        return rms_y_contents, kurt_y_contents, epoch_dates_y_timeline, background_color, border_color

    def define_z(self, server_url, mac_id):
        background_color, border_color = [], []

        (values_z, dates_z) = DataAcquisition.get_sensor_data(
            server_url=server_url,
            mac_id=mac_id,
            start_time=self.start_time_stamp_str,
            end_time=self.end_time_stamp_str,
            limit=self.limit,
            axis=self.axis_z,
            hpf=self.hpf
        )

        i = 0
        epoch_dates_z_timeline = []
        json_z_datas = []

        rms_z_contents = []
        kurt_z_contents = []
        for date in dates_z:
            if not values_z and not dates_z:
                break

            try:
                # d = round(datetime.datetime.strptime(date, "%Y-%m-%dT%H:%M:%S.%f+00:00").timestamp() * 1000)
                d = datetime.datetime.strptime(date, "%Y-%m-%dT%H:%M:%S.%f+00:00").timestamp()
                data_z = [{"serviceId": "76", "deviceId": "reshenie1", "timestamp": d,
                           "contents": {"XRms": None, "gKurtX": None,
                                        "YRms": None, "gKurtY": None,
                                        "ZRms": rms(values_z[i]), "gKurtZ": stats.kurtosis(values_z[i])}
                           }]

                epoch_dates_z_timeline.append(d - self.start_time)
                json_results = json.dumps(data_z, indent=4)
                json_z_datas.extend(json.loads(json_results))

                background_color.append('#3e95cd')
                border_color.append('#3e95cd')

                i += 1

            except ValueError or IndexError:
                try:
                    # d = round(datetime.datetime.strptime(date, "%Y-%m-%dT%H:%M:%S.%f+00:00").timestamp() * 1000)
                    d = datetime.datetime.strptime(date, "%Y-%m-%dT%H:%M:%S+00:00").timestamp()
                    data_z = [{"serviceId": "76", "deviceId": "reshenie1", "timestamp": d,
                               "contents": {"XRms": None, "gKurtX": None,
                                            "YRms": None, "gKurtY": None,
                                            "ZRms": rms(values_z[i]), "gKurtZ": stats.kurtosis(values_z[i])}
                               }]

                    epoch_dates_z_timeline.append(d - self.start_time)
                    json_results = json.dumps(data_z, indent=4)
                    json_z_datas.extend(json.loads(json_results))

                    background_color.append('#3e95cd')
                    border_color.append('#3e95cd')

                    i += 1

                except ValueError or IndexError:
                    print("Error in date data format")

                    return [], [], [], background_color, border_color

        for json_data in json_z_datas:
            rms_z_contents.append(json_data['contents']['ZRms'])
            kurt_z_contents.append(json_data['contents']['gKurtZ'])

        print(f'mac_id: {mac_id}')
        print(f'epoch_dates_z_timeline: {epoch_dates_z_timeline}')
        print(f'rms_z_contents: {rms_z_contents}')
        print(f'kurt_z_contents: {kurt_z_contents}')

        return rms_z_contents, kurt_z_contents, epoch_dates_z_timeline, background_color, border_color

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
        # print(f"dictionary result: {xyz_rms_results}")

        xyz_rms_time_list = list(xyz_rms_results.keys())
        xyz_kurtosis_time_list = list(xyz_kurtosis_results.keys())

        # rms 값은 value 배열에 저장
        xyz_rms_value_list = list(xyz_rms_results.values())
        xyz_kurtosis_value_list = list(xyz_kurtosis_results.values())

        # 시간을 빼주고 다른 배열에 저장
        for i in range(len(xyz_rms_results)):
            xyz_rms_date_list.append(xyz_rms_time_list[i])

        for i in range(len(xyz_rms_results)):
            xyz_kurtosis_date_list.append(xyz_kurtosis_time_list[i])

        print(f"xyz result time : {xyz_rms_date_list}")

        bar_plot_xyz_rms_values = xyz_rms_value_list
        bar_plot_xyz_kurtosis_values = xyz_kurtosis_value_list

        bar_plot_xyz_time = xyz_rms_date_list

        for i in range(len(xyz_rms_time_list)):
            background_color.append('#3e95cd')
            border_color.append('#3e95cd')

        return bar_plot_xyz_time, bar_plot_xyz_rms_values, bar_plot_xyz_kurtosis_values, background_color, border_color

    def get_result_from_json(self, sensor_id, sensor_tag):

        # logging.basicConfig(level=logging.INFO)
        # logging.getLogger("graphql").setLevel(logging.WARNING)

        # replace xx.xx.xx.xx with the IP address of your server
        sensor = RequestTotalSerializer.request_sensor_name_check(sensor_tag)
        # print(f'sensor fk : {sensor.get().server_fk_id}')

        server = Server.objects.filter(server_id=sensor.get().server_fk_id)
        server_ip = server.get().server_name
        server_url = urlparse('http://{:s}:8000/graphql'.format(server_ip))

        sensor = Sensor.objects.get(sensor_id=sensor_id)
        try:
            sensor_url = sensor.sensor_img.url[5:]
        except ValueError:
            sensor_url = []

        # session = requests.Session()
        # retry = Retry(connect=sensor_count)
        # adapter = HTTPAdapter(max_retries=retry)
        # session.mount('http://{:s}:8000/graphql'.format(server_ip), adapter=adapter)
        requests.get('http://{:s}:8000/graphql'.format(server_ip), timeout=30)

        # replace xx:xx:xx:xx with your sensors macId
        mac_id = sensor.sensor_mac

        print(f'server_url, sensor_url, server_ip, mac_id =  {server_url}, {sensor_url}, {server_ip}, {mac_id} \n')

        try:

            # you can change graph parameters
            # epoch_dates_t_timeline, board_temperature = self.define_t(server_url, mac_id)
            # (bar_plot_x_rms_values, bar_plot_x_kurtosis_values, bar_plot_x_time,
            #  background_x_color, border_x_color) = self.define_x(server_url, mac_id)
            # (bar_plot_y_rms_values, bar_plot_y_kurtosis_values, bar_plot_y_time,
            #  background_y_color, border_y_color) = self.define_y(server_url, mac_id)
            # (bar_plot_z_rms_values, bar_plot_z_kurtosis_values, bar_plot_z_time,
            #  background_z_color, border_z_color) = self.define_z(server_url, mac_id)

            with ThreadPoolExecutor(max_workers=4) as TPE:
                t_future = TPE.submit(self.define_t, server_url, mac_id)
                x_future = TPE.submit(self.define_x, server_url, mac_id)
                y_future = TPE.submit(self.define_y, server_url, mac_id)
                z_future = TPE.submit(self.define_z, server_url, mac_id)
                time.sleep(1)

                # epoch_dates_t_timeline = t_future.result()[0]
                # board_temperature = t_future.result()[1]
                # bar_plot_x_rms_values = x_future.result()[0]
                # bar_plot_x_kurtosis_values = x_future.result()[1]
                # bar_plot_x_time = x_future.result()[2]
                # background_x_color = x_future.result()[3]
                # border_x_color = x_future.result()[4]
                # bar_plot_y_rms_values = y_future.result()[0]
                # bar_plot_y_kurtosis_values = y_future.result()[1]
                # bar_plot_y_time = y_future.result()[2]
                # background_y_color = y_future.result()[3]
                # border_y_color = y_future.result()[4]
                # bar_plot_z_rms_values = z_future.result()[0]
                # bar_plot_z_kurtosis_values = z_future.result()[1]
                # bar_plot_z_time = z_future.result()[2]
                # background_z_color = z_future.result()[3]
                # border_z_color = z_future.result()[4]

                (bar_plot_xyz_time, bar_plot_xyz_rms_values, bar_plot_xyz_kurtosis_values, xyz_background_color,
                 xyz_border_color) = self.xyz_define(
                    start_time=self.start_time,
                    x_rms=x_future.result()[0], y_rms=y_future.result()[0], z_rms=z_future.result()[0],
                    x_kurtosis=x_future.result()[1], y_kurtosis=y_future.result()[1],
                    z_kurtosis=z_future.result()[1],
                    x_time=x_future.result()[2], y_time=y_future.result()[2], z_time=z_future.result()[2],
                )

                return {
                    'sensor_id': sensor_id,
                    'sensor_tag': sensor_tag,
                    'Measurement_Start_Time': self.kor_start_time_stamp_str,
                    'BarPlot_XYZ_RMS_Values': bar_plot_xyz_rms_values,
                    'BarPlot_XYZ_Time': bar_plot_xyz_time,
                    'BarPlot_XYZ_Kurtosis_Values': bar_plot_xyz_kurtosis_values,
                    'BarPlot_X_RMS_Values': x_future.result()[0],
                    'BarPlot_Y_RMS_Values': y_future.result()[0],
                    'BarPlot_Z_RMS_Values': z_future.result()[0],
                    'BarPlot_X_Kurtosis_Values': x_future.result()[1],
                    'BarPlot_Y_Kurtosis_Values': y_future.result()[1],
                    'BarPlot_Z_Kurtosis_Values': z_future.result()[1],
                    'BarPlot_Board_Temperature': t_future.result()[1],
                    'BarPlot_Board_Time': t_future.result()[0],
                    'BarPlot_Board_Temperature_BackColor': xyz_background_color[0],
                    'BarPlot_Board_Temperature_BorderColor': xyz_border_color[0],
                    'BarPlot_X_Time': x_future.result()[2],
                    'BarPlot_Y_Time': y_future.result()[2],
                    'BarPlot_Z_Time': z_future.result()[2],
                    'XBackgroundColor': x_future.result()[3],
                    'XBorderColor': x_future.result()[4],
                    'YBackgroundColor': y_future.result()[3],
                    'YBorderColor': y_future.result()[4],
                    'ZBackgroundColor': z_future.result()[3],
                    'ZBorderColor': z_future.result()[4],
                    'XYZBackgroundColor': xyz_background_color,
                    'XYZBorderColor': xyz_border_color,
                }

        except IndexError:
            board_temperature = 0
            epoch_dates_t_timeline = []
            return {
                'sensor_id': sensor_id,
                'sensor_tag': sensor_tag,
                'sensor_url': sensor_url,
                'Measurement_Start_Time': self.kor_start_time_stamp_str,
                'BarPlot_X_RMS_Values': [],
                'BarPlot_Y_RMS_Values': [],
                'BarPlot_Z_RMS_Values': [],
                'BarPlot_XYZ_RMS_Values': [],
                'BarPlot_X_Kurtosis_Values': [],
                'BarPlot_Y_Kurtosis_Values': [],
                'BarPlot_Z_Kurtosis_Values': [],
                'BarPlot_XYZ_Kurtosis_Values': [],
                'BarPlot_Board_Temperature': board_temperature,
                'BarPlot_Board_Time': epoch_dates_t_timeline,
                'BarPlot_Board_Temperature_BackColor': [],
                'BarPlot_Board_Temperature_BorderColor': [],
                'BarPlot_X_Time': [],
                'BarPlot_Y_Time': [],
                'BarPlot_Z_Time': [],
                'BarPlot_XYZ_Time': [],
                'XBackgroundColor': [],
                'XBorderColor': [],
                'YBackgroundColor': [],
                'YBorderColor': [],
                'ZBackgroundColor': [],
                'ZBorderColor': [],
                'XYZBackgroundColor': [],
                'XYZBorderColor': [],
            }

    def post(self, request, *args, **kwargs):
        start_proc = time.time()

        # RMS (rms acceleration; rms 가속도 : 일정 시간 동안의 가속도 제곱의 평균의 제곱근
        sensor_ids = request.POST.getlist('sensor_id[]')
        sensor_tags = request.POST.getlist('sensor_tag[]')

        sensor_ids = [int(sensor_id) for sensor_id in sensor_ids]
        sensor_tags = [str(sensor_tag) for sensor_tag in sensor_tags]

        sending = {}
        if sensor_tags:
            i = 0
            # for sensor_id, sensor_tag in zip(sensor_ids, sensor_tags):
            # ProcessPoolExecutor -> cannot pickle '_io.bufferedreader' object python

            # 하마치 꺼져 있으면 아래 에러
            # requests.exceptions.ConnectTimeout: HTTPConnectionPool(host='25.80.89.221', port=8000): Max retries exceeded with url: /graphql
            with ThreadPoolExecutor(max_workers=len(sensor_ids)) as TPE:
                future_to_array = [TPE.submit(self.get_result_from_json, sensor_id, sensor_tag) for
                                   sensor_id, sensor_tag in zip(sensor_ids, sensor_tags)]
                for future in future_to_array:
                    sending.update({sensor_ids[i]: future.result()})
                    print('%s is completed \n' % sending)
                    i += 1
            context = {
                'sending': sending,
            }

            end_proc = time.time() - start_proc
            print(f"graphql running time : {end_proc}")

        else:
            context = {
                'sending': {},
            }
            # schedule.every(60).seconds.do(result_json)

            # while request:
            #     schedule.run_pending()
            #     time.sleep(1)

        return JsonResponse({'context': context}, status=201)


@register.filter
def protocol_repeat(request, sensor_tag):
    start_time = time.time()
    with ThreadPoolExecutor(max_workers=2) as TPE:
        gql_future = TPE.submit(result_json(), sensor_tag)

        opcua_future = TPE.submit(opcua_view.opcua_process, sensor_tag)

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


# request,
def result_json(sensor_tag):
    start_proc = time.time()

    logging.basicConfig(level=logging.INFO)
    logging.getLogger("graphql").setLevel(logging.WARNING)

    # sensor = Sensor.objects.filter(sensor_tag=sensor_tag)
    # mac_id = sensor.get().sensor_mac

    # replace xx.xx.xx.xx with the IP address of your server
    sensor = RequestTotalSerializer.request_sensor_name_check(sensor_tag)
    # print(f'sensor fk : {sensor.get().server_fk_id}')
    server = Server.objects.filter(server_id=sensor.get().server_fk_id)
    server_ip = server.get().server_name
    serverUrl = urlparse('http://{:s}:8000/graphql'.format(server_ip))
    requests.get('http://{:s}:8000/graphql'.format(server_ip), timeout=30)

    # replace xx:xx:xx:xx with your sensors macId
    mac_id = sensor.get().sensor_mac

    # change settings
    hpf = 6  # high pass filter (Hz)
    # endtime = datetime.datetime.now() - datetime.timedelta(minutes=30)
    # starttime = endtime - datetime.timedelta(minutes=10)

    # endtime = datetime.datetime.now() - datetime.timedelta(hours=9)
    # starttime = endtime - datetime.timedelta(hours=12)

    # endtime = endtime.isoformat()
    # starttime = starttime.isoformat()

    endtime = time.time() - 3600
    starttime = endtime - 3600

    end_time_stamp_str = datetime.datetime.fromtimestamp(endtime).strftime("%Y-%m-%dT%H:%M:%S+00:00")
    start_time_stamp_str = datetime.datetime.fromtimestamp(starttime).strftime("%Y-%m-%dT%H:%M:%S+00:00")

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
        return [], [], [], [], None, None

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

        except ValueError or IndexError:
            try:
                # d = round(datetime.datetime.strptime(date, "%Y-%m-%dT%H:%M:%S.%f+00:00").timestamp() * 1000)
                d = datetime.datetime.strptime(date, "%Y-%m-%dT%H:%M:%S+00:00").timestamp()
                epoch_dates_x.append(d)

                XRmsRawValue.append(rms(values_x[i]))
                gKurtXRawValue.append(stats.kurtosis(values_x[i]))
                i += 1

            except ValueError or IndexError:
                print("Error in date data format")

    (values_y, datesY) = DataAcquisition.get_sensor_data(
        serverUrl=serverUrl,
        macId=mac_id,
        starttime=start_time_stamp_str,
        endtime=end_time_stamp_str,
        limit=limit,
        axis=axisY
    )

    if not values_y or not datesY:
        return [], [], [], [], None, None

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

        except ValueError or IndexError:
            try:
                # d = round(datetime.datetime.strptime(date, "%Y-%m-%dT%H:%M:%S.%f+00:00").timestamp() * 1000)
                d = datetime.datetime.strptime(date, "%Y-%m-%dT%H:%M:%S+00:00").timestamp()
                epoch_dates_y.append(d)

                YRmsRawValue.append(rms(values_y[i]))
                gKurtYRawValue.append(stats.kurtosis(values_y[i]))
                i += 1

            except ValueError or IndexError:
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
    check = []
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

        except ValueError or IndexError:
            try:
                # d = round(datetime.datetime.strptime(date, "%Y-%m-%dT%H:%M:%S.%f+00:00").timestamp() * 1000)
                d = datetime.datetime.strptime(date, "%Y-%m-%dT%H:%M:%S+00:00").timestamp()
                epoch_dates_z.append(d)

                val_z = np.array(values_z[i])
                ZRmsRawValue.append(rms(val_z))
                gKurtZRawValue.append(stats.kurtosis(val_z))
                i += 1

            except ValueError or IndexError:
                print("Error in date data format")

    if not values_z or not datesZ:
        return [], [], [], [], None, None

    print(f'x length : {len(epoch_dates_x)}, y length : {len(epoch_dates_y)}, z length : {len(epoch_dates_z)}')

    (dateT, temperature) = DataAcquisition.get_temperature_data(
        serverUrl=serverUrl,
        macId=mac_id
    )

    x_flag = y_flag = z_flag = 1
    if len(epoch_dates_x) == 0:
        x_flag = 0
    if len(epoch_dates_y) == 0:
        y_flag = 0
    if len(epoch_dates_z) == 0:
        z_flag = 0

    try:
        base_time = time.mktime(
            datetime.datetime.strptime(start_time_stamp_str, "%Y-%m-%dT%H:%M:%S.%f+00:00").timetuple())
        print(f"start base time : {base_time}")

    except ValueError:
        base_time = time.mktime(datetime.datetime.strptime(start_time_stamp_str, "%Y-%m-%dT%H:%M:%S+00:00").timetuple())
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

        epoch_dates_x_timeline.append(epoch_dates_x[i])
        json_results = json.dumps(data_x, indent=4)
        json_x_datas.extend(json.loads(json_results))

    for json_data in json_x_datas:
        x_rms_contents.append(json_data['contents']['XRms'])
        x_kurt_contents.append(json_data['contents']['gKurtX'])

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

        epoch_dates_y_timeline.append(epoch_dates_y[i])
        json_results = json.dumps(data_y, indent=4)
        json_y_datas.extend(json.loads(json_results))

    for json_data in json_y_datas:
        y_rms_contents.append(json_data['contents']['YRms'])
        y_kurt_contents.append(json_data['contents']['gKurtY'])

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

        epoch_dates_z_timeline.append(epoch_dates_z[i])
        json_results = json.dumps(data_z, indent=4)
        json_z_datas.extend(json.loads(json_results))

    for json_data in json_z_datas:
        z_rms_contents.append(json_data['contents']['ZRms'])
        z_kurt_contents.append(json_data['contents']['gKurtZ'])

    end_proc = time.time() - start_proc
    print(f"graphql process time : {end_proc}")

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
                date_list_x.append(x_time[i] - start)
                # d = datetime.datetime.fromtimestamp(x_time[i]).strftime("%H시 %M분 %S.%f초")
                # date_list_x.append(d)

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
                date_list_y.append(y_time[i] - start)
                # d = datetime.datetime.fromtimestamp(y_time[i]).strftime("%H시 %M분 %S.%f초")
                # date_list_y.append(d)

                # print(f'converter_time_y: {date_list_y}')


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
        my_rms, my_kurtosis, my_time, flags, start_time, my_board_temperature = JsonGraph.get_result_from_json(kwargs['sensor_id'], kwargs['sensor_tag'])
        if start_time is not None:
            start_time_str = datetime.datetime.fromtimestamp(start_time).strftime("%Y년 %m월 %d일 %H시 %M분 %S초")
            start_time = time.mktime(datetime.datetime.strptime(start_time_str, "%Y년 %m월 %d일 %H시 %M분 %S초").timetuple())
        else:
            start_time_str = datetime.datetime.now().strftime("%Y년 %m월 %d일 %H시 %M분 %S초")

        try:
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
                'BarPlot_Board_Temperature_BackColor': xyz_background_color[0],
                'BarPlot_Board_Temperature_BorderColor': xyz_border_color[0],
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

        except IndexError:
            my_board_temperature = 0
            context = {
                'Measurement_Start_Time': start_time_str,
                'BarPlot_X_RMS_Values': [],
                'BarPlot_Y_RMS_Values': [],
                'BarPlot_Z_RMS_Values': [],
                'BarPlot_XYZ_RMS_Values': [],
                'BarPlot_X_Kurtosis_Values': [],
                'BarPlot_Y_Kurtosis_Values': [],
                'BarPlot_Z_Kurtosis_Values': [],
                'BarPlot_XYZ_Kurtosis_Values': [],
                'BarPlot_Board_Temperature': my_board_temperature,
                'BarPlot_X_Time': [],
                'BarPlot_Y_Time': [],
                'BarPlot_Z_Time': [],
                'BarPlot_XYZ_Time': [],
                'XBackgroundColor': [],
                'XBorderColor': [],
                'YBackgroundColor': [],
                'YBorderColor': [],
                'ZBackgroundColor': [],
                'ZBorderColor': [],
                'XYZBackgroundColor': [],
                'XYZBorderColor': [],
            }

            return render(request, 'home/other-data.html', {'context': context})
