import os
from flask import Flask, render_template, request, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy

app = Flask(__name__)

# PRODUKCYJNY BEZPIECZNY KLUCZ SEKRETNY:
# Pobiera klucz z systemu chmurowego. Jeśli go nie ma (czyli działasz lokalnie),
# używa Twojego standardowego klucza 'super-sekretny-klucz-piggybank'
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'super-sekretny-klucz-piggybank')

# PRODUKCYJNA DYNAMICZNA BAZA DANYCH:
# Jeśli chmura udostępni bazę produkcyjną (np. PostgreSQL), system się z nią połączy.
# Jeśli nie (czyli uruchamiasz lokalnie), automatycznie użyje Twojego pliku 'sqlite:///piggybank.db'
DATABASE_URL = os.environ.get('DATABASE_URL', 'sqlite:///piggybank.db')
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

app.config['SQLALCHEMY_DATABASE_URI'] = DATABASE_URL
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# ==========================================
# MODELE BAZY DANYCH (M w architekturze MVC)
# ==========================================

class Goal(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100), nullable=False)        # Nazwa celu
    target_amount = db.Column(db.Float, nullable=False)     # Kwota docelowa
    current_amount = db.Column(db.Float, default=0.0)       # Obecny stan oszczędności
    category = db.Column(db.String(50), default='Ogólne')    # Kategoria

    # Relacja z wpłatami - usunięcie celu usuwa też jego wpłaty (cascade)
    payments = db.relationship('Payment', backref='goal', lazy=True, cascade="all, delete-orphan")

    # Funkcja pomocnicza do obliczania procentu realizacji celu
    def get_progress(self):
        if self.target_amount <= 0:
            return 0
        progress = (self.current_amount / self.target_amount) * 100
        return min(round(progress, 1), 100.0)

class Payment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    amount = db.Column(db.Float, nullable=False)            # Kwota wpłaty
    date_added = db.Column(db.String(10), nullable=False)   # Data wpłaty w formacie RRRR-MM-DD
    description = db.Column(db.String(200))                 # Opcjonalny opis
    goal_id = db.Column(db.Integer, db.ForeignKey('goal.id'), nullable=False)

# ==========================================
# KONTROLERY / TRASY (C w architekturze MVC)
# ==========================================

# 1. Strona główna - Lista wszystkich celów (READ)
@app.route('/')
def index():
    all_goals = Goal.query.all()
    
    # Obliczanie globalnych statystyk na tablicę rozdzielczą
    total_saved = sum(g.current_amount for g in all_goals)
    total_target = sum(g.target_amount for g in all_goals)
    global_progress = (total_saved / total_target * 100) if total_target > 0 else 0
    
    return render_template('index.html', goals=all_goals, total_saved=round(total_saved, 2), total_target=round(total_target, 2), global_progress=round(global_progress, 1))

# 2. Dodawanie nowego celu (CREATE)
@app.route('/goal/add', methods=['POST'])
def add_goal():
    title = request.form.get('title')
    target_amount = request.form.get('target_amount')
    category = request.form.get('category', 'Ogólne')

    # Podstawowa walidacja danych wejściowych
    if not title or not target_amount:
        flash('Wszystkie pola są wymagane!', 'error')
        return redirect(url_for('index'))
    
    try:
        new_goal = Goal(
            title=title,
            target_amount=float(target_amount),
            current_amount=0.0,
            category=category
        )
        db.session.add(new_goal)
        db.session.commit()
        flash('Nowy cel oszczędnościowy został dodany!', 'success')
    except ValueError:
        flash('Kwota docelowa musi być liczbą!', 'error')
        
    return redirect(url_for('index'))

# 3. Szczegóły celu i zarządzanie wpłatami (READ cel + READ/CREATE wpłaty)
@app.route('/goal/<int:goal_id>')
def goal_detail(goal_id):
    goal = Goal.query.get_or_404(goal_id)
    return render_template('detail.html', goal=goal)

# 4. Edycja celu oszczędnościowego (UPDATE)
@app.route('/goal/edit/<int:goal_id>', methods=['POST'])
def edit_goal(goal_id):
    goal = Goal.query.get_or_404(goal_id)
    goal.title = request.form.get('title')
    target_amount = request.form.get('target_amount')
    goal.category = request.form.get('category')

    if not goal.title or not target_amount:
        flash('Pola tytułu i kwoty nie mogą być puste!', 'error')
        return redirect(url_for('goal_detail', goal_id=goal_id))

    try:
        goal.target_amount = float(target_amount)
        db.session.commit()
        flash('Cel został pomyślnie zaktualizowany!', 'success')
    except ValueError:
        flash('Kwota docelowa musi być prawidłową liczbą!', 'error')

    return redirect(url_for('goal_detail', goal_id=goal_id))

# 5. Usuwanie celu oszczędnościowego (DELETE)
@app.route('/goal/delete/<int:goal_id>')
def delete_goal(goal_id):
    goal = Goal.query.get_or_404(goal_id)
    db.session.delete(goal)
    db.session.commit()
    flash('Cel oszczędnościowy został usunięty.', 'info')
    return redirect(url_for('index'))

# 6. Dodawanie wpłaty do celu (CREATE dla Payment + UPDATE dla Goal)
@app.route('/goal/<int:goal_id>/payment', methods=['POST'])
def add_payment(goal_id):
    goal = Goal.query.get_or_404(goal_id)
    amount = request.form.get('amount')
    date_added = request.form.get('date_added')
    description = request.form.get('description', '')

    if not amount or not date_added:
        flash('Kwota wpłaty oraz data są wymagane!', 'error')
        return redirect(url_for('goal_detail', goal_id=goal_id))

    try:
        payment_amount = float(amount)
        if payment_amount <= 0:
            flash('Kwota wpłaty musi być większa od zera!', 'error')
            return redirect(url_for('goal_detail', goal_id=goal_id))

        # Rejestracja nowej wpłaty
        new_payment = Payment(
            amount=payment_amount,
            date_added=date_added,
            description=description,
            goal_id=goal.id
        )
        # Aktualizacja stanu konta w celu (Real-time recalculation)
        goal.current_amount += payment_amount
        
        db.session.add(new_payment)
        db.session.commit()
        flash('Wpłata została zarejestrowana!', 'success')
    except ValueError:
        flash('Wprowadzona kwota wpłaty jest nieprawidłowa!', 'error')

    return redirect(url_for('goal_detail', goal_id=goal_id))

# 7. Usuwanie pojedynczej wpłaty (DELETE dla Payment + UPDATE dla Goal)
@app.route('/payment/delete/<int:payment_id>')
def delete_payment(payment_id):
    payment = Payment.query.get_or_404(payment_id)
    goal = Goal.query.get(payment.goal_id)
    
    # Cofnięcie kwoty z konta celu oszczędnościowego
    goal.current_amount -= payment.amount
    if goal.current_amount < 0:
        goal.current_amount = 0.0

    db.session.delete(payment)
    db.session.commit()
    flash('Wpłata została wycofana.', 'info')
    return redirect(url_for('goal_detail', goal_id=goal.id))


# INTELIGENTNY PUNKT STARTOWY:
if __name__ == '__main__':
    with app.app_context():
        db.create_all()  # Tworzy bazę lokalną przy pierwszym uruchomieniu
        
    # Sprawdza czy aplikacja działa w chmurze (Render/Heroku definiują port środowiskowy)
    # Jeśli działasz lokalnie na Macu, uruchomi serwer z parametrem debug=True i portem 5000.
    port = int(os.environ.get("PORT", 5000))
    is_production = "PORT" in os.environ
    
    app.run(host='0.0.0.0', port=port, debug=not is_production)
