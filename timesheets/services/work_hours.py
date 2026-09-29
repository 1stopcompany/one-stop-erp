from collections import defaultdict

def calculate_daily_hours(records):
    daily_hours = defaultdict(int)
    last_check_in = None

    for record in records:
        if record.check_type == 'in':
            last_check_in = record.timestamp

        elif record.check_type == 'out' and last_check_in:
            duration = record.timestamp - last_check_in
            if duration.total_seconds() > 0:
                date = last_check_in.date()
                daily_hours[date] += duration.total_seconds()
            last_check_in = None

    return daily_hours
