import time
import sys
import pytz
import logging
import datetime
from urllib.parse import urlparse
import matplotlib.pyplot as plt
import os
import numpy as np
import math
import scipy.signal

import pandas as pd
from dateutil import parser
from opcua import ua, Client


#
# class HighPassFilter(object):
#
#     @staticmethod
#     def get_highpass_coefficients(lowcut, sampleRate, order=5):
#         nyq = 0.5 * sampleRate
#         low = lowcut / nyq
#         b, a = scipy.signal.butter(order, [low], btype='highpass')
#         return b, a
#
#     @staticmethod
#     def run_highpass_filter(data, lowcut, sampleRate, order=5):
#         if lowcut >= sampleRate / 2.0:
#             return data * 0.0
#         b, a = HighPassFilter.get_highpass_coefficients(lowcut, sampleRate, order=order)
#         y = scipy.signal.filtfilt(b, a, data, padtype='even')
#         return y
#
#     @staticmethod
#     def perform_hpf_filtering(data, sampleRate, hpf=3):
#         if hpf == 0:
#             return data
#         data[0:6] = data[13:7:-1]  # skip compressor settling
#         data = HighPassFilter.run_highpass_filter(
#             data=data,
#             lowcut=3,
#             sampleRate=sampleRate,
#             order=1,
#         )
#         data = HighPassFilter.run_highpass_filter(
#             data=data,
#             lowcut=int(hpf),
#             sampleRate=sampleRate,
#             order=2,
#         )
#         return data
#
#
# class FourierTransform(object):
#
#     @staticmethod
#     def perform_fft_windowed(signal, fs, winSize, nOverlap, window, detrend=True, mode='lin'):
#         assert (nOverlap < winSize)
#         assert (mode in ('magnitudeRMS', 'magnitudePeak', 'lin', 'log'))
#
#         # Compose window and calculate 'coherent gain scale factor'
#         w = scipy.signal.get_window(window, winSize)
#         # http://www.bores.com/courses/advanced/windows/files/windows.pdf
#         # Bores signal processing: "FFT window functions: Limits on FFT analysis"
#         # F. J. Harris, "On the use of windows for harmonic analysis with the
#         # discrete Fourier transform," in Proceedings of the IEEE, vol. 66, no. 1,
#         # pp. 51-83, Jan. 1978.
#         coherentGainScaleFactor = np.sum(w) / winSize
#
#         # Zero-pad signal if smaller than window
#         padding = len(w) - len(signal)
#         if padding > 0:
#             signal = np.pad(signal, (0, padding), 'constant')
#
#         # Number of windows
#         k = int(np.fix((len(signal) - nOverlap) / (len(w) - nOverlap)))
#
#         # Calculate psd
#         j = 0
#         spec = np.zeros(len(w))
#         for i in range(0, k):
#             segment = signal[j:j + len(w)]
#             if detrend is True:
#                 segment = scipy.signal.detrend(segment)
#             winData = segment * w
#             # Calculate FFT, divide by sqrt(N) for power conservation,
#             # and another sqrt(N) for RMS amplitude spectrum.
#             fftData = np.fft.fft(winData, len(w)) / len(w)
#             sqAbsFFT = abs(fftData / coherentGainScaleFactor) ** 2
#             spec = spec + sqAbsFFT;
#             j = j + len(w) - nOverlap
#
#         # Scale for number of windows
#         spec = spec / k
#
#         # If signal is not complex, select first half
#         if len(np.where(np.iscomplex(signal))[0]) == 0:
#             stop = int(math.ceil(len(w) / 2.0))
#             # Multiply by 2, except for DC and fmax. It is asserted that N is even.
#             spec[1:stop - 1] = 2 * spec[1:stop - 1]
#         else:
#             stop = len(w)
#         spec = spec[0:stop]
#         freq = np.round(float(fs) / len(w) * np.arange(0, stop), 2)
#
#         if mode == 'lin':  # Linear Power spectrum
#             return (spec, freq)
#         elif mode == 'log':  # Log Power spectrum
#             return (10. * np.log10(spec), freq)
#         elif mode == 'magnitudeRMS':  # RMS Magnitude spectrum
#             return (np.sqrt(spec), freq)
#         elif mode == 'magnitudePeak':  # Peak Magnitude spectrum
#             return (np.sqrt(2. * spec), freq)


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
    MAX_VALUES_PER_ENDNODE = 100000  # Num values per endnode
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
                # DataAcquisition.LOGGER.warn(
                DataAcquisition.LOGGER.warning(
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


def extractNsave(serverUrl, macId, path):
    # change settings
    timeZone = "Asia/Seoul"  # local time zone
    # limit = 10000  # limit limits the number of returned measurements
    # axis = 'Y'  # axis allows to select data from only 1 or multiple axes
    # hpf = 6

    # note: time should be set in 
    starttime = pytz.utc.localize(
        datetime.datetime.strptime("2022-04-04 00:00:00", '%Y-%m-%d %H:%M:%S')
    )
    endtime = pytz.utc.localize(
        datetime.datetime.strptime("2022-04-04 9:59:59", '%Y-%m-%d %H:%M:%S')
    )
    # acquire history data
    # browseName = ["accelerationPack", "axis", "batteryVoltage", "boardTemperature",
    #               "firmware", "formatRange", "gKurtX", "gKurtY", "gKurtZ", "gRmsX", "gRmsY",
    #               "gRmsZ", "hardware", "mmsKurtX", "mmsKurtY", "mmsKurtZ",
    #               "mmsRmsX", "mmsRmsY", "mmsRmsZ", "numSamples", "sampleRate"]
    browseName = ["pitch", "roll"]

    (values, dates) = DataAcquisition.get_sensor_data(
        serverUrl=serverUrl,
        macId=macId,
        browseName=browseName[0],
        starttime=starttime,
        endtime=endtime
    )

    # for result in zip (values, dates):
    #     print(result)

    dates = [date[i] for date in dates]

    (values2, dates2) = DataAcquisition.get_sensor_data(
        serverUrl=serverUrl,
        macId=macId,
        browseName=browseName[1],
        starttime=starttime,
        endtime=endtime
    )

    dates2 = [date2[i] for date2 in dates2]

    for result in zip(values2, dates2):
        print(result)

        # for i in range(len(dates2)):
        # convert vibration data to 'g' units and plot data
        # data = [val[1:-6] for val in values]
        # numSamples = [val[0] for val in values]
        # sampleRates = [val[-6] for val in values]
        # fRanges = [val[-5] for val in values]
        # axes = [val[-3] for val in values]
        # axis='Y'

        # for i in range(len(fRanges)):
        #     data[i] = [d / 512.0 * fRanges[i] for d in data[i]]
        #     maxTimeValue = numSamples[i] / sampleRates[i]
        #     stepSize = 1 / sampleRates[i]
        #     timeValues = np.arange(0, maxTimeValue, stepSize)
        #
        #     data[i] = HighPassFilter.perform_hpf_filtering(
        #         data=data[i],
        #         sampleRate=sampleRates[i],
        #         hpf=hpf
        #     )
        #     axis = ' '
        #
        #     if axes[i] == 0:
        #         axis = 'X'
        #     elif axes[i] == 1:
        #         axis = 'Y'
        #     else:
        #         axis = "Z"
        #
        #     windowSize = len(data[i])  # window size
        #     nOverlap = 0  # overlap window
        #     windowType = 'hann'  # hanning window
        #     mode = 'magnitudeRMS'  # RMS magnitude spectrum.
        #     (npFFT, npFreqs) = FourierTransform.perform_fft_windowed(
        #         signal=values[i],
        #         fs=sampleRates[i],
        #         winSize=windowSize,
        #         nOverlap=nOverlap,
        #         window=windowType,
        #         detrend=False,
        #         mode=mode)
        #
        #     # Write to csv files
        #
        #     tdata = {"Time [s]": timeValues, 'RMS Acceleration [g]': data[i]}
        #     fdata = {"Frequency [Hz]": npFreqs, 'RMS Acceleration [g]': npFFT}
        #     df = pd.DataFrame(tdata)
        #     df2 = pd.DataFrame(fdata)

        pitch_data = {'Date ': dates, 'pitch [deg]': values}
        df = pd.DataFrame.from_records(pitch_data)
        FN = "sensor_time-" + str(starttime).replace(':', '-') + "_pitch.csv"
        df.to_csv(path + '\\' + FN)

        roll_data = {'Data ': dates2, 'roll [deg]': values2}
        df2 = pd.DataFrame.from_records(roll_data)
        FN2 = "sensor_time-" + str(starttime).replace(':', '-') + "_roll.csv"
        df2.to_csv(path + '\\' + FN2)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    logging.getLogger("opcua").setLevel(logging.WARNING)

    # replace xx.xx.xx.xx with the IP address of your server
    # serverIP = "25.77.104.183"    #reshenieYC_new
    # serverIP = "25.27.135.161"    #Tachyon
    # serverIP= "25.100.74.22"      # 21C
    # serverIP = "25.31.102.59"      # 지인철 
    # serverIP = "25.52.52.52"       # DKSW
    # serverIP = "25.58.137.19"    #reshenieYC_old
    serverIP = "25.9.7.151"
    serverUrl = urlparse('opc.tcp://{:s}:4840'.format(serverIP))

    # replace xx:xx:xx:xx with your sensors macId
    # macId = 'b7:90:74:36'   #reshenieYC_New Vibration_Power
    # macId = '9e:85:50:50'   #Tachyon sensor 1
    # macId = 'b9:07:6c:24'   #Tachyon sensor 4
    # macId = '9d:d7:01:32'   #21C vib2_spindle_lowfq
    # macId = 'e0:89:b9:3c'   #21C vib1_spindle_highfq
    # macId = 'b4:a0:a4:07'   #21C vib3_Bed
    # macIds = ['0d:66:24:8e', '43:6d:7a:44', '4d:cf:46:e8', 'c5:76:f8:1f']   #지인철
    # macNames = ['TrapLine_1_Motor','TrapLine_1_Shaft','TrapLine_2_Motor','TrapLine_2_Shaft']   #지인철

    # macIds = ['95:b0:30:c5']
    macIds = ['5e:54:8a:8a']
    # macNames = ['Vibration']
    macNames = ['Inclination']

    # macIds = ['11:90:77:d8', 'a3:40:ba:60', '4b:98:18:4d', 'fb:cc:b1:63',
    #          '92:7c:bd:51', 'ce:42:0e:97']                                 #DKSW
    # macNames = ['Welding_Vib_LowFQ', 'Welding_Vib_HighFQ', 'Milling_Right_Vib_HighF', 'Milling_Left_Vib_LowF',
    #            'Current_WeldingLeft', 'Current_WeldingRight']              #DKSW

    parent_dir = 'C:\\Users\\User\\Iqunet_reshenie_old_test'
    for i in range(len(macIds)):
        childPath = parent_dir + '\\' + macNames[i]
        # create directory
        extractNsave(serverUrl, macIds[i], childPath)

        # try:
        #     os.mkdir(childPath)
        # except:
        #     pass
        # finally:
        #     extractNsave(serverUrl, macIds[i], childPath)

"""
        # Plot Figures, time domain
        
        plt.figure(); plt.subplot(2,1,1); plt.plot(timeValues, data[i])
        title = (local_time + datetime.timedelta(seconds=.5)).replace(microsecond=0)
        title = title.strftime("%a %b %d %Y %H:%M:%S")+" "+axis +" axis"
#        title = title.strftime("%a %b %d %Y %H:%M:%S")+" "+axis[i] +" axis"        
        plt.title(title)
#        plt.xlim((0, maxTimeValue)) 
        # plt.axis([0, maxTimeValue, -5.0, 5.0])
        plt.grid(True)
        plt.xlabel('Time [s]')
        plt.ylabel('RMS Acceleration [g]')
        #plot frequency domain
        plt.subplot(2,1,2);plt.plot(npFreqs, npFFT)
        plt.xlim((0, sampleRates[i]/2)) 
        viewPortOptions = [0.1, 0.2, 0.5, 1, 2, 4, 8, 16, 32, 64, 128]
        viewPort = [i for i in viewPortOptions if i >= max(npFFT)][0]
        plt.ylim((0,viewPort));plt.grid(True)
        plt.xlabel('Frequency [Hz]')
        plt.ylabel('RMS Acceleration [g]')       
"""
'''
    # acquire board temperature
    (temperatures, dates) = DataAcquisition.get_sensor_data(
        serverUrl=serverUrl,
        macId=macId,
        browseName="boardTemperature",
        starttime=starttime,
        endtime=endtime
    )
    for i in range(len(dates)):
          dates[i] = datetime.datetime.strptime(dates[i], '%Y-%m-%d %H:%M:%S')
          dates[i] = dates[i].replace(tzinfo=pytz.timezone('UTC')).astimezone(pytz.timezone(timeZone))
    plt.figure()
    plt.plot(dates, temperatures)
    plt.gcf().autofmt_xdate()
    myFmt = dates.DateFormatter('%Y-%m-%d %H:%M')
    plt.gca().xaxis.set_major_formatter(myFmt)
    plt.title('Board Temperature')
    plt.ylabel('°C')
'''
