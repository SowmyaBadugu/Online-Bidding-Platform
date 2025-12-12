from flask import Flask, request, jsonify, send_from_directory, session
from flask_cors import CORS
import mysql.connector
from mysql.connector import Error
from datetime import datetime, timedelta
import hashlib
import secrets
import os

app = Flask(__name__, static_folder='static')
app.secret_key = secrets.token_hex(16)  # Generate random secret key
CORS(app, supports_credentials=True)

# Database configuration
DB_CONFIG = {
    'host': 'localhost',
    'user': 'root',
    'password': 'sowmya2004',  # Change this
    'database': 'bidding_system'
}

def get_db_connection():
    try:
        conn = mysql.connector.connect(**DB_CONFIG)
        return conn
    except Error as e:
        print(f"Error: {e}")
        return None

def hash_password(password):
    """Hash password using SHA-256"""
    return hashlib.sha256(password.encode()).hexdigest()

def init_db():
    conn = get_db_connection()
    if conn:
        cursor = conn.cursor()
        
        cursor.execute("CREATE DATABASE IF NOT EXISTS bidding_system")
        cursor.execute("USE bidding_system")
        
        # Create users table with password
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INT AUTO_INCREMENT PRIMARY KEY,
                username VARCHAR(50) UNIQUE NOT NULL,
                email VARCHAR(100) UNIQUE NOT NULL,
                password VARCHAR(255) NOT NULL,
                full_name VARCHAR(100),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Create items table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS items (
                id INT AUTO_INCREMENT PRIMARY KEY,
                title VARCHAR(200) NOT NULL,
                description TEXT,
                starting_price DECIMAL(10, 2) NOT NULL,
                current_price DECIMAL(10, 2) NOT NULL,
                image_url VARCHAR(500),
                end_time DATETIME NOT NULL,
                seller_id INT,
                status ENUM('active', 'closed') DEFAULT 'active',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (seller_id) REFERENCES users(id)
            )
        """)
        
        # Create bids table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS bids (
                id INT AUTO_INCREMENT PRIMARY KEY,
                item_id INT NOT NULL,
                user_id INT NOT NULL,
                bid_amount DECIMAL(10, 2) NOT NULL,
                bid_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (item_id) REFERENCES items(id),
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
        """)
        
        conn.commit()
        cursor.close()
        conn.close()
        print("Database initialized successfully")

# Authentication Routes
@app.route('/api/auth/signup', methods=['POST'])
def signup():
    data = request.json
    conn = get_db_connection()
    if not conn:
        return jsonify({'error': 'Database connection failed'}), 500
    
    cursor = conn.cursor()
    try:
        hashed_password = hash_password(data['password'])
        cursor.execute(
            "INSERT INTO users (username, email, password, full_name) VALUES (%s, %s, %s, %s)",
            (data['username'], data['email'], hashed_password, data.get('full_name', ''))
        )
        conn.commit()
        user_id = cursor.lastrowid
        
        # Create session
        session['user_id'] = user_id
        session['username'] = data['username']
        
        return jsonify({
            'message': 'User created successfully',
            'user': {
                'id': user_id,
                'username': data['username'],
                'email': data['email']
            }
        }), 201
    except Error as e:
        return jsonify({'error': str(e)}), 400
    finally:
        cursor.close()
        conn.close()

@app.route('/api/auth/login', methods=['POST'])
def login():
    data = request.json
    conn = get_db_connection()
    if not conn:
        return jsonify({'error': 'Database connection failed'}), 500
    
    cursor = conn.cursor(dictionary=True)
    try:
        hashed_password = hash_password(data['password'])
        cursor.execute(
            "SELECT id, username, email, full_name FROM users WHERE username = %s AND password = %s",
            (data['username'], hashed_password)
        )
        user = cursor.fetchone()
        
        if user:
            # Create session
            session['user_id'] = user['id']
            session['username'] = user['username']
            
            return jsonify({
                'message': 'Login successful',
                'user': user
            }), 200
        else:
            return jsonify({'error': 'Invalid username or password'}), 401
    finally:
        cursor.close()
        conn.close()

@app.route('/api/auth/logout', methods=['POST'])
def logout():
    session.clear()
    return jsonify({'message': 'Logged out successfully'}), 200

@app.route('/api/auth/check', methods=['GET'])
def check_auth():
    if 'user_id' in session:
        return jsonify({
            'authenticated': True,
            'user': {
                'id': session['user_id'],
                'username': session['username']
            }
        }), 200
    return jsonify({'authenticated': False}), 200

# Protected route decorator
def login_required(f):
    def wrapper(*args, **kwargs):
        if 'user_id' not in session:
            return jsonify({'error': 'Authentication required'}), 401
        return f(*args, **kwargs)
    wrapper.__name__ = f.__name__
    return wrapper

# Routes
@app.route('/')
def index():
    return send_from_directory('static', 'index.html')

@app.route('/api/users', methods=['GET'])
def get_users():
    conn = get_db_connection()
    if not conn:
        return jsonify({'error': 'Database connection failed'}), 500
    
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT id, username, email, full_name FROM users")
    users = cursor.fetchall()
    cursor.close()
    conn.close()
    return jsonify(users)

@app.route('/api/items', methods=['POST'])
@login_required
def create_item():
    data = request.json
    conn = get_db_connection()
    if not conn:
        return jsonify({'error': 'Database connection failed'}), 500
    
    cursor = conn.cursor()
    try:
        end_time = datetime.now() + timedelta(hours=int(data.get('duration', 24)))
        cursor.execute(
            """INSERT INTO items (title, description, starting_price, 
               current_price, image_url, end_time, seller_id) 
               VALUES (%s, %s, %s, %s, %s, %s, %s)""",
            (data['title'], data['description'], data['starting_price'],
             data['starting_price'], data.get('image_url', ''), 
             end_time, session['user_id'])
        )
        conn.commit()
        item_id = cursor.lastrowid
        return jsonify({'id': item_id, 'message': 'Item created successfully'}), 201
    except Error as e:
        return jsonify({'error': str(e)}), 400
    finally:
        cursor.close()
        conn.close()

@app.route('/api/items', methods=['GET'])
def get_items():
    conn = get_db_connection()
    if not conn:
        return jsonify({'error': 'Database connection failed'}), 500
    
    cursor = conn.cursor(dictionary=True)
    cursor.execute("""
        SELECT i.*, u.username as seller_name,
        (SELECT COUNT(*) FROM bids WHERE item_id = i.id) as bid_count
        FROM items i
        LEFT JOIN users u ON i.seller_id = u.id
        WHERE i.status = 'active' AND i.end_time > NOW()
        ORDER BY i.created_at DESC
    """)
    items = cursor.fetchall()
    
    for item in items:
        if item['end_time']:
            item['end_time'] = item['end_time'].isoformat()
        if item['created_at']:
            item['created_at'] = item['created_at'].isoformat()
    
    cursor.close()
    conn.close()
    return jsonify(items)

@app.route('/api/items/<int:item_id>', methods=['GET'])
def get_item(item_id):
    conn = get_db_connection()
    if not conn:
        return jsonify({'error': 'Database connection failed'}), 500
    
    cursor = conn.cursor(dictionary=True)
    cursor.execute("""
        SELECT i.*, u.username as seller_name
        FROM items i
        LEFT JOIN users u ON i.seller_id = u.id
        WHERE i.id = %s
    """, (item_id,))
    item = cursor.fetchone()
    
    if item:
        cursor.execute("""
            SELECT b.*, u.username 
            FROM bids b
            JOIN users u ON b.user_id = u.id
            WHERE b.item_id = %s
            ORDER BY b.bid_amount DESC
            LIMIT 10
        """, (item_id,))
        bids = cursor.fetchall()
        item['bids'] = bids
        
        if item['end_time']:
            item['end_time'] = item['end_time'].isoformat()
    
    cursor.close()
    conn.close()
    return jsonify(item) if item else jsonify({'error': 'Item not found'}), 404

@app.route('/api/bids', methods=['POST'])
@login_required
def place_bid():
    data = request.json
    conn = get_db_connection()
    if not conn:
        return jsonify({'error': 'Database connection failed'}), 500
    
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute("SELECT current_price, end_time FROM items WHERE id = %s", 
                      (data['item_id'],))
        item = cursor.fetchone()
        
        if not item:
            return jsonify({'error': 'Item not found'}), 404
        
        if datetime.now() > item['end_time']:
            return jsonify({'error': 'Auction has ended'}), 400
        
        if float(data['bid_amount']) <= float(item['current_price']):
            return jsonify({'error': 'Bid must be higher than current price'}), 400
        
        cursor.execute(
            "INSERT INTO bids (item_id, user_id, bid_amount) VALUES (%s, %s, %s)",
            (data['item_id'], session['user_id'], data['bid_amount'])
        )
        
        cursor.execute(
            "UPDATE items SET current_price = %s WHERE id = %s",
            (data['bid_amount'], data['item_id'])
        )
        
        conn.commit()
        return jsonify({'message': 'Bid placed successfully'}), 201
    except Error as e:
        conn.rollback()
        return jsonify({'error': str(e)}), 400
    finally:
        cursor.close()
        conn.close()

if __name__ == '__main__':
    init_db()
    app.run(debug=True, port=5000)