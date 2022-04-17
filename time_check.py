import time
from datetime import datetime, timedelta

end_time_time = time.time() - 3600 * 9
start_time_time = end_time_time - 3600 * 9

end_date_time_stamp = datetime.now().timestamp() - 3600 * 9
start_date_time_stamp = end_date_time_stamp - 3600 * 9

end_time_stamp_str = datetime.fromtimestamp(end_time_time).strftime("%Y-%m-%dT%H:%M:%S.%f+00:00")
start_time_stamp_str = datetime.fromtimestamp(start_time_time).strftime("%Y-%m-%dT%H:%M:%S.%f+00:00")

end_date_time_stamp_str = datetime.fromtimestamp(end_date_time_stamp).strftime("%Y-%m-%dT%H:%M:%S.%f+00:00")
start_date_time_stamp_str = datetime.fromtimestamp(start_date_time_stamp).strftime("%Y-%m-%dT%H:%M:%S.%f+00:00")

end_time = datetime.now() - timedelta(hours=9)
start_time = end_time - timedelta(hours=9)
end_time = end_time.isoformat()
start_time = start_time.isoformat()

print(f'start time stamp = {start_time_time}, end time stamp = {end_time_time}')
print(f'start date_time stamp = {start_date_time_stamp}, end date_time stamp = {end_date_time_stamp}')

print(f'start time stamp to str = {start_time_stamp_str}, end time stamp = {end_time_stamp_str}')
print(f'start date_time stamp to str = {start_date_time_stamp_str}, end date_time stamp to str = {end_date_time_stamp_str}')

print(f"current time : {datetime.now()}")
print(f'start time = {start_time}, end time = {end_time}')
