import os
from flask import Flask, render_template, request, redirect, url_for, flash, session
from dotenv import load_dotenv
import mysql.connector

# Load local .env file if it exists (for local development)
load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "fallback-default-secret-key-2026")

# Dynamic database configuration pointing directly to Aiven.io via Render Environment Variables
DB_CONFIG = {
    "host": os.getenv("DB_HOST"),
    "port": int(os.getenv("DB_PORT") or 20890),
    "user": os.getenv("DB_USER"),
    "password": os.getenv("DB_PASSWORD"),
    "database": os.getenv("DB_NAME")
}

def init_db():
    """Automatically connects to Aiven.io and builds tables if they don't exist yet."""
    try:
        db = mysql.connector.connect(**DB_CONFIG)
        cur = db.cursor()
        
        # 1. Admin Table
        cur.execute("""
        CREATE TABLE IF NOT EXISTS admin (
            id INT AUTO_INCREMENT PRIMARY KEY, 
            username VARCHAR(100) UNIQUE NOT NULL, 
            password_hash VARCHAR(255) NOT NULL
        )""")
        
        # 2. Menu Table
        cur.execute("""
        CREATE TABLE IF NOT EXISTS menu (
            id INT AUTO_INCREMENT PRIMARY KEY, 
            name VARCHAR(255) NOT NULL, 
            description TEXT, 
            price DECIMAL(10,2) NOT NULL, 
            available TINYINT(1) DEFAULT 1, 
            image VARCHAR(255)
        )""")
        
        # 3. Orders Table
        cur.execute("""
        CREATE TABLE IF NOT EXISTS orders (
            id INT AUTO_INCREMENT PRIMARY KEY, 
            customer_name VARCHAR(255) NOT NULL, 
            customer_phone VARCHAR(50) NOT NULL, 
            menu_id INT, 
            quantity INT NOT NULL DEFAULT 1, 
            notes TEXT, 
            status VARCHAR(50) DEFAULT 'pending', 
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, 
            FOREIGN KEY (menu_id) REFERENCES menu(id) ON DELETE CASCADE
        )""")
        
        # 4. Reviews Table
        cur.execute("""
        CREATE TABLE IF NOT EXISTS reviews (
            id INT AUTO_INCREMENT PRIMARY KEY, 
            customer_name VARCHAR(255) NOT NULL, 
            menu_id INT, 
            rating INT NOT NULL, 
            comment TEXT, 
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, 
            FOREIGN KEY (menu_id) REFERENCES menu(id) ON DELETE CASCADE
        )""")
        
        db.commit()
        cur.close()
        db.close()
        print("Database tables verified/initialized successfully on Aiven.io!")
    except Exception as e:
        print(f"Error during database initialization: {e}")

# Run table builder before the web engine handles requests
init_db()

def get_db():
    """Generates a fresh database connection for web requests."""
    return mysql.connector.connect(**DB_CONFIG)

@app.route('/')
def index():
    try:
        db = get_db()
        cur = db.cursor(dictionary=True)
        cur.execute("SELECT * FROM menu WHERE available = 1 ORDER BY id DESC")
        items = cur.fetchall()
        cur.close()
        db.close()
        return render_template('index.html', items=items)
    except Exception as e:
        return f"Database Query Error: {e}", 500

@app.route('/order', methods=['POST'])
def place_order():
    customer_name = request.form.get('customer_name')
    customer_phone = request.form.get('customer_phone')
    menu_id = request.form.get('menu_id')
    quantity = request.form.get('quantity', 1)
    notes = request.form.get('notes', '')

    if not customer_name or not customer_phone or not menu_id:
        flash("Please fill in all required order details.", "danger")
        return redirect(url_for('index'))

    try:
        db = get_db()
        cur = db.cursor()
        cur.execute(
            "INSERT INTO orders (customer_name, customer_phone, menu_id, quantity, notes) VALUES (%s, %s, %s, %s, %s)",
            (customer_name, customer_phone, menu_id, quantity, notes)
        )
        db.commit()
        cur.close()
        db.close()
        flash("Order placed successfully!", "success")
    except Exception as e:
        flash(f"Failed to place order: {e}", "danger")
        
    return redirect(url_for('index'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        # Simple plain-text check for practice app (Replace with real hashing logic if needed)
        if username == "admin" and password == "admin123":
            session['logged_in'] = True
            return redirect(url_for('admin_dashboard'))
        else:
            flash("Invalid credentials, try again.", "danger")
            
    return render_template('login.html')

@app.route('/admin')
def admin_dashboard():
    if not session.get('logged_in'):
        return redirect(url_for('login'))
        
    try:
        db = get_db()
        cur = db.cursor(dictionary=True)
        cur.execute("SELECT orders.*, menu.name as item_name FROM orders LEFT JOIN menu ON orders.menu_id = menu.id ORDER BY orders.id DESC")
        orders = cur.fetchall()
        cur.close()
        db.close()
        return render_template('admin.html', orders=orders)
    except Exception as e:
        return f"Admin Loading Error: {e}", 500

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))

if __name__ == '__main__':
    # Local fallback port for standard computer running
    app.run(host='0.0.0.0', port=int(os.getenv("PORT", 5000)), debug=True)
