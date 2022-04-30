import time
from concurrent.futures import ThreadPoolExecutor

result = 0


def thread_one(results):
    global result
    time.sleep(1)
    return "str test"


def thread_two(results):
    global result
    while 1:
        for i in range(10000):
            result += 1
        result -= 9999
        print(f'two : {time.time()}, result: {result}\n')


def main():
    global result
    with ThreadPoolExecutor(max_workers=4) as exe:
        # start_time = time.time()
        #
        # end_time = time.time()

        future = exe.submit(thread_one, result)
        print(future.result())

if __name__ == '__main__':
    # while 1:
    main()
        # time.sleep(1.0)
