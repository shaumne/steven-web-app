"""
Authentication module for the trading bot dashboard
"""
import os
import json
import hashlib
import logging
from functools import wraps
from datetime import datetime
from flask import session, redirect, url_for, request, flash

logger = logging.getLogger(__name__)

# Path to users file
USERS_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'users.json')

def hash_password(password):
    """Hash a password using SHA-256"""
    return hashlib.sha256(password.encode()).hexdigest()

def verify_password(username, password):
    """Verify a password for a given username"""
    try:
        with open(USERS_FILE, 'r') as f:
            users = json.load(f)
            
        if username in users:
            stored_hash = users[username]['password']
            return stored_hash == hash_password(password)
    except Exception as e:
        logger.error(f"Error verifying password: {e}")
    
    return False

def init_users_file():
    """Initialize the users file if it doesn't exist"""
    if not os.path.exists(USERS_FILE):
        default_users = {
            "admin": {
                "password": hash_password("admin"),
                "role": "admin",
                "last_login": None,
                "login_count": 0
            }
        }
        try:
            with open(USERS_FILE, 'w') as f:
                json.dump(default_users, f, indent=4)
            logger.info("Created default users file")
        except Exception as e:
            logger.error(f"Error creating users file: {e}")

def get_users():
    """Get all users from the users file"""
    try:
        if not os.path.exists(USERS_FILE):
            init_users_file()
            
        with open(USERS_FILE, 'r') as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Failed to read users file: {e}")
        return {}

def update_last_login(username):
    """Update user's last login time and login count"""
    try:
        users = get_users()
        if username in users:
            users[username]['last_login'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            users[username]['login_count'] = users[username].get('login_count', 0) + 1
            
            with open(USERS_FILE, 'w') as f:
                json.dump(users, f, indent=4)
            return True
    except Exception as e:
        logger.error(f"Error updating last login: {e}")
    return False

def authenticate_user(username, password):
    """Authenticate a user"""
    users = get_users()
    
    if username in users and verify_password(username, password):
        # Update last login time on successful authentication
        update_last_login(username)
        return True, users[username]['role']
    
    return False, None

def login_required(f):
    """Decorator for views that require login"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user' not in session:
            # Save the requested URL for redirecting after login
            session['next_url'] = request.url
            flash('You need to login to access this page', 'warning')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def admin_required(f):
    """Decorator for views that require admin role"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user' not in session:
            session['next_url'] = request.url
            flash('You need to login to access this page', 'warning')
            return redirect(url_for('login'))
        
        if 'role' not in session or session['role'] != 'admin':
            flash('You need admin privileges to access this page', 'danger')
            return redirect(url_for('dashboard'))
            
        return f(*args, **kwargs)
    return decorated_function

def add_user(username, password, role='user'):
    """Add a new user"""
    try:
        users = get_users()
        if username in users:
            return False
            
        users[username] = {
            'password': hash_password(password),
            'role': role,
            'last_login': None,
            'login_count': 0
        }
        
        with open(USERS_FILE, 'w') as f:
            json.dump(users, f, indent=4)
        return True
    except Exception as e:
        logger.error(f"Error adding user: {e}")
        return False

def change_password(username, new_password):
    """Change a user's password"""
    try:
        users = get_users()
        if username not in users:
            return False
            
        users[username]['password'] = hash_password(new_password)
        
        with open(USERS_FILE, 'w') as f:
            json.dump(users, f, indent=4)
        return True
    except Exception as e:
        logger.error(f"Error changing password: {e}")
        return False 