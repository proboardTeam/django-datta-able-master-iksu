# Using GQL to retrieve and plot vibration data of a specific time period.

# requires iQunet version > 1.2.2
# install gql from github:
# (pip install -e git+git://github.com/graphql-python/gql.git#egg=gql)

import logging
from urllib.parse import urlparse
import time
import matplotlib.pyplot as plt

from gql import Client, gql
from gql.transport.requests import RequestsHTTPTransport
import requests

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
                                                headers={'x-csrftoken':  csrf}
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
                ... on GrapheneVibrationCombo {vibrationTimestampHistory(start:"''' + str(starttime) + '''", end:"''' + str(endtime) + '''", limit:''' + str(limit) + ''', axis:"''' + axis + '''")}
            }}}
            '''
            result = client.execute_query(querytext)
            times = \
                result['deviceManager']['device']['vibrationTimestampHistory']
            dates, values, franges = ([], [], [])
            for t in times:
                result = DataAcquisition.get_sensor_measurement(
                        client,
                        macId,
                        t
                )
                dates.append(t)
                deviceData = result['deviceManager']['device']
                values.append(
                        deviceData['vibrationArray']['rawSamples']
                )
                franges.append(
                        deviceData['vibrationArray']['formatRange']
                )
            return (values, dates, franges)


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

if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    logging.getLogger("graphql").setLevel(logging.WARNING)

    # replace xx.xx.xx.xx with the IP address of your server
    serverIP = "25.52.52.52"
    serverUrl = urlparse('http://{:s}:8000/graphql'.format(serverIP))

    # replace xx:xx:xx:xx with your sensors macId
    macId = 'a3:40:ba:60'
    starttime = "2022-04-13"
    endtime = "2022-04-14"

    limit = 1000  # limit limits the number of returned measurements
    axis = 'XYZ'  # axis allows to select data from only 1 or multiple axes

    # acquire history data
    (values, dates, franges) = DataAcquisition.get_sensor_data(
            serverUrl=serverUrl,
            macId=macId,
            starttime=starttime,
            endtime=endtime,
            limit=limit,
            axis=axis
    )

    # convert vibration data to 'g' units and plot data
    for i in range(len(franges)):
        values[i] = [d/512.0*franges[i] for d in values[i]]
        plt.figure()
        plt.plot(values[i])
        plt.title(str(dates[i]))