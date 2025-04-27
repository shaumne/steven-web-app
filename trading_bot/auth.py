"""
Authentication module for the trading bot dashboard
"""
import os
import json
import logging
from functools import wraps
from flask import session, redirect, url_for, request, flash

# Path to users file
USERS_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'users.json')

def init_users_file():
    """Initialize the users file if it doesn't exist"""
    if not os.path.exists(USERS_FILE):
        try:
            # Create with a default admin user
            with open(USERS_FILE, 'w') as f:
                json.dump({
                    "admin": {
                        "password": "change_me_immediately",
                        "role": "admin"
                    }
                }, f, indent=4)
            logging.info(f"Created default users file at {USERS_FILE}")
            logging.warning("Default admin user created with password 'change_me_immediately'. Please change it!")
        except Exception as e:
            logging.error(f"Failed to create users file: {e}")

def get_users():
    """Get all users from the users file"""
    try:
        if not os.path.exists(USERS_FILE):
            init_users_file()
            
        with open(USERS_FILE, 'r') as f:
            return json.load(f)
    except Exception as e:
        logging.error(f"Failed to read users file: {e}")
        return {}

def authenticate_user(username, password):
    """Authenticate a user"""
    users = get_users()
    
    if username in users and users[username]['password'] == password:
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