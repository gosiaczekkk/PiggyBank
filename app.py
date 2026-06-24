import os
from flask import Flask, render_template, request, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy

app = Flask(__name__)

# Klucz sekretny pobierany ze zmiennych środowiskowych serwera (dla bezpieczeństwa)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'super-sekretny-klucz-piggybank-produkcja')

# DYNAMICZNA BAZA DANYCH: Jeśli serwer produkcyjny (np. PostgreSQL) poda swój adres, Flask się podepnie.
# W przeciwnym wypadku fallback do lokalnego SQLite.
DATABASE_URL = os.environ.get('DATABASE_URL', 'sqlite:///piggybank.db')
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

app.config['SQLALCHEMY_DATABASE_URI'] = DATABASE_URL
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# =========================================================================
# WARSTWA MODELI
# =========================================================================

class Goal(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100), nullable=False)
    target_amount = db.Column(db.Float, nullable=False)
    current_amount = db.Column(db.Float, default=0.0)
    category = db.Column(db.String(50), default='Ogólne')
    payments = db.relationship('Payment', backref='goal', lazy=True, cascade="all, delete-orphan")

    def get_progress(self):
        if self.target_amount <= 0:
            return 0
        progress = (self.current_amount / self.target_amount) * 100
        return min(round(progress, 1), 100.0)

class Payment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    amount = db.Column(db.Float, nullable=False)
    date_added = db.Column(db.String(10), nullable=False)
    description = db.Column(db.String(200))
    goal_id = db.Column(db.Integer, db.ForeignKey('goal.id'), nullable=False)

# =========================================================================
# KONTROLERY / TRASY
# =========================================================================

@app.route('/')
def index():
    all_goals = Goal.query.all()
    total_saved = sum(g.current_amount for g in all_goals)
    total_target = sum(g.target_amount for g in all_goals)
    global_progress = (total_saved / total_target * 100) if total_target > 0 else 0
    return render_template('index.html', goals=all_goals, total_saved=round(total_saved, 2), total_target=round(total_target, 2), global_progress=round(global_progress, 1))

@app.route('/goal/add', methods=['POST'])
def add_goal():
    title = request.form.get('title')
    target_amount = request.form.get('target_amount')
    category = request.form.get('category', 'Ogólne')

    if not title or not target_amount:
        flash('Wszystkie pola są wymagane!', 'error')
        return redirect(url_for('index'))
    
    try:
        new_goal = Goal(title=title, target_amount=float(target_amount), current_amount=0.0, category=category)
        db.session.add(new_goal)
        db.session.commit()
        flash('Nowy cel został dodany!', 'success')
    except ValueError:
        flash('Kwota docelowa musi być liczbą!', 'error')
        
    return redirect(url_for('index'))

@app.route('/goal/<int:goal_id>')
def goal_detail(goal_id):
    goal = Goal.query.get_or_404(goal_id)
    return render_template('detail.html', goal=goal)

@app.route('/goal/edit/<int:goal_id>', methods=['POST'])
def edit_goal(goal_id):
    goal = Goal.query.get_or_404(goal_id)
    goal.title = request.form.get('title')
    target_amount = request.form.get('target_amount')
    goal.category = request.form.get('category')

    try:
        goal.target_amount = float(target_amount)
        db.session.commit()
        flash('Cel zaktualizowany!', 'success')
    except ValueError:
        flash('Błąd kwoty!', 'error')
        
    return redirect(url_for('goal_detail', goal_id=goal_id))

@app.route('/goal/delete/<int:goal_id>')
def delete_goal(goal_id):
    goal = Goal.query.get_or_404(goal_id)
    db.session.delete(goal)
    db.session.commit()
    flash('Cel usunięty.', 'info')
    return redirect(url_for('index'))

@app.route('/goal/<int:goal_id>/payment', methods=['POST'])
def add_payment(goal_id):
    goal = Goal.query.get_or_404(goal_id)
    amount = request.form.get('amount')
    date_added = request.form.get('date_added')
    description = request.form.get('description', '')

    try:
        payment_amount = float(amount)
        if payment_amount > 0 and date_added:
            new_payment = Payment(amount=payment_amount, date_added=date_added, description=description, goal_id=goal.id)
            goal.current_amount += payment_amount
            db.session.add(new_payment)
            db.session.commit()
    except ValueError:
        pass
        
    return redirect(url_for('goal_detail', goal_id=goal.id))

@app.route('/payment/delete/<int:payment_id>')
def delete_payment(payment_id):
    payment = Payment.query.get_or_404(payment_id)
    goal = Goal.query.get(payment.goal_id)
    
    goal.current_amount -= payment.amount
    if goal.current_amount < 0:
        goal.current_amount = 0.0

    db.session.delete(payment)
    db.session.commit()
    return redirect(url_for('goal_detail', goal_id=goal.id))

# Inicjalizacja tabel bazodanowych przy starcie (jeśli nie istnieją)
with app.app_context():
    db.create_all()
