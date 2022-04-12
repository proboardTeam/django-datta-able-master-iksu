# -*- coding: utf-8 -*-
"""
Created on Thu Nov  4 15:39:07 2021

@author: Sumin Lee
"""
import datetime
import time
import schedule
import keyboard

# import OPCUA_extract_send_anom_copy2 
# import OPCUA_extract_send_anom_copy3 
# import OPCUA_extract_send_anom_copy4 
# import OPCUA_extract_send_anom_copy5 
import T_DK_Curr_to_Metatron

# polytec1=OPCUA_extract_send_anom_copy1.main
# polytec2=OPCUA_extract_send_anom_copy2.main
# gpn1=OPCUA_extract_send_anom_copy3.main
# gpn2=OPCUA_extract_send_anom_copy4.main
# kpi1=OPCUA_extract_send_anom_copy5.main
# kpi2=OPCUA_extract_send_anom_copy6.main

main = T_DK_Curr_to_Metatron.main

start_time = time.time()

class sensorInfo:
    def __init__(self, servIP, servName, macID,serviceID):
        self.servIP = servIP
        self.servName = servName
        self.macID = macID
        self.serviceId = serviceID


# def signal_handler():
#     print('You pressed Ctrl+C!')
#     raise KeyPress 

# #Assign Handler Function
# signal.signal(signal.SIGINT, signal_handler)

# class KeyPress(Exception):
#     pass

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
    # sensors.append(sensorInfo('25.52.52.52', "dksw1",'11:90:77:d8')) #(T_DK) Welding_Vib_LowFQ 
    # sensors.append(sensorInfo('25.52.52.52', "dksw2",'a3:40:ba:60')) #(T_DK) Welding_Vib_HighFQ 
    # sensors.append(sensorInfo('25.52.52.52', "dksw3",'92:7c:bd:51', '83')) 현재 동작 # (T_DK) Current_WeldingLeft
    # sensors.append(sensorInfo('25.52.52.52', "dksw4",'ce:42:0e:97', '83')) 현재 동작 # (T_DK) Current_WeldingRight
    sensors.append(sensorInfo('25.9.7.151', "reshenie1", ''))
    # sensors.append(sensorInfo('25.52.52.52', "dksw5",'92:7c:bd:51')) #(T_DK) Milling_Right_Vib_HighFQ
    # sensors.append(sensorInfo('25.52.52.52', "dksw6",'ce:42:0e:97')) #(T_DK) Milling_Left_Vib_LowFQ 

    print(sensors)
    print('=====',time.ctime(),'=====')

    for i in range(len(sensors)):
        print(datetime.datetime.now(),sensors[i].servName)
        main(sensors[i], duration)    
        # try:
        # except Exception as e:
        #     errors_occurred.append((time.ctime(), sensors[i].servName, e))
        #     errors_solved.append((time.ctime(), sensors[i].servName, e))     
    print(errors_occurred)
    
if __name__ == '__main__':   
    global errors_occurred
    errors_occurred = []
    global errors_solved
    errors_solved = []
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
            break
            # if len(errors_solved)>0:
            #     print("Errors solved during execution: ")
                # for item in errors_occurred:
                #     print(item)
            break
        else:
            schedule.run_pending()
            time.sleep(1)
    #except KeyboardInterrupt:
    #    print("Terminated sending data")
    #    if len(errors_occurred)>0:
    #        print("Errors occured during execution: ")
    #        for item in errors_occurred:
    #            print(item)
                
                