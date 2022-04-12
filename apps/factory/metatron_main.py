# -*- coding: utf-8 -*-
"""
Created on Thu Nov  4 15:39:07 2021

@author: Sumin Lee
"""

import sys
import datetime
import numpy as np
from azure.servicebus import ServiceBusClient, ServiceBusMessage
import json
import schedule

from ctypes import byref, create_string_buffer, c_bool, c_double

import time
from datetime import datetime
import os

from keras.models import load_model
from TLPM import TLPM

sys.path.append(r"H:/내 드라이브/이수민/21C laser AI POC/21C data/code")

# get sensor's serial number(센서 시리얼 넘버 확인)
os.add_dll_directory(r"H:/내 드라이브/이수민/21C laser AI POC/21C data/code")


def send_a_list_of_messages(sender, tr_data):
    # create a list of messages
    # messages = [ServiceBusMessage(str(json_data)) for _ in range(1)]
    messages = []
    for i in range(len(tr_data)):
        a = ServiceBusMessage(str(tr_data[i]))
        messages.append(a)
    print(len(tr_data), messages)
    # print(messages, type(messages))
    current_time = datetime.now()

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
        except Exception as e:
            print("Error in sending messages")
            print(e)


def send_alarm(sensorname, rawdates):
    import requests
    import json

    # 1.
    with open(r"C:\Users\user\Google Drive(reshenie.work@gmail.com)\Dashboard\dashboard\kakao_code.json", "r") as fp:
        tokens = json.load(fp)

    # #2.
    # with open("kakao_code.json","r") as fp:
    #     tokens = json.load(fp)

    url = "https://kapi.kakao.com/v2/api/talk/memo/default/send"

    # kapi.kakao.com/v2/api/talk/memo/default/send 

    headers = {
        "Authorization": "Bearer " + tokens["access_token"]
    }

    data = {
        "template_object": json.dumps({
            "object_type": "text",
            "text": """\
                RESHENIE Alarm
                - 이상 징후 감지 센서: %s
                - 이상 징후 발생 값: %s

                - Alarm Level 기준값 대비 10%% 이상 발생.
                - 설비를 점검해 주시기 바랍니다.""" % (str(sensorname), str(rawdates)),
            "link": {
                "web_url": "www.naver.com"
            }
        })
    }

    response = requests.post(url, headers=headers, data=data)
    # response.status_code
    print(response.status_code)


def main(TLPM, wavelength, model, duration):
    TLPM.setWavelength(c_double(wavelength))

    power_measurements = []
    current_measurements = []
    time_stamps = []

    start_time = round(time.time() * 1000)
    experiment_time = round(time.time() * 1000)

    power = c_double()
    current = c_double()

    # collect samples 
    while ((experiment_time - start_time) / 60000.0) <= duration:
        experiment_time = round(time.time() * 1000)
        TLPM.measPower(byref(power))
        TLPM.measCurrent(byref(current))
        time_stamps.append(experiment_time)
        power_measurements.append(power.value)
        current_measurements.append(current.value)

    # generate calculated parameters
    irr_values = np.multiply(power_measurements, 127.32)
    pow_dBm = 10 * np.log10(power_measurements)
    sat_values = np.multiply(power_measurements, 14925.3731343)

    for i in range(len(sat_values)):
        if sat_values[i] > 100:
            sat_values[i] = 100

    # load trained model and calculate predictive error

    power_pred = model.predict(power_measurements)
    predError_list = np.mean(np.abs(power_pred - power_measurements), axis=1)[0]

    # zero_list = np.zeros((len(power_measurements),),dtype=np.float)
    # print(len(power_measurements))
    # try:
    # data2 = [{"serviceId":"76", "deviceId":"reshenie1", "timestamp": t, "contents":{"PredError": pe,"Power(W)": p,"Current(A)": c, "Power(dBm)":d, "Irradiance(W/cm^2)":irr, "Saturation(%)":s}} \
    # data2 = [{"serviceId": "85", "deviceId": "c21-1", "timestamp": t,
    #           "contents": {"PredError": pe, "Power_W": pw, "Current_A": c, "Irradiance_Wcm": irr, "Power_dBm": pw_dBm,
    #                        "Saturation_Per": s}}
    data2 = [{"serviceId": "85", "deviceId": "c21-1", "timestamp": t,
              "contents": {"PredError": pe, "Power_W": pw, "Current_A": c, "Irradiance_Wcm": irr, "Power_dBm": pw_dBm,
                           "Saturation_Per": s}}
             for (t, pe, pw, c, irr, pw_dBm, s) in list(
            zip(time_stamps, predError_list, power_measurements, current_measurements, irr_values, pow_dBm,
                sat_values))]
    # for (t,pe, p, c,d,irr,s) in list(zip(time_stamps,predError_list, power_measurements, current_measurements, irr_values, pow_dBm, sat_values))]
    # except:
    #     print("Error in creating dictionary objects")
    # print(data2)
    data_list = []
    for i in range(len(data2)):
        data = json.dumps(data2[i])
        data_list.append(data)

    # CONNECTION_STR = "Endpoint=sb://reshenietest2.servicebus.windows.net/;SharedAccessKeyName=RootManageSharedAccessKey;SharedAccessKey=aNo/hnefeXUKS6ei/VeOcFewKPYZ49MwSLMpH59Yk6M="
    # CONNECTION_STR = "Endpoint=sb://sktiotcomservicebus01prd.servicebus.windows.net/;SharedAccessKeyName=reshenie;SharedAccessKey=LNbyO1dtSkYN2j6t1kwfh8Idn0IrGTNu6c1iczUPg5Q=;EntityPath=reshenie-telemetry-queue" # "<NAMESPACE CONNECTION STRING>"
    # QUEUE_NAME = "reshenietest2"
    CONNECTION_STR = "Endpoint=sb://sktiotcomservicebus01prd.servicebus.windows.net/;SharedAccessKeyName=reshenie;SharedAccessKey=U/MZ9W8ih7R7KE14Zrf3/5ef8k3valVnvsRNRK4+MuA=;EntityPath=reshenie-telemetry-queue"
    QUEUE_NAME = "reshenie-telemetry-queue"  # "<QUEUE NAME>"

    # Sending message to skt 
    servicebus_client = ServiceBusClient.from_connection_string(conn_str=CONNECTION_STR, logging_enable=True)

    with servicebus_client:
        # get a Queue Sender object to send messages to the queue
        sender = servicebus_client.get_queue_sender(queue_name=QUEUE_NAME)
        with sender:
            send_a_list_of_messages(sender, tr_data=data_list)
    print("Done sending data")

    # with open('G:/내 드라이브/이수민/21C laser AI POC/Dashboard/json_data.json', 'w') as json_file:
    #     json.dump(data2, json_file, indent=4)
    #     # data_list.append(data2)
    #     print("Done dumping data")


if __name__ == '__main__':
    # max_power = 0.000067
    wavelength = 600
    duration = 1

    tlPM = TLPM()
    resourceName = create_string_buffer(b'USB0::0x1313::0x807B::210629100::INSTR')
    tlPM.open(resourceName, c_bool(True), c_bool(True))

    model = load_model('allNormCond')

    # main(TLPM=tlPM, wavelength=wavelength, model=model, duration = duration)
    # schedule.every(duration*0.8).minutes.do(main, TLPM=tlPM, wavelength=wavelength, model=model, duration = duration)

    errors_occurred = []
    while 1:
        try:
            main(TLPM=tlPM, wavelength=wavelength, model=model, duration=duration)
        # schedule.run_pending()
        # time.sleep(1)

        except KeyboardInterrupt:
            print("Photodiode Recording Terminated")
            try:
                tlPM.close()
            except:
                pass
            schedule.clear()
            print(errors_occurred)
            break
        except Exception as e:
            errors_occurred.append((time.ctime(), e))
