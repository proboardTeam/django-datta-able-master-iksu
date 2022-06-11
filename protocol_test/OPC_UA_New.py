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
from apps.factory.models import Server, Sensor
from concurrent.futures import ThreadPoolExecutor
from django.shortcuts import render
from django import template
from django.views import View
import pytz
from apps.templatetags import repeat

from apps.graph.statistics import HighPassFilter


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
        return self.objectsNode.get_children()

    @property
    @Decorators.auto_connecting_client
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
                         ua_node,
                         start_time=None,
                         end_time=None,
                         num_values=0,
                         cont=None):
        details = ua.ReadRawModifiedDetails()
        details.IsReadModified = False
        details.StartTime = start_time or ua.get_win_epoch()
        details.EndTime = end_time or ua.get_win_epoch()
        details.NumValuesPerNode = num_values
        details.ReturnBounds = True
        result = OpcUaClient._history_read(ua_node, details, cont)
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
    MAX_VALUES_PER_REQUEST = 2  # Num values per history request

    @staticmethod
    def get_sensor_data(server_url, mac_id, browse_name, start_time, end_time):
        with OpcUaClient(server_url) as client:
            assert (client._client.uaclient._uasocket.timeout == 15)
            sensor_node = DataAcquisition.get_sensor_node(client, mac_id, browse_name)
            DataAcquisition.LOGGER.info(
                'Browsing {:s}'.format(mac_id)
            )
            (values, dates) = DataAcquisition.get_end_node_data(
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
        b_path = [
            ua.QualifiedName(name=mac_id, namespaceidx=ns_idx),
            ua.QualifiedName(name=browse_name, namespaceidx=ns_idx)
        ]
        sensor_node = client.objectsNode.get_child(b_path)
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

        # If no start time is given, results of read_raw_history are reversed.
        if start_time is None:
            values.reverse()
            dates.reverse()
        return values, dates

    # ms 단위까지
    @staticmethod
    def get_end_node_microseconds_data(client, end_node, start_time, end_time):
        dv_list = DataAcquisition.download_end_node(
            client=client,
            end_node=end_node,
            start_time=start_time,
            end_time=end_time
        )
        dates, values = ([], [])
        for dv in dv_list:
            try:
                dates.append(dv.SourceTimestamp.strftime('%Y-%m-%d %H:%M:%S.%f'))
            except ValueError:
                dates.append(dv.SourceTimestamp.strftime('%Y-%m-%d %H:%M:%S'))

            values.append(dv.Value.Value)

        # If no start time is given, results of read_raw_history are reversed.
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
                ua_node=end_node,
                start_time=start_time,
                end_time=end_time,
                num_values=num_values,
                cont=cont_id
            )
            if not len(partial):
                DataAcquisition.LOGGER.warning(
                    'No data was returned for {:s}'.format(end_node_name)
                )
                break
            dv_list.extend(partial)
            sys.stdout.write('\r    Loaded {:d} values, {:s} -> {:s}\n'.format(
                len(dv_list),
                str(dv_list[0].ServerTimestamp.strftime("%Y-%m-%d %H:%M:%S")),
                str(dv_list[-1].ServerTimestamp.strftime("%Y-%m-%d %H:%M:%S"))
            ))
            sys.stdout.flush()
            if cont_id is None:
                break  # No more data.
            if len(dv_list) >= DataAcquisition.MAX_VALUES_PER_END_NODE:
                break  # Too much data.

            # print(f"dvList : {dvList}")

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

        sensor_node = client.objectsNode.get_child(b_path)

        return sensor_node

    @staticmethod
    def get_anomaly_model_nodes(client, mac_id):
        sensor_node = DataAcquisition.get_sensor_sub_node(client, mac_id, "tensorFlow", "models")
        DataAcquisition.LOGGER.info(
            'Browsing for models of {:s}'.format(mac_id)
        )
        model_nodes = sensor_node.get_children()
        return model_nodes

    @staticmethod
    def get_axis_acceleration_pack_nodes(client, mac_id, axis):
        sensor_node = None
        if axis == 'x':
            sensor_node = DataAcquisition.get_sensor_sub_node(client, mac_id, "vibration", axis, "accel", "xAccelTimeOrdinate")
        if axis == 'y':
            sensor_node = DataAcquisition.get_sensor_sub_node(client, mac_id, "vibration", axis, "accel", "yAccelTimeOrdinate")
        if axis == 'z':
            sensor_node = DataAcquisition.get_sensor_sub_node(client, mac_id, "vibration", axis, "accel", "zAccelTimeOrdinate")

        DataAcquisition.LOGGER.info(
            'Browsing for {:s} axis vibration of {:s}'.format(axis, mac_id)
        )

        return sensor_node

    @staticmethod
    def get_axis_rms_nodes(client, mac_id, axis):
        sensor_node = None
        if axis == 'x':
            sensor_node = DataAcquisition.get_sensor_sub_node(client, mac_id, "aggregate", axis, "rms", "accelRmsX")
        if axis == 'y':
            sensor_node = DataAcquisition.get_sensor_sub_node(client, mac_id, "aggregate", axis, "rms", "accelRmsY")
        if axis == 'z':
            sensor_node = DataAcquisition.get_sensor_sub_node(client, mac_id, "aggregate", axis, "rms", "accelRmsZ")

        DataAcquisition.LOGGER.info(
            'Browsing for {:s} axis vibration of {:s}'.format(axis, mac_id)
        )

        return sensor_node

    @staticmethod
    def get_anomaly_model_parameters(client, mac_id, start_time, end_time, axis):
        model_nodes = DataAcquisition.get_anomaly_model_nodes(client, mac_id)
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
                                                        "alarmLevel")
                alarm_level = sensor_node.get_value()
                model_set = {
                    "raw": (values_raw, dates_raw),
                    "alarmLevel": alarm_level
                }
                models[key] = model_set

        return models

    @staticmethod
    def get_acceleration_pack_parameters(client, mac_id, start_time, end_time, axis):
        sensor_node = DataAcquisition.get_axis_acceleration_pack_nodes(client, mac_id, axis)

        (values_raw, dates_raw) = DataAcquisition.get_end_node_microseconds_data(
                                                                        client=client,
                                                                        end_node=sensor_node,
                                                                        start_time=start_time,
                                                                        end_time=end_time
                                                                   )

        # print(f'get_acceleration_pack_parameters values_raw : {values_raw}, dates_raw : {dates_raw}')

        return values_raw, dates_raw

    @staticmethod
    def get_rms_parameters(client, mac_id, start_time, end_time, axis):
        sensor_node = DataAcquisition.get_axis_rms_nodes(client, mac_id, axis)

        (values_raw, dates_raw) = DataAcquisition.get_end_node_microseconds_data(
            client=client,
            end_node=sensor_node,
            start_time=start_time,
            end_time=end_time
        )

        # print(f'get_acceleration_pack_parameters values_raw : {values_raw}, dates_raw : {dates_raw}')

        return values_raw, dates_raw


def get_draw_data_by_opcua():
    # '25.31.102.59', "ziincheol1",'0d:66:24:8e','84'
    # servName = sensor.servName
    # servIP = sensor.servIP
    # macID = sensor.macID

    # sensor = Sensor.objects.filter(sensor_id=sensor_id)
    # server = Server.objects.filter(server_id=sensor.get().server_fk_id)

    server_ip = "25.80.89.221"
    mac_id = "6e:99:6f:4f"

    background_color, border_color = [], []

    # logging.basicConfig(level=logging.INFO)
    # logging.getLogger("opcua").setLevel(logging.WARNING)

    # serverIP = '25.17.10.130' #SKT2_polytec
    # serverIP = '25.3.15.233' #BKT_KPI

    # serverIP = sensor.servIP
    # macId = sensor.macID
    # deviceId = sensor.servName

    server_url = urlparse('opc.tcp://{:s}:4840'.format(server_ip))

    # macId='05:92:6d:a7' #(SKT2) Polytec Pump_Left_vib
    # macId='66:a0:b7:9d' #(SKT2) Polytec Pump_Left_vib
    # macId='94:f3:9e:df' #(SKT1) GPN Etching_White
    # macId = macID  # (SKT1) GPN Etching_Black
    # macId='82:8e:2c:a3' #(BKT) KPI Press_Vib_110Right
    # macId='9b:a3:eb:47' #(BKT) KPI Press_Vib_80Left

    # change settings
    limit = 1000  # limit limits the number of returned measurements
    # axis = 'Y'  # axis allows to select data from only 1 or multiple axes
    hpf = 6

    # endtime = datetime.datetime.now() - datetime.timedelta(minutes=60 * 24)
    # starttime = endtime - datetime.timedelta(minutes=60 * 24)

    # start_time_stamp_str = "2022-04-19"
    # end_time_stamp_str = "2022-04-20"
    #
    # end_time = datetime.datetime.strptime("2022-04-20", '%Y-%m-%d')
    # start_time = datetime.datetime.strptime("2022-04-19", '%Y-%m-%d')

    # end_time_stamp_str = "2022-04-20"
    # start_time_stamp_str = "2022-04-19"

    end_time = time.time() - 3600
    start_time = end_time - 3600 * 24

    end_time_stamp_str = datetime.datetime.fromtimestamp(end_time).strftime("%Y-%m-%d %H:%M:%S.%f+00:00")
    start_time_stamp_str = datetime.datetime.fromtimestamp(start_time).strftime("%Y-%m-%d %H:%M:%S.%f+00:00")

    end_date_time = datetime.datetime.strptime(end_time_stamp_str, '%Y-%m-%d %H:%M:%S.%f+00:00')
    start_date_time = datetime.datetime.strptime(start_time_stamp_str, "%Y-%m-%d %H:%M:%S.%f+00:00")

    # (values, dates) = DataAcquisition.get_sensor_data(
    #     server_url=server_url,
    #     mac_id=mac_id,
    #     browse_name="accelerationPack",
    #     start_time=start_date_time,
    #     end_time=end_date_time
    # )

    # # convert vibration data to 'g' units and plot data
    # data = [val[1:-6] for val in values]
    # sample_rates = [val[-6] for val in values]
    # format_ranges = [val[-5] for val in values]
    # axes = [val[-3] for val in values]
    # for i in range(len(format_ranges)):
    #     data[i] = [d / 512.0 * format_ranges[i] for d in data[i]]
    #     data[i] = HighPassFilter.perform_hpf_filtering(
    #         data=data[i],
    #         sample_rate=sample_rates[i],
    #         hpf=hpf
    #     )

    temp_list, temp_date_list, voltage_list, voltage_date_list = [], [], [], []
    (temperatures, t_dates) = DataAcquisition.get_sensor_data(
        server_url=server_url,
        mac_id=mac_id,
        browse_name="boardTemperature",  # 3
        start_time=start_date_time,
        end_time=end_date_time
    )

    (batteryVoltage, v_dates) = DataAcquisition.get_sensor_data(
        server_url=server_url,
        mac_id=mac_id,
        browse_name="batteryVoltage",  # 2
        start_time=start_date_time,
        end_time=end_date_time
    )

    for i in range(len(t_dates)):
        temp_list.append(temperatures[i])
        temp_date_list.append(t_dates[i])

    for i in range(len(v_dates)):
        voltage_list.append(batteryVoltage[i])
        voltage_date_list.append(v_dates[i])

    # dates = [round(datetime.datetime.strptime(date, "%Y-%m-%d %H:%M:%S").timestamp() * 1000 + 3600000 * 9) for date in
    #          dates]
    t_dates = [round(datetime.datetime.strptime(date, "%Y-%m-%d %H:%M:%S").timestamp()) for date in
               t_dates]
    v_dates = [round(datetime.datetime.strptime(date, "%Y-%m-%d %H:%M:%S").timestamp()) for date in
               v_dates]

    with OpcUaClient(server_url) as client:
        assert (client._client.uaclient._uasocket.timeout == 15)
        ad_x_dates, ad_y_dates, ad_z_dates, pe_x, pe_y, pe_z = ([] for i in range(6))
        with ThreadPoolExecutor(max_workers=6) as TPE:
            rms_x_future = TPE.submit(
                DataAcquisition.get_rms_parameters, client, mac_id, start_date_time, end_date_time, 'x')
            rms_y_future = TPE.submit(
                DataAcquisition.get_rms_parameters, client, mac_id, start_date_time, end_date_time, 'y')
            rms_z_future = TPE.submit(
                DataAcquisition.get_rms_parameters, client, mac_id, start_date_time, end_date_time, 'z')

            model_x_future = TPE.submit(
                DataAcquisition.get_anomaly_model_parameters, client, mac_id, start_date_time, end_date_time, 'x')
            model_y_future = TPE.submit(
                DataAcquisition.get_anomaly_model_parameters, client, mac_id, start_date_time, end_date_time, 'y')
            model_z_future = TPE.submit(
                DataAcquisition.get_anomaly_model_parameters, client, mac_id, start_date_time, end_date_time, 'z')

            # rms_x_datas, rms_x_dates = DataAcquisition.get_rms_parameters(
            #     client=client,
            #     mac_id=mac_id,
            #     start_time=start_date_time,
            #     end_time=end_date_time,
            #     axis='x'
            # )

            # print(f'x axis vibration rms datas : {rms_x_datas}')
            # print(f'x axis vibration rms dates : {rms_x_dates}')

            epoch_dates_x_rms_date = []
            rms_x_list = []
            kurt_x_list = []
            i = 0
            for rms_x_date in rms_x_future.result()[1]:
                try:
                    d = datetime.datetime.strptime(rms_x_date, "%Y-%m-%d %H:%M:%S.%f").timestamp()
                    epoch_dates_x_rms_date.append(d - start_time)
                    rms_x_list.append(rms_x_future.result()[0][i])

                    background_color.append('#3e95cd')
                    border_color.append('#3e95cd')

                    i += 1

                except ValueError or IndexError:
                    try:
                        d = datetime.datetime.strptime(rms_x_date, "%Y-%m-%d %H:%M:%S").timestamp()
                        epoch_dates_x_rms_date.append(d - start_time)
                        rms_x_list.append(rms_x_future.result()[0][i])

                        background_color.append('#3e95cd')
                        border_color.append('#3e95cd')

                    except ValueError or IndexError:
                        print("Error in date data format")

                        return [], [], [], background_color, border_color

            # rms_y_datas, rms_y_dates = DataAcquisition.get_rms_parameters(
            #     client=client,
            #     mac_id=mac_id,
            #     start_time=start_date_time,
            #     end_time=end_date_time,
            #     axis='y'
            # )
            # print(f'y axis vibration rms datas : {rms_y_datas}')
            # print(f'y axis vibration rms dates : {rms_y_dates}')

            epoch_dates_y_rms_date = []
            rms_y_list = []
            kurt_y_list = []
            i = 0
            for rms_y_date in rms_y_future.result()[1]:
                try:
                    d = datetime.datetime.strptime(rms_y_date, "%Y-%m-%d %H:%M:%S.%f").timestamp()
                    epoch_dates_y_rms_date.append(d - start_time)
                    rms_y_list.append(rms_y_future.result()[0][i])

                    background_color.append('#3e95cd')
                    border_color.append('#3e95cd')

                    i += 1

                except ValueError or IndexError:
                    try:
                        d = datetime.datetime.strptime(rms_y_date, "%Y-%m-%d %H:%M:%S").timestamp()
                        epoch_dates_y_rms_date.append(d - start_time)
                        rms_y_list.append(rms_y_future.result()[0][i])

                        background_color.append('#3e95cd')
                        border_color.append('#3e95cd')

                    except ValueError or IndexError:
                        print("Error in date data format")

                        return [], [], [], background_color, border_color

            # rms_z_datas, rms_z_dates = DataAcquisition.get_rms_parameters(
            #     client=client,
            #     mac_id=mac_id,
            #     start_time=start_date_time,
            #     end_time=end_date_time,
            #     axis='z'
            # )
            # print(f'z axis vibration rms datas : {rms_z_datas}')
            # print(f'z axis vibration rms dates : {rms_z_dates}')

            epoch_dates_z_rms_date = []
            rms_z_list = []
            kurt_z_list = []
            i = 0
            for rms_z_date in rms_z_future.result()[1]:
                try:
                    d = datetime.datetime.strptime(rms_z_date, "%Y-%m-%d %H:%M:%S.%f").timestamp()
                    epoch_dates_z_rms_date.append(d - start_time)
                    rms_z_list.append(rms_z_future.result()[0][i])

                    background_color.append('#3e95cd')
                    border_color.append('#3e95cd')

                    i += 1

                except ValueError or IndexError:
                    try:
                        d = datetime.datetime.strptime(rms_z_date, "%Y-%m-%d %H:%M:%S").timestamp()
                        epoch_dates_z_rms_date.append(d - start_time)
                        rms_z_list.append(rms_z_future.result()[0][i])

                        background_color.append('#3e95cd')
                        border_color.append('#3e95cd')

                    except ValueError or IndexError:
                        print("Error in date data format")

                        return [], [], [], background_color, border_color

            # acquire model data
            # model_dict_x = DataAcquisition.get_anomaly_model_parameters(
            #     client=client,
            #     mac_id=mac_id,
            #     start_time=start_date_time,
            #     end_time=end_date_time,
            #     axis='X'
            # )
            if len(list(model_x_future.result().keys())) > 1:
                print("There are more than one AI models for X")
            if len(list(model_x_future.result().keys())) > 0:
                model = list(model_x_future.result().keys())[-1]
                ad_x_dates = model_x_future.result()[model]["raw"][1]
                for i in range(len(ad_x_dates)):
                    ad_x_dates[i] = round(
                        datetime.datetime.strptime(ad_x_dates[i], '%Y-%m-%d %H:%M:%S').timestamp())
                pe_x = model_x_future.result()[model]["raw"][0]

            # model_dict_y = DataAcquisition.get_anomaly_model_parameters(
            #     client=client,
            #     mac_id=mac_id,
            #     start_time=start_date_time,
            #     end_time=end_date_time,
            #     axis='Y'
            # )
            if len(list(model_y_future.result().keys())) > 1:
                print("There are more than one AI models for Y")
            if len(list(model_y_future.result().keys())) > 0:
                model = list(model_y_future.result().keys())[-1]
                ad_y_dates = model_y_future.result()[model]["raw"][1]
                for i in range(len(ad_y_dates)):
                    ad_y_dates[i] = round(
                        datetime.datetime.strptime(ad_y_dates[i], '%Y-%m-%d %H:%M:%S').timestamp())
                pe_y = model_y_future.result()[model]["raw"][0]

            # model_dict_z = DataAcquisition.get_anomaly_model_parameters(
            #     client=client,
            #     mac_id=mac_id,
            #     start_time=start_date_time,
            #     end_time=end_date_time,
            #     axis='Z'
            # )
            if len(list(model_z_future.result().keys())) > 1:
                print("There are more than one AI models for Z")
            if len(list(model_z_future.result().keys())) > 0:
                model = list(model_z_future.result().keys())[-1]
                ad_z_dates = model_z_future.result()[model]["raw"][1]
                for i in range(len(ad_z_dates)):
                    ad_z_dates[i] = round(
                        datetime.datetime.strptime(ad_z_dates[i], '%Y-%m-%d %H:%M:%S').timestamp())
                pe_z = model_z_future.result()[model]["raw"][0]

    # rms, kurtosis

    # prediction error
    # pe_x, pe_y, pe_z

    # prediction error time
    # ad_x_dates, ad_y_dates, ad_z_dates

    # temperature, voltage
    # temp_list, temp_date_list, voltage_list, voltage_date_list

    # yield acceleration_x_datas[0]

    # return [rms_x_list, rms_y_list, rms_z_list, pe_x, ad_x_dates, pe_y, ad_y_dates, pe_z, ad_z_dates, temp_list, temp_date_list, voltage_list, voltage_date_list]

    yield rms_x_list
    yield rms_y_list
    yield rms_z_list
    yield pe_x
    yield ad_x_dates
    yield pe_y
    yield ad_y_dates
    yield pe_z
    yield ad_z_dates
    yield temp_list
    yield temp_date_list
    yield voltage_list
    yield voltage_date_list


def main():
    # '25.31.102.59', "ziincheol1",'0d:66:24:8e','84'
    # servName = sensor.servName
    # servIP = sensor.servIP
    # macID = sensor.macID

    # yield rms_x_list
    # yield rms_y_list
    # yield rms_z_list
    # yield pe_x
    # yield ad_x_dates
    # yield pe_y
    # yield ad_y_dates
    # yield pe_z
    # yield ad_z_dates
    # yield temp_list
    # yield temp_date_list
    # yield voltage_list
    # yield voltage_date_list

    # print(f'get_draw_data_by_opcua : {get_draw_data_by_opcua()}')
    for i in get_draw_data_by_opcua():
        print(f'get_draw_data_by_opcua : {i}')


if __name__ == '__main__':

    start_proc = time.time()

    main()

    end_proc = time.time() - start_proc

    print(f'opc-ua running time : {end_proc}')