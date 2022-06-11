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
from itertools import zip_longest, chain
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

from ctypes import cdll,c_long, c_ulong, c_uint32,byref,create_string_buffer,c_bool,c_char_p,c_int,c_int16,c_double, sizeof, c_voidp

import time
from datetime import datetime
import os
from pandas import DataFrame
import pandas as pd
from matplotlib import pyplot as plt
from matplotlib import dates as mdates
from matplotlib import ticker
from tensorflow import keras
import kwe
import platform
import subprocess
from imutils.video import VideoStream
import argparse
import imutils
import cv2
import queue
from threading import Thread
import shutil 

sys.path.append(r"G:/내 드라이브/이수민/21C laser AI POC/21C data/code")
os.add_dll_directory(r"G:/내 드라이브/이수민/21C laser AI POC/21C data/code")
from TLPM import TLPM

sys.path.append(r"G:/내 드라이브/이수민/21C laser AI POC/21C data/Dashboard/Camera")
from keyclipwriter import KeyClipWriter
# get sensor's serial number(센서 시리얼 넘버 확인)

def send_a_list_of_messages(sender, tr_data):
    # create a list of messages
    # messages = [ServiceBusMessage(str(json_data)) for _ in range(1)]
    messages=[]
    for i in range(len(tr_data)):
        a= ServiceBusMessage(str(tr_data[i]))
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
            
# CODE FOR INSTANCE CLIP RECORDING
def notEnoughStorage():
        if (shutil.disk_usage('/').free / (1024.0 ** 3))<10:
            return False
        else:
            return True

def delete_oldest_file(path):
    list_of_files = os.listdir(path)
    oldest_file = min(list_of_files, key=os.path.getctime)
    os.remove(os.path.abspath(oldest_file))
    return list_of_files.remove(oldest_file)

def clip_saver():
    global glob_trig
    # construct the argument parse and parse the arguments
    ap = argparse.ArgumentParser()
    # ap.add_argument("-o", "--output", required=True,
    #     help="path to output directory")
    ap.add_argument("-p", "--picamera", type=int, default=-1,
        help="whether or not the Raspberry Pi camera should be used")
    ap.add_argument("-f", "--fps", type=int, default=80,
        help="FPS of output video")
    ap.add_argument("-c", "--codec", type=str, default="MJPG",
        help="codec of output video")
    ap.add_argument("-b", "--buffer-size", type=int, default=80,
        help="buffer size of video clip writer")
    args = vars(ap.parse_args())

    # initialize the video stream and allow the camera sensor to
    # warmup
    print("[INFO] warming up camera...")
    vs = VideoStream(usePiCamera=args["picamera"] > 0).start()
    time.sleep(2.0)
    trigger_time = 0
    while True:
        # initialize key clip writer and the consecutive number of
        # frames that have *not* contained any action
        kcw = KeyClipWriter(bufSize=args["fps"]*5)
        consecFrames = 0
    
        # keep looping
        while True:
            # grab the current frame, resize it, and initialize a
            # boolean used to indicate if the consecutive frames
            # counter should be updated
            frame = vs.read()
            frame = imutils.resize(frame, width=600)

            if glob_trig==0:
                trigger_time = time.time()
            else:
                trigger_time = glob_trig
            
            if time.time()-trigger_time > 600:
                consecFrames = 0
                # if we are not already recording, start recording
                if not kcw.recording:
                    timestamp = datetime.datetime.now()
                    p = "{}.avi".format(timestamp.strftime("%Y-%m-%d-%H_%M_%S"))
                    kcw.start(p, cv2.VideoWriter_fourcc(*args["codec"]),
                        args["fps"])
            # otherwise, increment the number of consecutive frames that contain no action
            else:
                consecFrames += 1
            # update the key frame clip buffer
            kcw.update(frame)
            # if we are recording and reached a threshold on consecutive
            # number of frames with no action, stop recording the clip
            if kcw.recording and consecFrames == args["buffer_size"]:
                kcw.finish()
            # show the frame
            cv2.imshow("Frame", frame)
            key = cv2.waitKey(1) & 0xFF
            # if the `q` key was pressed, break from the loop
            if key == ord("q"):
                print("stopping camera")
                break

        # if we are in the middle of recording a clip, wrap it up
        if kcw.recording:
            #if disk full remove oldest file in camera recordings folder
            if notEnoughStorage()==True:
                delete_oldest_file(path="")
            kcw.finish()
        # do a bit of cleanup
        cv2.destroyAllWindows()
        vs.stop()
        
# CODE FOR COLLECTING DATA FROM SENSOR
def collect_data(TLPM, wavelength, model, duration):
    TLPM.setWavelength(c_double(wavelength))
    
    power_measurements = []
    current_measurements = []
    time_stamps = []
    
    start_time = round(time.time()*1000)
    experiment_time = round(time.time()*1000)
    
    power = c_double()
    current = c_double()
    
    # collect samples 
    while ((experiment_time-start_time)/ 60000.0)<=duration:
        experiment_time = round(time.time()*1000)
        TLPM.measPower(byref(power))
        TLPM.measCurrent(byref(current))
        time_stamps.append(experiment_time)
        power_measurements.append(power.value)
        current_measurements.append(current.value)
        

    # generate calculated parameters
    irr_values = np.multiply(power_measurements, 127.32)
    pow_dBm = 10*np.log10(power_measurements)
    sat_values = np.multiply(power_measurements, 14925.3731343)

    for i in range(len(sat_values)):
        if sat_values[i] > 100:
            sat_values[i]=100
            
    
    #load trained model and calculate predictive error
    power_pred = model.predict(power_measurements)
    predError_list = np.mean(np.abs(power_pred-power_measurements),axis = 1)[0]
    
    predError_list = np.where(~np.isfinite(current_measurements), None, current_measurements)
    power_measurements = np.where(~np.isfinite(power_measurements), None, current_measurements)
    current_measurements = np.where(~np.isfinite(current_measurements), None, current_measurements)
    irr_values = np.where(~np.isfinite(irr_values) , None, irr_values)
    pow_dBm = np.where(~np.isfinite(pow_dBm) , None, pow_dBm)
    sat_values = np.where(~np.isfinite(sat_values) , None, sat_values)
    # zero_list = np.zeros((len(power_measurements),),dtype=np.float)
    # print(len(power_measurements))
    # try:
        # data2 = [{"serviceId":"76", "deviceId":"reshenie1", "timestamp": t, "contents":{"PredError": pe,"Power(W)": p,"Current(A)": c, "Power(dBm)":d, "Irradiance(W/cm^2)":irr, "Saturation(%)":s}} \
    data2 = [{"serviceId":"85", "deviceId":"c21-1", "timestamp": t, "contents":{"PredError": pe,"Power_W": pw, "Current_A": c, "Irradiance_Wcm": irr, "Power_dBm": pw_dBm, "Saturation_Per": s}}  
        for (t,pe,pw,c,irr,pw_dBm,s) in list(zip(time_stamps,predError_list, power_measurements, current_measurements, irr_values, pow_dBm, sat_values))]
            # for (t,pe, p, c,d,irr,s) in list(zip(time_stamps,predError_list, power_measurements, current_measurements, irr_values, pow_dBm, sat_values))]
    # except:
    #     print("Error in creating dictionary objects")
    # print(data2)
    data_list=[]
    for i in range(len(data2)):
        data = json.dumps(data2[i])
        data_list.append(data)
    return data_list

# CODE FOR SENDING DATA TO METATRON
def send_metatron(datalist):
    # CONNECTION_STR = "Endpoint=sb://reshenietest2.servicebus.windows.net/;SharedAccessKeyName=RootManageSharedAccessKey;SharedAccessKey=aNo/hnefeXUKS6ei/VeOcFewKPYZ49MwSLMpH59Yk6M="
    # CONNECTION_STR = "Endpoint=sb://sktiotcomservicebus01prd.servicebus.windows.net/;SharedAccessKeyName=reshenie;SharedAccessKey=LNbyO1dtSkYN2j6t1kwfh8Idn0IrGTNu6c1iczUPg5Q=;EntityPath=reshenie-telemetry-queue" # "<NAMESPACE CONNECTION STRING>"
    # QUEUE_NAME = "reshenietest2"
    CONNECTION_STR = "Endpoint=sb://sktiotcomservicebus01prd.servicebus.windows.net/;SharedAccessKeyName=reshenie;SharedAccessKey=U/MZ9W8ih7R7KE14Zrf3/5ef8k3valVnvsRNRK4+MuA=;EntityPath=reshenie-telemetry-queue"
    QUEUE_NAME = "reshenie-telemetry-queue" #"<QUEUE NAME>"

    # Sending message to skt 
    servicebus_client = ServiceBusClient.from_connection_string(conn_str=CONNECTION_STR, logging_enable=True)
    
    with servicebus_client:
        # get a Queue Sender object to send messages to the queue
        sender = servicebus_client.get_queue_sender(queue_name=QUEUE_NAME)
        with sender:
            send_a_list_of_messages(sender, tr_data=datalist)
    print("Done sending data")

    # with open('G:/내 드라이브/이수민/21C laser AI POC/Dashboard/json_data.json', 'w') as json_file:
    #     json.dump(data2, json_file, indent=4)
    #     # data_list.append(data2)
    #     print("Done dumping data")

        
if __name__=='__main__':
    # max_power = 0.000067
    wavelength = 600
    duration = 1
    
    tlPM = TLPM() 
    resourceName = create_string_buffer(b'USB0::0x1313::0x807B::210629100::INSTR')
    tlPM.open(resourceName, c_bool(True), c_bool(True))

    model = load_model(r'G:\내 드라이브\이수민\21C laser AI POC\Dashboard\allNormCond')
    
    # internet connection checking
    param = '-n' if platform.system().lower()=='windows' else '-c'
    host = "www.google.com"
    command = ['ping', param, '1', host]
    
    # for trigger management
    glob_trig = 0
    # main(TLPM=tlPM, wavelength=wavelength, model=model, duration = duration)
    # schedule.every(duration*0.8).minutes.do(main, TLPM=tlPM, wavelength=wavelength, model=model, duration = duration)

    errors_occurred = []
    collecting = -1     # will be 0 duing data collection and 1 while data sending
    data_stored = []
    
    clipper = Thread(target=clip_saver)
    clipper.daemon = True
    clipper.start()

    while 1:
        # data collection
        try:
            time.sleep(1)
            collecting = 0
            Data = collect_data(TLPM=tlPM, wavelength=wavelength, model=model, duration = duration)
            print("data: ", Data)
            collecting = 1
            send_metatron(Data)
            if len(data_stored)>0:
                collecting = 2
                send_metatron(data_stored)
                data_stored = []

        except KeyboardInterrupt:
            try:
                tlPM.close()
            except:
                pass
            
            if collecting == 0:
                print("Photodiode Recording Terminated While Collecting Data")
            elif collecting == 1:
                print("Photodiode Recording Terminated While Sending New Data")
            elif collecting == 2:
                print("Photodiode Recording Terminated While Sending Stored Data")
           
    
            if len(data_stored)>0:
                print("Unsent data exists, please hold")
                try:
                    send_metatron(data_stored)
                    print("Done sending unsent data")
                    data_stored = []
                except: 
                    path = 'G:/내 드라이브/이수민/21C laser AI POC/Dashboard/Data_stored_'+datetime.now().strftime('%Y-%m-%d_%H_%M_%S')+'.json' 
                    with open(path, 'w+') as json_file:
                        json.dump(data_stored, json_file, indent=4)
                        # data_list.append(data2)
                        print("Done saving unsent data")
    
            if len(errors_occurred)>0:
                print("Errors occurred during execution: ")
                print(errors_occurred)
                # append all errors occurred to error log
                with open("G:/내 드라이브/이수민/21C laser AI POC/Dashboard/error_log.txt", "a+") as f:
                    for err in errors_occurred:
                        f.write("\n"+str(err))
                print("Error log updated")
            else:
                print("No Errors Occurred")
            break

        except Exception as e:
            if collecting == 0:
                error_message = "Collecting Error"
            elif collecting == 1:
                error_message = "Sending New Data Error"
                # append new data to data stored list
                data_stored.extend(Data)
                print(data_stored)
                # if data stored list length greater than limit, save data sotred as json file and empty list
                if  len(data_stored)>2500:
                    path = 'G:/내 드라이브/이수민/21C laser AI POC/Dashboard/Data_stored_'+datetime.now().strftime('%Y-%m-%d_%H_%M_%S')+'.json' 
                    with open(path, 'w+') as json_file:
                        json.dump(data_stored, json_file, indent=4)
                        print("Done saving stored data")
                    data_stored = []
            elif collecting == 3:
                error_message = "Sending Stored Data Error"
            errors_occurred.append((error_message, time.ctime(), e))
