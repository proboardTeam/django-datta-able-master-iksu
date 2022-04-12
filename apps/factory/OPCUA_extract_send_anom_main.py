# -*- coding: utf-8 -*-
"""
Created on Thu Nov  4 15:39:07 2021

@author: Sumin Lee
"""

import time
import sys
import pytz
import logging
import datetime
from urllib.parse import urlparse
import matplotlib.pyplot as plt
import json
import numpy as np
import math
import scipy.signal
from scipy import stats
import csv
# from datetime import datetime
import calendar
from itertools import zip_longest
import pandas as pd
from dateutil import parser
from opcua import ua, Client
from azure.servicebus import ServiceBusClient, ServiceBusMessage
import json
import time
from azure.servicebus._common.constants import MAX_ABSOLUTE_EXPIRY_TIME
import schedule
import re
from opcua.common.node import Node
from azure.servicebus import ServiceBusClient, ServiceBusMessage
from azure.servicebus._common.constants import MAX_ABSOLUTE_EXPIRY_TIME
from itertools import chain

def send_a_list_of_messages(sender, tr_data):
    # create a list of messages
    # messages = [ServiceBusMessage(str(json_data)) for _ in range(1)]
    messages=[]
    for i in range(len(tr_data)):
        a= ServiceBusMessage(str(tr_data[i]))
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
        except:
            print("Error in sending messages")
            
class HighPassFilter(object):
    @staticmethod
    def get_highpass_coefficients(lowcut, sampleRate, order=5):
        nyq = 0.5 * sampleRate
        low = lowcut / nyq
        b, a = scipy.signal.butter(order, [low], btype='highpass')
        return b, a

    @staticmethod
    def run_highpass_filter(data, lowcut, sampleRate, order=5):
        if lowcut >= sampleRate/2.0:
            return data*0.0
        b, a = HighPassFilter.get_highpass_coefficients(
            lowcut, sampleRate, order=order)
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
        assert(nOverlap < winSize)
        assert(mode in ('magnitudeRMS', 'magnitudePeak', 'lin', 'log'))

        # Compose window and calculate 'coherent gain scale factor'
        w = scipy.signal.get_window(window, winSize)
        # http://www.bores.com/courses/advanced/windows/files/windows.pdf
        # Bores signal processing: "FFT window functions: Limits on FFT analysis"
        # F. J. Harris, "On the use of windows for harmonic analysis with the
        # discrete Fourier transform," in Proceedings of the IEEE, vol. 66, no. 1,
        # pp. 51-83, Jan. 1978.
        coherentGainScaleFactor = np.sum(w)/winSize

        # Zero-pad signal if smaller than window
        padding = len(w) - len(signal)
        if padding > 0:
            signal = np.pad(signal, (0, padding), 'constant')

        # Number of windows
        k = int(np.fix((len(signal)-nOverlap)/(len(w)-nOverlap)))

        # Calculate psd
        j = 0
        spec = np.zeros(len(w))
        for i in range(0, k):
            segment = signal[j:j+len(w)]
            if detrend is True:
                segment = scipy.signal.detrend(segment)
            winData = segment*w
            # Calculate FFT, divide by sqrt(N) for power conservation,
            # and another sqrt(N) for RMS amplitude spectrum.
            fftData = np.fft.fft(winData, len(w))/len(w)
            sqAbsFFT = abs(fftData/coherentGainScaleFactor)**2
            spec = spec + sqAbsFFT
            j = j + len(w) - nOverlap

        # Scale for number of windows
        spec = spec/k

        # If signal is not complex, select first half
        if len(np.where(np.iscomplex(signal))[0]) == 0:
            stop = int(math.ceil(len(w)/2.0))
            # Multiply by 2, except for DC and fmax. It is asserted that N is even.
            spec[1:stop-1] = 2*spec[1:stop-1]
        else:
            stop = len(w)
        spec = spec[0:stop]
        freq = np.round(float(fs)/len(w)*np.arange(0, stop), 2)

        if mode == 'lin':  # Linear Power spectrum
            return (spec, freq)
        elif mode == 'log':  # Log Power spectrum
            return (10.*np.log10(spec), freq)
        elif mode == 'magnitudeRMS':  # RMS Magnitude spectrum
            return (np.sqrt(spec), freq)
        elif mode == 'magnitudePeak':  # Peak Magnitude spectrum
            return (np.sqrt(2.*spec), freq)

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
        assert(result.StatusCode.is_good())
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
            assert(client._client.uaclient._uasocket.timeout == 15)
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
            assert(remaining >= 0)
            numvalues = min(DataAcquisition.MAX_VALUES_PER_REQUEST, remaining)
            partial, contId = client.read_raw_history(
                uaNode=endNode,
                starttime=starttime,
                endtime=endtime,
                numvalues=numvalues,
                cont=contId
            )
            if not len(partial):
                DataAcquisition.LOGGER.warn(
                    'No data was returned for {:s}'.format(endNodeName)
                )
                break
            dvList.extend(partial)
            sys.stdout.write('\r    Loaded {:d} values, {:s} -> {:s}'.format(
                len(dvList),
                str(dvList[0].ServerTimestamp.strftime("%Y-%m-%d %H:%M:%S")),
                str(dvList[-1].ServerTimestamp.strftime("%Y-%m-%d %H:%M:%S"))
            ))
            sys.stdout.flush()
            if contId is None:
                break  # No more data.
            if len(dvList) >= DataAcquisition.MAX_VALUES_PER_ENDNODE:
                break  # Too much data.
        sys.stdout.write('...OK.\n')
        return dvList

    @staticmethod
    def get_sensor_sub_node(client, macId, browseName, subBrowseName, sub2BrowseName=None, sub3BrowseName=None, sub4BrowseName=None):
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
            if key[-1]==axis:
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
                    DataAcquisition.get_sensor_sub_node(client, macId, "tensorFlow", "models", key, "lossMAE", "alarmLevel")
                alarmLevel = sensorNode.get_value()
                modelSet = {
                    "raw": (valuesraw, datesraw),
                    "alarmLevel": alarmLevel
                    }
                models[key] = modelSet
                
        return models
    

def rms(arr):
    return np.sqrt(np.mean(arr**2))

def main(sensor, duration):

    servName = sensor.servName
    servIP = sensor.servIP
    macID = sensor.macID    

    logging.basicConfig(level=logging.INFO)
    logging.getLogger("opcua").setLevel(logging.WARNING)
    
    # serverIP = '25.17.10.130' #SKT2_polytec
    serverIP = servIP #SKT1_GPN
    # serverIP = '25.3.15.233' #BKT_KPI

    # serverIP = sensor.servIP
    # macId = sensor.macID
    # deviceId = sensor.servName

    serverUrl = urlparse('opc.tcp://{:s}:4840'.format(serverIP))

    # macId='05:92:6d:a7' #(SKT2) Polytec Pump_Left_vib
    # macId='66:a0:b7:9d' #(SKT2) Polytec Pump_Left_vib
    # macId='94:f3:9e:df' #(SKT1) GPN Etching_White
    macId=macID #(SKT1) GPN Etching_Black
    # macId='82:8e:2c:a3' #(BKT) KPI Press_Vib_110Right 
    # macId='9b:a3:eb:47' #(BKT) KPI Press_Vib_80Left


    # change settings
    limit = 1000  # limit limits the number of returned measurements
    # axis = 'Y'  # axis allows to select data from only 1 or multiple axes
    hpf = 6

    endtime = datetime.datetime.now() - datetime.timedelta(minutes=540)
    starttime = endtime - datetime.timedelta(minutes=duration)
    
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
        data[i] = [d/512.0*formatRanges[i] for d in data[i]]
        data[i] = HighPassFilter.perform_hpf_filtering(
            data=data[i],
            sampleRate=sampleRates[i], 
            hpf=hpf
        )

    (temperatures, datesT) = DataAcquisition.get_sensor_data(
        serverUrl=serverUrl,
        macId=macId,
        browseName="boardTemperature", #3
        starttime=starttime,
        endtime=endtime
    )

    (batteryVoltage, datesV) = DataAcquisition.get_sensor_data(
        serverUrl=serverUrl,
        macId=macId,
        browseName="batteryVoltage", #2
        starttime=starttime,
        endtime=endtime
    )

    dates = [round(datetime.datetime.strptime(date, "%Y-%m-%d %H:%M:%S").timestamp()*1000+3600000*9) for date in dates]
    datesT = [round(datetime.datetime.strptime(date, "%Y-%m-%d %H:%M:%S").timestamp()*1000+3600000*9) for date in datesT]
    datesV = [round(datetime.datetime.strptime(date, "%Y-%m-%d %H:%M:%S").timestamp()*1000+3600000*9) for date in datesV]
        
    with OpcUaClient(serverUrl) as client:
        assert(client._client.uaclient._uasocket.timeout == 15)
        datesAD_X, datesAD_Y, datesAD_Z, X_pe, Y_pe, Z_pe = ([] for i in range(6)) 

        # acquire model data
        modelDictX = DataAcquisition.get_anomaly_model_parameters(
            client=client,
            macId=macId,
            starttime=starttime,
            endtime=endtime,
            axis='X'
        )
        if len(list(modelDictX.keys()))>1:
            print("There are more than one AI models for X")
        if len(list(modelDictX.keys()))>0:
            model = list(modelDictX.keys())[-1]
            datesAD_X = modelDictX[model]["raw"][1]
            datesAD_X = [round(datetime.datetime.strptime(date, '%Y-%m-%d %H:%M:%S').timestamp()*1000+3600000*9) for date in datesAD_X]
            X_pe = modelDictX[model]["raw"][0]
        
        modelDictY = DataAcquisition.get_anomaly_model_parameters(
            client=client,
            macId=macId,
            starttime=starttime,
            endtime=endtime,
            axis='Y'
        )
        if len(list(modelDictY.keys()))>1:
            print("There are more than one AI models for Y")
        if len(list(modelDictY.keys()))>0:
            model = list(modelDictY.keys())[-1]
            datesAD_Y = modelDictY[model]["raw"][1]
            for i in range(len(datesAD_Y)):
                datesAD_Y[i] = round(datetime.datetime.strptime(datesAD_Y[i], '%Y-%m-%d %H:%M:%S').timestamp()*1000+3600000*9)
            Y_pe = modelDictY[model]["raw"][0]
            
        modelDictZ = DataAcquisition.get_anomaly_model_parameters(
            client=client,
            macId=macId,
            starttime=starttime,
            endtime=endtime,
            axis='Z'
        )
        if len(list(modelDictZ.keys()))>1:
            print("There are more than one AI models for Z")
        if len(list(modelDictZ.keys()))>0:
            model = list(modelDictZ.keys())[-1]
            datesAD_Z = modelDictZ[model]["raw"][1]
            for i in range(len(datesAD_Z)):
                datesAD_Z[i] = round(datetime.datetime.strptime(datesAD_Z[i], '%Y-%m-%d %H:%M:%S').timestamp()*1000+3600000*9)
            Z_pe = modelDictZ[model]["raw"][0]

    
        
    time_list = list(chain(dates, datesT, datesV, datesAD_X, datesAD_Y, datesAD_Z))
    
    #10개 리스트 초기화
    Xrms_list, Yrms_list, Zrms_list, Xkurt_list, Ykurt_list, Zkurt_list, Temp_list, Voltage_list, X_AD, Y_AD, Z_AD = ([] for i in range(11))
    
    for i in range(len(dates)):
        # X axis
        if axes[i]==0:
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
        elif axes[i]==1:
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
        elif axes[i]==2:
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
    
    Xrms_list.extend([None]*(xlen+ylen+zlen))
    Xkurt_list.extend([None]*(xlen+ylen+zlen))
    Yrms_list.extend([None]*(xlen+ylen+zlen))
    Ykurt_list.extend([None]*(xlen+ylen+zlen))
    Zrms_list.extend([None]*(xlen+ylen+zlen))
    Zkurt_list.extend([None]*(xlen+ylen+zlen))
    Temp_list.extend([None]*(xlen+ylen+zlen))
    Voltage_list.extend([None]*(xlen+ylen+zlen))

    
    X_AD.extend(X_pe)
    X_AD.extend([None]*(ylen+zlen))
    
    Y_AD.extend([None]*(xlen))
    Y_AD.extend(Y_pe)
    Y_AD.extend([None]*(zlen))
    
    Z_AD.extend([None]*(xlen+ylen))
    Z_AD.extend(Z_pe)

    # print(time_list)
    
    # print(len(time_list))
    # print(len(Xrms_list))
    # print(len(Yrms_list))
    # print(len(Zrms_list))
    # print(len(Xkurt_list))
    # print(len(Ykurt_list))
    # print(len(Zkurt_list))
    
    # print(len(X_AD))
    # print(len(Y_AD))
    # print(len(Z_AD))
    # print(len(Temp_list))
    # print(len(Voltage_list))
    # print(Voltage_list)
    # print("Done collecting data, start dumping")

    try:
        data2 = [{"serviceId":"76", "deviceId":servName, "timestamp": d, "contents":{"XRms": x,"YRms": y, "ZRms": z, "gKurtX": kx, "gKurtY": ky, "gKurtZ": kz, "XaiPredError":adX, "YaiPredError":adY, "ZaiPredError":adZ, "BoardTemperature": t, "BatteryState":v}} 
             for (d, x, y, z, kx, ky, kz, adX, adY, adZ, t, v) in list(zip(time_list, Xrms_list, Yrms_list, Zrms_list, Xkurt_list, Ykurt_list, Zkurt_list, X_AD, Y_AD, Z_AD, Temp_list,Voltage_list))]
    except:
        print("Error in creating dictionary objects")
        
    data_list=[]
    for i in range(len(data2)):
        data = json.dumps(data2[i])
        data_list.append(data)

    # CONNECTION_STR = "Endpoint=sb://reshenietest2.servicebus.windows.net/;SharedAccessKeyName=RootManageSharedAccessKey;SharedAccessKey=aNo/hnefeXUKS6ei/VeOcFewKPYZ49MwSLMpH59Yk6M="
    CONNECTION_STR = "Endpoint=sb://sktiotcomservicebus01prd.servicebus.windows.net/;SharedAccessKeyName=reshenie;SharedAccessKey=LNbyO1dtSkYN2j6t1kwfh8Idn0IrGTNu6c1iczUPg5Q=;EntityPath=reshenie-telemetry-queue" # "<NAMESPACE CONNECTION STRING>"
    # QUEUE_NAME = "reshenietest2"
    QUEUE_NAME = "reshenie-telemetry-queue" #"<QUEUE NAME>"
    
    # Sending message to skt 
    servicebus_client = ServiceBusClient.from_connection_string(conn_str=CONNECTION_STR, logging_enable=True)
    
    with servicebus_client:
        # get a Queue Sender object to send messages to the queue
        sender = servicebus_client.get_queue_sender(queue_name=QUEUE_NAME)
        with sender:
            send_a_list_of_messages(sender, tr_data=data_list)
    print("Done sending data")
    
    # with servicebus_client:
    #     receiver = servicebus_client.get_queue_receiver(queue_name=QUEUE_NAME)
    #     with receiver:
    #         send_a_list_of_messages(receiver, tr_data=data_list)
    #         for msg in receiver:
    #             print("Received: " + str(msg))
    #             # complete the message so that the message is removed from the queue
    #             receiver.complete_message(msg)

    with open('C:/Users/user/Google Drive(reshenie.work@gmail.com)/Dashboard/dashboard/Reshenie_Old_wirevibsensor/SKT2_reshenie_Pump_right_vib_data.json', 'w') as json_file:
        json.dump(data2, json_file, indent=4)
        # data_list.append(data2)
        print("Done dumping data")
 