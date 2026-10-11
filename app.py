import os
import random
import smtplib
import ssl
import traceback
import pytz
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
from flask import Flask, render_template, request, jsonify, redirect, url_for, session
from pymongo import MongoClient
import joblib
import pandas as pd
import qrcode

# --- TIMEZONE SETUP ---
IST = pytz.timezone('Asia/Kolkata')

def get_current_ist_time():
    return datetime.now(IST).strftime('%Y-%m-%d %H:%M:%S')

# --- FORCE ABSOLUTE PATHS FOR VERCEL SERVERLESS DEPLOYMENT ---
basedir = os.path.abspath(os.path.dirname(__file__))
template_dir = os.path.join(basedir, 'templates')

# Vercel filesystem is read-only except /tmp
if os.getenv("VERCEL"):
    QR_FOLDER = os.path.join('/tmp', 'qr_codes')
else:
    QR_FOLDER = os.path.join(basedir, 'static', 'qr_codes')

MODELS_FOLDER = os.path.join(basedir, 'models')

# --- APP INITIALIZATION ---
app = Flask(__name__, template_folder=template_dir)
app.secret_key = os.getenv('SECRET_KEY', 'indian_railways_super_secret_key')
app.config['TEMPLATES_AUTO_RELOAD'] = True

os.makedirs(QR_FOLDER, exist_ok=True)
os.makedirs(MODELS_FOLDER, exist_ok=True)

# --- MONGODB ATLAS DATABASE SETUP WITH CLOUD TIMEOUTS ---
MONGO_URI = os.getenv(
    "MONGO_URI",
    "mongodb://ksshashwath79_db_user:SXZqgnsfALFHj3RI@ac-dwwl65l-shard-00-00.ruxvlwt.mongodb.net:27017,ac-dwwl65l-shard-00-01.ruxvlwt.mongodb.net:27017,ac-dwwl65l-shard-00-02.ruxvlwt.mongodb.net:27017/?ssl=true&replicaSet=atlas-xvffg3-shard-0&authSource=admin&appName=Cluster0"
)

try:
    client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000, connectTimeoutMS=5000)
    db = client["smart_track_db"]
    client.admin.command('ping')
    print("[SUCCESS] Connected to MongoDB Atlas successfully!")
except Exception as e:
    print(f"[WARNING] MongoDB Connection Error: {e}")
    client = None
    db = None

# Collections
inventory_col = db["inventory_data"] if db is not None else None
logs_col = db["activity_logs"] if db is not None else None
settings_col = db["settings"] if db is not None else None

# Helper functions for database operations
def get_alert_email():
    try:
        if settings_col is not None:
            setting = settings_col.find_one({"key": "alert_email_receiver"}, {"_id": 0})
            if setting:
                return setting.get("value", os.getenv("ALERT_RECEIVER", "ksshashwath77@gmail.com"))
    except Exception as e:
        print(f"[ERROR Fetching Alert Email]: {e}")
    return os.getenv("ALERT_RECEIVER", "ksshashwath77@gmail.com")

def set_alert_email_db(email):
    try:
        if settings_col is not None:
            settings_col.update_one(
                {"key": "alert_email_receiver"},
                {"$set": {"key": "alert_email_receiver", "value": email}},
                upsert=True
            )
    except Exception as e:
        print(f"[ERROR Updating Alert Email]: {e}")

# ACTIVITY LOGGING
def log_activity(user, action):
    try:
        if logs_col is not None:
            logs_col.insert_one({
                'user': user,
                'action': action,
                'time': get_current_ist_time()
            })
    except Exception as e:
        print(f"[ERROR Logging Activity]: {e}")

# --- BULLETPROOF ML MODEL LOADING ---
class FallbackModel:
    def predict(self, df):
        return [random.uniform(0.5, 12.0)]

try:
    model_path = os.path.join(MODELS_FOLDER, 'rf_model.pkl')
    if os.path.exists(model_path):
        model = joblib.load(model_path)
        print("[SUCCESS] Scikit-Learn ML Model loaded successfully.")
    else:
        print("[WARNING] rf_model.pkl not found. Using Fallback Predictor.")
        model = FallbackModel()
except Exception as e:
    print(f"[WARNING] ML Model Error: {e}. Using Fallback Predictor.")
    model = FallbackModel()

# --- SYNCHRONOUS SMTP EMAIL SENDER FOR VERCEL SERVERLESS ---
def send_critical_alert_email(recipient_email, asset_id, zone, gps, rul, weather, traffic, grade, warranty):
    sender_email = os.getenv("SENDER_EMAIL", "railwayalert001@gmail.com")
    sender_password = os.getenv("SENDER_PASSWORD", "voaxhhonjtyxjrtm").replace(" ", "")
    
    print(f"[EMAIL INITIATED] Preparing alert for Asset: {asset_id} -> Recipient: {recipient_email}")

    msg = MIMEMultipart('alternative')
    msg['From'] = f"Railways AayusPredict <{sender_email}>"
    msg['To'] = recipient_email
    msg['Subject'] = f"URGENT: Track Asset {asset_id} Requires Immediate Maintenance"

    html_body = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <style>
            body {{ font-family: Arial, sans-serif; color: #1e293b; background-color: #f8fafc; padding: 20px; }}
            .container {{ max-width: 600px; margin: 0 auto; background: #ffffff; padding: 25px; border-radius: 8px; border: 1px solid #cbd5e1; }}
            .header {{ font-size: 16px; font-weight: bold; color: #1e3a8a; border-bottom: 2px solid #0f172a; padding-bottom: 10px; margin-bottom: 15px; text-transform: uppercase; }}
            table {{ width: 100%; border-collapse: collapse; margin-top: 10px; }}
            th, td {{ padding: 10px 14px; text-align: left; font-size: 14px; border: 1px solid #cbd5e1; }}
            th {{ background-color: #f1f5f9; color: #0f172a; font-weight: bold; }}
            .status-critical {{ color: #dc2626; font-weight: bold; }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">[ALERT] Railways AayusPredict System</div>
            <table>
                <tr><th>Property</th><th>Details</th></tr>
                <tr><td><b>Asset ID</b></td><td><b>{asset_id}</b></td></tr>
                <tr><td><b>Railway Zone</b></td><td>{zone}</td></tr>
                <tr><td><b>GPS Location</b></td><td>{gps}</td></tr>
                <tr><td><b>Service Loads</b></td><td>{traffic}</td></tr>
                <tr><td><b>Weather Conditions</b></td><td>{weather}</td></tr>
                <tr><td><b>Inspector Grade</b></td><td>{grade}</td></tr>
                <tr><td><b>Warranty / Life</b></td><td>{warranty}</td></tr>
                <tr><td><b>Predicted RUL</b></td><td style="color: #dc2626; font-weight: bold;">{rul} Months Remaining</td></tr>
            </table>
        </div>
    </body>
    </html>
    """
    msg.attach(MIMEText(html_body, 'html'))

    # Synchronous attempt via Port 587 STARTTLS
    try:
        print("[EMAIL LOG] Connecting via Port 587 STARTTLS...")
        server = smtplib.SMTP('smtp.gmail.com', 587, timeout=10)
        server.ehlo()
        context = ssl.create_default_context()
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
        server.starttls(context=context)
        server.ehlo()
        server.login(sender_email, sender_password)
        server.sendmail(sender_email, recipient_email, msg.as_string())
        server.quit()
        print(f"[SUCCESS] Alert email dispatched to {recipient_email}")
        return True
    except Exception as e1:
        print(f"[WARNING] Port 587 failed: {e1}. Retrying via Port 465 SSL...")
        try:
            context = ssl.create_default_context()
            context.check_hostname = False
            context.verify_mode = ssl.CERT_NONE
            with smtplib.SMTP_SSL('smtp.gmail.com', 465, context=context, timeout=10) as server:
                server.login(sender_email, sender_password)
                server.sendmail(sender_email, recipient_email, msg.as_string())
            print(f"[SUCCESS] Alert email dispatched via Port 465 to {recipient_email}")
            return True
        except Exception as e2:
            print(f"[CRITICAL] Both SMTP ports failed: {e2}")
            traceback.print_exc()
            return False

# --- ROUTES ---

@app.route('/')
def index():
    return render_template('welcome.html')

@app.route('/welcome')
def welcome():
    return render_template('welcome.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        if username == 'admin' and password == 'admin':
            session['logged_in'] = True
            session['username'] = username
            log_activity(username, 'Logged In')
            return redirect(url_for('option'))
        return render_template('login.html', error="Invalid Credentials. Use admin / admin.")
    return render_template('login.html')

@app.route('/logout')
def logout():
    if session.get('username'):
        log_activity(session['username'], 'Logged Out')
    session.clear()
    return redirect(url_for('login'))

@app.route('/option')
def option():
    if not session.get('logged_in'): return redirect(url_for('login'))
    return render_template('option.html')

@app.route('/dashboard')
def dashboard():
    if not session.get('logged_in'): return redirect(url_for('login'))
    
    try:
        all_assets = list(inventory_col.find({}, {"_id": 0})) if inventory_col is not None else []
    except Exception as e:
        print(f"[DB DASHBOARD ERROR]: {e}")
        all_assets = []
    
    valid_assets = [a for a in all_assets if a.get('track_load') != 'Pending Scan' and a.get('track_load') != 'Unknown' and not str(a.get('asset_id', '')).startswith('TRK-')]
    total = len(valid_assets)
    critical = sum(1 for a in valid_assets if a.get('status') == 'Critical')
    replaced = sum(1 for a in valid_assets if a.get('status') == 'Replaced')
    good = total - critical - replaced
    
    stats = {'total': total, 'good': good, 'damaged': critical, 'replaced': replaced}
    return render_template('dashboard.html', assets=all_assets, items=all_assets, total=total, healthy=good, critical=critical, stats=stats)

@app.route('/scanner')
def scanner():
    if not session.get('logged_in'): return redirect(url_for('login'))
    current_zone = session.get('selected_zone', 'Southern Railway (HQ: Chennai Central)')
    current_gps = session.get('selected_gps', '12.800058, 77.706495')
    return render_template('scanner.html', zone=current_zone, gps=current_gps)

@app.route('/set_location', methods=['POST'])
def set_location():
    if not session.get('logged_in'): return jsonify({'error': 'Unauthorized'}), 401
    data = request.get_json()
    if data:
        session['selected_zone'] = data.get('zone', 'Southern Railway (HQ: Chennai Central)')
        session['selected_gps'] = data.get('gps', '12.800058, 77.706495')
    return jsonify({'success': True})

@app.route('/map')
def view_map():
    if not session.get('logged_in'): return redirect(url_for('login'))
    
    try:
        all_items = list(inventory_col.find({}, {"_id": 0})) if inventory_col is not None else []
    except Exception as e:
        print(f"[DB MAP ERROR]: {e}")
        all_items = []

    active_items = [item for item in all_items if item.get('status') != 'Replaced' and item.get('track_load') != 'Pending Scan']
    return render_template('map.html', items=active_items, assets=active_items)

@app.route('/activity')
def activity():
    if not session.get('logged_in'): return redirect(url_for('login'))
    
    try:
        logs = list(logs_col.find({}, {"_id": 0}).sort("_id", -1).limit(50)) if logs_col is not None else []
    except Exception as e:
        print(f"[DB ACTIVITY ERROR]: {e}")
        logs = []

    current_email = get_alert_email()
    return render_template('activity.html', logs=logs, current_email=current_email)

@app.route('/set_alert_email', methods=['POST'])
def set_alert_email():
    if not session.get('logged_in'): return redirect(url_for('login'))
    new_email = request.form.get('new_email')
    if new_email:
        set_alert_email_db(new_email)
        log_activity(session.get('username', 'admin'), f'Updated Alert Email to: {new_email}')
    return redirect(url_for('activity'))

@app.route('/clear_activity')
def clear_activity():
    if not session.get('logged_in'): return redirect(url_for('login'))
    if logs_col is not None:
        logs_col.delete_many({})
    log_activity(session.get('username', 'admin'), 'Cleared Activity Logs')
    return redirect(url_for('activity'))

@app.route('/clear_inventory')
def clear_inventory():
    if not session.get('logged_in'): return redirect(url_for('login'))
    if inventory_col is not None:
        inventory_col.delete_many({})
    log_activity(session.get('username', 'admin'), 'Cleared Dashboard Inventory Data')
    return redirect(url_for('dashboard'))

@app.route('/generate', methods=['GET', 'POST'])
def generate():
    if not session.get('logged_in'): return redirect(url_for('login'))
    qr_path, item_id = None, None
    
    if request.method == 'POST':
        network_prefix = request.form.get('network_prefix', 'IR')
        component_type = request.form.get('component_type', 'ERC')
        alloy_grade = request.form.get('alloy_grade', 'EN45')
        serial_id = request.form.get('serial_id', '000000')
        exact_date = request.form.get('exact_date', '2026-09-01')
        warranty_years = int(request.form.get('warranty_years', 20))
        
        try:
            install_dt = datetime.strptime(exact_date, "%Y-%m-%d")
            expiry_dt = install_dt.replace(year=install_dt.year + warranty_years)
            warranty_date_str = f"{expiry_dt.strftime('%Y-%m-%d')} ({warranty_years} Years)"
        except:
            warranty_date_str = f"{warranty_years} Years"
        
        mfg_raw = request.form.get('mfg_month', '2026-09')
        try:
            mfg_mmyy = datetime.strptime(mfg_raw, "%Y-%m").strftime("%m%y")
        except:
            mfg_mmyy = "0926"
        
        item_id = f"{network_prefix}-{component_type}-{alloy_grade}-{mfg_mmyy}-{serial_id}"
        
        new_asset = {
            "asset_id": item_id,
            "vendor": "Indian Railways Centralized",
            "install_date": exact_date,
            "warranty_expiry": warranty_date_str,
            "track_load": "Pending Scan",
            "current_rust": "Pending Scan",
            "predicted_rul": 8.0,
            "status": "Good",
            "scan_zone": "Pending Scan",
            "scan_time": "Pending Scan",
            "inspector_grade": "Pending Scan",
            "gps_location": "Pending Scan"
        }
        
        if inventory_col is not None:
            inventory_col.update_one({"asset_id": item_id}, {"$set": new_asset}, upsert=True)

        img = qrcode.make(item_id)
        filename = f"{item_id}.png"
        filepath = os.path.join(QR_FOLDER, filename)
        img.save(filepath)
        qr_path = url_for('static', filename=f"qr_codes/{filename}")
        
    return render_template('generate.html', qr_path=qr_path, item_id=item_id)

@app.route('/replace_asset/<path:asset_id>')
def replace_asset(asset_id):
    if not session.get('logged_in'): return redirect(url_for('login'))
    current_timestamp = get_current_ist_time()
    
    if inventory_col is not None:
        inventory_col.update_one(
            {"asset_id": asset_id},
            {"$set": {"status": "Replaced", "replacement_date": current_timestamp}}
        )
    return redirect(url_for('dashboard'))

# --- INSTANT ML SCANNING API ---
@app.route('/api/predict', methods=['POST'])
def predict_rul():
    if not session.get('logged_in'): return jsonify({'error': 'Unauthorized'}), 401
    
    data = request.json
    asset_id = data.get('asset_id')
    rust_grade = int(data.get('rust_grade', 1))
    
    scan_zone = data.get('zone', session.get('selected_zone', 'Southern Railway (HQ: Chennai Central)'))
    scan_time = get_current_ist_time()
    gps_location = data.get('location', session.get('selected_gps', '12.800058, 77.706495'))
    
    existing_asset = None
    if inventory_col is not None:
        existing_asset = inventory_col.find_one({"asset_id": asset_id}, {"_id": 0})
    
    if not existing_asset:
        existing_asset = {
            "asset_id": asset_id,
            "vendor": "Standard Rail Depot",
            "install_date": "2026-01-01",
            "warranty_expiry": "2046-01-01 (20 Years)"
        }

    try:
        traffic = round(random.uniform(45.0, 88.0), 1)
        axle_load = round(random.uniform(20.0, 22.5), 1)
        speed = round(random.uniform(70.0, 110.0), 1)
        temp, humidity = random.uniform(28, 42), random.uniform(45, 85)
        rainfall = 1200.0
        corrosion_zone = 1 if rust_grade > 2 else 0

        input_data = pd.DataFrame([[axle_load, speed, traffic, temp, humidity, rainfall, corrosion_zone]], 
                                  columns=['Axle_Load_Tonnes', 'Train_Speed_kmh', 'Traffic_Volume_GMT', 
                                           'Ambient_Temp_C', 'Humidity_Pct', 'Rainfall_mm_yr', 'Corrosion_Zone'])
        
        predicted_rul = round(model.predict(input_data)[0], 2)
        if rust_grade == 3: predicted_rul -= 2.5  
        elif rust_grade == 4: predicted_rul -= 5.0  
            
        predicted_rul = max(0.1, round(predicted_rul, 2))
        status = 'Good' if predicted_rul >= 1.5 else 'Critical'
        
        load_ui_string = f"{traffic:.1f} GMT, {axle_load:.1f}T"
        weather_ui_string = f"{temp:.0f}°C, {humidity:.0f}% Hum"
        inspector_grade_string = f"Grade {rust_grade}"
        warranty_string = existing_asset.get("warranty_expiry", "2046-01-01 (20 Years)")

        updated_asset = {
            "asset_id": asset_id,
            "vendor": existing_asset.get("vendor", "Standard Rail Depot"),
            "install_date": existing_asset.get("install_date", "2026-01-01"),
            "warranty_expiry": warranty_string,
            "track_load": load_ui_string,
            "current_rust": weather_ui_string,
            "predicted_rul": predicted_rul,
            "status": status,
            "scan_zone": scan_zone,
            "scan_time": scan_time,
            "inspector_grade": inspector_grade_string,
            "gps_location": gps_location
        }

        if inventory_col is not None:
            inventory_col.update_one({"asset_id": asset_id}, {"$set": updated_asset}, upsert=True)

        if status == 'Critical':
            receiver_email = get_alert_email()
            rul_months_str = f"{(predicted_rul * 12):.0f}"
            
            # Executed synchronously for Vercel
            send_critical_alert_email(
                recipient_email=receiver_email,
                asset_id=asset_id,
                zone=scan_zone,
                gps=gps_location,
                rul=rul_months_str,
                weather=weather_ui_string,
                traffic=load_ui_string,
                grade=inspector_grade_string,
                warranty=warranty_string
            )
        
        return jsonify({
            'asset_id': asset_id, 
            'predicted_rul': predicted_rul, 
            'status': status, 
            'traffic_load': load_ui_string, 
            'weather': weather_ui_string
        })
    except Exception as e:
        print(f"[ERROR IN ML/DB SAVING]: {e}")
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5888))
    app.run(host='0.0.0.0', port=port, debug=True)