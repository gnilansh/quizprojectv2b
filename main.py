from flask import Flask, request, jsonify, Response
from flask_sqlalchemy import SQLAlchemy
from flask_bcrypt import Bcrypt
from flask_cors import CORS
from flask_mail import Mail
from datetime import datetime
from functools import wraps
from flask_caching import Cache
import csv
from io import StringIO

# ─── App Setup ───
app = Flask(__name__)
bcrypt = Bcrypt(app)
CORS(app)

# ─── Mail Config ───
app.config.update(
    MAIL_SERVER='smtp.gmail.com',
    MAIL_PORT=587,
    MAIL_USE_TLS=True,
    MAIL_USERNAME='gnilansh@gmail.com',
    MAIL_PASSWORD='lbna mnzo nzad eqcd'
)
mail = Mail(app)

# ─── Database Config ───
app.config.update(
    SQLALCHEMY_DATABASE_URI='sqlite:///quizmaster.db',
    SQLALCHEMY_TRACK_MODIFICATIONS=False
)
db = SQLAlchemy(app)

# ─── Cache Config ───
app.config['CACHE_TYPE'] = 'RedisCache'
app.config['CACHE_REDIS_URL'] = 'redis://localhost:6379/0'
cache = Cache(app)

# ─── Models ───
class User(db.Model):
    id            = db.Column(db.Integer, primary_key=True)
    email         = db.Column(db.String(100), unique=True, nullable=False)
    password      = db.Column(db.String(200), nullable=False)
    full_name     = db.Column(db.String(100), nullable=False)
    qualification = db.Column(db.String(100), nullable=False)
    dob           = db.Column(db.String(20), nullable=False)

class Subject(db.Model):
    id          = db.Column(db.Integer, primary_key=True)
    name        = db.Column(db.String(100), nullable=False)
    description = db.Column(db.String(200))

class Chapter(db.Model):
    id          = db.Column(db.Integer, primary_key=True)
    name        = db.Column(db.String(100), nullable=False)
    description = db.Column(db.String(200))
    subject_id  = db.Column(db.Integer, db.ForeignKey('subject.id'))

class Quiz(db.Model):
    id            = db.Column(db.Integer, primary_key=True)
    chapter_id    = db.Column(db.Integer, db.ForeignKey('chapter.id'))
    date_of_quiz  = db.Column(db.String(20))
    time_duration = db.Column(db.String(20))
    remarks       = db.Column(db.String(200))

class Question(db.Model):
    id                 = db.Column(db.Integer, primary_key=True)
    quiz_id            = db.Column(db.Integer, db.ForeignKey('quiz.id'))
    question_statement = db.Column(db.String(300))
    option1            = db.Column(db.String(100))
    option2            = db.Column(db.String(100))
    option3            = db.Column(db.String(100))
    option4            = db.Column(db.String(100))
    correct_option     = db.Column(db.String(100))

class Score(db.Model):
    id                   = db.Column(db.Integer, primary_key=True)
    user_id              = db.Column(db.Integer, db.ForeignKey('user.id'))
    quiz_id              = db.Column(db.Integer, db.ForeignKey('quiz.id'))
    total_scored         = db.Column(db.Integer)
    time_stamp_of_attempt= db.Column(db.String(30))

# ─── Celery Tasks Import ───
from celery_worker import (
    add,
    send_reminder_emails,
    send_monthly_report,
    export_user_scores,
    export_all_user_scores
)

# ─── Auto-create tables on first real request ───
_initialized = False
@app.before_request
def ensure_tables_exist():
    global _initialized
    if not _initialized:
        db.create_all()
        _initialized = True

# ─── Optional Manual DB Reset ───
@app.route("/init-db", methods=["GET"])
def init_db():
    db.drop_all()
    db.create_all()
    return "✅ Tables dropped and created again!"

# ─── Admin Config ───
ADMIN_EMAIL    = "admin@quizmaster.com"
ADMIN_PASSWORD = "admin123"
def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if request.headers.get("Authorization") != "admin-secret-token":
            return jsonify({"error":"Unauthorized"}), 403
        return f(*args, **kwargs)
    return decorated

# ─── Routes ───

@app.route("/", methods=["GET"])
def home():
    return jsonify({"message":"Quiz Master Backend Running!"})

@app.route("/admin/login", methods=["POST"])
def admin_login():
    data = request.get_json(force=True)
    if (data.get("email")==ADMIN_EMAIL and
        data.get("password")==ADMIN_PASSWORD):
        return jsonify({"message":"Admin login successful","token":"admin-secret-token"})
    return jsonify({"error":"Invalid admin credentials"}), 401

@app.route("/register", methods=["POST"])
def register():
    data = request.get_json(force=True)
    for f in ('email','password','full_name','qualification','dob'):
        if not data.get(f):
            return jsonify({"error":f"Missing field: {f}"}), 400
    if User.query.filter_by(email=data['email']).first():
        return jsonify({"error":"Email already registered"}), 409
    try:
        pw_hash = bcrypt.generate_password_hash(data['password']).decode()
        u = User(
            email=data['email'],
            password=pw_hash,
            full_name=data['full_name'],
            qualification=data['qualification'],
            dob=data['dob']
        )
        db.session.add(u)
        db.session.commit()
        return jsonify({"message":"User registered successfully!"}), 201
    except:
        return jsonify({"error":"Server error during registration"}), 500

@app.route("/login", methods=["POST"])
def login():
    data = request.get_json(force=True)
    user = User.query.filter_by(email=data.get('email')).first()
    if not user or not bcrypt.check_password_hash(user.password, data.get('password')):
        return jsonify({"error":"Invalid email or password"}), 401
    return jsonify({
        "message":"Login successful",
        "user": {"id":user.id,"email":user.email,"full_name":user.full_name}
    })

# ─── Admin CRUD ───
@app.route("/subject", methods=["POST"])
@admin_required
def add_subject():
    d = request.get_json(force=True)
    if not d.get("name"):
        return jsonify({"error":"Subject name is required"}), 400
    s = Subject(name=d["name"], description=d.get("description"))
    db.session.add(s); db.session.commit()
    return jsonify({"message":"Subject added","id":s.id})

@app.route("/subject/<int:sid>", methods=["PUT"])
@admin_required
def update_subject(sid):
    d = request.get_json(force=True)
    s = Subject.query.get_or_404(sid)
    s.name = d.get("name", s.name)
    s.description = d.get("description", s.description)
    db.session.commit()
    return jsonify({"message":"Subject updated"})

@app.route("/subject/<int:sid>", methods=["DELETE"])
@admin_required
def delete_subject(sid):
    s = Subject.query.get_or_404(sid)
    db.session.delete(s); db.session.commit()
    return jsonify({"message":"Subject deleted"})

@app.route("/chapter", methods=["POST"])
@admin_required
def add_chapter():
    d = request.get_json(force=True)
    if not d.get("name") or not d.get("subject_id"):
        return jsonify({"error":"Chapter name and subject_id are required"}), 400
    c = Chapter(name=d["name"],
                description=d.get("description"),
                subject_id=d["subject_id"])
    db.session.add(c); db.session.commit()
    return jsonify({"message":"Chapter added","id":c.id})

@app.route("/quiz", methods=["POST"])
@admin_required
def add_quiz():
    d = request.get_json(force=True)
    if not all([d.get("chapter_id"), d.get("date_of_quiz"), d.get("time_duration")]):
        return jsonify({"error":"Missing required fields"}), 400
    q = Quiz(
        chapter_id=d["chapter_id"],
        date_of_quiz=d["date_of_quiz"],
        time_duration=d["time_duration"],
        remarks=d.get("remarks")
    )
    db.session.add(q); db.session.commit()
    return jsonify({"message":"Quiz created","quiz_id":q.id})

@app.route("/question", methods=["POST"])
@admin_required
def add_question():
    d = request.get_json(force=True)
    keys = ["quiz_id","question_statement","option1","option2","option3","option4","correct_option"]
    if not all(d.get(k) for k in keys):
        return jsonify({"error":"All fields are required"}), 400
    qt = Question(
        quiz_id=d["quiz_id"],
        question_statement=d["question_statement"],
        option1=d["option1"], option2=d["option2"],
        option3=d["option3"], option4=d["option4"],
        correct_option=d["correct_option"]
    )
    db.session.add(qt); db.session.commit()
    return jsonify({"message":"Question added","question_id":qt.id})

# ─── Public API ───
@app.route("/subjects", methods=["GET"])
def list_subjects():
    subs = Subject.query.all()
    return jsonify({"subjects":[{"id":s.id,"name":s.name} for s in subs]})

@app.route("/subjects/<int:sid>/chapters", methods=["GET"])
def list_chapters(sid):
    chaps = Chapter.query.filter_by(subject_id=sid).all()
    return jsonify({"chapters":[{"id":c.id,"name":c.name} for c in chaps]})

@app.route("/chapters/<int:cid>/quizzes", methods=["GET"])
def list_quizzes(cid):
    qs = Quiz.query.filter_by(chapter_id=cid).all()
    return jsonify({"quizzes":[{"id":q.id,"date":q.date_of_quiz,"duration":q.time_duration} for q in qs]})

@app.route("/quiz/<int:qz>", methods=["GET"])
def get_quiz_questions(qz):
    qs = Question.query.filter_by(quiz_id=qz).all()
    return jsonify({
        "quiz_id":qz,
        "questions":[
            {"id":q.id,
             "question_statement":q.question_statement,
             "options":[q.option1,q.option2,q.option3,q.option4]}
            for q in qs
        ]
    })

@app.route("/quiz/submit", methods=["POST"])
def submit_quiz():
    d = request.get_json(force=True)
    if not all([d.get("user_id"), d.get("quiz_id"), d.get("answers")]):
        return jsonify({"error":"Missing data"}), 400
    score = sum(
        1 for ans in d["answers"]
        if (q := Question.query.get(ans["question_id"]))
           and q.correct_option == ans["selected"]
    )
    rec = Score(
        user_id=d["user_id"],
        quiz_id=d["quiz_id"],
        total_scored=score,
        time_stamp_of_attempt=datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    )
    db.session.add(rec); db.session.commit()
    return jsonify({"message":"Quiz submitted","score":score,"total_questions":len(d["answers"])})

@app.route("/user/<int:uid>/scores", methods=["GET"])
def get_user_scores(uid):
    hist = []
    for s in Score.query.filter_by(user_id=uid).all():
        q   = Quiz.query.get(s.quiz_id)
        ch  = Chapter.query.get(q.chapter_id) if q else None
        sbj = Subject.query.get(ch.subject_id) if ch else None
        hist.append({
            "score_id": s.id,
            "quiz_id":  s.quiz_id,
            "subject":  sbj.name   if sbj else None,
            "chapter":  ch.name    if ch  else None,
            "date":     s.time_stamp_of_attempt,
            "score":    s.total_scored
        })
    return jsonify({"user_id":uid, "history":hist})

# ─── Trigger Celery Export (email) ───
@app.route("/export-user-scores", methods=["POST"])
def trigger_export():
    d = request.get_json(force=True)
    if not d.get("user_id"):
        return jsonify({"error":"User ID is required"}),400
    task = export_user_scores.delay(d["user_id"])
    return jsonify({"message":"Export started","task_id":task.id}),202

# ─── Immediate CSV Download ───
@app.route("/user/<int:uid>/export", methods=["GET"])
def export_user_csv(uid):
    scores = Score.query.filter_by(user_id=uid).all()

    si = StringIO()
    writer = csv.writer(si)
    writer.writerow(['Quiz ID','Subject','Chapter','Date','Score'])

    for s in scores:
        q   = Quiz.query.get(s.quiz_id)
        ch  = Chapter.query.get(q.chapter_id) if q else None
        sbj = Subject.query.get(ch.subject_id) if ch else None
        writer.writerow([
            s.quiz_id,
            sbj.name   if sbj else '',
            ch.name    if ch  else '',
            s.time_stamp_of_attempt,
            s.total_scored
        ])

    output = si.getvalue(); si.close()
    return Response(
        output,
        mimetype="text/csv",
        headers={"Content-Disposition":f"attachment; filename=user_{uid}_history.csv"}
    )

# ─── Run Server ───
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
