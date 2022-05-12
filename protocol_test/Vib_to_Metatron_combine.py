# -*- coding: utf-8 -*-
"""
Created on Thu Nov  4 15:39:07 2021

@author: Sumin Lee
"""
import datetime
import time
import schedule
import keyboard

import Vib_to_Metatron

main = Vib_to_Metatron.main

start_time = time.time()

class sensorInfo:
    def __init__(self, servIP, servName, macID,serviceID):
        self.servIP = servIP
        self.servName = servName
        self.macID = macID
        self.serviceId = serviceID


# def signal_handler():
#     print('You pressed Ctrl+C')
#     raise KeyPress 

# #Assign Handler Function
# signal.signal(signal.SIGINT, signal_handler)

class KeyPress(Exception):
    pass

def dataTrans(duration):
    sensors = []

    # sensors.append(sensorInfo('25.58.137.19', "reshenie1", '88:6e:7a:43')) # (O_RS_Old) vibration_test
    # sensors.append(sensorInfo('25.77.104.183', "reshenie1", 'b7:90:74:36')) #(O_RS_New) Reshenie New
    # sensors.append(sensorInfo('25.17.10.130', "pumpleftvib", '05:92:6d:a7')) #(T_PT) Pump_Left_vib
    # sensors.append(sensorInfo('25.17.10.130', "pumprightvib", '66:a0:b7:9d')) #(T_PT) Pump_Right_vib
    # sensors.append(sensorInfo('25.12.181.157', "gpn1", '94:f3:9e:df')) #(E_GP) Etching_White
    # sensors.append(sensorInfo('25.12.181.157', "gpn2", 'c6:28:a5:a3')) #(E_GP) Etching_Black
    # sensors.append(sensorInfo('25.3.15.233', "kpi1", '82:8e:2c:a3')) #(T_KP) Press_Vib_110Right 
    # sensors.append(sensorInfo('25.3.15.233', "kpi2",'9b:a3:eb:47')) #(T_KP) Press_Vib_80Left
    # sensors.append(sensorInfo('25.36.219.165', "side_spindle_2line",'11:90:77:d8')) #(S_K_ICT) 
    # sensors.append(sensorInfo('25.52.52.52', "dksw5",'92:7c:bd:51')) #(T_DK) Milling_Right_Vib_HighFQ 
    # sensors.append(sensorInfo('25.52.52.52', "dksw6",'ce:42:0e:97')) #(T_DK) Milling_Left_Vib_LowFQ 

    sensors.append(sensorInfo('25.31.102.59', "ziincheol1",'0d:66:24:8e','84')) #(T_ZC) TrapLine_1_Motor
    sensors.append(sensorInfo('25.31.102.59', "ziincheol2",'43:6d:7a:44','84')) #(T_ZC) TrapLine_1_Shaft
    # sensors.append(sensorInfo('25.31.102.59', "ziincheol3",'4d:cf:46:e8','84')) #(T_ZC) TrapLine_2_Motor 
    # sensors.append(sensorInfo('25.31.102.59', "ziincheol4",'c5:76:f8:1f','84')) #(T_ZC) TrapLine_2_Shaft 
    
    # sensors.append(sensorInfo('25.52.52.52', "dksw1",'11:90:77:d8', '83')) #(T_DK) Welding_Vib_LowFQ
    # sensors.append(sensorInfo('25.52.52.52', "dksw2",'a3:40:ba:60', '83')) #(T_DK) Welding_Vib_HighFQ
    # sensors.append(sensorInfo('25.52.52.52', "dksw5",'4b:98:18:4d', '83')) #(T_DK) Milling_Right_Vib_HighFQ
    # sensors.append(sensorInfo('25.52.52.52', "dksw6",'fb:cc:b1:63', '83')) #(T_DK) Milling_Left_Vib_LowFQ

    print(sensors)
    print('=====',time.ctime(),'=====')

    for i in range(len(sensors)):
        print(datetime.datetime.now(),sensors[i].servName)
        try:
            main(sensors[i], duration)    
        except Exception as e:
            errors_occurred.append((time.ctime(), sensors[i].servName, e))
            # errors_solved.append((time.ctime(), sensors[i].servName, e))     
    print(errors_occurred)
    
if __name__ == '__main__':   
    global errors_occurred
    errors_occurred = []
    # global errors_solved
    # errors_solved = []
    duration = 60
    dataTrans(duration)
    schedule.every(duration).minutes.do(dataTrans, duration)

    while 1:
        if keyboard.is_pressed('q'):
            print("Terminated sending data")
            if len(errors_occurred)>0:
                print("Errors occured during execution: ")
                for item in errors_occurred:
                    print(item)
            # if len(errors_solved)>0:
            #     print("Errors solved during execution: ")
                # for item in errors_occurred:
                #     print(item)
        else:
            schedule.run_pending()
            time.sleep(1)

    #except KeyboardInterrupt:
    #    print("Terminated sending data")
    #    if len(errors_occurred)>0:
    #        print("Errors occured during execution: ")
    #        for item in errors_occurred:
    #            print(item)
                
                