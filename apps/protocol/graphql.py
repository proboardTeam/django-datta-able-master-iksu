# api ---
import logging
import time
import datetime
import numpy as np

from urllib.parse import urlparse
from scipy import stats
from gql import Client, client, gql
from gql.transport.requests import RequestsHTTPTransport
import requests
import json

from django.shortcuts import redirect

from apps.factory.models import Sensor
from apps.factory.serializer import RequestTotalSerializer
from apps.graph.statistics import HighPassFilter


# GraphQL
# ---
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
    # LOGGER = logging.getLogger('DataAcquisition')

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
                hpf_value = HighPassFilter.hpf_loop(hpf=6, valuesX=values, fRangesX=fRanges, sampleRatesX=sampleRates)
            elif axis == "Y":
                hpf_value = HighPassFilter.hpf_loop(hpf=6, valuesY=values, fRangesY=fRanges, sampleRatesY=sampleRates)
            elif axis == "Z":
                hpf_value = HighPassFilter.hpf_loop(hpf=6, valuesZ=values, fRangesZ=fRanges, sampleRatesZ=sampleRates)
            elif axis == "XYZ":
                hpf_value = HighPassFilter.hpf_loop(hpf=6, valuesXYZ=values, fRangesXYZ=fRanges,
                                                    sampleRatesXYZ=sampleRates)

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
            date = (datetime.datetime.now().timestamp())
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


def get_draw_data_by_graphql(request, sensor_tag):
    # logging.basicConfig(level=logging.INFO)
    # logging.getLogger("graphql").setLevel(logging.WARNING)

    # replace xx.xx.xx.xx with the IP address of your server
    # serverIP = "25.3.15.233" #BKT
    # serverIP = '25.55.114.208'  # KPU
    # serverIP = '25.12.181.157' #SKT1
    # serverIP = '25.17.10.130' #SKT2
    # serverIP = '25.9.7.151'
    serverIP = request.session.get("serverIP")
    serverUrl = urlparse('http://{:s}:8000/graphql'.format(serverIP))

    sensor = RequestTotalSerializer.request_sensor_name_check(sensor_tag)

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

    endtime = time.time() - 3600 * 6
    starttime = endtime - 3600 * 6

    end_time_stamp_str = datetime.datetime.fromtimestamp(endtime).strftime("%Y-%m-%dT%H:%M:%S+00:00")
    start_time_stamp_str = datetime.datetime.fromtimestamp(starttime).strftime("%Y-%m-%dT%H:%M:%S+00:00")

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
            d = datetime.datetime.strptime(date, "%Y-%m-%dT%H:%M:%S+00:00").timestamp()
            epoch_dates_x.append(d)

            XRmsRawValue.append(HighPassFilter.rms(values_x[i]))
            gKurtXRawValue.append(stats.kurtosis(values_x[i]))
            i += 1

        except TypeError or IndexError or ValueError:
            try:
                d = datetime.datetime.strptime(date, "%Y-%m-%dT%H:%M:%S+00:00").timestamp()
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
            d = datetime.datetime.strptime(date, "%Y-%m-%dT%H:%M:%S+00:00").timestamp()
            epoch_dates_y.append(d)

            YRmsRawValue.append(HighPassFilter.rms(values_y[i]))
            gKurtYRawValue.append(stats.kurtosis(values_y[i]))
            i += 1

        except TypeError or IndexError or ValueError:
            try:
                d = datetime.datetime.strptime(date, "%Y-%m-%dT%H:%M:%S+00:00").timestamp()
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
            d = datetime.datetime.strptime(date, "%Y-%m-%dT%H:%M:%S+00:00").timestamp()
            epoch_dates_z.append(d)

            val_z = np.array(values_z[i])
            ZRmsRawValue.append(HighPassFilter.rms(val_z))
            gKurtZRawValue.append(stats.kurtosis(val_z))
            i += 1

        except TypeError or IndexError or ValueError:
            try:
                d = datetime.datetime.strptime(date, "%Y-%m-%dT%H:%M:%S+00:00").timestamp()
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

    yield start_time_stamp_str
    yield temperature

    yield epoch_dates_x
    yield XRmsRawValue
    yield gKurtXRawValue

    yield epoch_dates_y
    yield YRmsRawValue
    yield gKurtYRawValue

    yield epoch_dates_z
    yield ZRmsRawValue
    yield gKurtZRawValue


def gql_process(request, sensor_tag):
    start_proc = time.time()

    header = [i for i in get_draw_data_by_graphql(request, sensor_tag)]

    for start_time_stamp_str, temperature, epoch_dates_x, XRmsRawValue, gKurtXRawValue, epoch_dates_y, YRmsRawValue, gKurtYRawValue, epoch_dates_z, ZRmsRawValue, gKurtZRawValue in zip(
            header):
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