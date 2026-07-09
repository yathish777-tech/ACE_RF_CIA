from datetime import date, timedelta

def check(submission_type, acknowledged, exam_date, end_date, absence):
    today = date.today()
    retest_open = (end_date is not None and end_date >= today)
    if submission_type == 'pre':
        if not retest_open:
            return 'closed'
    else:
        # late: enforce exam_date < today <= end_date
        if not (exam_date is not None and exam_date < today and end_date is not None and end_date >= today):
            return 'closed'
        if acknowledged != '1':
            return 'ack_required'
    # Absence is required only for LATE submissions per updated rules
    if submission_type == 'late' and not absence:
        return 'absence_required'
    return 'allowed'

if __name__ == '__main__':
    today = date.today()
    exam_future = today + timedelta(days=5)
    exam_past = today - timedelta(days=5)
    end_future = today + timedelta(days=10)

    cases = [
        ('pre','0',exam_future,end_future,True),
        ('pre','1',exam_future,end_future,True),
        ('late','0',exam_past,end_future,True),
        ('late','1',exam_past,end_future,True),
    ]

    for c in cases:
        print(c[0], 'ack=', c[1], '->', check(*c))

    print('pre without absence ->', check('pre','0',exam_future,end_future,False))
