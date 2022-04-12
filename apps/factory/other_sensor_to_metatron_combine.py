# -*- coding: utf-8 -*-
"""
Created on Thu Nov  4 15:39:07 2021

@author: Sumin Lee
"""
import datetime
import time
import schedule
import keyboard

import other_sensor_to_metatron

main = other_sensor_to_metatron.main
start_time = time.time()


class SensorInfo:
    # hamachi 가상 ip,
    def __init__(self, serv_ip, serv_name, mac_id, service_id):
        self.servIP = serv_ip
        self.servName = serv_name
        self.macID = mac_id
        self.serviceId = service_id


class KeyPress(Exception):
    pass


class DataResult:

    def __init__(self):
        self.errors_occurred = []

    def data_trans(self, duration):
        sensors = [SensorInfo('25.0.255.7', "inclination_test", '5e:54:8a:8a', None),
                   SensorInfo('25.0.255.7', "proxmity_hall_test", '07:a7:c4:95', None),
                   SensorInfo('25.0.255.7', "proxmity_switch_test", '8e:19:de:33', None),
                   ]

        print(sensors)
        print('=====', time.ctime(), '=====')

        for i in range(len(sensors)):
            print(datetime.datetime.now(), sensors[i].servName)
            try:
                main(sensors[i], duration)
            except Exception as e:
                self.errors_occurred.append((time.ctime(), sensors[i].servName, e))
                # errors_solved.append((time.ctime(), sensors[i].servName, e))
        print(self.errors_occurred)


if __name__ == '__main__':
    # global errors_solved
    # errors_solved = []
    current_duration = 60
    dataResult = DataResult()
    dataResult.data_trans(current_duration)
    schedule.every(current_duration).minutes.do(DataResult.data_trans, current_duration)

    while 1:
        if keyboard.is_pressed('q'):
            print("Terminated sending data")
            if len(dataResult.errors_occurred) > 0:
                print("Errors occured during execution: ")
                for item in dataResult.errors_occurred:
                    print(item)

        else:
            schedule.run_pending()
            time.sleep(1)
