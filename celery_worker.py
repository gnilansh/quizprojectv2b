# celery_worker.py

import time
import csv
from io import StringIO
from datetime import datetime, date

from celery import Celery
from celery.schedules import crontab

from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_mail import Mail, Message

# ─── Import your models directly ───────────────────────────────────
from models import User, Score, Quiz, Chapter, Subject

# ─── Celery Setup ─────────────────────────────────────────────────
celery = Celery(
    'celery_worker',
    broker='redis://admin:NGad**90@redis-19711.c267.us-east-1-4.ec2-redns.redis-cloud.com:19711/0',
    backend='redis://admin:NGad**90@redis-19711.c267.us-east-1-4.ec2-redns.redis-cloud.com:19711/0'
)
celery.conf.update(
    broker_connection_retry_on_startup=True,
    broker_pool_limit=10,
    result_backend_pool_limit=10,
    worker_prefetch_multiplier=1,
    task_acks_late=True,
    worker_max_tasks_per_child=1000,
    beat_schedule={
        'daily-reminder-email': {
            'task': 'celery_worker.send_reminder_emails',
            'schedule': crontab(hour=18, minute=0),
        },
        'monthly-report-email': {
            'task': 'celery_worker.send_monthly_report',
            'schedule': crontab(day_of_month=1, hour=9, minute=0),
        },
    }
)

ADMIN_EMAIL = 'admin@quizmaster.com'

def make_app():
    """
    Create a minimal Flask+SQLAlchemy+Mail app context
    so tasks can run standalone.
    """
    app = Flask(__name__)
    app.config.update(
        SQLALCHEMY_DATABASE_URI='sqlite:///quizmaster.db',
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        MAIL_SERVER='smtp.gmail.com',
        MAIL_PORT=587,
        MAIL_USE_TLS=True,
        MAIL_USERNAME='gnilansh@gmail.com',
        MAIL_PASSWORD='lbna mnzo nzad eqcd'
    )
    db = SQLAlchemy(app)
    mail = Mail(app)
    return app, db, mail

# ─── Tasks ─────────────────────────────────────────────────────────

@celery.task(name='celery_worker.add')
def add(x, y):
    time.sleep(3)
    return x + y

@celery.task(name='celery_worker.send_reminder_emails')
def send_reminder_emails():
    """
    Every day at 18:00, email users who haven't taken a quiz today.
    """
    app, db, mail = make_app()
    with app.app_context():
        today_str = date.today().isoformat()
        sent = 0
        for user in User.query.all():
            last = (Score.query
                    .filter_by(user_id=user.id)
                    .order_by(Score.id.desc())
                    .first())
            if not last or not last.time_stamp_of_attempt.startswith(today_str):
                msg = Message(
                    subject="🔔 Reminder: Take Your Quiz Today!",
                    sender=app.config['MAIL_USERNAME'],
                    recipients=[user.email],
                    body=(
                        f"Hi {user.full_name},\n\n"
                        "You haven't taken any quizzes today. Log in and attempt one now!\n\n"
                        "- Quiz Master"
                    )
                )
                mail.send(msg)
                sent += 1
        print(f"[{datetime.now()}] Sent daily reminders to {sent} users")
        return f"Sent {sent} reminders"

@celery.task(name='celery_worker.send_monthly_report')
def send_monthly_report():
    """
    On the 1st of each month at 09:00, email every user their activity report.
    """
    app, db, mail = make_app()
    with app.app_context():
        sent = 0
        for user in User.query.all():
            scores = Score.query.filter_by(user_id=user.id).all()
            count  = len(scores)
            total  = sum(s.total_scored for s in scores)
            avg    = total / count if count else 0
            html = (
                f"<h2>Monthly Report for {user.full_name}</h2>"
                f"<ul>"
                f"<li>Quizzes Taken: {count}</li>"
                f"<li>Total Score: {total}</li>"
                f"<li>Average Score: {avg:.2f}</li>"
                f"</ul>"
            )
            msg = Message(
                subject="📈 Your Monthly Quiz Report",
                sender=app.config['MAIL_USERNAME'],
                recipients=[user.email],
                html=html
            )
            mail.send(msg)
            sent += 1
        print(f"[{datetime.now()}] Sent monthly reports to {sent} users")
        return f"Sent {sent} monthly reports"

@celery.task(name='celery_worker.export_user_scores')
def export_user_scores(user_id):
    """
    Triggered by user: build their history CSV and email it to them.
    """
    app, db, mail = make_app()
    with app.app_context():
        user = db.session.get(User, user_id)
        if not user:
            return f"User {user_id} not found"

        buf = StringIO()
        writer = csv.writer(buf)
        writer.writerow(['Quiz ID','Subject','Chapter','Date','Score'])

        for s in Score.query.filter_by(user_id=user.id).all():
            q   = Quiz.query.get(s.quiz_id)
            ch  = Chapter.query.get(q.chapter_id) if q else None
            sbj = Subject.query.get(ch.subject_id) if ch else None
            writer.writerow([
                s.quiz_id,
                sbj.name if sbj else '',
                ch.name  if ch  else '',
                s.time_stamp_of_attempt,
                s.total_scored
            ])

        data = buf.getvalue()
        buf.close()

        msg = Message(
            subject="📄 Your Quiz History Export",
            sender=app.config['MAIL_USERNAME'],
            recipients=[user.email],
            body=f"Hi {user.full_name},\n\nFind attached your quiz history CSV.\n\n- Quiz Master"
        )
        msg.attach(
            filename=f"user_{user.id}_history.csv",
            content_type="text/csv",
            data=data
        )
        mail.send(msg)
        print(f"[{datetime.now()}] Emailed export to {user.email}")
        return f"Emailed export to {user.email}"

@celery.task(name='celery_worker.export_all_user_scores')
def export_all_user_scores():
    """
    Triggered by admin: build a CSV summary of all users,
    attach it to an email to ADMIN_EMAIL.
    """
    app, db, mail = make_app()
    with app.app_context():
        buf = StringIO()
        writer = csv.writer(buf)
        writer.writerow(['User ID','Email','Quizzes Taken','Average Score'])

        for user in User.query.all():
            scores = Score.query.filter_by(user_id=user.id).all()
            count  = len(scores)
            total  = sum(s.total_scored for s in scores)
            avg    = total/count if count else 0
            writer.writerow([user.id, user.email, count, f"{avg:.2f}"])

        data = buf.getvalue()
        buf.close()

        msg = Message(
            subject="🗃️ All Users Quiz Summary",
            sender=app.config['MAIL_USERNAME'],
            recipients=[ADMIN_EMAIL],
            body="Attached is the CSV summary for all users."
        )
        msg.attach(
            filename="all_users_summary.csv",
            content_type="text/csv",
            data=data
        )
        mail.send(msg)
        print(f"[{datetime.now()}] Emailed admin summary to {ADMIN_EMAIL}")
        return f"Admin summary emailed to {ADMIN_EMAIL}"
