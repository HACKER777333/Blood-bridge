from flask import Flask, request, jsonify
from flask_cors import CORS
from google.cloud import firestore
from dotenv import load_dotenv
import os
from datetime import datetime, timedelta
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
import random

# Load environment variables
load_dotenv()

app = Flask(__name__)
CORS(app)  # Enable CORS for frontend connection
app.secret_key = os.getenv('SECRET_KEY', 'your-secret-key-change-this')

# Initialize Firebase
try:
    creds_path = os.getenv('GOOGLE_APPLICATION_CREDENTIALS', 'firebase_config.json')
    if os.path.exists(creds_path):
        os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = creds_path
        db = firestore.Client()
        print(f"✅ Firebase connected successfully")
    else:
        print(f"❌ Firebase credentials file not found: {creds_path}")
        db = None
except Exception as e:
    print(f"❌ Firebase initialization error: {str(e)}")
    db = None

# Gmail Configuration
GMAIL_ADDRESS = os.getenv('GMAIL_ADDRESS')
GMAIL_APP_PASSWORD = os.getenv('GMAIL_APP_PASSWORD')

# Admin credentials
ADMIN_PASSWORD = os.getenv('ADMIN_PASSWORD', 'admin123')

# Spam Protection Configuration
EMERGENCY_COOLDOWN_MINUTES = 30
MAX_REQUESTS_PER_HOUR = 3
EMAIL_SEND_DELAY = 0.5
MAX_WORKERS = 5

# Twilio Configuration
TWILIO_ACCOUNT_SID = os.getenv('TWILIO_ACCOUNT_SID')
TWILIO_AUTH_TOKEN = os.getenv('TWILIO_AUTH_TOKEN')
TWILIO_PHONE_NUMBER = os.getenv('TWILIO_PHONE_NUMBER')

# Initialize Twilio client
try:
    from twilio.rest import Client
    twilio_client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
    print(f"✅ Twilio connected successfully")
except Exception as e:
    print(f"⚠️ Twilio initialization error: {str(e)}")
    twilio_client = None

# Store OTPs temporarily
otp_storage = {}

def check_spam_protection(requester_ip):
    """Check if the request is spam based on IP and timing"""
    try:
        recent_requests = db.collection('emergency_requests')\
            .where('requester_ip', '==', requester_ip)\
            .order_by('created_at', direction=firestore.Query.DESCENDING)\
            .limit(10)\
            .stream()
        
        recent_list = list(recent_requests)
        
        if not recent_list:
            return True, "OK"
        
        last_request = recent_list[0].to_dict()
        last_time = last_request.get('created_at')
        
        if last_time:
            time_diff = datetime.now() - last_time
            if time_diff < timedelta(minutes=EMERGENCY_COOLDOWN_MINUTES):
                minutes_left = EMERGENCY_COOLDOWN_MINUTES - int(time_diff.total_seconds() / 60)
                return False, f"⏳ Please wait {minutes_left} minutes before submitting another emergency request."
        
        one_hour_ago = datetime.now() - timedelta(hours=1)
        recent_hour_requests = [req for req in recent_list 
                               if req.to_dict().get('created_at', datetime.now()) > one_hour_ago]
        
        if len(recent_hour_requests) >= MAX_REQUESTS_PER_HOUR:
            return False, f"⚠️ Maximum {MAX_REQUESTS_PER_HOUR} emergency requests per hour allowed."
        
        return True, "OK"
        
    except Exception as e:
        print(f"Spam check error: {str(e)}")
        return True, "OK"

def log_emergency_request(data, requester_ip, sent_count, failed_count):
    """Log emergency request to database"""
    emergency_data = {
        'requester_name': data.get('requester_name'),
        'hospital_name': data.get('hospital_name'),
        'blood_group': data.get('blood_group'),
        'city': data.get('city'),
        'state': data.get('state'),
        'address': data.get('address'),
        'notes': data.get('notes', ''),
        'requester_ip': requester_ip,
        'alerts_sent': sent_count,
        'alerts_failed': failed_count,
        'created_at': datetime.now()
    }
    db.collection('emergency_requests').add(emergency_data)

def send_email_thread_safe(to_email, subject, body, donor_name):
    """Thread-safe email sending function"""
    try:
        message = MIMEMultipart()
        message['From'] = GMAIL_ADDRESS
        message['To'] = to_email
        message['Subject'] = subject
        message.attach(MIMEText(body, 'html'))
        
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(GMAIL_ADDRESS, GMAIL_APP_PASSWORD)
        server.send_message(message)
        server.quit()
        
        time.sleep(EMAIL_SEND_DELAY)
        return (True, donor_name, to_email, None)
    except Exception as e:
        return (False, donor_name, to_email, str(e))

# API Routes

@app.route('/api/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({
        'status': 'ok',
        'firebase': db is not None,
        'twilio': twilio_client is not None,
        'gmail': GMAIL_ADDRESS is not None
    })

@app.route('/api/register', methods=['POST'])
def register():
    """Register new donor"""
    try:
        if db is None:
            return jsonify({'success': False, 'message': 'Database connection error.'}), 500
            
        data = request.get_json()
        
        donor_data = {
            'name': data.get('name'),
            'email': data.get('email'),
            'password': data.get('password'),
            'blood_group': data.get('blood_group'),
            'address': data.get('address'),
            'city': data.get('city'),
            'state': data.get('state'),
            'phone': data.get('phone'),
            'phone_verified': data.get('phone_verified', False),
            'verified': False,
            'created_at': datetime.now()
        }
        
        db.collection('donors').add(donor_data)
        
        return jsonify({
            'success': True,
            'message': 'Registration successful! Await admin verification.'
        })
    except Exception as e:
        return jsonify({'success': False, 'message': f'Registration failed: {str(e)}'}), 500

@app.route('/api/search', methods=['POST'])
def search():
    """Search for donors"""
    try:
        if db is None:
            return jsonify({'success': False, 'message': 'Database connection error.'}), 500
            
        data = request.get_json()
        blood_group = data.get('blood_group')
        city = data.get('city')
        
        donors_ref = db.collection('donors')
        query = donors_ref.where('verified', '==', True)\
                         .where('blood_group', '==', blood_group)\
                         .where('city', '==', city)
        
        donors = []
        for doc in query.stream():
            donor_data = doc.to_dict()
            donors.append({
                'id': doc.id,
                'name': donor_data.get('name'),
                'blood_group': donor_data.get('blood_group'),
                'city': donor_data.get('city'),
                'state': donor_data.get('state')
            })
        
        return jsonify({'success': True, 'donors': donors})
    except Exception as e:
        return jsonify({'success': False, 'message': f'Search failed: {str(e)}'}), 500

@app.route('/api/emergency', methods=['POST'])
def emergency():
    """Send emergency alerts"""
    try:
        if db is None:
            return jsonify({'success': False, 'message': 'Database connection error.'}), 500
        
        requester_ip = request.headers.get('X-Forwarded-For', request.remote_addr)
        if requester_ip:
            requester_ip = requester_ip.split(',')[0].strip()
        
        data = request.get_json()
        
        # Verify reCAPTCHA
        recaptcha_response = data.get('g-recaptcha-response')
        if not recaptcha_response or len(recaptcha_response) < 10:
            return jsonify({'success': False, 'message': '⚠️ CAPTCHA verification required.'}), 400
        
        # Spam protection
        is_allowed, spam_message = check_spam_protection(requester_ip)
        if not is_allowed:
            return jsonify({'success': False, 'message': spam_message}), 429
        
        blood_group = data.get('blood_group')
        city = data.get('city')
        
        # Fetch donors
        donors_ref = db.collection('donors')
        query = donors_ref.where('verified', '==', True)\
                         .where('blood_group', '==', blood_group)\
                         .where('city', '==', city)
        
        donors_list = list(query.stream())
        
        if not donors_list:
            return jsonify({
                'success': False,
                'message': f'No verified {blood_group} donors found in {city}.'
            })
        
        # Limit to 50 donors
        if len(donors_list) > 50:
            donors_list = donors_list[:50]
        
        # Prepare emails
        email_tasks = []
        for doc in donors_list:
            donor_data = doc.to_dict()
            donor_email = donor_data.get('email')
            donor_name = donor_data.get('name')
            
            subject = f"🚨 URGENT: Blood Donation Request - {blood_group}"
            
            email_body = f"""
            <html>
                <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
                    <div style="max-width: 600px; margin: 0 auto; padding: 20px; border: 2px solid #dc3545; border-radius: 10px;">
                        <h2 style="color: #dc3545; text-align: center;">🚨 URGENT BLOOD DONATION NEEDED</h2>
                        
                        <div style="background-color: #f8f9fa; padding: 20px; border-radius: 5px; margin: 20px 0;">
                            <h3 style="color: #dc3545;">Dear {donor_name},</h3>
                            <p>A patient urgently needs <strong>{blood_group}</strong> blood donation.</p>
                        </div>
                        
                        <div style="background-color: #fff3cd; padding: 15px; border-left: 4px solid #ffc107; margin: 20px 0;">
                            <h4 style="margin-top: 0;">⚡ Emergency Details:</h4>
                            <p><strong>🏥 Hospital:</strong> {data.get('hospital_name')}</p>
                            <p><strong>📍 Location:</strong> {data.get('address')}, {city}, {data.get('state')}</p>
                            <p><strong>🩸 Blood Group Required:</strong> {blood_group}</p>
                            <p><strong>👤 Contact Person:</strong> {data.get('requester_name')}</p>
                            <p><strong>🕐 Alert Time:</strong> {datetime.now().strftime('%I:%M %p, %d %b %Y')}</p>
                        </div>
                        
                        <div style="background-color: #d4edda; padding: 15px; border-radius: 5px; margin: 20px 0;">
                            <h4 style="color: #155724; margin-top: 0;">✅ How You Can Help:</h4>
                            <p>If you are available to donate, please contact the hospital immediately.</p>
                            <p style="font-size: 1.1em; font-weight: bold; color: #dc3545;">Your donation can save a life! ❤️</p>
                        </div>
                        
                        <div style="text-align: center; margin-top: 30px; padding: 20px; background-color: #f8f9fa; border-radius: 5px;">
                            <p style="margin: 0; color: #666;">Thank you for being a registered blood donor with BloodBridge</p>
                        </div>
                    </div>
                </body>
            </html>
            """
            
            email_tasks.append((donor_email, subject, email_body, donor_name))
        
        # Send emails in parallel
        sent_count = 0
        failed_count = 0
        
        start_time = time.time()
        
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            future_to_email = {
                executor.submit(send_email_thread_safe, email, subj, body, name): (email, name)
                for email, subj, body, name in email_tasks
            }
            
            for future in as_completed(future_to_email):
                try:
                    success, donor_name, donor_email, error = future.result()
                    if success:
                        sent_count += 1
                    else:
                        failed_count += 1
                except Exception as exc:
                    failed_count += 1
        
        duration = round(time.time() - start_time, 2)
        
        # Log request
        log_emergency_request(data, requester_ip, sent_count, failed_count)
        
        return jsonify({
            'success': True,
            'message': f'🚨 Emergency alert sent to {sent_count} verified {blood_group} donors in {city}!',
            'stats': {
                'total_donors': len(email_tasks),
                'sent': sent_count,
                'failed': failed_count,
                'duration_seconds': duration
            }
        })
    except Exception as e:
        return jsonify({'success': False, 'message': f'Emergency alert failed: {str(e)}'}), 500

@app.route('/api/admin/login', methods=['POST'])
def admin_login():
    """Admin login"""
    try:
        data = request.get_json()
        password = data.get('password')
        
        if password != ADMIN_PASSWORD:
            return jsonify({'success': False, 'message': 'Invalid password'}), 401
        
        return jsonify({'success': True, 'message': 'Login successful'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/admin/donors', methods=['POST'])
def get_donors():
    """Get all donors for admin"""
    try:
        if db is None:
            return jsonify({'success': False, 'message': 'Database connection error.'}), 500
            
        data = request.get_json()
        password = data.get('password')
        
        if password != ADMIN_PASSWORD:
            return jsonify({'success': False, 'message': 'Invalid password'}), 401
        
        donors_ref = db.collection('donors')
        donors = []
        
        for doc in donors_ref.stream():
            donor_data = doc.to_dict()
            donors.append({
                'id': doc.id,
                'name': donor_data.get('name'),
                'email': donor_data.get('email'),
                'blood_group': donor_data.get('blood_group'),
                'city': donor_data.get('city'),
                'state': donor_data.get('state'),
                'phone': donor_data.get('phone'),
                'phone_verified': donor_data.get('phone_verified', False),
                'verified': donor_data.get('verified', False)
            })
        
        return jsonify({'success': True, 'donors': donors})
    except Exception as e:
        return jsonify({'success': False, 'message': f'Failed to fetch donors: {str(e)}'}), 500

@app.route('/api/admin/verify/<donor_id>', methods=['POST'])
def verify_donor(donor_id):
    """Verify donor"""
    try:
        if db is None:
            return jsonify({'success': False, 'message': 'Database connection error.'}), 500
            
        donor_ref = db.collection('donors').document(donor_id)
        donor_ref.update({'verified': True})
        
        return jsonify({'success': True, 'message': 'Donor verified successfully'})
    except Exception as e:
        return jsonify({'success': False, 'message': f'Verification failed: {str(e)}'}), 500

@app.route('/api/admin/delete/<donor_id>', methods=['DELETE'])
def delete_donor(donor_id):
    """Delete donor"""
    try:
        if db is None:
            return jsonify({'success': False, 'message': 'Database connection error.'}), 500
            
        db.collection('donors').document(donor_id).delete()
        
        return jsonify({'success': True, 'message': 'Donor deleted successfully'})
    except Exception as e:
        return jsonify({'success': False, 'message': f'Deletion failed: {str(e)}'}), 500

@app.route('/api/send-otp', methods=['POST'])
def send_otp():
    """Send OTP via Twilio SMS"""
    try:
        data = request.get_json()
        phone = data.get('phone')
        
        if not phone:
            return jsonify({'success': False, 'message': 'Phone number is required'}), 400
        
        if not twilio_client:
            return jsonify({'success': False, 'message': 'SMS service is not available.'}), 500
        
        otp = str(random.randint(100000, 999999))
        
        otp_storage[phone] = {
            'code': otp,
            'expires_at': datetime.now() + timedelta(minutes=5)
        }
        
        message = twilio_client.messages.create(
            body=f"Your BloodBridge verification code is: {otp}\n\nThis code expires in 5 minutes.",
            from_=TWILIO_PHONE_NUMBER,
            to=phone
        )
        
        return jsonify({'success': True, 'message': f'OTP sent successfully to {phone}'})
        
    except Exception as e:
        return jsonify({'success': False, 'message': f'Failed to send OTP: {str(e)}'}), 500

@app.route('/api/verify-otp', methods=['POST'])
def verify_otp():
    """Verify OTP"""
    try:
        data = request.get_json()
        phone = data.get('phone')
        code = data.get('code')
        
        if not phone or not code:
            return jsonify({'success': False, 'message': 'Phone number and OTP code are required'}), 400
        
        if phone not in otp_storage:
            return jsonify({'success': False, 'message': 'No OTP found for this number.'}), 400
        
        stored_otp = otp_storage[phone]
        
        if datetime.now() > stored_otp['expires_at']:
            del otp_storage[phone]
            return jsonify({'success': False, 'message': 'OTP expired.'}), 400
        
        if stored_otp['code'] != code:
            return jsonify({'success': False, 'message': 'Invalid OTP.'}), 400
        
        del otp_storage[phone]
        
        return jsonify({'success': True, 'message': 'Phone number verified successfully!'})
        
    except Exception as e:
        return jsonify({'success': False, 'message': f'Verification failed: {str(e)}'}), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
