from models import db, User, Subject, Chapter, Quiz, Question, Score
from main import app
from sqlalchemy import inspect

with app.app_context():
    print("📋 Tables in DB:")
    inspector = inspect(db.engine)
    tables = inspector.get_table_names()
    for table in tables:
        print(" -", table)

    print("\n🧪 User table data:")
    try:
        users = User.query.all()
        for u in users:
            print(f"  {u.id} | {u.email} | {u.full_name}")
        if not users:
            print("  (no users yet)")
    except Exception as e:
        print("Error:", e)
