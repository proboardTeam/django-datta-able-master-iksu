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
from django.http import JsonResponse
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

    # @staticmethod
    # def get_sensor_data(server_url, mac_id, browse_name, start_time, end_time):
    #     with OpcUaClient(server_url) as client:
    #         assert (client._client.uaclient._uasocket.timeout == 15)
    #
    #         sensor_node = DataAcquisition.get_sensor_node(client, mac_id, browse_name)
    #         DataAcquisition.LOGGER.info(
    #             'Browsing {:s}'.format(mac_id)
    #         )
    #         (values, dates) = DataAcquisition.get_end_node_data(
    #             client=client,
    #             end_node=sensor_node,
    #             start_time=start_time,
    #             end_time=end_time
    #         )
    #     return values, dates

    @staticmethod
    def get_sensor_data(server_url, mac_id, browse_name, start_time, end_time):
        with OpcUaClient(server_url) as client:
            assert (client._client.uaclient._uasocket.timeout == 15)

            sensor_node = DataAcquisition.get_sensor_node(client, mac_id, browse_name)
            DataAcquisition.LOGGER.info(
                'Browsing {:s}'.format(mac_id)
            )
            (values, dates) = DataAcquisition.get_end_node_microseconds_data(
                client=client,
                end_node=sensor_node,
                start_time=start_time,
                end_time=end_time
            )
        return values, dates

    @staticmethod
    def get_sensor_axis_data(server_url, mac_id, browse_name, start_time, end_time, axis):
        with OpcUaClient(server_url) as client:
            assert (client._client.uaclient._uasocket.timeout == 15)

            sensor_node = DataAcquisition.get_sensor_axis_node(client, mac_id, browse_name, axis)

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
        b_path = [
            ua.QualifiedName(name=mac_id, namespaceidx=ns_idx),
            ua.QualifiedName(name=browse_name, namespaceidx=ns_idx)
        ]
        sensor_node = client.objectsNode.get_child(b_path)
        return sensor_node

    @staticmethod
    def get_sensor_axis_node(client, mac_id, browse_name, axis):
        ns_idx = client.get_namespace_index(
            'http://www.iqunet.com'
        )  # iQunet namespace index
        b_path = [
            ua.QualifiedName(name=mac_id, namespaceidx=ns_idx),
            ua.QualifiedName(name=browse_name, namespaceidx=ns_idx),
            ua.QualifiedName(name=axis, namespaceidx=ns_idx)
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
            sensor_node = DataAcquisition.get_sensor_sub_node(client, mac_id, "vibration", axis, "accel",
                                                              "xAccelTimeOrdinate")
        if axis == 'y':
            sensor_node = DataAcquisition.get_sensor_sub_node(client, mac_id, "vibration", axis, "accel",
                                                              "yAccelTimeOrdinate")
        if axis == 'z':
            sensor_node = DataAcquisition.get_sensor_sub_node(client, mac_id, "vibration", axis, "accel",
                                                              "zAccelTimeOrdinate")

        DataAcquisition.LOGGER.info(
            'Browsing for {:s} axis vibration of {:s}'.format(axis, mac_id)
        )

        return sensor_node

    # rms 축별로 시간대까지 측정
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
    def get_anomaly_model_parameters(server_url, mac_id, start_time, end_time, axis):
        with OpcUaClient(server_url) as client:
            assert (client._client.uaclient._uasocket.timeout == 15)

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
    def get_rms_parameters(server_url, mac_id, start_time, end_time, axis):
        with OpcUaClient(server_url) as client:
            assert (client._client.uaclient._uasocket.timeout == 15)

            sensor_node = DataAcquisition.get_axis_rms_nodes(client, mac_id, axis)

            (values_raw, dates_raw) = DataAcquisition.get_end_node_microseconds_data(
                client=client,
                end_node=sensor_node,
                start_time=start_time,
                end_time=end_time
            )

        # print(f'get_acceleration_pack_parameters values_raw : {values_raw}, dates_raw : {dates_raw}')

        return values_raw, dates_raw


class OPCUAgraph(View):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        # change settings
        self.limit = 1000  # limit limits the number of returned measurements

        # axis = 'Y'  # axis allows to select data from only 1 or multiple axes
        self.hpf = 6

        self.end_time = time.time() - 3600
        self.start_time = self.end_time - 3600 * 24

        self.end_time_stamp_str = datetime.datetime.fromtimestamp(self.end_time).strftime("%Y-%m-%d %H:%M:%S.%f+00:00")
        self.start_time_stamp_str = datetime.datetime.fromtimestamp(self.start_time).strftime(
            "%Y-%m-%d %H:%M:%S.%f+00:00")

        self.end_date_time = datetime.datetime.strptime(self.end_time_stamp_str, '%Y-%m-%d %H:%M:%S.%f+00:00')
        self.start_date_time = datetime.datetime.strptime(self.start_time_stamp_str, "%Y-%m-%d %H:%M:%S.%f+00:00")

        self.kor_start_time_stamp_str = datetime.datetime.fromtimestamp(self.start_time).strftime(
            "%Y년 %m월 %d일 %H시 %M분 %S초")

    def get_draw_data_by_opcua(self, sensor_id):

        sensor = Sensor.objects.filter(sensor_id=sensor_id)
        server = Server.objects.filter(server_id=sensor.get().server_fk_id)

        server_ip = server.get().server_name
        mac_id = sensor.get().sensor_mac

        print(f'server_ip : {server_ip}')
        print(f'mac_id : {mac_id}')

        # logging.basicConfig(level=logging.INFO)
        # logging.getLogger("opcua").setLevel(logging.WARNING)

        server_url = urlparse('opc.tcp://{:s}:4840'.format(server_ip))

        background_color, border_color = [], []
        background_x_color, border_x_color, background_y_color, border_y_color, background_z_color, border_z_color = (
            [] for i in range(6))
        temp_list, voltage_list = [], []
        pe_x, pe_y, pe_z = [], [], []
        rms_xyz_list, kurt_xyz_list, ad_x_dates, ad_y_dates, ad_z_dates = ([] for i in range(5))

        with ThreadPoolExecutor(max_workers=12) as TPE:
            temp_future = TPE.submit(
                DataAcquisition.get_sensor_data, server_url, mac_id, "boardTemperature", self.start_date_time,
                self.end_date_time)
            voltage_future = TPE.submit(
                DataAcquisition.get_sensor_data, server_url, mac_id, "batteryVoltage", self.start_date_time,
                self.end_date_time)

            rms_xyz_future = TPE.submit(DataAcquisition.get_sensor_data, server_url, mac_id,
                                        "accelerationPack", self.start_date_time, self.end_date_time)

            rms_x_future = TPE.submit(
                DataAcquisition.get_rms_parameters, server_url, mac_id, self.start_date_time, self.end_date_time, 'x')
            rms_y_future = TPE.submit(
                DataAcquisition.get_rms_parameters, server_url, mac_id, self.start_date_time, self.end_date_time, 'y')
            rms_z_future = TPE.submit(
                DataAcquisition.get_rms_parameters, server_url, mac_id, self.start_date_time, self.end_date_time, 'z')

            model_x_future = TPE.submit(
                DataAcquisition.get_anomaly_model_parameters, server_url, mac_id, self.start_date_time,
                self.end_date_time, 'x')
            model_y_future = TPE.submit(
                DataAcquisition.get_anomaly_model_parameters, server_url, mac_id, self.start_date_time,
                self.end_date_time, 'y')
            model_z_future = TPE.submit(
                DataAcquisition.get_anomaly_model_parameters, server_url, mac_id, self.start_date_time,
                self.end_date_time, 'z')
            time.sleep(1)

            try:
                xyz_dates = [
                    (datetime.datetime.strptime(r_xyz_date, "%Y-%m-%d %H:%M:%S.%f").timestamp() - self.start_time)
                    for r_xyz_date in rms_xyz_future.result()[1]]
                temperature_dates = [
                    (datetime.datetime.strptime(t_date, "%Y-%m-%d %H:%M:%S.%f").timestamp() - self.start_time)
                    for t_date in temp_future.result()[1]]
                voltage_dates = [
                    (datetime.datetime.strptime(v_date, "%Y-%m-%d %H:%M:%S.%f").timestamp() - self.start_time)
                    for v_date in voltage_future.result()[1]]

            except ValueError:
                xyz_dates = [
                    (datetime.datetime.strptime(r_xyz_date, "%Y-%m-%d %H:%M:%S").timestamp() - self.start_time)
                    for r_xyz_date in rms_xyz_future.result()[1]]
                temperature_dates = [
                    (datetime.datetime.strptime(t_date, "%Y-%m-%d %H:%M:%S").timestamp() - self.start_time)
                    for t_date in temp_future.result()[1]]
                voltage_dates = [
                    (datetime.datetime.strptime(v_date, "%Y-%m-%d %H:%M:%S").timestamp() - self.start_time)
                    for v_date in voltage_future.result()[1]]

            for i in range(len(temperature_dates)):
                temp_list.append(temp_future.result()[0][i])

            for i in range(len(voltage_dates)):
                voltage_list.append(voltage_future.result()[0][i])

            # convert vibration data to 'g' units and plot data
            data = [val[1:-6] for val in rms_xyz_future.result()[0]]
            sample_rates = [val[-6] for val in rms_xyz_future.result()[0]]
            format_ranges = [val[-5] for val in rms_xyz_future.result()[0]]
            for i in range(len(format_ranges)):
                data[i] = [d / 512.0 * format_ranges[i] for d in data[i]]
                data[i] = HighPassFilter.perform_hpf_filtering(
                    data=data[i],
                    sample_rate=sample_rates[i],
                    hpf=self.hpf
                )

            for j in range(len(xyz_dates)):
                if not data or not xyz_dates:
                    break

                rms_xyz_list.append(HighPassFilter.rms(data[j]))
                kurt_xyz_list.append(stats.kurtosis(data[j]))

                background_color.append('#3e95cd')
                border_color.append('#3e95cd')

            # acquire model data
            epoch_dates_x_rms_date = []
            rms_x_list = []
            kurt_x_list = []
            i = 0
            for rms_x_date in rms_x_future.result()[1]:
                try:
                    d = datetime.datetime.strptime(rms_x_date, "%Y-%m-%d %H:%M:%S.%f").timestamp()
                    epoch_dates_x_rms_date.append(d - self.start_time)
                    rms_x_list.append(rms_x_future.result()[0][i])

                    background_x_color.append('#3e95cd')
                    border_x_color.append('#3e95cd')

                    i += 1

                except ValueError or IndexError:
                    try:
                        d = datetime.datetime.strptime(rms_x_date, "%Y-%m-%d %H:%M:%S").timestamp()
                        epoch_dates_x_rms_date.append(d - self.start_time)
                        rms_x_list.append(rms_x_future.result()[0][i])

                        background_x_color.append('#3e95cd')
                        border_x_color.append('#3e95cd')

                        i += 1

                    except ValueError or IndexError:
                        print("Error in date data format")

                        return [], [], [], background_x_color, border_x_color

            epoch_dates_y_rms_date = []
            rms_y_list = []
            kurt_y_list = []
            i = 0
            for rms_y_date in rms_y_future.result()[1]:
                try:
                    d = datetime.datetime.strptime(rms_y_date, "%Y-%m-%d %H:%M:%S.%f").timestamp()
                    epoch_dates_y_rms_date.append(d - self.start_time)
                    rms_y_list.append(rms_y_future.result()[0][i])

                    background_y_color.append('#3e95cd')
                    border_y_color.append('#3e95cd')

                    i += 1

                except ValueError or IndexError:
                    try:
                        d = datetime.datetime.strptime(rms_y_date, "%Y-%m-%d %H:%M:%S").timestamp()
                        epoch_dates_y_rms_date.append(d - self.start_time)
                        rms_y_list.append(rms_y_future.result()[0][i])

                        background_y_color.append('#3e95cd')
                        border_y_color.append('#3e95cd')

                        i += 1

                    except ValueError or IndexError:
                        print("Error in date data format")

                        return [], [], [], background_color, border_color

            epoch_dates_z_rms_date = []
            rms_z_list = []
            kurt_z_list = []
            i = 0
            for rms_z_date in rms_z_future.result()[1]:
                try:
                    d = datetime.datetime.strptime(rms_z_date, "%Y-%m-%d %H:%M:%S.%f").timestamp()
                    epoch_dates_z_rms_date.append(d - self.start_time)
                    rms_z_list.append(rms_z_future.result()[0][i])

                    background_z_color.append('#3e95cd')
                    border_z_color.append('#3e95cd')

                    i += 1

                except ValueError or IndexError:
                    try:
                        d = datetime.datetime.strptime(rms_z_date, "%Y-%m-%d %H:%M:%S").timestamp()
                        epoch_dates_z_rms_date.append(d - self.start_time)
                        rms_z_list.append(rms_z_future.result()[0][i])

                        background_z_color.append('#3e95cd')
                        border_z_color.append('#3e95cd')

                        i += 1

                    except ValueError or IndexError:
                        print("Error in date data format")

                        return [], [], [], background_z_color, border_z_color

            if len(list(model_x_future.result().keys())) > 1:
                print("There are more than one AI models for X")
            if len(list(model_x_future.result().keys())) > 0:
                model = list(model_x_future.result().keys())[-1]
                ad_x_dates = model_x_future.result()[model]["raw"][1]
                for i in range(len(ad_x_dates)):
                    ad_x_dates[i] = round(
                        datetime.datetime.strptime(ad_x_dates[i], '%Y-%m-%d %H:%M:%S').timestamp())
                pe_x = model_x_future.result()[model]["raw"][0]

            if len(list(model_y_future.result().keys())) > 1:
                print("There are more than one AI models for Y")
            if len(list(model_y_future.result().keys())) > 0:
                model = list(model_y_future.result().keys())[-1]
                ad_y_dates = model_y_future.result()[model]["raw"][1]
                for i in range(len(ad_y_dates)):
                    ad_y_dates[i] = round(
                        datetime.datetime.strptime(ad_y_dates[i], '%Y-%m-%d %H:%M:%S').timestamp())
                pe_y = model_y_future.result()[model]["raw"][0]

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

            # yield rms_xyz_list
            # yield kurt_xyz_list
            # yield xyz_dates
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
            # yield temperature_dates
            # yield voltage_list
            # yield voltage_dates

            try:
                return {
                    'sensor_id': sensor_id,
                    'sensor_tag': sensor.get().sensor_tag,
                    'Measurement_Start_Time': self.kor_start_time_stamp_str,
                    'BarPlot_XYZ_RMS_Values': rms_xyz_list,
                    'BarPlot_XYZ_Time': xyz_dates,
                    'BarPlot_XYZ_Kurtosis_Values': kurt_xyz_list,
                    'BarPlot_X_RMS_Values': rms_x_list,
                    'BarPlot_Y_RMS_Values': rms_y_list,
                    'BarPlot_Z_RMS_Values': rms_z_list,
                    'BarPlot_X_Kurtosis_Values': [],
                    'BarPlot_Y_Kurtosis_Values': [],
                    'BarPlot_Z_Kurtosis_Values': [],
                    'BarPlot_Board_Temperature': temp_list,
                    'BarPlot_Board_Time': temperature_dates,
                    'BarPlot_Board_Temperature_BackColor': background_color,
                    'BarPlot_Board_Temperature_BorderColor': border_color,
                    'BarPlot_X_Time': epoch_dates_x_rms_date,
                    'BarPlot_Y_Time': epoch_dates_y_rms_date,
                    'BarPlot_Z_Time': epoch_dates_z_rms_date,
                    'XBackgroundColor': background_x_color,
                    'XBorderColor': border_x_color,
                    'YBackgroundColor': background_y_color,
                    'YBorderColor': border_y_color,
                    'ZBackgroundColor': background_z_color,
                    'ZBorderColor': border_z_color,
                    'XYZBackgroundColor': background_color,
                    'XYZBorderColor': border_color,
                }

            except IndexError:
                return {
                    'sensor_id': sensor_id,
                    'sensor_tag': sensor.get().sensor_tag,
                    'Measurement_Start_Time': self.kor_start_time_stamp_str,
                    'BarPlot_X_RMS_Values': [],
                    'BarPlot_Y_RMS_Values': [],
                    'BarPlot_Z_RMS_Values': [],
                    'BarPlot_XYZ_RMS_Values': [],
                    'BarPlot_X_Kurtosis_Values': [],
                    'BarPlot_Y_Kurtosis_Values': [],
                    'BarPlot_Z_Kurtosis_Values': [],
                    'BarPlot_XYZ_Kurtosis_Values': [],
                    'BarPlot_Board_Temperature': temp_list,
                    'BarPlot_Board_Time': temperature_dates,
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
        sensor_ids = [int(sensor_id) for sensor_id in sensor_ids]

        sending = {}
        if sensor_ids is not None:
            i = 0

            # ProcessPoolExecutor -> cannot pickle '_io.bufferedreader' object python
            # 하마치 꺼져 있으면 아래 에러 requests.exceptions.ConnectTimeout: HTTPConnectionPool(host='25.80.89.221',
            # port=8000): Max retries exceeded with url: /graphql

            with ThreadPoolExecutor(max_workers=len(sensor_ids)) as TPE:
                future_to_array = [TPE.submit(self.get_draw_data_by_opcua, sensor_id) for sensor_id in sensor_ids]
                for future in future_to_array:
                    sending.update({sensor_ids[i]: future.result()})
                    print('%s is completed \n' % sending)
                    i += 1

            context = {
                'sending': sending,
            }

            end_proc = time.time() - start_proc
            print(f"opc-ua running time : {end_proc}")

        else:
            context = {
                'sending': {},
            }
            # schedule.every(60).seconds.do(result_json)

            # while request:
            #     schedule.run_pending()
            #     time.sleep(1)

        return JsonResponse({'context': context}, status=201)

# def opcua_process(request, sensor_id):
#     # '25.31.102.59', "ziincheol1",'0d:66:24:8e','84'
#     # servName = sensor.servName
#     # servIP = sensor.servIP
#     # macID = sensor.macID
#     start_proc = time.time()
#
#     # try:
#     #     data2 = [{"serviceId": "76", "deviceId": "reshenie", "timestamp": d,
#     #               "contents": {"XRms": x, "YRms": y, "ZRms": z, "gKurtX": kx, "gKurtY": ky, "gKurtZ": kz,
#     #                            "XaiPredError": adX, "YaiPredError": adY, "ZaiPredError": adZ, "BoardTemperature": t,
#     #                            "BatteryState": v}}
#     #              for (d, x, y, z, kx, ky, kz, adX, adY, adZ, t, v) in list(
#     #             zip(time_list, Xrms_list, Yrms_list, Zrms_list, Xkurt_list, Ykurt_list, Zkurt_list, X_AD, Y_AD,
#     #                 Z_AD,
#     #                 Temp_list, Voltage_list))]
#     #
#     #     json_results = []
#     #     x_rms, y_rms, z_rms, x_kurt, y_kurt, z_kurt, x_pred_error, y_pred_error, z_pred_error, board_temperature, battery_state = [], [], [], [], [], [], [], [], [], [], []
#     #
#     #     for i in range(len(data2)):
#     #         data = [data2[i]['contents']]
#     #         json_results.append(data)
#     #
#     #         # data_list.append(data)
#     #
#     #     print(f'result length : {len(json_results)}')
#     #     print("Done dumping data")
#     #
#     #     j = 0
#     #     for i in range(len(json_results)):
#     #         x_rms.append(json_results[i][j]['XRms'])
#     #         y_rms.append(json_results[i][j]['YRms'])
#     #         z_rms.append(json_results[i][j]['ZRms'])
#     #         x_kurt.append(json_results[i][j]['gKurtX'])
#     #         y_kurt.append(json_results[i][j]['gKurtY'])
#     #         z_kurt.append(json_results[i][j]['gKurtZ'])
#     #         x_pred_error.append(json_results[i][j]['XaiPredError'])
#     #         y_pred_error.append(json_results[i][j]['YaiPredError'])
#     #         z_pred_error.append(json_results[i][j]['ZaiPredError'])
#     #         board_temperature.append(json_results[i][j]['BoardTemperature'])
#     #         battery_state.append(json_results[i][j]['BatteryState'])
#
#     # for i in get_draw_data_by_opcua():
#     #     print(f'get_draw_data_by_opcua : {i}')
#
#     end_proc = time.time() - start_proc
#     print(f"opc-ua process time : {end_proc}")
#
#     return {
#         # 'sensor_id': sensor_id,
#         # 'sensor_tag': sensor_tag,
#         # 'Measurement_Start_Time': datetime.datetime.fromtimestamp(start_time).strftime(
#         #                                                                     "%Y년 %m월 %d일 %H시 %M분 %S초"),
#         #
#         # 'BarPlot_XYZ_RMS_Values': bar_plot_xyz_rms_values,
#         # 'BarPlot_XYZ_Kurtosis_Values': bar_plot_xyz_kurtosis_values,
#         # 'BarPlot_XYZ_Time': bar_plot_xyz_time,
#         # 'BarPlot_X_RMS_Values': x_future.result()[0],
#         # 'BarPlot_Y_RMS_Values': y_future.result()[0],
#         # 'BarPlot_Z_RMS_Values': z_future.result()[0],
#         # 'BarPlot_X_Kurtosis_Values': x_future.result()[1],
#         # 'BarPlot_Y_Kurtosis_Values': y_future.result()[1],
#         # 'BarPlot_Z_Kurtosis_Values': z_future.result()[1],
#         # 'BarPlot_Board_Temperature': t_future.result()[1],
#         # 'BarPlot_Board_Time': t_future.result()[0],
#         # 'BarPlot_Board_Temperature_BackColor': xyz_background_color[0],
#         # 'BarPlot_Board_Temperature_BorderColor': xyz_border_color[0],
#         # 'BarPlot_X_Time': x_future.result()[2],
#         # 'BarPlot_Y_Time': y_future.result()[2],
#         # 'BarPlot_Z_Time': z_future.result()[2],
#         # 'XBackgroundColor': x_future.result()[3],
#         # 'XBorderColor': x_future.result()[4],
#         # 'YBackgroundColor': y_future.result()[3],
#         # 'YBorderColor': y_future.result()[4],
#         # 'ZBackgroundColor': z_future.result()[3],
#         # 'ZBorderColor': z_future.result()[4],
#         # 'XYZBackgroundColor': xyz_background_color,
#         # 'XYZBorderColor': xyz_border_color,
#     }
