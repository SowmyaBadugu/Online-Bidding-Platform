from flask import Flask, request, jsonify, session
from flask_cors import CORS
import mysql.connector
from datetime import datetime, timedelta
import os

app = Flask(__name__)
app.secret_key = "supersecretkey123"  # change for production

# Allow frontend to access backend with cookies
CORS(app, supports_credentials=True)


# ---------------------------------------------------------
# DATABASE CONNECTION
# ---------------------------------------------------------
def get_db_connection():
    try:
        return mysql.connector.connect(
            'host': 'localhost',
            'user': 'root',
            'password': 'sowmya2004',  # Change this
            'database': 'bidding_system'
        )
    except Exception as e:
        print("DB connection error:", e)
        return None


# ---------------------------------------------------------
# AUTH ROUTES
# ---------------------------------------------------------
@app.route("/api/auth/signup", methods=["POST"])
def signup():
    data = request.json

    conn = get_db_connection()
    if not conn:
        return jsonify({"error": "Database connection failed"}), 500

    cursor = conn.cursor(dictionary=True)

    # Check if username exists
    cursor.execute("SELECT * FROM users WHERE username=%s", (data["username"],))
    if cursor.fetchone():
        return jsonify({"error": "Username already exists"}), 400

    cursor.execute(
        "INSERT INTO users(full_name, username, email, password) VALUES (%s, %s, %s, %s)",
        (data["full_name"], data["username"], data["email"], data["password"])
    )
    conn.commit()

    session["username"] = data["username"]

    return jsonify({"user": {"username": data["username"]}})


@app.route("/api/auth/login", methods=["POST"])
def login():
    data = request.json

    conn = get_db_connection()
    if not conn:
        return jsonify({"error": "Database connection failed"}), 500

    cursor = conn.cursor(dictionary=True)

    cursor.execute(
        "SELECT * FROM users WHERE username=%s AND password=%s",
        (data["username"], data["password"])
    )
    user = cursor.fetchone()

    if not user:
        return jsonify({"error": "Invalid username or password"}), 400

    session["username"] = user["username"]

    return jsonify({"user": {"username": user["username"]}})


@app.route("/api/auth/logout", methods=["POST"])
def logout():
    session.clear()
    return jsonify({"message": "Logged out"})


@app.route("/api/auth/check")
def check_auth():
    if "username" in session:
        return jsonify({
            "authenticated": True,
            "user": {"username": session["username"]}
        })
    return jsonify({"authenticated": False})


# ---------------------------------------------------------
# MIDDLEWARE: REQUIRE LOGIN
# ---------------------------------------------------------
def require_login():
    if "username" not in session:
        return {"error": "Unauthorized"}, 401
    return None


# ---------------------------------------------------------
# ITEMS ROUTES
# ---------------------------------------------------------
@app.route("/api/items", methods=["GET"])
def list_items():
    conn = get_db_connection()
    if not conn:
        return jsonify([])

    cursor = conn.cursor(dictionary=True)
    cursor.execute("""
        SELECT id, title, description, starting_price AS current_price,
               image_url, end_time,
               (SELECT COUNT(*) FROM bids WHERE item_id = items.id) AS bid_count
        FROM items
        ORDER BY end_time DESC
    """)

    items = cursor.fetchall()
    return jsonify(items)


@app.route("/api/items", methods=["POST"])
def create_item():
    check = require_login()
    if check:
        return check

    data = request.json

    conn = get_db_connection()
    if not conn:
        return jsonify({"error": "Database connection failed"}), 500

    cursor = conn.cursor()

    duration_hours = int(data["duration"])

    cursor.execute("""
        INSERT INTO items(title, description, starting_price, image_url, end_time)
        VALUES (%s, %s, %s, %s, DATE_ADD(NOW(), INTERVAL %s HOUR))
    """, (data["title"], data["description"], data["starting_price"],
          data["image_url"], duration_hours))

    conn.commit()
    return jsonify({"message": "Item created successfully"})


# ---------------------------------------------------------
# BID ROUTE
# ---------------------------------------------------------
@app.route("/api/bids", methods=["POST"])
def place_bid():
    check = require_login()
    if check:
        return check

    data = request.json

    conn = get_db_connection()
    if not conn:
        return jsonify({"error": "Database connection failed"}), 500

    cursor = conn.cursor(dictionary=True)

    # Check item info
    cursor.execute(
        "SELECT starting_price AS current_price, end_time FROM items WHERE id=%s",
        (data["item_id"],)
    )
    item = cursor.fetchone()

    if not item:
        return jsonify({"error": "Item not found"}), 404

    if datetime.now() > item["end_time"]:
        return jsonify({"error": "Auction ended"}), 400

    # Check bid amount
    bid_amount = float(data["bid_amount"])
    if bid_amount <= float(item["current_price"]):
        return jsonify({"error": "Bid must be higher than current price"}), 400

    cursor.execute(
        "INSERT INTO bids(item_id, username, bid_amount, bid_time) VALUES (%s, %s, %s, NOW())",
        (data["item_id"], session["username"], bid_amount)
    )

    # Update item current price
    cursor.execute(
        "UPDATE items SET starting_price=%s WHERE id=%s",
        (bid_amount, data["item_id"])
    )

    conn.commit()

    return jsonify({"message": "Bid placed successfully"})


# ---------------------------------------------------------
# RENDER DEPLOYMENT SUPPORT
# ---------------------------------------------------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
