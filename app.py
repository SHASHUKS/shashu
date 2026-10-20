import os
import io
import csv
import base64
import random
import smtplib
import ssl
import pytz
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
from flask import Flask, render_template, request, jsonify, redirect, url_for, session, Response
from pymongo import MongoClient
import qrcode

# --- TIMEZONE SETUP ---
IST = pytz.timezone('Asia/Kolkata')

def get_current_ist_time():
    return datetime.now(IST).strftime('%Y-%m-%d %H:%M:%S')

# --- FORCE ABSOLUTE PATHS FOR VERCEL SERVERLESS DEPLOYMENT ---
basedir = os.path.abspath(os.path.dirname(__file__))
template_dir = os.path.join(basedir, 'templates')

# --- APP INITIALIZATION ---
app = Flask(__name__, template_folder=template_dir)
app.secret_key = os.getenv('SECRET_KEY', 'indian_railways_super_secret_key')
app.config['TEMPLATES_AUTO_RELOAD'] = True

# --- HARDCODED BASE CREDENTIALS ---
USERS_DB = {
    "sripriya": {"password": "13062005", "role": "user", "name": "Sripriya"},
    "navya": {"password": "13062005", "role": "user", "name": "Navya"},
    "admin": {"password": "shashu", "role": "admin", "name": "System Administrator"}
}

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
users_col = db["users_collection"] if db is not None else None

# Load DB stored users into USERS_DB on startup
def load_db_users():
    if users_col is not None:
        try:
            db_users = list(users_col.find({}, {"_id": 0}))
            for u in db_users:
                USERS_DB[u["username"]] = {"password": u["password"], "role": u["role"], "name": u.get("name", u["username"].capitalize())}
        except Exception as e:
            print(f"[ERROR Loading DB Users]: {e}")

load_db_users()

# Helper functions for alert email configuration
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

# --- SMTP EMAIL ALERT ---
def send_critical_alert_email(recipient_email, asset_id, zone, gps, rul, weather, traffic, grade, warranty):
    sender_email = os.getenv("SENDER_EMAIL", "railwayalert001@gmail.com")
    sender_password = "voaxhhonjtyxjrtm"

    msg = MIMEMultipart('alternative')
    msg['From'] = f"Railways AayusPredict <{sender_email}>"
    msg['To'] = recipient_email
    msg['Subject'] = f"URGENT: Track Asset {asset_id} Requires Immediate Maintenance"

    html_body = f"""
    <!DOCTYPE html>
    <html>
    <body style="font-family: Arial, sans-serif; color: #1e293b; padding: 20px;">
        <h2 style="color: #dc2626;">[CRITICAL ALERT] Railways AayusPredict System</h2>
        <p>A critical track asset has failed inspection and requires immediate maintenance or replacement.</p>
        <hr style="border: 1px solid #e2e8f0;">
        <p><b>Asset ID:</b> {asset_id}</p>
        <p><b>Railway Zone:</b> {zone}</p>
        <p><b>GPS Coordinates:</b> {gps}</p>
        <p><b>Inspector Grade:</b> {grade}</p>
        <p><b>Remaining Useful Life (RUL):</b> <span style="color: #dc2626; font-weight: bold;">{rul} Years</span></p>
        <p><b>Traffic Load:</b> {traffic}</p>
        <p><b>Local Weather:</b> {weather}</p>
        <br>
        <p style="font-size: 12px; color: #64748b;">This is an automated dispatch alert from Smart Track AI - Indian Railways Maintenance System.</p>
    </body>
    </html>
    """
    msg.attach(MIMEText(html_body, 'html'))

    try:
        server = smtplib.SMTP('smtp.gmail.com', 587, timeout=10)
        server.starttls()
        server.login(sender_email, sender_password)
        server.sendmail(sender_email, recipient_email, msg.as_string())
        server.quit()
        print(f"[SUCCESS] Critical alert email sent successfully to {recipient_email}")
        return True
    except Exception as e:
        print(f"[ERROR Sending Email Alert]: {e}")
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
        username = request.form.get('username', '').strip().lower()
        password = request.form.get('password', '').strip()
        
        load_db_users()
        
        if username in USERS_DB and USERS_DB[username]['password'] == password:
            session['logged_in'] = True
            session['username'] = username
            session['role'] = USERS_DB[username]['role']
            session['display_name'] = USERS_DB[username]['name']
            
            log_activity(username, f"Logged In ({session['role'].upper()})")
            return redirect(url_for('option'))
        
        return render_template('login.html', error="Invalid Credentials. Please try again.")
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
    return render_template('option.html', username=session.get('username'), role=session.get('role'))

@app.route('/dashboard')
def dashboard():
    if not session.get('logged_in'): return redirect(url_for('login'))
    
    current_user = session.get('username')
    role = session.get('role')

    try:
        if role == 'admin':
            all_assets = list(inventory_col.find({}, {"_id": 0})) if inventory_col is not None else []
        else:
            all_assets = list(inventory_col.find({
                "$or": [
                    {"created_by": current_user},
                    {"scanned_by": current_user}
                ]
            }, {"_id": 0})) if inventory_col is not None else []
    except Exception as e:
        all_assets = []
    
    total = len(all_assets)
    critical = sum(1 for a in all_assets if a.get('status') == 'Critical')
    replaced = sum(1 for a in all_assets if a.get('status') == 'Replaced')
    good = sum(1 for a in all_assets if a.get('status') == 'Good')
    
    stats = {'total': total, 'good': good, 'damaged': critical, 'replaced': replaced}
    
    return render_template('dashboard.html', assets=all_assets, items=all_assets, total=total, healthy=good, critical=critical, stats=stats, role=role, current_user=current_user)

@app.route('/activity')
def activity():
    if not session.get('logged_in'): return redirect(url_for('login'))
    
    current_user = session.get('username')
    role = session.get('role')
    filter_date = request.args.get('filter_date', '').strip()
    log_search = request.args.get('log_search', '').strip()

    user_summary = []
    user_credentials = []

    if role == 'admin':
        load_db_users()
        for uname, udata in USERS_DB.items():
            user_credentials.append({
                "username": uname,
                "password": udata["password"],
                "role": udata["role"],
                "name": udata.get("name", uname.capitalize())
            })

            if filter_date:
                date_regex = f"^{filter_date}"
                scans = inventory_col.count_documents({
                    "scanned_by": uname,
                    "scan_time": {"$regex": date_regex}
                }) if inventory_col is not None else 0
                
                qrs = inventory_col.count_documents({
                    "created_by": uname,
                    "install_date": filter_date
                }) if inventory_col is not None else 0
            else:
                scans = inventory_col.count_documents({"scanned_by": uname}) if inventory_col is not None else 0
                qrs = inventory_col.count_documents({"created_by": uname}) if inventory_col is not None else 0

            user_summary.append({
                "username": uname,
                "role": udata["role"],
                "scan_count": scans,
                "qr_count": qrs
            })

    try:
        # --- EXCLUDE SCANS, QR GENERATIONS, AND REPLACEMENTS FROM ACTIVITY LOGS ---
        filter_query = {
            "action": {
                "$not": {
                    "$regex": "^(Scanned Asset|Generated QR for Asset|Marked Asset)"
                }
            }
        }

        if role == 'admin':
            if log_search:
                filter_query["$or"] = [
                    {"user": {"$regex": log_search, "$options": "i"}},
                    {"action": {"$regex": log_search, "$options": "i"}},
                    {"time": {"$regex": log_search, "$options": "i"}}
                ]
            logs = list(logs_col.find(filter_query, {"_id": 0}).sort("_id", -1).limit(100)) if logs_col is not None else []
        else:
            filter_query["user"] = current_user
            if log_search:
                filter_query["$and"] = [
                    {"user": current_user},
                    {"$or": [
                        {"action": {"$regex": log_search, "$options": "i"}},
                        {"time": {"$regex": log_search, "$options": "i"}}
                    ]}
                ]
            logs = list(logs_col.find(filter_query, {"_id": 0}).sort("_id", -1).limit(50)) if logs_col is not None else []
    except Exception as e:
        logs = []

    current_email = get_alert_email()
    msg = request.args.get('msg')
    msg_type = request.args.get('msg_type', 'info')

    return render_template(
        'activity.html', 
        logs=logs, 
        role=role, 
        current_user=current_user, 
        user_summary=user_summary,
        user_credentials=user_credentials,
        selected_date=filter_date,
        current_email=current_email,
        msg=msg,
        msg_type=msg_type
    )

# --- MAP VIEW ROUTE ---
@app.route('/map')
def map_view():
    if not session.get('logged_in'): 
        return redirect(url_for('login'))
    
    current_user = session.get('username')
    role = session.get('role')

    try:
        if role == 'admin':
            assets = list(inventory_col.find({}, {"_id": 0})) if inventory_col is not None else []
        else:
            assets = list(inventory_col.find({
                "$or": [
                    {"created_by": current_user},
                    {"scanned_by": current_user}
                ]
            }, {"_id": 0})) if inventory_col is not None else []
    except Exception as e:
        assets = []

    return render_template('map.html', assets=assets, role=role, current_user=current_user)

# --- SET ACTIVE LOCATION FROM MAP ROUTE (SILENT UPDATE WITHOUT LOGGING) ---
@app.route('/set_location', methods=['POST'])
def set_location():
    if not session.get('logged_in'): 
        return jsonify({'error': 'Unauthorized'}), 401
    
    data = request.json or request.form
    zone = data.get('zone')
    gps = data.get('gps')
    
    if zone:
        session['selected_zone'] = zone
    if gps:
        session['selected_gps'] = gps
        
    return jsonify({'success': True, 'zone': zone, 'gps': gps})

# --- SCANNER VIEW ROUTE (SYNCED TO SESSION LOCATION) ---
@app.route('/scanner')
def scanner():
    if not session.get('logged_in'): 
        return redirect(url_for('login'))
    
    current_user = session.get('username')
    role = session.get('role')
    
    # Retrieve user's selected zone and GPS from session (synced from map selection)
    zone = session.get('selected_zone', 'Southern Railway (HQ: Chennai Central)')
    gps = session.get('selected_gps', '12.800058, 77.706495')
    
    return render_template('scanner.html', role=role, current_user=current_user, zone=zone, gps=gps)

# --- MARK ASSET AS REPLACED ROUTE ---
@app.route('/replace_asset/<path:asset_id>')
def replace_asset(asset_id):
    if not session.get('logged_in'): 
        return redirect(url_for('login'))
    
    current_user = session.get('username')
    replacement_time = get_current_ist_time()

    try:
        if inventory_col is not None:
            inventory_col.update_one(
                {"asset_id": asset_id},
                {
                    "$set": {
                        "status": "Replaced",
                        "replacement_date": replacement_time,
                        "replaced_by": current_user
                    }
                }
            )
        log_activity(current_user, f"Marked Asset {asset_id} as Replaced")
    except Exception as e:
        print(f"[ERROR Replacing Asset]: {e}")

    return redirect(url_for('dashboard'))

# --- CLEAR DASHBOARD INVENTORY DATA ROUTES ---
@app.route('/clear_data', methods=['GET', 'POST'])
@app.route('/clear_dashboard', methods=['GET', 'POST'])
@app.route('/cleardata', methods=['GET', 'POST'])
@app.route('/clear_inventory', methods=['GET', 'POST'])
def clear_dashboard():
    if not session.get('logged_in'): 
        return redirect(url_for('login'))
    
    current_user = session.get('username')
    role = session.get('role')

    try:
        if inventory_col is not None:
            if role == 'admin':
                inventory_col.delete_many({})
            else:
                inventory_col.delete_many({
                    "$or": [
                        {"created_by": current_user},
                        {"scanned_by": current_user}
                    ]
                })
        log_activity(current_user, 'Cleared Dashboard Inventory Data')
    except Exception as e:
        print(f"[ERROR Clearing Dashboard Data]: {e}")

    return redirect(url_for('dashboard'))

# --- CLEAR ACTIVITY LOGS ROUTES ---
@app.route('/clear_activity', methods=['GET', 'POST'])
@app.route('/clear_logs', methods=['GET', 'POST'])
@app.route('/clear_log', methods=['GET', 'POST'])
def clear_activity():
    if not session.get('logged_in'): return redirect(url_for('login'))
    current_user = session.get('username')
    role = session.get('role')

    if logs_col is not None:
        if role == 'admin':
            logs_col.delete_many({})
        else:
            logs_col.delete_many({"user": current_user})
            
    log_activity(current_user, 'Cleared Activity Logs')
    return redirect(url_for('activity'))

# --- ADMIN EXCLUSIVE: DELETE USER ROUTE ---
@app.route('/delete_user', methods=['POST'])
def delete_user():
    if not session.get('logged_in') or session.get('role') != 'admin':
        return redirect(url_for('login'))
        
    username_to_delete = request.form.get('username_to_delete', '').strip().lower()
    
    if username_to_delete == 'admin':
        return redirect(url_for('activity', msg="Cannot delete the primary admin account!", msg_type="error"))

    if username_to_delete in USERS_DB:
        del USERS_DB[username_to_delete]

    if users_col is not None:
        try:
            users_col.delete_one({"username": username_to_delete})
        except Exception as e:
            print(f"[ERROR Deleting User from DB]: {e}")

    log_activity(session.get('username'), f"Deleted user account: {username_to_delete}")
    return redirect(url_for('activity', msg=f"User '{username_to_delete}' removed successfully!", msg_type="success"))

# --- ADMIN EXCLUSIVE: UPDATE USER CREDENTIALS ROUTE ---
@app.route('/update_user_credentials', methods=['POST'])
def update_user_credentials():
    if not session.get('logged_in') or session.get('role') != 'admin':
        return redirect(url_for('login'))
        
    old_username = request.form.get('old_username', '').strip().lower()
    new_username = request.form.get('new_username', '').strip().lower()
    new_password = request.form.get('new_password', '').strip()
    
    if not new_username or not new_password:
        return redirect(url_for('activity', msg="Username and password cannot be empty.", msg_type="error"))

    load_db_users()

    if old_username not in USERS_DB:
        return redirect(url_for('activity', msg="User not found!", msg_type="error"))

    if new_username != old_username and new_username in USERS_DB:
        return redirect(url_for('activity', msg=f"Username '{new_username}' already exists!", msg_type="error"))

    user_data = USERS_DB.pop(old_username)
    user_data['password'] = new_password
    user_data['name'] = new_username.capitalize()
    USERS_DB[new_username] = user_data

    if users_col is not None:
        try:
            users_col.update_one(
                {"username": old_username},
                {
                    "$set": {
                        "username": new_username,
                        "password": new_password,
                        "name": new_username.capitalize()
                    }
                },
                upsert=True
            )
        except Exception as e:
            print(f"[ERROR Updating User in DB]: {e}")

    log_activity(session.get('username'), f"Updated credentials for user: {old_username} -> {new_username}")
    return redirect(url_for('activity', msg=f"Credentials for '{new_username}' updated successfully!", msg_type="success"))

# --- CSV EXPORT: SYSTEM ACCESS LOGS ---
@app.route('/export_logs_csv')
def export_logs_csv():
    if not session.get('logged_in'): return redirect(url_for('login'))
    
    current_user = session.get('username')
    role = session.get('role')
    search_query = request.args.get('search', '').strip()

    try:
        filter_query = {"action": {"$not": {"$regex": "^(Scanned Asset|Generated QR for Asset|Marked Asset)"}}}
        if role != 'admin':
            filter_query["user"] = current_user
        elif search_query:
            filter_query["$or"] = [
                {"user": {"$regex": search_query, "$options": "i"}},
                {"action": {"$regex": search_query, "$options": "i"}},
                {"time": {"$regex": search_query, "$options": "i"}}
            ]

        logs = list(logs_col.find(filter_query, {"_id": 0}).sort("_id", -1)) if logs_col is not None else []
    except Exception as e:
        logs = []

    def generate():
        data = io.StringIO()
        writer = csv.writer(data)
        writer.writerow(['Timestamp (IST)', 'Username', 'Action Event'])
        yield data.getvalue()
        data.seek(0)
        data.truncate(0)

        for log in logs:
            writer.writerow([log.get('time', ''), log.get('user', ''), log.get('action', '')])
            yield data.getvalue()
            data.seek(0)
            data.truncate(0)

    filename = f"System_Access_Logs_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    return Response(generate(), mimetype="text/csv", headers={"Content-Disposition": f"attachment;filename={filename}"})

# --- CSV EXPORT: USER ACTIVITY METRICS ---
@app.route('/export_metrics_csv')
def export_metrics_csv():
    if not session.get('logged_in') or session.get('role') != 'admin':
        return redirect(url_for('login'))

    filter_date = request.args.get('filter_date', '').strip()
    load_db_users()
    
    user_summary = []
    for uname, udata in USERS_DB.items():
        if filter_date:
            date_regex = f"^{filter_date}"
            scans = inventory_col.count_documents({"scanned_by": uname, "scan_time": {"$regex": date_regex}}) if inventory_col is not None else 0
            qrs = inventory_col.count_documents({"created_by": uname, "install_date": filter_date}) if inventory_col is not None else 0
        else:
            scans = inventory_col.count_documents({"scanned_by": uname}) if inventory_col is not None else 0
            qrs = inventory_col.count_documents({"created_by": uname}) if inventory_col is not None else 0

        user_summary.append({
            "username": uname,
            "role": udata["role"],
            "scan_count": scans,
            "qr_count": qrs
        })

    def generate():
        data = io.StringIO()
        writer = csv.writer(data)
        writer.writerow(['Username', 'Role', 'Total Scans', 'QRs Created', 'Filter Date'])
        yield data.getvalue()
        data.seek(0)
        data.truncate(0)

        for u in user_summary:
            writer.writerow([u['username'], u['role'], u['scan_count'], u['qr_count'], filter_date if filter_date else 'Lifetime'])
            yield data.getvalue()
            data.seek(0)
            data.truncate(0)

    filename = f"User_Activity_Metrics_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    return Response(generate(), mimetype="text/csv", headers={"Content-Disposition": f"attachment;filename={filename}"})

# --- ROUTE TO UPDATE CRITICAL ALERT RECEIVER EMAIL ---
@app.route('/set_alert_email', methods=['POST'])
def set_alert_email():
    if not session.get('logged_in'): return redirect(url_for('login'))
    new_email = request.form.get('new_email')
    if new_email:
        set_alert_email_db(new_email)
        log_activity(session.get('username', 'admin'), f'Updated Alert Email to: {new_email}')
    return redirect(url_for('activity', msg="Alert email updated successfully!", msg_type="success"))

# --- ADMIN EXCLUSIVE: CREATE USER ROUTE ---
@app.route('/create_user', methods=['POST'])
def create_user():
    if not session.get('logged_in') or session.get('role') != 'admin':
        return redirect(url_for('login'))
        
    new_uname = request.form.get('new_username', '').strip().lower()
    new_pass = request.form.get('new_password', '').strip()
    new_role = request.form.get('user_role', 'user').strip().lower()
    
    if not new_uname or not new_pass:
        return redirect(url_for('activity', msg="Username and password cannot be empty.", msg_type="error"))

    load_db_users()
    if new_uname in USERS_DB:
        return redirect(url_for('activity', msg=f"User '{new_uname}' already exists!", msg_type="error"))

    user_data = {
        "username": new_uname,
        "password": new_pass,
        "role": new_role,
        "name": new_uname.capitalize(),
        "created_at": get_current_ist_time()
    }

    if users_col is not None:
        users_col.insert_one(user_data)

    USERS_DB[new_uname] = {"password": new_pass, "role": new_role, "name": new_uname.capitalize()}
    log_activity(session.get('username'), f"Created new user account: {new_uname} ({new_role.upper()})")

    return redirect(url_for('activity', msg=f"User '{new_uname}' created successfully!", msg_type="success"))

@app.route('/generate', methods=['GET', 'POST'])
def generate():
    if not session.get('logged_in'): return redirect(url_for('login'))
    qr_data_url, item_id = None, None
    current_user = session.get('username', 'admin')
    
    if request.method == 'POST':
        network_prefix = request.form.get('network_prefix', 'IR')
        component_type = request.form.get('component_type', 'ERC')
        alloy_grade = request.form.get('alloy_grade', 'EN45')
        serial_id = request.form.get('serial_id', '000000')
        exact_date = request.form.get('exact_date', '2026-09-15')
        warranty_years = int(request.form.get('warranty_years', 20))
        
        mfg_raw = request.form.get('mfg_month', '2026-09')
        try:
            mfg_mmyy = datetime.strptime(mfg_raw, "%Y-%m").strftime("%m%y")
        except:
            mfg_mmyy = "0926"

        try:
            install_dt = datetime.strptime(exact_date, "%Y-%m-%d")
            install_mmyy = install_dt.strftime("%m%y")
            expiry_dt = install_dt.replace(year=install_dt.year + warranty_years)
            expiry_yyyy = expiry_dt.strftime("%Y")
            warranty_date_str = f"{expiry_dt.strftime('%Y-%m-%d')} ({warranty_years} Years)"
        except:
            install_mmyy = "0926"
            expiry_yyyy = str(2026 + warranty_years)
            warranty_date_str = f"{warranty_years} Years"
        
        item_id = f"{network_prefix}-{component_type}-{alloy_grade}-{mfg_mmyy}-{install_mmyy}-{expiry_yyyy}-{serial_id}"
        
        new_asset = {
            "asset_id": item_id,
            "created_by": current_user,
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

        log_activity(current_user, f"Generated QR for Asset: {item_id}")

        try:
            qr_img = qrcode.make(item_id)
            img_buffer = io.BytesIO()
            qr_img.save(img_buffer, format='PNG')
            img_buffer.seek(0)
            b64_str = base64.b64encode(img_buffer.getvalue()).decode('utf-8')
            qr_data_url = f"data:image/png;base64,{b64_str}"
        except Exception as img_err:
            qr_data_url = None
        
    return render_template('generate.html', qr_path=qr_data_url, item_id=item_id)

@app.route('/api/predict', methods=['POST'])
def predict_rul():
    if not session.get('logged_in'): return jsonify({'error': 'Unauthorized'}), 401
    
    current_user = session.get('username', 'admin')
    data = request.json
    asset_id = data.get('asset_id', '')
    rust_grade = int(data.get('rust_grade', 1))
    
    scan_zone = data.get('zone', session.get('selected_zone', 'Southern Railway (HQ: Chennai Central)'))
    scan_time = get_current_ist_time()
    gps_location = data.get('location', session.get('selected_gps', '12.800058, 77.706495'))
    
    existing_asset = None
    if inventory_col is not None:
        existing_asset = inventory_col.find_one({"asset_id": asset_id}, {"_id": 0})

    try:
        # --- 1. PARSE ALL DATES (MFG, INSTALL, EXPIRY) & ALLOY GRADE ---
        parts = asset_id.split('-')
        expiry_year = 2046  # Default fallback
        install_year = 2026
        alloy_grade = parts[2] if len(parts) >= 3 else "Unknown"

        if len(parts) >= 6:
            try:
                install_mmyy = parts[4]
                install_year = int("20" + install_mmyy[2:])
                expiry_year = int(parts[5])
            except:
                pass

        # Determine Material Strength Multiplier based on Alloy Grade
        alloy_multipliers = {
            "EN47": 1.20,    # 20% extra life for premium chromium-vanadium
            "SCM435": 1.25,  # 25% extra life for high-tensile steel
            "SiMn": 1.15,    # 15% extra life for silico-manganese
            "EN45": 1.00     # Standard baseline
        }
        material_multiplier = alloy_multipliers.get(alloy_grade, 1.0)

        current_year = datetime.now().year
        
        # Calculate base design life span vs current age
        total_design_life = max(1, expiry_year - install_year) 
        elapsed_years = current_year - install_year
        base_warranty_rul = total_design_life - elapsed_years

        # --- 2. LOCATION-BASED ENVIRONMENT DATA ---
        combined_seed = abs(hash(f"{asset_id}_{rust_grade}_{gps_location}")) % (2**32)
        random.seed(combined_seed)

        traffic = round(random.uniform(30.0, 70.0), 1)      # Gross Million Tons
        axle_load = round(random.uniform(20.0, 22.5), 1)    # Tonnes
        temp = round(random.uniform(28.0, 42.0), 1)         # Celsius
        humidity = round(random.uniform(45.0, 85.0), 1)     # Percentage

        # --- 3. DYNAMIC DEGRADATION ALGORITHM (Extended up to 50 Years with Alloy Factor) ---
        weather_impact = ((temp - 25) * 0.05) + ((humidity - 40) * 0.02)
        traffic_impact = (traffic * 0.05) + ((axle_load - 20) * 0.2)
        
        # Heavier penalties for poor grades
        grade_multiplier = {1: 0.0, 2: 1.5, 3: 4.0, 4: 8.0}.get(rust_grade, 0.0)
        
        if base_warranty_rul <= 0:
            # EXPIRED ASSET calculation (Factors in Alloy Strength)
            residual_base = (2.0 - (rust_grade * 0.4)) * material_multiplier
            expired_penalties = (traffic * 0.005) + (temp * 0.005)
            predicted_rul = max(0.1, round(residual_base - expired_penalties, 2))
        else:
            # LIFE EXTENSION: Good components (Grade 1 & 2) in good weather get a massive lifespan boost!
            if rust_grade <= 2:
                # Bonus life calculation based on mild weather and low traffic
                weather_bonus = max(0, 42 - temp) * 0.8      
                traffic_bonus = max(0, 70 - traffic) * 0.6   
                base_warranty_rul += (weather_bonus + traffic_bonus)
            
            # Apply Material Strength Multiplier to the total base life
            base_warranty_rul *= material_multiplier

            total_degradation = weather_impact + traffic_impact + grade_multiplier
            predicted_rul = round(base_warranty_rul - total_degradation, 2)
            
            # ABSOLUTE CAP: Allow RUL up to 50.0 Years maximum
            predicted_rul = max(0.1, min(50.0, predicted_rul))

        status = 'Good' if predicted_rul >= 1.5 else 'Critical'
        
        load_ui_string = f"{traffic:.1f} GMT, {axle_load:.1f}T"
        weather_ui_string = f"{temp:.0f}°C, {humidity:.0f}% Hum"
        inspector_grade_string = f"Grade {rust_grade}"
        warranty_string = f"{expiry_year} ({total_design_life} Years Design Life)"

        updated_asset = {
            "asset_id": asset_id,
            "scanned_by": current_user,
            "track_load": load_ui_string,
            "current_rust": weather_ui_string,
            "predicted_rul": predicted_rul,
            "status": status,
            "scan_zone": scan_zone,
            "scan_time": scan_time,
            "inspector_grade": inspector_grade_string,
            "gps_location": gps_location,
            "warranty_expiry": warranty_string
        }

        if inventory_col is not None:
            inventory_col.update_one(
                {"asset_id": asset_id}, 
                {
                    "$set": updated_asset,
                    "$setOnInsert": {"created_by": current_user}
                }, 
                upsert=True
            )

        log_activity(current_user, f"Scanned Asset {asset_id} - RUL: {predicted_rul} Years ({status})")

        # --- TRIGGER EMAIL ALERT IF CRITICAL ---
        if status == 'Critical':
            receiver_email = get_alert_email()
            send_critical_alert_email(
                recipient_email=receiver_email,
                asset_id=asset_id,
                zone=scan_zone,
                gps=gps_location,
                rul=predicted_rul,
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
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5888))
    app.run(host='0.0.0.0', port=port, debug=True)