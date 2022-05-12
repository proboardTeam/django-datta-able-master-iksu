# import the necessary packages
from keyclipwriter import KeyClipWriter
from imutils.video import VideoStream
import argparse
import datetime
import imutils
import time
import cv2
import queue
from random import randrange
from threading import Thread
import shutil 
import os

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

            trigger_flag = glob_trig
            if trigger_flag==True:
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

        # # if we are in the middle of recording a clip, wrap it up
        # if kcw.recording:
        #     #if disk full remove oldest file in camera recordings folder
        #     while notEnoughStorage()==True:
        #         delete_oldest_file(path=)
        #     kcw.finish()
        # do a bit of cleanup
        cv2.destroyAllWindows()
        vs.stop()

def trigger_generator():
    '''
    This function appends timestamps of instances where predictive error exceeds threshold. 
    In testing this function will randomly append timestamps.
    '''
    global trigger_history
    global last_time 
    temp = 1
    time.sleep(5)
    while 1:
        temp = randrange(4)
        print(temp)
        if temp==0: 
            now = time.time()
            last_time = now
            trigger_history.append(now)
        time.sleep(5)

if __name__ == '__main__':
    timestamp_queue = queue.Queue()
    instance_array,trigger_history = [], []
    start_time, last_time = 0, 0
    max_interval = 3
    glob_trig = False
    trigger_str = []

    start_time = time.time()
    # start generating trigger instances as a thread
    generator = Thread(target=trigger_generator)
    generator.daemon = True
    generator.start()

    clipper = Thread(target=clip_saver)
    clipper.daemon = True
    clipper.start()

    while True:
        try:
            if time.time()-last_time < 5:
                glob_trig = True
            else:
                glob_trig = False
            time.sleep(0.01)

        except KeyboardInterrupt:
            for t in trigger_history:
                trigger_str.append(datetime.datetime.fromtimestamp(t).strftime('%Y-%m-%d %H:%M:%S.%f'))
            
            print("Time passed: ", time.time()-start_time)
            print("Trigger history: ", trigger_str)
            break
