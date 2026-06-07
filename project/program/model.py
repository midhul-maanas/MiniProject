import pandas as pd
from sklearn.ensemble import RandomForestRegressor
import joblib

df = pd.read_csv("hourly_usage_data.csv")

X = df[[
    "duration",
    "cpu_usage",
    "idle_time",
    "hour"
]]

y = df["co2"]

model = RandomForestRegressor(
    n_estimators=100, 
    random_state=42 
)

model.fit(X, y) 

joblib.dump(model, "co2_model.pkl")

print("✅ Hourly model trained successfully")