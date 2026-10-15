import pandas as pd
import os
import joblib
from sklearn.ensemble import RandomForestRegressor

# 1. Create the models folder if it doesn't exist
os.makedirs('models', exist_ok=True)

# 2. Load the dataset
print("Loading dataset...")
try:
    df = pd.read_csv('indian_railways_track_asset_data.csv')
except FileNotFoundError:
    print("[ERROR] Cannot find 'indian_railways_track_asset_data.csv'. Ensure it is in the same folder.")
    exit()

# 3. Define Inputs (X) and Target (y)
X = df[['Axle_Load_Tonnes', 'Train_Speed_kmh', 'Traffic_Volume_GMT', 
        'Ambient_Temp_C', 'Humidity_Pct', 'Rainfall_mm_yr', 'Corrosion_Zone']]
y = df['RUL_Years']

# 4. Train an Optimized, Lightweight Random Forest AI
print("Training Compressed Random Forest AI...")
# Reduced estimators and limited depth to keep the file size tiny
rf_model = RandomForestRegressor(n_estimators=25, max_depth=10, random_state=42)
rf_model.fit(X, y)

# 5. Save the trained model with high compression (compress=3)
model_path = 'models/rf_model.pkl'
joblib.dump(rf_model, model_path, compress=3)
print(f"[SUCCESS] Lightweight Model saved successfully to {model_path}!")