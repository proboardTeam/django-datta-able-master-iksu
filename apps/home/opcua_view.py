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
from opcua import ua, Client, client
import time
from itertools import chain
from apps.factory.serializer import RequestTotalSerializer
from concurrent.futures import ThreadPoolExecutor
from django.shortcuts import render
from django import template
from django.views import View
import pytz
from apps.templatetags import repeat

register = template.Library()


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
            print(f'transformed : {transformed}')

        print(f'transformed done : {transformed}')
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
            print(f'y_transformed : {transformed}')

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


class OpcUaClient(object):
    CONNECT_TIMEOUT = 15  # [sec]
    RETRY_DELAY = 10  # [sec]
    MAX_RETRIES = 3  # [-]

    class Decorators(object):
        @staticmethod
        def autoConnectingClient(wrappedMethod):
            def wrapper(obj, *args, **kwargs):
                for retry in range(OpcUaClient.MAX_RETRIES):
                    try:
                        return wrappedMethod(obj, *args, **kwargs)
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
                    return wrappedMethod(obj, *args, **kwargs)

            return wrapper

    def __init__(self, serverUrl):
        self._logger = logging.getLogger(self.__class__.__name__)
        self._client = Client(
            serverUrl.geturl(),
            timeout=self.CONNECT_TIMEOUT
        )

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.disconnect()
        self._client = None

    @property
    @Decorators.autoConnectingClient
    def sensorList(self):
        return self.objectsNode.get_children()

    @property
    @Decorators.autoConnectingClient
    def objectsNode(self):
        path = [ua.QualifiedName(name='Objects', namespaceidx=0)]
        return self._client.get_root_node().get_child(path)
        # return self._client.get_root_node().get_node_class(path)

    def connect(self):
        self._client.connect()
        self._client.load_type_definitions()

    def disconnect(self):
        try:
            self._client.disconnect()
        except Exception:
            pass

    def reconnect(self):
        self.disconnect()
        self.connect()

    @Decorators.autoConnectingClient
    def get_browse_name(self, uaNode):
        return uaNode.get_browse_name()

    @Decorators.autoConnectingClient
    def get_node_class(self, uaNode):
        return uaNode.get_node_class()

    @Decorators.autoConnectingClient
    def get_namespace_index(self, uri):
        return self._client.get_namespace_index(uri)

    @Decorators.autoConnectingClient
    def get_child(self, uaNode, path):
        return uaNode.get_child(path)

    # def get_node_class(self, uaNode, path):
    #     return uaNode.get_node_class(path)

    @Decorators.autoConnectingClient
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
    def _history_read(uaNode, details, cont):
        valueid = ua.HistoryReadValueId()
        valueid.NodeId = uaNode.nodeid
        valueid.IndexRange = ''
        valueid.ContinuationPoint = cont

        params = ua.HistoryReadParameters()
        params.HistoryReadDetails = details
        params.TimestampsToReturn = ua.TimestampsToReturn.Both
        params.ReleaseContinuationPoints = False
        params.NodesToRead.append(valueid)
        result = uaNode.server.history_read(params)[0]
        return result


class DataAcquisition(object):
    LOGGER = logging.getLogger('DataAcquisition')
    MAX_VALUES_PER_ENDNODE = 10000  # Num values per endnode
    MAX_VALUES_PER_REQUEST = 2  # Num values per history request

    @staticmethod
    def get_sensor_data(serverUrl, macId, browseName, starttime, endtime):
        with OpcUaClient(serverUrl) as client:
            assert (client._client.uaclient._uasocket.timeout == 15)
            sensorNode = \
                DataAcquisition.get_sensor_node(client, macId, browseName)
            DataAcquisition.LOGGER.info(
                'Browsing {:s}'.format(macId)
            )
            (values, dates) = \
                DataAcquisition.get_endnode_data(
                    client=client,
                    endNode=sensorNode,
                    starttime=starttime,
                    endtime=endtime
                )
        return (values, dates)

    @staticmethod
    def get_sensor_axis_data(serverUrl, macId, browseName, starttime, endtime, axis):
        with OpcUaClient(serverUrl) as client:
            assert (client._client.uaclient._uasocket.timeout == 15)

            sensorNode = DataAcquisition.get_sensor_axis_node(client, macId, browseName, axis)

            DataAcquisition.LOGGER.info(
                'Browsing {:s}'.format(macId)
            )
            (values, dates) = \
                DataAcquisition.get_endnode_data(
                    client=client,
                    endNode=sensorNode,
                    starttime=starttime,
                    endtime=endtime
                )
        return (values, dates)

    @staticmethod
    def get_sensor_node(client, macId, browseName):
        nsIdx = client.get_namespace_index(
            'http://www.iqunet.com'
        )  # iQunet namespace index
        bpath = [
            ua.QualifiedName(name=macId, namespaceidx=nsIdx),
            ua.QualifiedName(name=browseName, namespaceidx=nsIdx)
        ]
        sensorNode = client.objectsNode.get_child(bpath)
        return sensorNode

    @staticmethod
    def get_sensor_axis_node(client, macId, browseName, axis):
        nsIdx = client.get_namespace_index(
            'http://www.iqunet.com'
        )  # iQunet namespace index
        bpath = [
            ua.QualifiedName(name=macId, namespaceidx=nsIdx),
            ua.QualifiedName(name=browseName, namespaceidx=nsIdx),
            ua.QualifiedName(name=axis, namespaceidx=nsIdx)
        ]
        sensorNode = client.objectsNode.get_child(bpath)
        return sensorNode

    @staticmethod
    def get_endnode_data(client, endNode, starttime, endtime):
        dvList = DataAcquisition.download_endnode(
            client=client,
            endNode=endNode,
            starttime=starttime,
            endtime=endtime
        )
        dates, values = ([], [])
        for dv in dvList:
            dates.append(dv.SourceTimestamp.strftime('%Y-%m-%d %H:%M:%S'))
            values.append(dv.Value.Value)

        # If no starttime is given, results of read_raw_history are reversed.
        if starttime is None:
            values.reverse()
            dates.reverse()
        return (values, dates)

    @staticmethod
    def download_endnode(client, endNode, starttime, endtime):
        endNodeName = client.get_browse_name(endNode).Name
        DataAcquisition.LOGGER.info(
            'Downloading endnode {:s}'.format(
                endNodeName
            )
        )
        dvList, contId = [], None
        while True:
            remaining = DataAcquisition.MAX_VALUES_PER_ENDNODE - len(dvList)
            assert (remaining >= 0)
            numvalues = min(DataAcquisition.MAX_VALUES_PER_REQUEST, remaining)
            partial, contId = client.read_raw_history(
                uaNode=endNode,
                starttime=starttime,
                endtime=endtime,
                numvalues=numvalues,
                cont=contId
            )
            if not len(partial):
                DataAcquisition.LOGGER.warning(
                    'No data was returned for {:s}'.format(endNodeName)
                )
                break
            dvList.extend(partial)
            sys.stdout.write('\r    Loaded {:d} values, {:s} -> {:s}\n'.format(
                len(dvList),
                str(dvList[0].ServerTimestamp.strftime("%Y-%m-%d %H:%M:%S")),
                str(dvList[-1].ServerTimestamp.strftime("%Y-%m-%d %H:%M:%S"))
            ))
            sys.stdout.flush()
            if contId is None:
                break  # No more data.
            if len(dvList) >= DataAcquisition.MAX_VALUES_PER_ENDNODE:
                break  # Too much data.

            # print(f"dvList : {dvList}")

        sys.stdout.write('...OK.\n')
        return dvList

    @staticmethod
    def get_sensor_sub_node(client, macId, browseName, subBrowseName, sub2BrowseName=None, sub3BrowseName=None,
                            sub4BrowseName=None):
        nsIdx = client.get_namespace_index(
            'http://www.iqunet.com'
        )  # iQunet namespace index
        bpath = [
            ua.QualifiedName(name=macId, namespaceidx=nsIdx),
            ua.QualifiedName(name=browseName, namespaceidx=nsIdx),
            ua.QualifiedName(name=subBrowseName, namespaceidx=nsIdx)
        ]
        if sub2BrowseName is not None:
            bpath.append(ua.QualifiedName(name=sub2BrowseName, namespaceidx=nsIdx))
        if sub3BrowseName is not None:
            bpath.append(ua.QualifiedName(name=sub3BrowseName, namespaceidx=nsIdx))
        if sub4BrowseName is not None:
            bpath.append(ua.QualifiedName(name=sub4BrowseName, namespaceidx=nsIdx))
        sensorNode = client.objectsNode.get_child(bpath)
        return sensorNode

    @staticmethod
    def get_anomaly_model_nodes(client, macId):
        sensorNode = \
            DataAcquisition.get_sensor_sub_node(client, macId, "tensorFlow", "models")
        DataAcquisition.LOGGER.info(
            'Browsing for models of {:s}'.format(macId)
        )
        modelNodes = sensorNode.get_children()
        return modelNodes

    @staticmethod
    def get_anomaly_model_parameters(client, macId, starttime, endtime, axis):
        modelNodes = \
            DataAcquisition.get_anomaly_model_nodes(client, macId)
        models = dict()
        for mnode in modelNodes:
            key = mnode.get_display_name().Text
            if key[-1] == axis:
                sensorNode = \
                    DataAcquisition.get_sensor_sub_node(client, macId, "tensorFlow", "models", key, "lossMAE")
                (valuesraw, datesraw) = \
                    DataAcquisition.get_endnode_data(
                        client=client,
                        endNode=sensorNode,
                        starttime=starttime,
                        endtime=endtime
                    )
                sensorNode = \
                    DataAcquisition.get_sensor_sub_node(client, macId, "tensorFlow", "models", key, "lossMAE",
                                                        "alarmLevel")
                alarmLevel = sensorNode.get_value()
                modelSet = {
                    "raw": (valuesraw, datesraw),
                    "alarmLevel": alarmLevel
                }
                models[key] = modelSet

        return models


def main(sensor_tag):
    # '25.31.102.59', "ziincheol1",'0d:66:24:8e','84'
    # servName = sensor.servName
    # servIP = sensor.servIP
    # macID = sensor.macID
    start_proc = time.time()

    servName = "reshenie1"
    servIP = "25.52.52.52"

    sensor = RequestTotalSerializer.request_sensor_name_check(sensor_tag)
    macID = sensor.get().sensor_mac

    logging.basicConfig(level=logging.INFO)
    logging.getLogger("opcua").setLevel(logging.WARNING)

    # serverIP = '25.17.10.130' #SKT2_polytec
    serverIP = servIP  # SKT1_GPN
    # serverIP = '25.3.15.233' #BKT_KPI

    # serverIP = sensor.servIP
    # macId = sensor.macID
    # deviceId = sensor.servName

    serverUrl = urlparse('opc.tcp://{:s}:4840'.format(serverIP))

    # macId='05:92:6d:a7' #(SKT2) Polytec Pump_Left_vib
    # macId='66:a0:b7:9d' #(SKT2) Polytec Pump_Left_vib
    # macId='94:f3:9e:df' #(SKT1) GPN Etching_White
    macId = macID  # (SKT1) GPN Etching_Black
    # macId='82:8e:2c:a3' #(BKT) KPI Press_Vib_110Right 
    # macId='9b:a3:eb:47' #(BKT) KPI Press_Vib_80Left

    # change settings
    limit = 1000  # limit limits the number of returned measurements
    # axis = 'Y'  # axis allows to select data from only 1 or multiple axes
    hpf = 6

    # endtime = datetime.datetime.now() + datetime.timedelta(hours=8)
    # starttime = endtime - datetime.timedelta(hours=24.5)

    start_time = "2022-04-26T04:21:30.448000+00:00"
    end_time = "2022-04-26T04:21:31.448000+00:00"

    start_time = pytz.utc.localize(
        datetime.datetime.strptime(start_time, '%Y-%m-%dT%H:%M:%S.%f+00:00')
    )
    end_time = pytz.utc.localize(
        datetime.datetime.strptime(end_time, '%Y-%m-%dT%H:%M:%S.%f+00:00')
    )

    print(f"opcua start time : {start_time}")
    print(f"opcua end time : {end_time}")

    start_time_stamp_str = "2022-04-25T00:00:00"
    # end_time_stamp_str = "2022-04-20"
    # start_time_stamp_str = "2022-04-19"

    (values, dates) = DataAcquisition.get_sensor_data(
        serverUrl=serverUrl,
        macId=macId,
        browseName="accelerationPack",
        starttime=start_time,
        endtime=end_time
    )

    # (values_x, dates_x) = DataAcquisition.get_sensor_axis_data(
    #     serverUrl=serverUrl,
    #     macId=macId,
    #     browseName="accelerationPack",
    #     starttime=start_time,
    #     endtime=end_time,
    #     axis='X'
    # )
    #
    # (values_y, dates_y) = DataAcquisition.get_sensor_axis_data(
    #     serverUrl=serverUrl,
    #     macId=macId,
    #     browseName="accelerationPack",
    #     starttime=start_time,
    #     endtime=end_time,
    #     axis='Y'
    # )
    #
    # (values_z, dates_z) = DataAcquisition.get_sensor_axis_data(
    #     serverUrl=serverUrl,
    #     macId=macId,
    #     browseName="accelerationPack",
    #     starttime=start_time,
    #     endtime=end_time,
    #     axis='Z'
    # )

    # convert vibration data to 'g' units and plot data
    data = [val[1:-6] for val in values]
    sampleRates = [val[-6] for val in values]
    formatRanges = [val[-5] for val in values]
    axes = [val[-3] for val in values]
    for i in range(len(formatRanges)):
        data[i] = [d / 512.0 * formatRanges[i] for d in data[i]]
        data[i] = HighPassFilter.perform_hpf_filtering(
            data=data[i],
            sampleRate=sampleRates[i],
            hpf=hpf
        )

    (temperatures, datesT) = DataAcquisition.get_sensor_data(
        serverUrl=serverUrl,
        macId=macId,
        browseName="boardTemperature",  # 3
        starttime=start_time,
        endtime=end_time
    )

    (batteryVoltage, datesV) = DataAcquisition.get_sensor_data(
        serverUrl=serverUrl,
        macId=macId,
        browseName="batteryVoltage",  # 2
        starttime=start_time,
        endtime=end_time
    )

    dates = [round(datetime.datetime.strptime(date, "%Y-%m-%d %H:%M:%S").timestamp() * 1000 + 3600000 * 9) for date in
             dates]
    print(f"opcua dates: {dates}")

    # dates_x = [round(datetime.datetime.strptime(date_x, "%Y-%m-%d %H:%M:%S").timestamp()) for date_x in dates_x]
    # print(f"opcua x dates: {dates_x}")
    #
    # dates_y = [round(datetime.datetime.strptime(date_y, "%Y-%m-%d %H:%M:%S").timestamp()) for date_y in dates_y]
    # print(f"opcua y dates: {dates_y}")
    #
    # dates_z = [round(datetime.datetime.strptime(date_z, "%Y-%m-%d %H:%M:%S").timestamp()) for date_z in dates_z]
    # print(f"opcua z dates: {dates_z}")

    datesT = [round(datetime.datetime.strptime(date, "%Y-%m-%d %H:%M:%S").timestamp() * 1000 + 3600000 * 9) for date in
              datesT]
    print(f"opcua datesT: {datesT}")

    datesV = [round(datetime.datetime.strptime(date, "%Y-%m-%d %H:%M:%S").timestamp() * 1000 + 3600000 * 9) for date in
              datesV]
    print(f"opcua datesV: {datesV}")

    with OpcUaClient(serverUrl) as client:
        assert (client._client.uaclient._uasocket.timeout == 15)
        datesAD_X, datesAD_Y, datesAD_Z, X_pe, Y_pe, Z_pe = ([] for i in range(6))

        # acquire model data
        modelDictX = DataAcquisition.get_anomaly_model_parameters(
            client=client,
            macId=macId,
            starttime=start_time,
            endtime=end_time,
            axis='X'
        )
        if len(list(modelDictX.keys())) > 1:
            print("There are more than one AI models for X")
        if len(list(modelDictX.keys())) > 0:
            model = list(modelDictX.keys())[-1]
            datesAD_X = modelDictX[model]["raw"][1]
            datesAD_X = [round(datetime.datetime.strptime(date, '%Y-%m-%d %H:%M:%S').timestamp() * 1000 + 3600000 * 9)
                         for date in datesAD_X]
            X_pe = modelDictX[model]["raw"][0]

        modelDictY = DataAcquisition.get_anomaly_model_parameters(
            client=client,
            macId=macId,
            starttime=start_time,
            endtime=end_time,
            axis='Y'
        )
        if len(list(modelDictY.keys())) > 1:
            print("There are more than one AI models for Y")
        if len(list(modelDictY.keys())) > 0:
            model = list(modelDictY.keys())[-1]
            datesAD_Y = modelDictY[model]["raw"][1]
            for i in range(len(datesAD_Y)):
                datesAD_Y[i] = round(
                    datetime.datetime.strptime(datesAD_Y[i], '%Y-%m-%d %H:%M:%S').timestamp() * 1000 + 3600000 * 9)
            Y_pe = modelDictY[model]["raw"][0]

        modelDictZ = DataAcquisition.get_anomaly_model_parameters(
            client=client,
            macId=macId,
            starttime=start_time,
            endtime=end_time,
            axis='Z'
        )
        if len(list(modelDictZ.keys())) > 1:
            print("There are more than one AI models for Z")
        if len(list(modelDictZ.keys())) > 0:
            model = list(modelDictZ.keys())[-1]
            datesAD_Z = modelDictZ[model]["raw"][1]
            for i in range(len(datesAD_Z)):
                datesAD_Z[i] = round(
                    datetime.datetime.strptime(datesAD_Z[i], '%Y-%m-%d %H:%M:%S').timestamp() * 1000 + 3600000 * 9)
            Z_pe = modelDictZ[model]["raw"][0]

    time_list = list(chain(dates, datesT, datesV, datesAD_X, datesAD_Y, datesAD_Z))

    # 10개 리스트 초기화
    Xrms_list, Yrms_list, Zrms_list, Xkurt_list, Ykurt_list, Zkurt_list, Temp_list, Voltage_list, X_AD, Y_AD, Z_AD, tim = \
        ([] for i in range(11))

    for i in range(len(dates)):
        # X axis
        if axes[i] == 0:
            Xrms_list.append(rms(data[i]))
            # print(f"Xrms: {Xrms_list}")
            Xkurt_list.append(stats.kurtosis(data[i]))
            Yrms_list.append(None)
            Ykurt_list.append(None)
            Zrms_list.append(None)
            Zkurt_list.append(None)
            Temp_list.append(None)
            Voltage_list.append(None)
            X_AD.append(None)
            Y_AD.append(None)
            Z_AD.append(None)

        # Y axis
        elif axes[i] == 1:
            Xrms_list.append(None)
            Xkurt_list.append(None)
            Yrms_list.append(rms(data[i]))
            Ykurt_list.append(stats.kurtosis(data[i]))
            Zrms_list.append(None)
            Zkurt_list.append(None)
            Temp_list.append(None)
            Voltage_list.append(None)
            X_AD.append(None)
            Y_AD.append(None)
            Z_AD.append(None)

        # Z axis
        elif axes[i] == 2:
            Xrms_list.append(None)
            Xkurt_list.append(None)
            Yrms_list.append(None)
            Ykurt_list.append(None)
            Zrms_list.append(rms(data[i]))
            Zkurt_list.append(stats.kurtosis(data[i]))
            Temp_list.append(None)
            Voltage_list.append(None)
            X_AD.append(None)
            Y_AD.append(None)
            Z_AD.append(None)

        else:
            print("Axes not in X, Y, Z")

    for i in range(len(datesT)):
        Xrms_list.append(None)
        Xkurt_list.append(None)
        Yrms_list.append(None)
        Ykurt_list.append(None)
        Zrms_list.append(None)
        Zkurt_list.append(None)
        Temp_list.append(temperatures[i])
        Voltage_list.append(None)
        X_AD.append(None)
        Y_AD.append(None)
        Z_AD.append(None)

    for i in range(len(datesV)):
        Xrms_list.append(None)
        Xkurt_list.append(None)
        Yrms_list.append(None)
        Ykurt_list.append(None)
        Zrms_list.append(None)
        Zkurt_list.append(None)
        Temp_list.append(None)
        Voltage_list.append(batteryVoltage[i])
        X_AD.append(None)
        Y_AD.append(None)
        Z_AD.append(None)

    xlen = len(datesAD_X)
    ylen = len(datesAD_Y)
    zlen = len(datesAD_Z)

    Xrms_list.extend([None] * (xlen + ylen + zlen))
    Xkurt_list.extend([None] * (xlen + ylen + zlen))
    Yrms_list.extend([None] * (xlen + ylen + zlen))
    Ykurt_list.extend([None] * (xlen + ylen + zlen))
    Zrms_list.extend([None] * (xlen + ylen + zlen))
    Zkurt_list.extend([None] * (xlen + ylen + zlen))
    Temp_list.extend([None] * (xlen + ylen + zlen))
    Voltage_list.extend([None] * (xlen + ylen + zlen))

    X_AD.extend(X_pe)
    X_AD.extend([None] * (ylen + zlen))

    Y_AD.extend([None] * (xlen))
    Y_AD.extend(Y_pe)
    Y_AD.extend([None] * (zlen))

    Z_AD.extend([None] * (xlen + ylen))
    Z_AD.extend(Z_pe)

    try:
        data2 = [{"serviceId": "76", "deviceId": servName, "timestamp": d,
                  "contents": {"XRms": x, "YRms": y, "ZRms": z, "gKurtX": kx, "gKurtY": ky, "gKurtZ": kz,
                               "XaiPredError": adX, "YaiPredError": adY, "ZaiPredError": adZ, "BoardTemperature": t,
                               "BatteryState": v}}
                 for (d, x, y, z, kx, ky, kz, adX, adY, adZ, t, v) in list(
                zip(time_list, Xrms_list, Yrms_list, Zrms_list, Xkurt_list, Ykurt_list, Zkurt_list, X_AD, Y_AD, Z_AD,
                    Temp_list, Voltage_list))]
        date_list = []
        json_results = []
        x_rms, y_rms, z_rms, x_kurt, y_kurt, z_kurt, x_pred_error, y_pred_error, z_pred_error, board_temperature, \
        battery_state = [], [], [], [], [], [], [], [], [], [], []

        for i in range(len(data2)):
            data = [data2[i]['contents']]
            json_results.append(data)

            # data_list.append(data)

        print(f'result length : {len(json_results)}')

        # print(json.dumps(data2, indent=4))
        # print(json.dumps(data_list, indent=4))

        # data_list.append(data2)
        print("Done dumping data")
        j = 0
        for i in range(len(json_results)):
            date_list.extend(json_results[i][j]['timestamp'])
            x_rms.extend(json_results[i][j]['XRms'])
            y_rms.extend(json_results[i][j]['YRms'])
            z_rms.extend(json_results[i][j]['ZRms'])
            x_kurt.extend(json_results[i][j]['gKurtX'])
            y_kurt.extend(json_results[i][j]['gKurtY'])
            z_kurt.extend(json_results[i][j]['gKurtZ'])
            x_pred_error.extend(json_results[i][j]['XaiPredError'])
            y_pred_error.extend(json_results[i][j]['YaiPredError'])
            z_pred_error.extend(json_results[i][j]['ZaiPredError'])
            board_temperature.append(json_results[i][j]['BoardTemperature'])
            battery_state.append(json_results[i][j]['BatteryState'])
            # if i == 9:
            #     break

            print(f'timestamp: {date_list}')
            print(f"opcua x_rms : {x_rms}")

        # contents = {
        #     'RMS': {'X': x_rms, 'Y': y_rms, 'Z': z_rms},
        #     'kurtosis': {'X': x_kurt, 'Y': y_kurt, 'Z': z_kurt},
        #     'predict_error': {'X': x_pred_error, 'Y': y_pred_error, 'Z': z_pred_error},
        #     'board_temperature': {'board_temperature': board_temperature},
        #     'battery_state': {'battery_state': battery_state}
        # }

        base_time = time.mktime(datetime.datetime.strptime(start_time_stamp_str, "%Y-%m-%dT%H:%M:%S").timetuple())
        print(f"start base time : {base_time}")

        end_proc = time.time() - start_proc
        print(f"opc-ua process time : {end_proc}")

        # return JsonResponse({'contents': contents}, status=201)
        return [x_rms, y_rms, z_rms], [x_kurt, y_kurt, z_kurt], board_temperature, base_time

    except ValueError:
        print("Error in creating dictionary objects")
        # return JsonResponse({'contents': 'value_error'}, status=201)


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
        bar_plot_x_time = date_list_x

        x_step_size = 0
        for i in range(len(x_time)):
            background_color.append('#3e95cd')
            border_color.append('#3e95cd')
            x_step_size += 0.5

        return rms, kurtosis, bar_plot_x_time, background_color, border_color

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
        my_rms, my_kurtosis, my_board_temperatures, my_time, start_time = main(kwargs['sensor_tag'])
        plot_temp = []
        for i in range(len(my_board_temperatures)):
            plot_temp.extend(my_board_temperatures[i])
        print(f'plot_temp = {plot_temp}')

        start_time_str = datetime.datetime.fromtimestamp(start_time).strftime("%Y년 %m월 %d일 %H시 %M분 %S초")
        print(f'my_rms[x] length : {len(my_rms[x])}, my_time[x] length : {len(my_time[x])}')
        print(f'my_rms[y] length : {len(my_rms[y])}, my_time[y] length : {len(my_time[y])}, my_time : {my_time[y]}')
        print(f'my_rms[z] length : {len(my_rms[z])}, my_time[z] length : {len(my_time[z])}')

        # you can change graph parameters
        (bar_plot_x_rms_values, bar_plot_x_kurtosis_values, bar_plot_x_time,
         x_background_color, x_border_color) = self.x_define(start_time, my_time[x], my_rms[x],
                                                             my_kurtosis[x])
        (bar_plot_y_rms_values, bar_plot_y_kurtosis_values, bar_plot_y_time,
         y_background_color, y_border_color) = self.y_define(start_time, my_time[y], my_rms[y],
                                                             my_kurtosis[y])
        (bar_plot_z_rms_values, bar_plot_z_kurtosis_values, bar_plot_z_time,
         z_background_color, z_border_color) = self.z_define(start_time, my_time[z], my_rms[z],
                                                             my_kurtosis[z])
        (bar_plot_xyz_time, bar_plot_xyz_rms_values, bar_plot_xyz_kurtosis_values,
         xyz_background_color, xyz_border_color) = self.xyz_define(
            start_time=start_time,
            x_time=my_time[x], y_time=my_time[y], z_time=my_time[z],
            x_rms=my_rms[x], y_rms=my_rms[y], z_rms=my_rms[z],
            x_kurtosis=my_kurtosis[x], y_kurtosis=my_kurtosis[y], z_kurtosis=my_kurtosis[z])

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
            'BarPlot_Board_Temperatures': plot_temp,
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

        return render(request, 'home/show-graph.html', {'context': context})




def opcua_process(sensor_tag):
    time.sleep(1)

    # '25.31.102.59', "ziincheol1",'0d:66:24:8e','84'
    # servName = sensor.servName
    # servIP = sensor.servIP
    # macID = sensor.macID
    start_proc = time.time()

    servName = "dksw1"
    servIP = "25.52.52.52"
    # servIP = "25.9.7.151"

    sensor = RequestTotalSerializer.request_sensor_name_check(sensor_tag)
    macID = sensor.get().sensor_mac

    logging.basicConfig(level=logging.INFO)
    logging.getLogger("opcua").setLevel(logging.WARNING)

    # serverIP = '25.17.10.130' #SKT2_polytec
    serverIP = servIP  # SKT1_GPN
    # serverIP = '25.3.15.233' #BKT_KPI

    # serverIP = sensor.servIP
    # macId = sensor.macID
    # deviceId = sensor.servName

    serverUrl = urlparse('opc.tcp://{:s}:4840'.format(serverIP))

    # macId='05:92:6d:a7' #(SKT2) Polytec Pump_Left_vib
    # macId='66:a0:b7:9d' #(SKT2) Polytec Pump_Left_vib
    # macId='94:f3:9e:df' #(SKT1) GPN Etching_White
    macId = macID  # (SKT1) GPN Etching_Black
    # macId='82:8e:2c:a3' #(BKT) KPI Press_Vib_110Right
    # macId='9b:a3:eb:47' #(BKT) KPI Press_Vib_80Left

    # change settings
    limit = 1000  # limit limits the number of returned measurements
    # axis = 'Y'  # axis allows to select data from only 1 or multiple axes
    hpf = 6

    # endtime = datetime.datetime.now() - datetime.timedelta(minutes=60 * 24)
    # starttime = endtime - datetime.timedelta(minutes=60 * 24)

    start_time_stamp_str = "2022-04-19"
    end_time_stamp_str = "2022-04-20"

    endtime = datetime.datetime.strptime("2022-04-20", '%Y-%m-%d')
    starttime = datetime.datetime.strptime("2022-04-19", '%Y-%m-%d')

    # end_time_stamp_str = "2022-04-20"
    # start_time_stamp_str = "2022-04-19"

    (values, dates) = DataAcquisition.get_sensor_data(
        serverUrl=serverUrl,
        macId=macId,
        browseName="accelerationPack",
        starttime=starttime,
        endtime=endtime
    )

    # convert vibration data to 'g' units and plot data
    data = [val[1:-6] for val in values]
    sampleRates = [val[-6] for val in values]
    formatRanges = [val[-5] for val in values]
    axes = [val[-3] for val in values]
    for i in range(len(formatRanges)):
        data[i] = [d / 512.0 * formatRanges[i] for d in data[i]]
        data[i] = HighPassFilter.perform_hpf_filtering(
            data=data[i],
            sampleRate=sampleRates[i],
            hpf=hpf
        )

    (temperatures, datesT) = DataAcquisition.get_sensor_data(
        serverUrl=serverUrl,
        macId=macId,
        browseName="boardTemperature",  # 3
        starttime=starttime,
        endtime=endtime
    )

    (batteryVoltage, datesV) = DataAcquisition.get_sensor_data(
        serverUrl=serverUrl,
        macId=macId,
        browseName="batteryVoltage",  # 2
        starttime=starttime,
        endtime=endtime
    )

    dates = [round(datetime.datetime.strptime(date, "%Y-%m-%d %H:%M:%S").timestamp() * 1000 + 3600000 * 9) for date in
             dates]
    datesT = [round(datetime.datetime.strptime(date, "%Y-%m-%d %H:%M:%S").timestamp() * 1000 + 3600000 * 9) for date in
              datesT]
    datesV = [round(datetime.datetime.strptime(date, "%Y-%m-%d %H:%M:%S").timestamp() * 1000 + 3600000 * 9) for date in
              datesV]

    with OpcUaClient(serverUrl) as client:
        assert (client._client.uaclient._uasocket.timeout == 15)
        datesAD_X, datesAD_Y, datesAD_Z, X_pe, Y_pe, Z_pe = ([] for i in range(6))

        # acquire model data
        modelDictX = DataAcquisition.get_anomaly_model_parameters(
            client=client,
            macId=macId,
            starttime=starttime,
            endtime=endtime,
            axis='X'
        )
        if len(list(modelDictX.keys())) > 1:
            print("There are more than one AI models for X")
        if len(list(modelDictX.keys())) > 0:
            model = list(modelDictX.keys())[-1]
            datesAD_X = modelDictX[model]["raw"][1]
            datesAD_X = [round(datetime.datetime.strptime(date, '%Y-%m-%d %H:%M:%S').timestamp() * 1000 + 3600000 * 9)
                         for date in datesAD_X]
            X_pe = modelDictX[model]["raw"][0]

        modelDictY = DataAcquisition.get_anomaly_model_parameters(
            client=client,
            macId=macId,
            starttime=starttime,
            endtime=endtime,
            axis='Y'
        )
        if len(list(modelDictY.keys())) > 1:
            print("There are more than one AI models for Y")
        if len(list(modelDictY.keys())) > 0:
            model = list(modelDictY.keys())[-1]
            datesAD_Y = modelDictY[model]["raw"][1]
            for i in range(len(datesAD_Y)):
                datesAD_Y[i] = round(
                    datetime.datetime.strptime(datesAD_Y[i], '%Y-%m-%d %H:%M:%S').timestamp() * 1000 + 3600000 * 9)
            Y_pe = modelDictY[model]["raw"][0]

        modelDictZ = DataAcquisition.get_anomaly_model_parameters(
            client=client,
            macId=macId,
            starttime=starttime,
            endtime=endtime,
            axis='Z'
        )
        if len(list(modelDictZ.keys())) > 1:
            print("There are more than one AI models for Z")
        if len(list(modelDictZ.keys())) > 0:
            model = list(modelDictZ.keys())[-1]
            datesAD_Z = modelDictZ[model]["raw"][1]
            for i in range(len(datesAD_Z)):
                datesAD_Z[i] = round(
                    datetime.datetime.strptime(datesAD_Z[i], '%Y-%m-%d %H:%M:%S').timestamp() * 1000 + 3600000 * 9)
            Z_pe = modelDictZ[model]["raw"][0]

    time_list = list(chain(dates, datesT, datesV, datesAD_X, datesAD_Y, datesAD_Z))

    # 10개 리스트 초기화
    Xrms_list, Yrms_list, Zrms_list, Xkurt_list, Ykurt_list, Zkurt_list, Temp_list, Voltage_list, X_AD, Y_AD, Z_AD = \
        ([] for i in range(11))

    for i in range(len(dates)):
        # X axis
        if axes[i] == 0:
            Xrms_list.append(rms(data[i]))
            Xkurt_list.append(stats.kurtosis(data[i]))
            Yrms_list.append(None)
            Ykurt_list.append(None)
            Zrms_list.append(None)
            Zkurt_list.append(None)
            Temp_list.append(None)
            Voltage_list.append(None)
            X_AD.append(None)
            Y_AD.append(None)
            Z_AD.append(None)

        # Y axis
        elif axes[i] == 1:
            Xrms_list.append(None)
            Xkurt_list.append(None)
            Yrms_list.append(rms(data[i]))
            Ykurt_list.append(stats.kurtosis(data[i]))
            Zrms_list.append(None)
            Zkurt_list.append(None)
            Temp_list.append(None)
            Voltage_list.append(None)
            X_AD.append(None)
            Y_AD.append(None)
            Z_AD.append(None)

        # Z axis
        elif axes[i] == 2:
            Xrms_list.append(None)
            Xkurt_list.append(None)
            Yrms_list.append(None)
            Ykurt_list.append(None)
            Zrms_list.append(rms(data[i]))
            Zkurt_list.append(stats.kurtosis(data[i]))
            Temp_list.append(None)
            Voltage_list.append(None)
            X_AD.append(None)
            Y_AD.append(None)
            Z_AD.append(None)

        else:
            print("Axes not in X, Y, Z")

    for i in range(len(datesT)):
        Xrms_list.append(None)
        Xkurt_list.append(None)
        Yrms_list.append(None)
        Ykurt_list.append(None)
        Zrms_list.append(None)
        Zkurt_list.append(None)
        Temp_list.append(temperatures[i])
        Voltage_list.append(None)
        X_AD.append(None)
        Y_AD.append(None)
        Z_AD.append(None)

    for i in range(len(datesV)):
        Xrms_list.append(None)
        Xkurt_list.append(None)
        Yrms_list.append(None)
        Ykurt_list.append(None)
        Zrms_list.append(None)
        Zkurt_list.append(None)
        Temp_list.append(None)
        Voltage_list.append(batteryVoltage[i])
        X_AD.append(None)
        Y_AD.append(None)
        Z_AD.append(None)

    xlen = len(datesAD_X)
    ylen = len(datesAD_Y)
    zlen = len(datesAD_Z)

    Xrms_list.extend([None] * (xlen + ylen + zlen))
    Xkurt_list.extend([None] * (xlen + ylen + zlen))
    Yrms_list.extend([None] * (xlen + ylen + zlen))
    Ykurt_list.extend([None] * (xlen + ylen + zlen))
    Zrms_list.extend([None] * (xlen + ylen + zlen))
    Zkurt_list.extend([None] * (xlen + ylen + zlen))
    Temp_list.extend([None] * (xlen + ylen + zlen))
    Voltage_list.extend([None] * (xlen + ylen + zlen))

    X_AD.extend(X_pe)
    X_AD.extend([None] * (ylen + zlen))

    Y_AD.extend([None] * (xlen))
    Y_AD.extend(Y_pe)
    Y_AD.extend([None] * (zlen))

    Z_AD.extend([None] * (xlen + ylen))
    Z_AD.extend(Z_pe)

    try:
        data2 = [{"serviceId": "76", "deviceId": servName, "timestamp": d,
                  "contents": {"XRms": x, "YRms": y, "ZRms": z, "gKurtX": kx, "gKurtY": ky, "gKurtZ": kz,
                               "XaiPredError": adX, "YaiPredError": adY, "ZaiPredError": adZ, "BoardTemperature": t,
                               "BatteryState": v}}
                 for (d, x, y, z, kx, ky, kz, adX, adY, adZ, t, v) in list(
                zip(time_list, Xrms_list, Yrms_list, Zrms_list, Xkurt_list, Ykurt_list, Zkurt_list, X_AD, Y_AD, Z_AD,
                    Temp_list, Voltage_list))]

        data_list = []
        json_results = []
        x_rms, y_rms, z_rms, x_kurt, y_kurt, z_kurt, x_pred_error, y_pred_error, z_pred_error, board_temperature, battery_state = [], [], [], [], [], [], [], [], [], [], []

        for i in range(len(data2)):
            data = [data2[i]['contents']]
            json_results.append(data)

            # data_list.append(data)

        print(f'result length : {len(json_results)}')

        # print(json.dumps(data2, indent=4))
        # print(json.dumps(data_list, indent=4))

        # data_list.append(data2)
        print("Done dumping data")
        j = 0
        for i in range(len(json_results)):
            x_rms.append(json_results[i][j]['XRms'])
            y_rms.append(json_results[i][j]['YRms'])
            z_rms.append(json_results[i][j]['ZRms'])
            x_kurt.append(json_results[i][j]['gKurtX'])
            y_kurt.append(json_results[i][j]['gKurtY'])
            z_kurt.append(json_results[i][j]['gKurtZ'])
            x_pred_error.append(json_results[i][j]['XaiPredError'])
            y_pred_error.append(json_results[i][j]['YaiPredError'])
            z_pred_error.append(json_results[i][j]['ZaiPredError'])
            board_temperature.append(json_results[i][j]['BoardTemperature'])
            battery_state.append(json_results[i][j]['BatteryState'])
            # if i == 9:
            #     break

        # contents = {
        #     'RMS': {'X': x_rms, 'Y': y_rms, 'Z': z_rms},
        #     'kurtosis': {'X': x_kurt, 'Y': y_kurt, 'Z': z_kurt},
        #     'predict_error': {'X': x_pred_error, 'Y': y_pred_error, 'Z': z_pred_error},
        #     'board_temperature': {'board_temperature': board_temperature},
        #     'battery_state': {'battery_state': battery_state}
        # }

        end_proc = time.time() - start_proc
        print(f"opc-ua process time : {end_proc}")

        return end_proc

    except ValueError:
        print("cancel")


def protocol_test(request, sensor_tag):
    start_time = time.time()

    with ThreadPoolExecutor(max_workers=2) as TPE:
        from django import apps
        gql_future = TPE.submit(repeat.gql_process, sensor_tag)

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

    context = {
        'gql_result': [gql_future.result()],
        'opcua_result': [opcua_future.result()],
        'current_running_time': [end_time],
        'sensor_tag': sensor_tag

    }
    return render(request, template_name='home/compare.html', context={'context': context})

#
# @register.filter
# def protocol_repeat(sensor_tag):
#     start_time = time.time()
#
#     with ThreadPoolExecutor(max_workers=2) as TPE:
#         from django import apps
#         gql_future = TPE.submit(repeat.gql_process, sensor_tag)
#
#         opcua_future = TPE.submit(opcua_process, sensor_tag)
#
#     # gql_future = gql_process(sensor_tag)
#     # opcua_future = opcua_process(sensor_tag)
#
#     end_time = time.time() - start_time
#
#     # print(f'gql_future : {gql_future.result()}')
#     # print(f'opcua_future : {opcua_future.result()}')
#
#     # return JsonResponse({'gql_future': gql_future.result(), 'opcua_future': opcua_future.result(),
#     #                      'current process time': end_time}, status=201)
#
#     # return JsonResponse({'gql_future': gql_future, 'opcua_future': opcua_future,  'current process time': end_time},
#     #                     status=201)
#
#     context = {
#         'gql_result': gql_future.result(),
#         'opcua_result': opcua_future.result(),
#         'current_running_time': end_time,
#
#     }
#
#     return context
