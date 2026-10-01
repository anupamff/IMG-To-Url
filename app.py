from flask import Flask, render_template, request, jsonify, send_from_directory, redirect, url_for, session
import os
import uuid
import requests
import json
from functools import wraps
from datetime import datetime, timedelta

app = Flask(__name__)
app.secret_key = "jubayer_super_secret_key_2026"
app.permanent_session_lifetime = timedelta(days=30)

# Google OAuth configuration
GOOGLE_CLIENT_ID = "YOUR_CLIENT_ID"
GOOGLE_CLIENT_SECRET = "YOUR_CLIENT_SECRET"
GOOGLE_REDIRECT_URI = "YOUR_CALBAKC_URL"

# Configuration
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['MAX_CONTENT_LENGTH'] = 10 * 1024 * 1024
app.config['ALLOWED_EXTENSIONS'] = {'png', 'jpg', 'jpeg', 'gif', 'webp'}

os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# Database file
DATABASE_FILE = 'database.json'

def load_database():
    if os.path.exists(DATABASE_FILE):
        with open(DATABASE_FILE, 'r') as f:
            return json.load(f)
    return {'users': {}, 'images': {}}

def save_database(data):
    with open(DATABASE_FILE, 'w') as f:
        json.dump(data, f, indent=2)

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user' not in session:
            return jsonify({'error': 'Please login first'}), 401
        return f(*args, **kwargs)
    return decorated_function

@app.route('/')
def landing():
    if 'user' in session:
        return redirect(url_for('index'))
    return render_template('landing.html')

@app.route('/login')
def login():
    if 'user' in session:
        return redirect(url_for('index'))
    return render_template('login.html')

@app.route('/index')
def index():
    if 'user' not in session:
        return redirect(url_for('landing'))
    return render_template('index.html')

@app.route('/auth/google')
def auth_google():
    google_auth_url = f"https://accounts.google.com/o/oauth2/v2/auth?client_id={GOOGLE_CLIENT_ID}&redirect_uri={GOOGLE_REDIRECT_URI}&response_type=code&scope=email%20profile"
    return redirect(google_auth_url)

@app.route('/google-callback')
def google_callback():
    code = request.args.get('code')
    error = request.args.get('error')
    
    if error or not code:
        return redirect(url_for('login'))
    
    token_url = "https://oauth2.googleapis.com/token"
    data = {
        'code': code,
        'client_id': GOOGLE_CLIENT_ID,
        'client_secret': GOOGLE_CLIENT_SECRET,
        'redirect_uri': GOOGLE_REDIRECT_URI,
        'grant_type': 'authorization_code'
    }
    
    response = requests.post(token_url, data=data)
    token_data = response.json()
    
    if 'access_token' not in token_data:
        return redirect(url_for('login'))
    
    user_info_url = "https://www.googleapis.com/oauth2/v1/userinfo"
    headers = {'Authorization': f"Bearer {token_data['access_token']}"}
    user_response = requests.get(user_info_url, headers=headers)
    user_data = user_response.json()
    
    session.permanent = True
    user_email = user_data.get('email')
    session['user'] = {
        'name': user_data.get('name'),
        'email': user_email,
        'picture': user_data.get('picture')
    }
    
    # Initialize user in database
    db = load_database()
    if user_email not in db['users']:
        db['users'][user_email] = {
            'name': user_data.get('name'),
            'email': user_email,
            'images': []
        }
        save_database(db)
    
    return redirect(url_for('index'))

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('landing'))

@app.route('/api/check-auth')
def check_auth():
    if 'user' in session:
        return jsonify({'authenticated': True, 'user': session['user']})
    return jsonify({'authenticated': False})

@app.route('/api/upload', methods=['POST'])
@login_required
def upload_image():
    try:
        if 'image' not in request.files:
            return jsonify({'error': 'No image file provided'}), 400
        
        file = request.files['image']
        
        if file.filename == '':
            return jsonify({'error': 'No file selected'}), 400
        
        if not allowed_file(file.filename):
            return jsonify({'error': 'Only PNG, JPG, JPEG, GIF, WEBP files allowed'}), 400
        
        unique_id = str(uuid.uuid4())[:8]
        original_ext = file.filename.rsplit('.', 1)[1].lower()
        
        filename = f"{unique_id}.{original_ext}"
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        
        file.save(filepath)
        
        base_url = request.host_url.rstrip('/')
        image_url = f"{base_url}/images/{unique_id}"
        
        # Save to database
        db = load_database()
        image_data = {
            'id': unique_id,
            'filename': filename,
            'url': image_url,
            'created_at': datetime.now().isoformat(),
            'status': 'active',
            'size': os.path.getsize(filepath)
        }
        
        db['images'][unique_id] = image_data
        
        user_email = session['user']['email']
        if user_email in db['users']:
            db['users'][user_email]['images'].append(unique_id)
        
        save_database(db)
        
        return jsonify({
            'success': True,
            'url': image_url,
            'id': unique_id,
            'message': 'Image uploaded successfully!'
        }), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/user/history')
@login_required
def user_history():
    db = load_database()
    user_email = session['user']['email']
    image_ids = db['users'].get(user_email, {}).get('images', [])
    
    images = []
    for img_id in image_ids:
        if img_id in db['images']:
            images.append(db['images'][img_id])
    
    return jsonify({'images': images})

@app.route('/api/toggle-status/<image_id>', methods=['POST'])
@login_required
def toggle_status(image_id):
    db = load_database()
    
    if image_id not in db['images']:
        return jsonify({'error': 'Image not found'}), 404
    
    current_status = db['images'][image_id]['status']
    new_status = 'deactive' if current_status == 'active' else 'active'
    db['images'][image_id]['status'] = new_status
    save_database(db)
    
    return jsonify({
        'success': True,
        'status': new_status,
        'message': f'Link {new_status}d successfully!'
    })

@app.route('/images/<image_id>')
def serve_image(image_id):
    db = load_database()
    
    if image_id not in db['images']:
        return render_template('not_found.html'), 404
    
    image_data = db['images'][image_id]
    
    if image_data['status'] == 'deactive':
        return render_template('not_found.html'), 404
    
    filename = image_data['filename']
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)