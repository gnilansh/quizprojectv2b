from celery.schedules import crontab
from celery_worker import celery
from celery_worker import send_daily_reminders

celery.conf.beat_schedule = {
    'daily-reminder-email': {
        'task': 'celery_worker.send_reminder_emails',
        'schedule': crontab(hour=18, minute=0),
    },
    'monthly-user-report': {
        'task': 'celery_worker.send_monthly_report',
        'schedule': crontab(day_of_month=1, hour=9, minute=0),
    }
}

