from flask import Flask, render_template, request, redirect, url_for, session, flash, Response
import mysql.connector
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from functools import wraps
import os, csv, io

app = Flask(__name__)
app.secret_key = "change-this-in-production"

DB_CONFIG = {
    "host": "localhost",
    "user": "root",
    "password": "1234",
    "database": "food_order",
}

UPLOAD_FOLDER = os.path.join("static", "uploads")
ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif", "webp"}
os.makedirs(UPLOAD_FOLDER, exist_ok=True)


def get_db():
    return mysql.connector.connect(**DB_CONFIG)


def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def save_image(file):
    if file and file.filename and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        file.save(os.path.join(UPLOAD_FOLDER, filename))
        return filename
    return None


def login_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if "admin_id" not in session:
            flash("Please log in first.", "error")
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return wrapper


# ---------- CUSTOMER ----------

@app.route("/")
def index():
    db = get_db()
    cur = db.cursor(dictionary=True)
    cur.execute("SELECT * FROM menu WHERE available = 1 ORDER BY id DESC")
    menu = cur.fetchall()
    cur.execute("""
        SELECT r.*, m.name AS menu_name
        FROM reviews r JOIN menu m ON r.menu_id = m.id
        ORDER BY r.created_at DESC LIMIT 20
    """)
    reviews = cur.fetchall()
    cur.close(); db.close()
    return render_template("index.html", menu=menu, reviews=reviews)


@app.route("/order", methods=["POST"])
def place_order():
    name = request.form.get("customer_name", "").strip()
    phone = request.form.get("customer_phone", "").strip()
    menu_id = request.form.get("menu_id")
    qty = int(request.form.get("quantity", 1))
    notes = request.form.get("notes", "").strip()
    if not (name and phone and menu_id and qty > 0):
        flash("Please fill all required fields.", "error")
        return redirect(url_for("index"))
    db = get_db()
    cur = db.cursor()
    cur.execute(
        "INSERT INTO orders (customer_name, customer_phone, menu_id, quantity, notes) VALUES (%s,%s,%s,%s,%s)",
        (name, phone, menu_id, qty, notes),
    )
    db.commit()
    cur.close(); db.close()
    flash("Order placed. Thank you!", "success")
    return redirect(url_for("index"))


@app.route("/review", methods=["POST"])
def leave_review():
    name = request.form.get("customer_name", "").strip()
    menu_id = request.form.get("menu_id")
    rating = int(request.form.get("rating", 5))
    comment = request.form.get("comment", "").strip()
    if not (name and menu_id and 1 <= rating <= 5):
        flash("Invalid review.", "error")
        return redirect(url_for("index"))
    db = get_db()
    cur = db.cursor()
    cur.execute(
        "INSERT INTO reviews (customer_name, menu_id, rating, comment) VALUES (%s,%s,%s,%s)",
        (name, menu_id, rating, comment),
    )
    db.commit()
    cur.close(); db.close()
    flash("Thanks for your review!", "success")
    return redirect(url_for("index"))


# ---------- ADMIN ----------

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        db = get_db()
        cur = db.cursor(dictionary=True)
        cur.execute("SELECT * FROM admin WHERE username=%s", (username,))
        admin = cur.fetchone()
        cur.close(); db.close()
        if admin and check_password_hash(admin["password_hash"], password):
            session["admin_id"] = admin["id"]
            session["admin_username"] = admin["username"]
            return redirect(url_for("admin_dashboard"))
        flash("Wrong username or password.", "error")
    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("index"))


@app.route("/admin")
@login_required
def admin_dashboard():
    db = get_db()
    cur = db.cursor(dictionary=True)
    cur.execute("SELECT * FROM menu ORDER BY id DESC")
    menu = cur.fetchall()
    cur.execute("""
        SELECT o.*, m.name AS menu_name, m.price
        FROM orders o JOIN menu m ON o.menu_id = m.id
        ORDER BY o.created_at DESC LIMIT 50
    """)
    orders = cur.fetchall()
    cur.execute("SELECT id, username FROM admin ORDER BY id")
    admins = cur.fetchall()
    cur.close(); db.close()
    return render_template("admin.html", menu=menu, orders=orders, admins=admins)


@app.route("/admin/menu/add", methods=["POST"])
@login_required
def add_menu():
    name = request.form.get("name", "").strip()
    description = request.form.get("description", "").strip()
    price = request.form.get("price")
    available = 1 if request.form.get("available") else 0
    image = save_image(request.files.get("image"))
    db = get_db()
    cur = db.cursor()
    cur.execute(
        "INSERT INTO menu (name, description, price, available, image) VALUES (%s,%s,%s,%s,%s)",
        (name, description, price, available, image),
    )
    db.commit()
    cur.close(); db.close()
    flash("Menu item added.", "success")
    return redirect(url_for("admin_dashboard"))


@app.route("/admin/menu/edit/<int:item_id>", methods=["POST"])
@login_required
def edit_menu(item_id):
    name = request.form.get("name", "").strip()
    description = request.form.get("description", "").strip()
    price = request.form.get("price")
    available = 1 if request.form.get("available") else 0
    new_image = save_image(request.files.get("image"))
    db = get_db()
    cur = db.cursor()
    if new_image:
        cur.execute(
            "UPDATE menu SET name=%s, description=%s, price=%s, available=%s, image=%s WHERE id=%s",
            (name, description, price, available, new_image, item_id),
        )
    else:
        cur.execute(
            "UPDATE menu SET name=%s, description=%s, price=%s, available=%s WHERE id=%s",
            (name, description, price, available, item_id),
        )
    db.commit()
    cur.close(); db.close()
    flash("Menu updated.", "success")
    return redirect(url_for("admin_dashboard"))


@app.route("/admin/menu/delete/<int:item_id>", methods=["POST"])
@login_required
def delete_menu(item_id):
    db = get_db()
    cur = db.cursor()
    cur.execute("DELETE FROM menu WHERE id=%s", (item_id,))
    db.commit()
    cur.close(); db.close()
    flash("Menu deleted.", "success")
    return redirect(url_for("admin_dashboard"))


@app.route("/admin/order/<int:order_id>/<status>", methods=["POST"])
@login_required
def update_order(order_id, status):
    if status not in ("pending", "done", "cancelled"):
        return redirect(url_for("admin_dashboard"))
    db = get_db()
    cur = db.cursor()
    cur.execute("UPDATE orders SET status=%s WHERE id=%s", (status, order_id))
    db.commit()
    cur.close(); db.close()
    return redirect(url_for("admin_dashboard"))


@app.route("/admin/create-admin", methods=["POST"])
@login_required
def create_admin():
    username = request.form.get("username", "").strip()
    password = request.form.get("password", "")
    if not (username and password):
        flash("Username and password required.", "error")
        return redirect(url_for("admin_dashboard"))
    db = get_db()
    cur = db.cursor()
    try:
        cur.execute(
            "INSERT INTO admin (username, password_hash) VALUES (%s,%s)",
            (username, generate_password_hash(password)),
        )
        db.commit()
        flash(f"Admin '{username}' created.", "success")
    except mysql.connector.errors.IntegrityError:
        flash(f"Username '{username}' already exists.", "error")
    cur.close(); db.close()
    return redirect(url_for("admin_dashboard"))


@app.route("/admin/delete-admin/<int:admin_id>", methods=["POST"])
@login_required
def delete_admin(admin_id):
    if admin_id == session["admin_id"]:
        flash("You cannot delete yourself.", "error")
        return redirect(url_for("admin_dashboard"))
    db = get_db()
    cur = db.cursor()
    cur.execute("DELETE FROM admin WHERE id=%s", (admin_id,))
    db.commit()
    cur.close(); db.close()
    flash("Admin deleted.", "success")
    return redirect(url_for("admin_dashboard"))


@app.route("/admin/export-orders")
@login_required
def export_orders():
    db = get_db()
    cur = db.cursor(dictionary=True)
    cur.execute("""
        SELECT o.id, o.customer_name, o.customer_phone, m.name AS item,
               o.quantity, m.price, (o.quantity * m.price) AS total,
               o.notes, o.status, o.created_at
        FROM orders o JOIN menu m ON o.menu_id = m.id
        ORDER BY o.created_at DESC
    """)
    orders = cur.fetchall()
    cur.close(); db.close()

    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=["id","customer_name","customer_phone","item","quantity","price","total","notes","status","created_at"])
    writer.writeheader()
    writer.writerows(orders)

    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=orders.csv"}
    )


@app.cli.command("init-admin")
def init_admin():
    db = get_db()
    cur = db.cursor()
    pwd = generate_password_hash("admin123")
    try:
        cur.execute("INSERT INTO admin (username, password_hash) VALUES (%s,%s)", ("admin", pwd))
        db.commit()
        print("Default admin created -> username: admin, password: admin123")
    except mysql.connector.errors.IntegrityError:
        print("Admin user already exists.")
    cur.close(); db.close()


if __name__ == "__main__":
    app.run(debug=True)