import time
from concurrent.futures import ThreadPoolExecutor

result = 0


def thread_one(results):
    global result
    while 1:
        for i in range(10000):
            result += 1
        result -= 9999
        print(f'one : {time.time()}, result: {result}\n')


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
        start_time = time.time()

        end_time = time.time()
        exe.submit(thread_one, end_time - start_time)

        exe.submit(thread_two, end_time - start_time)


if __name__ == '__main__':
    # while 1:
    main()
        # time.sleep(1.0)
