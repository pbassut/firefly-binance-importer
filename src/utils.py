from datetime import datetime
from dateutil.relativedelta import relativedelta

one_day = 24 * 60 * 60

def to_ms(timestamp):
    return int(timestamp * 1000)

def from_ms(timestamp):
    return int(timestamp / 1000)

def human_readable_interval(from_datetime, to_datetime):
    return str(from_datetime) + " to " + str(to_datetime - relativedelta(seconds=1))

def human_readable_interval_ts(from_timestamp, to_timestamp):
    return human_readable_interval(datetime.fromtimestamp(from_ms(from_timestamp)), datetime.fromtimestamp(from_ms(to_timestamp)))

def days_ms(timestamp, days=90):
    return timestamp + days * one_day

def interval(from_timestamp, to_timestamp, days=90):
    from_datetime = datetime.fromtimestamp(from_ms(from_timestamp))
    to_datetime = from_datetime + relativedelta(days=days)

    end_datetime = datetime.fromtimestamp(from_ms(to_timestamp))
    while from_datetime < end_datetime:
        if to_datetime > end_datetime:
            to_datetime = end_datetime

        yield from_datetime, to_datetime

        from_datetime = to_datetime + relativedelta(days=1)
        to_datetime = from_datetime + relativedelta(days=days) 
