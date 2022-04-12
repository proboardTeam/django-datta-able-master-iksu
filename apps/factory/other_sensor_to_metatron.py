# -*- coding: utf-8 -*-
"""
Created on Thu Nov  4 15:39:07 2021

@author: Sumin Lee
"""

import sys
import logging
import datetime
from urllib.parse import urlparse
import numpy as np
import math
import scipy.signal
from scipy import stats
from opcua import ua, Client
import json
import time
from azure.servicebus import ServiceBusClient, ServiceBusMessage
from itertools import chain
import socket

def send_a_list_of_messages(sender, tr_data):
    # create a list of messages
    # messages = [ServiceBusMessage(str(json_data)) for _ in range(1)]
    messages = []
    for i in range(len(tr_data)):
        a = ServiceBusMessage(str(tr_data[i]))
        messages.append(a)
    print(len(tr_data), messages)
    # print(messages, type(messages))
    current_time = datetime.datetime.now()

    if not messages:
        print("there are no data during this period")
        print(current_time)
        pass
    else:
        try:
            sender.send_messages(messages)
            print("Done sending messages")
            print("-----------------------")
            print(current_time)
        except ValueError:
            print("Error in sending messages")


class HighPassFilter(object):
    @staticmethod
    def get_highpass_coefficients(lowcut, sample_rate, order=5):
        nyq = 0.5 * sample_rate
        low = lowcut / nyq
        b, a = scipy.signal.butter(order, [low], btype='highpass')
        return b, a

    @staticmethod
    def run_highpass_filter(data, lowcut, sample_rate, order=5):
        if lowcut >= sample_rate / 2.0:
            return data * 0.0
        b, a = HighPassFilter.get_highpass_coefficients(
            lowcut, sample_rate, order=order)
        y = scipy.signal.filtfilt(b, a, data, padtype='even')
        return y

    @staticmethod
    def perform_hpf_filtering(data, sample_rate, hpf=3):
        if hpf == 0:
            return data
        data[0:6] = data[13:7:-1]  # skip compressor settling
        data = HighPassFilter.run_highpass_filter(
            data=data,
            lowcut=3,
            sample_rate=sample_rate,
            order=1,
        )
        data = HighPassFilter.run_highpass_filter(
            data=data,
            lowcut=int(hpf),
            sample_rate=sample_rate,
            order=2,
        )
        return data


class FourierTransform(object):

    @staticmethod
    def perform_fft_windowed(signal, fs, win_size, n_overlap, window, detrend=True, mode='lin'):
        assert (n_overlap < win_size)
        assert (mode in ('magnitudeRMS', 'magnitudePeak', 'lin', 'log'))

        # Compose window and calculate 'coherent gain scale factor'
        w = scipy.signal.get_window(window, win_size)
        # http://www.bores.com/courses/advanced/windows/files/windows.pdf
        # Bores signal processing: "FFT window functions: Limits on FFT analysis"
        # F. J. Harris, "On the use of windows for harmonic analysis with the
        # discrete Fourier transform," in Proceedings of the IEEE, vol. 66, no. 1,
        # pp. 51-83, Jan. 1978.
        coherent_gain_scale_factor = np.sum(w) / win_size

        # Zero-pad signal if smaller than window
        padding = len(w) - len(signal)
        if padding > 0:
            signal = np.pad(signal, (0, padding), 'constant')

        # Number of windows
        k = int(np.fix((len(signal) - n_overlap) / (len(w) - n_overlap)))

        # Calculate psd
        j = 0
        spec = np.zeros(len(w))
        for i in range(0, k):
            segment = signal[j:j + len(w)]
            if detrend is True:
                segment = scipy.signal.detrend(segment)
            win_data = segment * w
            # Calculate FFT, divide by sqrt(N) for power conservation,
            # and another sqrt(N) for RMS amplitude spectrum.
            fft_data = np.fft.fft(win_data, len(w)) / len(w)
            sq_abs_fft = abs(fft_data / coherent_gain_scale_factor) ** 2
            spec = spec + sq_abs_fft
            j = j + len(w) - n_overlap

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
            return spec, freq
        elif mode == 'log':  # Log Power spectrum
            return 10. * np.log10(spec), freq
        elif mode == 'magnitudeRMS':  # RMS Magnitude spectrum
            return np.sqrt(spec), freq
        elif mode == 'magnitudePeak':  # Peak Magnitude spectrum
            return np.sqrt(2. * spec), freq


class OpcUaClient(object):
    CONNECT_TIMEOUT = 15  # [sec]
    RETRY_DELAY = 10  # [sec]
    MAX_RETRIES = 3  # [-]

    class Decorators(object):
        @staticmethod
        def auto_connecting_client(wrapped_method):
            def wrapper(obj, *args, **kwargs):
                for retry in range(OpcUaClient.MAX_RETRIES):
                    try:
                        return wrapped_method(obj, *args, **kwargs)
                    except ua.uaerrors.BadNoMatch:
                        raise
                    except Exception:
                        pass
                    try:
                        obj._logger.warn('(Re)connecting to OPC-UA service.')
                        obj.reconnect()
                    except ConnectionRefusedError:
                        obj._logger.warn(
                            'Connection refused. Retry in 10s.'.format(
                                OpcUaClient.RETRY_DELAY
                            )
                        )
                        time.sleep(OpcUaClient.RETRY_DELAY)
                else:  # So the exception is exposed.
                    obj.reconnect()
                    return wrapped_method(obj, *args, **kwargs)

            return wrapper

    def __init__(self, server_url):
        self._logger = logging.getLogger(self.__class__.__name__)
        self._client = Client(
            server_url.geturl(),
            timeout=self.CONNECT_TIMEOUT
        )

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.disconnect()
        self._client = None

    @property
    @Decorators.auto_connecting_client
    def sensor_list(self):
        return self.objects_node.get_children()

    @property
    @Decorators.auto_connecting_client
    def objects_node(self):
        path = [ua.QualifiedName(name='Objects', namespaceidx=0)]
        return self._client.get_root_node().get_child(path)
        # return self._client.get_root_node().get_node_class(path)

    def connect(self):
        self._client.connect()
        self._client.load_type_definitions()

    def disconnect(self):
        try:
            self._client.disconnect()
        except (socket.error, OSError) as exc:
            pass

    def reconnect(self):
        self.disconnect()
        self.connect()

    @Decorators.auto_connecting_client
    def get_browse_name(self, ua_node):
        return ua_node.get_browse_name()

    @Decorators.auto_connecting_client
    def get_node_class(self, ua_node):
        return ua_node.get_node_class()

    @Decorators.auto_connecting_client
    def get_namespace_index(self, uri):
        return self._client.get_namespace_index(uri)

    @Decorators.auto_connecting_client
    def get_child(self, ua_node, path):
        return ua_node.get_child(path)

    # def get_node_class(self, uaNode, path):
    #     return uaNode.get_node_class(path)

    @Decorators.auto_connecting_client
    def read_raw_history(self,
                         uaNode,
                         starttime=None,
                         endtime=None,
                         numvalues=0,
                         cont=None):
        details = ua.ReadRawModifiedDetails()
        details.IsReadModified = False
        details.StartTime = starttime or ua.get_win_epoch()
        details.EndTime = endtime or ua.get_win_epoch()
        details.NumValuesPerNode = numvalues
        details.ReturnBounds = True
        result = OpcUaClient._history_read(uaNode, details, cont)
        assert (result.StatusCode.is_good())
        return result.HistoryData.DataValues, result.ContinuationPoint

    @staticmethod
    def _history_read(ua_node, details, cont):
        valueid = ua.HistoryReadValueId()
        valueid.NodeId = ua_node.nodeid
        valueid.IndexRange = ''
        valueid.ContinuationPoint = cont

        params = ua.HistoryReadParameters()
        params.HistoryReadDetails = details
        params.TimestampsToReturn = ua.TimestampsToReturn.Both
        params.ReleaseContinuationPoints = False
        params.NodesToRead.append(valueid)
        result = ua_node.server.history_read(params)[0]
        return result


class DataAcquisition(object):
    LOGGER = logging.getLogger('DataAcquisition')
    MAX_VALUES_PER_END_NODE = 10000  # Num values per endnode
    MAX_VALUES_PER_REQUEST = 1000  # Num values per history request

    @staticmethod
    def get_sensor_data(server_url, mac_id, browse_name, start_time, end_time):
        with OpcUaClient(server_url) as client:
            assert (client._client.uaclient._uasocket.timeout == 15)
            sensor_node = \
                DataAcquisition.get_sensor_node(client, mac_id, browse_name)
            DataAcquisition.LOGGER.info(
                'Browsing {:s}'.format(mac_id)
            )
            (values, dates) = \
                DataAcquisition.get_end_node_data(
                    client=client,
                    end_node=sensor_node,
                    start_time=start_time,
                    end_time=end_time
                )
        return values, dates

    @staticmethod
    def get_sensor_node(client, mac_id, browse_name):
        ns_idx = client.get_namespace_index(
            'http://www.iqunet.com'
        )  # iQunet namespace index
        bpath = [
            ua.QualifiedName(name=mac_id, namespaceidx=ns_idx),
            ua.QualifiedName(name=browse_name, namespaceidx=ns_idx)
        ]
        sensor_node = client.objects_node.get_child(bpath)
        return sensor_node

    @staticmethod
    def get_end_node_data(client, end_node, start_time, end_time):
        dv_list = DataAcquisition.download_end_node(
            client=client,
            end_node=end_node,
            start_time=start_time,
            end_time=end_time
        )
        dates, values = ([], [])
        for dv in dv_list:
            dates.append(dv.SourceTimestamp.strftime('%Y-%m-%d %H:%M:%S'))
            values.append(dv.Value.Value)

        # If no start_time is given, results of read_raw_history are reversed.
        if start_time is None:
            values.reverse()
            dates.reverse()
        return values, dates

    @staticmethod
    def download_end_node(client, end_node, start_time, end_time):
        end_node_name = client.get_browse_name(end_node).Name
        DataAcquisition.LOGGER.info(
            'Downloading endnode {:s}'.format(
                end_node_name
            )
        )
        dv_list, cont_id = [], None
        while True:
            remaining = DataAcquisition.MAX_VALUES_PER_END_NODE - len(dv_list)
            assert (remaining >= 0)
            num_values = min(DataAcquisition.MAX_VALUES_PER_REQUEST, remaining)
            partial, cont_id = client.read_raw_history(
                uaNode=end_node,
                start_time=start_time,
                end_time=end_time,
                numvalues=num_values,
                cont=cont_id
            )
            if not len(partial):
                DataAcquisition.LOGGER.warning(
                    'No data was returned for {:s}'.format(end_node_name)
                )
                break
            dv_list.extend(partial)
            sys.stdout.write('\r    Loaded {:d} values, {:s} -> {:s}'.format(
                len(dv_list),
                str(dv_list[0].ServerTimestamp.strftime("%Y-%m-%d %H:%M:%S")),
                str(dv_list[-1].ServerTimestamp.strftime("%Y-%m-%d %H:%M:%S"))
            ))
            sys.stdout.flush()
            if cont_id is None:
                break  # No more data.
            if len(dv_list) >= DataAcquisition.MAX_VALUES_PER_END_NODE:
                break  # Too much data.
        sys.stdout.write('...OK.\n')
        return dv_list

    @staticmethod
    def get_sensor_sub_node(client, mac_id, browse_name, sub_browse_name, sub2_browse_name=None, sub3_browse_name=None,
                            sub4_browse_name=None):
        ns_idx = client.get_namespace_index(
            'http://www.iqunet.com'
        )  # iQunet namespace index
        b_path = [
            ua.QualifiedName(name=mac_id, namespaceidx=ns_idx),
            ua.QualifiedName(name=browse_name, namespaceidx=ns_idx),
            ua.QualifiedName(name=sub_browse_name, namespaceidx=ns_idx)
        ]
        if sub2_browse_name is not None:
            b_path.append(ua.QualifiedName(name=sub2_browse_name, namespaceidx=ns_idx))
        if sub3_browse_name is not None:
            b_path.append(ua.QualifiedName(name=sub3_browse_name, namespaceidx=ns_idx))
        if sub4_browse_name is not None:
            b_path.append(ua.QualifiedName(name=sub4_browse_name, namespaceidx=ns_idx))
        sensor_node = client.objects_node.get_child(b_path)
        return sensor_node

    @staticmethod
    def get_anomaly_model_nodes(client, mac_id):
        sensor_node = \
            DataAcquisition.get_sensor_sub_node(client, mac_id, "tensorFlow", "models")
        DataAcquisition.LOGGER.info(
            'Browsing for models of {:s}'.format(mac_id)
        )
        model_nodes = sensor_node.get_children()
        return model_nodes

    @staticmethod
    def get_anomaly_model_parameters(client, mac_id, start_time, end_time, axis):
        model_nodes = \
            DataAcquisition.get_anomaly_model_nodes(client, mac_id)
        models = dict()
        for m_node in model_nodes:
            key = m_node.get_display_name().Text
            if key[-1] == axis:
                sensor_node = \
                    DataAcquisition.get_sensor_sub_node(client, mac_id, "tensorFlow", "models", key, "lossMAE")
                (values_raw, dates_raw) = \
                    DataAcquisition.get_end_node_data(
                        client=client,
                        end_node=sensor_node,
                        start_time=start_time,
                        end_time=end_time
                    )
                sensor_node = \
                    DataAcquisition.get_sensor_sub_node(client, mac_id, "tensorFlow", "models", key, "lossMAE",
                                                        "alarm_level")
                alarm_level = sensor_node.get_value()
                model_set = {
                    "raw": (values_raw, dates_raw),
                    "alarm_level": alarm_level
                }
                models[key] = model_set

        return models


def rms(arr):
    return np.sqrt(np.mean(arr ** 2))


def main(sensor, duration):
    logging.basicConfig(level=logging.INFO)
    logging.getLogger("opcua").setLevel(logging.WARNING)

    # server_ip = '25.17.10.130' #SKT2
    # server_ip = '25.12.181.157' #SKT1
    # server_ip = '25.3.15.233' #BKT
    # server_ip = "25.100.199.132" #Kowon
    # server_ip = "25.105.77.110" #SFood
    # server_ip = "25.58.137.19" #reshenie_old
    # server_ip = "25.52.52.52" #reshnei_new
    server_ip = sensor.servIP
    mac_id = sensor.macID
    device_id = sensor.servName
    service_id = sensor.serviceId

    server_url = urlparse('opc.tcp://{:s}:4840'.format(server_ip))

    # mac_id='05:92:6d:a7' #SKT2 센서1
    # mac_id='66:a0:b7:9d' #SKT2 센서2
    # mac_id='94:f3:9e:df' #SKT1 센서1
    # mac_id='c6:28:a5:a3' #SKT1 센서2
    # mac_id='82:8e:2c:a3' #BKT 센서1
    # mac_id='9b:a3:eb:47' #BKT 센서2
    # mac_id='00:85:b7:f9' #SFood Center
    # mac_id = 'e0:10:9a:cd' #Kowon
    # mac_id = "ce:42:0e:97" #T_DK_current
    # mac_id = "a3:40:ba:60" #T_DK_vib

    # change settings
    hpf = 6

    end_time = datetime.datetime.now() - datetime.timedelta(minutes=540)
    start_time = end_time - datetime.timedelta(minutes=duration)

    (values, dates) = DataAcquisition.get_sensor_data(
        server_url=server_url,
        mac_id=mac_id,
        browse_name="accelerationPack",
        start_time=start_time,
        end_time=end_time
    )
    (value_sb, date_sb) = DataAcquisition.get_sensor_data(
        server_url=server_url,
        mac_id=mac_id,
        browse_name="batteryVoltage",
        start_time=start_time,
        end_time=end_time
    )

    # convert vibration data to 'g' units and plot data
    data = [val[1:-6] for val in values]
    sample_rates = [val[-6] for val in values]
    format_ranges = [val[-5] for val in values]
    axes = [val[-3] for val in values]
    for i in range(len(format_ranges)):
        data[i] = [d / 512.0 * format_ranges[i] for d in data[i]]
        data[i] = HighPassFilter.perform_hpf_filtering(
            data=data[i],
            sample_rate=sample_rates[i],
            hpf=hpf
        )

    (temperatures, dates_t) = DataAcquisition.get_sensor_data(
        server_url=server_url,
        mac_id=mac_id,
        browse_name="boardTemperature",
        start_time=start_time,
        end_time=end_time
    )

    dates_t = [round(datetime.datetime.strptime(date, "%Y-%m-%d %H:%M:%S").timestamp() * 1000 + 3600000 * 9) for date in
               dates_t]

    with OpcUaClient(server_url) as client:
        assert (client._client.uaclient._uasocket.timeout == 15)
        dates_ad_x, dates_ad_y, dates_ad_Z, x_pe, y_pe, z_pe = ([] for i in range(6))

        # acquire model data
        model_shift_x = DataAcquisition.get_anomaly_model_parameters(
            client=client,
            mac_id=mac_id,
            start_time=start_time,
            end_time=end_time,
            axis='X'
        )
        if len(list(model_shift_x.keys())) > 1:
            print("There are more than one AI models for X")
        if len(list(model_shift_x.keys())) > 0:
            model = list(model_shift_x.keys())[-1]
            dates_ad_x = model_shift_x[model]["raw"][1]
            dates_ad_x = [round(datetime.datetime.strptime(date, '%Y-%m-%d %H:%M:%S').timestamp() * 1000 + 3600000 * 9)
                          for date in dates_ad_x]
            x_pe = model_shift_x[model]["raw"][0]

        model_dict_y = DataAcquisition.get_anomaly_model_parameters(
            client=client,
            mac_id=mac_id,
            start_time=start_time,
            end_time=end_time,
            axis='Y'
        )
        if len(list(model_dict_y.keys())) > 1:
            print("There are more than one AI models for Y")
        if len(list(model_dict_y.keys())) > 0:
            model = list(model_dict_y.keys())[-1]
            dates_ad_y = model_dict_y[model]["raw"][1]
            for i in range(len(dates_ad_y)):
                dates_ad_y[i] = round(
                    datetime.datetime.strptime(dates_ad_y[i], '%Y-%m-%d %H:%M:%S').timestamp() * 1000 + 3600000 * 9)
            y_pe = model_dict_y[model]["raw"][0]

        model_dict_z = DataAcquisition.get_anomaly_model_parameters(
            client=client,
            mac_id=mac_id,
            start_time=start_time,
            end_time=end_time,
            axis='Z'
        )
        if len(list(model_dict_z.keys())) > 1:
            print("There are more than one AI models for Z")
        if len(list(model_dict_z.keys())) > 0:
            model = list(model_dict_z.keys())[-1]
            dates_ad_z = model_dict_z[model]["raw"][1]
            for i in range(len(dates_ad_z)):
                dates_ad_z[i] = round(
                    datetime.datetime.strptime(dates_ad_z[i], '%Y-%m-%d %H:%M:%S').timestamp() * 1000 + 3600000 * 9)
            z_pe = model_dict_z[model]["raw"][0]

    time_list = list(chain(dates, dates_t, date_sb, dates_ad_x, dates_ad_y, dates_ad_z))

    # 10개 리스트 제작 - AD = anormaly detection; predict error
    x_rms_list, y_rms_list, z_rms_list, x_kurt_list, y_kurt_list, z_kurt_list, temp_list, x_ad, y_ad, z_ad, battery_list \
        = ([] for i in range(11))

    for i in range(len(dates)):
        time_list[i] = round(
            datetime.datetime.strptime(time_list[i], "%Y-%m-%d %H:%M:%S").timestamp() * 1000 + 3600000 * 9)
        # X axis
        if axes[i] == 0:
            x_rms_list.append(rms(data[i]))
            x_kurt_list.append(stats.kurtosis(data[i]))
            y_rms_list.append(None)
            y_kurt_list.append(None)
            z_rms_list.append(None)
            z_kurt_list.append(None)
            temp_list.append(None)
            battery_list.append(None)
            x_ad.append(None)
            y_ad.append(None)
            z_ad.append(None)

        # Y axis
        elif axes[i] == 1:
            x_rms_list.append(None)
            x_kurt_list.append(None)
            y_rms_list.append(rms(data[i]))
            y_kurt_list.append(stats.kurtosis(data[i]))
            z_rms_list.append(None)
            z_kurt_list.append(None)
            temp_list.append(None)
            battery_list.append(None)
            x_ad.append(None)
            y_ad.append(None)
            z_ad.append(None)

        # Z axis
        elif axes[i] == 2:
            x_rms_list.append(None)
            x_kurt_list.append(None)
            y_rms_list.append(None)
            y_kurt_list.append(None)
            z_rms_list.append(rms(data[i]))
            z_kurt_list.append(stats.kurtosis(data[i]))
            temp_list.append(None)
            battery_list.append(None)
            x_ad.append(None)
            y_ad.append(None)
            z_ad.append(None)

        else:
            print("Axes not in X, Y, Z")

    for i in range(len(dates_t)):
        x_rms_list.append(None)
        x_kurt_list.append(None)
        y_rms_list.append(None)
        y_kurt_list.append(None)
        z_rms_list.append(None)
        z_kurt_list.append(None)
        temp_list.append(temperatures[i])
        battery_list.append(None)
        x_ad.append(None)
        y_ad.append(None)
        z_ad.append(None)

    for i in range(len(date_sb)):
        x_rms_list.append(None)
        x_kurt_list.append(None)
        y_rms_list.append(None)
        y_kurt_list.append(None)
        z_rms_list.append(None)
        z_kurt_list.append(None)
        temp_list.append(None)
        battery_list.append(value_sb[i])
        x_ad.append(None)
        y_ad.append(None)
        z_ad.append(None)

    xlen = len(dates_ad_x)
    ylen = len(dates_ad_y)
    zlen = len(dates_ad_z)

    x_rms_list.extend([None] * (xlen + ylen + zlen))
    x_kurt_list.extend([None] * (xlen + ylen + zlen))
    y_rms_list.extend([None] * (xlen + ylen + zlen))
    y_kurt_list.extend([None] * (xlen + ylen + zlen))
    z_rms_list.extend([None] * (xlen + ylen + zlen))
    z_kurt_list.extend([None] * (xlen + ylen + zlen))
    temp_list.extend([None] * (xlen + ylen + zlen))
    battery_list.extend([None] * (xlen + ylen + zlen))

    x_ad.extend(x_pe)
    x_ad.extend([None] * (ylen + zlen))

    y_ad.extend([None] * xlen)
    y_ad.extend(y_pe)
    y_ad.extend([None] * zlen)

    z_ad.extend([None] * (xlen + ylen))
    z_ad.extend(z_pe)

    # check that all lists are of the same lengths
    it = [x_rms_list, y_rms_list, z_rms_list, x_kurt_list, y_kurt_list, z_kurt_list, temp_list, x_ad, y_ad, z_ad,
          battery_list, time_list]
    the_len = len(time_list)
    if not all(len(le) == the_len for le in it):
        raise ValueError('All lists must have the same length')

    try:
        data2 = [{"service_id": service_id, "device_id": device_id, "timestamp": d,
                  "contents": {"XRms": x, "YRms": y, "ZRms": z, "gKurtX": kx, "gKurtY": ky, "gKurtZ": kz,
                               "XaiPredError": adX, "YaiPredError": adY, "ZaiPredError": adZ, "BoardTemperature": t,
                               "BatteryState": b}}
                 for (d, x, y, z, kx, ky, kz, adX, adY, adZ, t, b) in list(
                zip(time_list, x_rms_list, y_rms_list, z_rms_list, x_kurt_list, y_kurt_list, z_kurt_list, x_ad, y_ad,
                    z_ad, temp_list, battery_list))]

        data_list = []
        for i in range(len(data2)):
            data = json.dumps(data2[i])
            data_list.append(data)
        print(data_list)

        # Sending Data to Metatron Grandview(SKT)
        connection_str = "Endpoint=sb://sktiotcomservicebus01prd.servicebus.windows.net/;SharedAccessKeyName=reshenie;SharedAccessKey=U/MZ9W8ih7R7KE14Zrf3/5ef8k3valVnvsRNRK4+MuA=;EntityPath=reshenie-telemetry-queue"  # "<NAMESPACE CONNECTION STRING>"
        queue_name = "reshenie-telemetry-queue"  # "<QUEUE NAME>"

        servicebus_client = ServiceBusClient.from_connection_string(conn_str=connection_str, logging_enable=True)

        with servicebus_client:
            # get a Queue Sender object to send messages to the queue
            sender = servicebus_client.get_queue_sender(queue_name=queue_name)
            with sender:
                send_a_list_of_messages(sender, tr_data=data_list)
        print("Done sending data")

    except ValueError:
        print("Error in creating dictionary objects")

    # Receiving Message from Queue
    # with servicebus_client:
    #     receiver = servicebus_client.get_queue_receiver(queue_name=QUEUE_NAME)
    #     with receiver:
    #         send_a_list_of_messages(receiver, tr_data=data_list)
    #         for msg in receiver:
    #             print("Received: " + str(msg))
    #             # complete the message so that the message is removed from the queue
    #             receiver.complete_message(msg)

    # with open('C:/Users/user/Google Drive(reshenie.work@gmail.com)/Dashboard/dashboard/Reshenie_Old_wirevibsensor
    # /SKT2_reshenie_Pump_right_vib_data.json', 'w') as json_file: json.dump(data2, json_file, indent=4) #
    # data_list.append(data2) print("Done dumping data")

# if __name__=="__main__":
#     main()
#     schedule.every(60).minutes.do(main)

#     while 1:
#         schedule.run_pending()
#         time.sleep(1)
