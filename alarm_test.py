import serial
import time

ser = serial.Serial('COM5', 9600)
class some_class:
    def __init__(self, num):
        self.num = num

    def alarm(self):
        print("in")
        if ser.readable():
            val = self.num
            print(val)

            if val == '1':
                val = val.encode('utf-8')
                ser.write(val)
                print("Serial no 1")

            elif val == '2':
                val = val.encode('utf-8')
                ser.write(val)
                ser.write("Serial no 2")
                time.sleep(0.5)

            elif val == '3':
                val = val.encode('utf-8')
                ser.write(val)
                ser.write("Serial no 3")
                time.sleep(0.5)

            elif val == '4':
                val = val.encode('utf-8')
                ser.write(val)
                ser.write("Serial no 4")
                time.sleep(0.5)

