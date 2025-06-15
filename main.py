import json
import os
from flask import Flask, request, jsonify, render_template, session, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.dialects.postgresql import JSON as PG_JSON
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
from functools import wraps

app = Flask(__name__, template_folder='templates', static_folder='static')
app.config['SQLALCHEMY_DATABASE_URI'] = 'postgresql://myuser:newpassword@localhost/quizapp'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'devkey')

db = SQLAlchemy(app)
migrate = Migrate(app, db)

# MODELS

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    password_hash = db.Column(db.Text, nullable=False)
    email = db.Column(db.String(100), unique=True, nullable=False)

class Quiz(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100), nullable=False)
    category = db.Column(db.String(50), nullable=True)  # e.g. 'Web', 'AI'

class Question(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    quiz_id = db.Column(db.Integer, db.ForeignKey('quiz.id'), nullable=False)
    question_text = db.Column(db.Text, nullable=False)
    option_a = db.Column(db.Text, nullable=False)
    option_b = db.Column(db.Text, nullable=False)
    option_c = db.Column(db.Text, nullable=False)
    option_d = db.Column(db.Text, nullable=False)
    correct_option = db.Column(db.String(1), nullable=False)  # 'A', 'B', 'C', or 'D'

class Result(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    quiz_id = db.Column(db.Integer, db.ForeignKey('quiz.id'), nullable=False)
    score = db.Column(db.Integer, nullable=False)
    submitted_at = db.Column(db.DateTime, default=datetime.utcnow)
    answers = db.Column(PG_JSON, nullable=True)  # {question_id: selected_option}

# UTILS

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login_page'))
        return f(*args, **kwargs)
    return decorated_function

def import_questions_from_json(json_path, category, quiz_title):
    if not os.path.exists(json_path):
        print(f"File {json_path} not found, skipping import for {category}")
        return
    with open(json_path, "r", encoding="utf-8") as f:
        questions = json.load(f)
    quiz = Quiz.query.filter_by(category=category).first()
    if not quiz:
        quiz = Quiz(title=quiz_title, category=category)
        db.session.add(quiz)
        db.session.commit()
    # Delete all old questions for this quiz before importing
    Question.query.filter_by(quiz_id=quiz.id).delete()
    db.session.commit()
    imported = 0
    for q in questions:
        q_text = q.get("question_text") or q.get("question")
        options = q.get("options")
        answer = q.get("correct_option") or q.get("answer")
        # Convert answer text to 'A'/'B'/'C'/'D' if needed
        if answer and options and answer not in ["A", "B", "C", "D"]:
            for idx, opt in enumerate(options):
                if opt.strip().lower() == answer.strip().lower():
                    answer = chr(65 + idx)  # 65 is 'A'
                    break
        if options and answer in ["A", "B", "C", "D"]:
            db.session.add(Question(
                quiz_id=quiz.id,
                question_text=q_text,
                option_a=options[0],
                option_b=options[1],
                option_c=options[2],
                option_d=options[3],
                correct_option=answer
            ))
            imported += 1
    db.session.commit()
    print(f"Imported {imported} questions for {category}")

def init_db():
    with app.app_context():
        db.create_all()
        import_questions_from_json("questions.json", "Web", "Web Technology Quiz")
        import_questions_from_json("ai.json", "AI", "AI Fundamentals Quiz")
        print("✓ Database initialized and questions imported from JSON.")

# ROUTES

@app.route('/')
@login_required
def index():
    return render_template('index.html')

@app.route('/quizselect')
@login_required
def quiz_select_page():
    return render_template('quiz_select.html')

@app.route('/quizpage')
@login_required
def quiz_page():
    return render_template('quiz.html')

@app.route('/scorepage')
@login_required
def score_page():
    return render_template('score.html')

@app.route('/login', methods=['GET'])
def login_page():
    if 'user_id' in session:
        return redirect(url_for('index'))
    return render_template('login.html')

@app.route('/register', methods=['GET'])
def register_page():
    return render_template('register.html')

@app.route('/logout')
def logout():
    session.pop('user_id', None)
    return redirect(url_for('login_page'))

@app.route('/register', methods=['POST'])
def register():
    data = request.get_json() or request.form
    username = data.get('username', '').strip()
    email = data.get('email', '').strip().lower()
    password = data.get('password', '')

    if not username or not email or not password:
        return jsonify({'error': 'All fields required'}), 400

    if User.query.filter((User.username == username) | (User.email == email)).first():
        return jsonify({'error': 'Username or email already exists'}), 409

    password_hash = generate_password_hash(password)
    user = User(username=username, email=email, password_hash=password_hash)
    db.session.add(user)
    db.session.commit()
    return jsonify({'message': 'User registered successfully'})

@app.route('/login', methods=['POST'])
def login():
    data = request.get_json() or request.form
    username = data.get('username', '').strip()
    password = data.get('password', '')
    user = User.query.filter_by(username=username).first()
    if user and check_password_hash(user.password_hash, password):
        session['user_id'] = user.id
        return jsonify({'message': 'Login successful', 'username': user.username, 'redirect': url_for('index')})
    return jsonify({'error': 'Invalid credentials'}), 401

@app.route('/quiz', methods=['GET'])
@login_required
def get_quiz():
    quiz_id = request.args.get('quiz_id')
    category = request.args.get('category')
    quiz = None
    if quiz_id:
        quiz = Quiz.query.filter_by(id=quiz_id).first()
    elif category:
        quiz = Quiz.query.filter_by(category=category).first()
    if not quiz:
        quiz = Quiz.query.first()
    if not quiz:
        return jsonify({'error': 'Quiz not found'}), 404
    questions = Question.query.filter_by(quiz_id=quiz.id).all()
    question_list = []
    for q in questions:
        question_list.append({
            'id': q.id,
            'question_text': q.question_text,
            'options': {
                'A': q.option_a,
                'B': q.option_b,
                'C': q.option_c,
                'D': q.option_d
            },
            'correct_option': q.correct_option
        })
    return jsonify({
        'quiz_id': quiz.id,
        'title': quiz.title,
        'category': quiz.category,
        'questions': question_list
    })

@app.route('/score', methods=['GET'])
@login_required
def user_scores():
    results = Result.query.filter_by(user_id=session['user_id']).order_by(Result.submitted_at.desc()).all()
    scores = []
    for r in results:
        quiz = Quiz.query.get(r.quiz_id)
        scores.append({
            'quiz_title': quiz.title if quiz else 'Unknown',
            'score': r.score,
            'submitted_at': r.submitted_at.strftime('%Y-%m-%d %H:%M:%S'),
            'quiz_id': r.quiz_id,
            'answers': r.answers if r.answers else {}
        })
    return jsonify({'scores': scores})

@app.route('/submit_quiz', methods=['POST'])
@login_required
def submit_quiz():
    data = request.get_json()
    score = data.get("score")
    answers = data.get("answers")
    quiz_id = data.get("quiz_id")
    result = Result(
        user_id=session["user_id"],
        quiz_id=quiz_id,
        score=score,
        answers=answers,
        submitted_at=datetime.utcnow()
    )
    db.session.add(result)
    db.session.commit()
    return jsonify({"message": "Result saved!"}), 200

@app.route('/quiz_list', methods=['GET'])
@login_required
def quiz_list():
    quizzes = Quiz.query.all()
    return jsonify([{"title": q.title, "category": q.category} for q in quizzes])

if __name__ == '__main__':
    os.makedirs('templates', exist_ok=True)
    os.makedirs('static', exist_ok=True)
    app.run(debug=True, host='0.0.0.0', port=5000)
