from flask import Flask, request, jsonify, render_template, redirect, url_for, current_app
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from models import db, User, Payment 
from datetime import datetime, timedelta
from flask_migrate import Migrate
import stripe
import os
from openai import OpenAI 


app = Flask(__name__)
app.config['SECRET_KEY'] = 'youpieceofshit'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///eqai.db'
app.config['STRIPE_SECRET_KEY'] = 'sk_test_51PcdKRLjkkNKzIGfSXuiOqFYeOlUro8MdIKsA0GUw7zFlt2EC7PMbKA8r1PUwLpMgiENGDfRkEPwvb6G1fNW92hk00WX8LoPn3'
app.config['OPENAI_API_KEY'] = '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'
db.init_app(app)
login_manager = LoginManager(app)

stripe.api_key = app.config['STRIPE_SECRET_KEY']
client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(user_id)

# Custom filter to format datetime
@app.template_filter('datetime_format')
def datetime_format(value):
    return value.strftime('%Y-%m-%d %H:%Mhr')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        email = request.form['email']
        password = request.form['password']
        
        if User.query.filter_by(email=email).first():
            return jsonify({'error': 'Email already registered'}), 400

        new_user = User(username=username, email=email)
        new_user.set_password(password)
        db.session.add(new_user)
        db.session.commit()
        
        login_user(new_user)
        return redirect(url_for('dashboard'))
    
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        
        user = User.query.filter_by(email=email).first()
        if user and user.check_password(password):
            login_user(user)
            if not current_user.has_active_subscription() and current_user.credits < 2:
                return redirect(url_for('dashboard'))
            return redirect(url_for('text_exchange'))
        
        return jsonify({'error': 'Invalid credentials'}), 400
    
    return render_template('login.html')

@app.route('/')
def index():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    else:
        return redirect(url_for('login'))

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

@app.route('/dashboard')
@login_required
def dashboard():
    return render_template('dashboard.html', user=current_user)

@app.route('/purchase', methods=['POST'])
@login_required
def purchase():
    try:
        data = request.json
        plan = data.get('plan')
        
        if plan == 'basic':
            amount = 3.99
            credits = 50
        elif plan == 'popular':
            amount = 5.99
            credits = 100
        elif plan == 'weekly':
            amount = 9.99
            credits = None 
        
        # Create a Stripe payment session
        session = stripe.checkout.Session.create(
            payment_method_types=['card'],
            line_items=[{
                'price_data': {
                    'currency': 'usd',
                    'product_data': {
                        'name': plan,
                    },
                    'unit_amount': int(amount * 100),
                },
                'quantity': 1,
            }],
            mode='payment',
            success_url=url_for('payment_success', plan=plan, _external=True),
            cancel_url=url_for('dashboard', _external=True),
        )
        
        return jsonify({'session_id': session.id})
    except Exception as e:
        current_app.logger.error(f"Error in /purchase: {e}")
        return jsonify({'error': 'An error occurred during the purchase process'}), 500

@app.route('/payment_success')
@login_required
def payment_success():
    try:
        plan = request.args.get('plan')
        current_app.logger.info(f"Plan: {plan}")  # Debugging statement
        
        if plan == 'basic':
            credits = 50
        elif plan == 'popular':
            credits = 100
        elif plan == 'weekly':
            current_user.subscription_end = datetime.utcnow() + timedelta(days=7)
            credits = 0
        else:
            credits = 0  # Default if the plan is not recognized

        current_app.logger.info(f"Credits before update: {current_user.credits}")  # Debugging statement
        
        if credits != 0:  # Only add credits if they are not zero
            current_user.credits += credits
        
        db.session.commit()

        current_app.logger.info(f"Credits after update: {current_user.credits}")  # Debugging statement
        current_app.logger.info(f"Subscription end date: {current_user.subscription_end}")  # Debugging statement
        
        return redirect(url_for('text_exchange'))
    except Exception as e:
        current_app.logger.error(f"Error in /payment_success: {e}")
        return jsonify({'error': 'An error occurred during the payment process'}), 500


'''
Main features which are the text generation components
'''

@app.route('/text_exchange')
@login_required
def text_exchange():
    return render_template('text_exchange.html', user=current_user)

@app.route('/generate_empathetic_text', methods=['POST'])
@login_required
def generate_empathetic_text():
    if not current_user.has_active_subscription() and current_user.credits < 2:
        return jsonify({'error': 'Not enough credits'}), 402
    
    data = request.json
    context = data.get('context')
    message = data.get('message')
    tone = data.get('tone')

    prompt = f"Context: {context}\nMessage: {message}\nTone: {tone}"

    response = client.chat.completions.create(
        model="gpt-3.5-turbo",
        messages=[
            {"role": "system", "content": "You are an empathetic assistant."},
            {"role": "user", "content": prompt}
        ],
        max_tokens=150
    )

    # Debugging: Print the response structure
    current_app.logger.info(f"OpenAI Response: {response}")

    if not current_user.has_active_subscription():
        current_user.credits -= 2
        db.session.commit()

    return jsonify(response.choices[0].message.content)


@app.route('/generate_flirty_text', methods=['POST'])
@login_required
def generate_flirty_text():
    if not current_user.has_active_subscription() and current_user.credits < 2:
        return jsonify({'error': 'Not enough credits'}), 402
    
    data = request.json
    persona = data.get('persona')
    message = data.get('message')

    prompt = f"Persona: {persona}\nMessage: {message}"

    response = client.chat.completions.create(
        model="gpt-3.5-turbo",
        messages=[
            {"role": "system", "content": "You are a love specialist and an expert in flirting. You have read a lot of charming love books and had a lot of love experiences. Given a text message, come up with the most charming and flirty response to it."},
            {"role": "user", "content": prompt}
        ],
        max_tokens=150
    )

    # Debugging: Print the response structure
    current_app.logger.info(f"OpenAI Response: {response}")

    if not current_user.has_active_subscription():
        current_user.credits -= 2
        db.session.commit()

    return jsonify(response.choices[0].message.content)



if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True)

