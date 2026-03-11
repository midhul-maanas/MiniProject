import pandas as pd
from sklearn.ensemble import RandomForestRegressor
import joblib

df = pd.read_csv("usage_data.csv")

df["timestamp"] = pd.to_datetime(df["timestamp"])
df["hour"] = df["timestamp"].dt.hour #added hour to df
df["category_encoded"] = df["category"].astype("category").cat.codes #converted the category to integer codes.

x = df[[
    "duration",
    "cpu_usage",
    "idle_time",
    "hour",
    "category_encoded"
]]  #input features

y=df["co2"]  #output feature

model = RandomForestRegressor(
    n_estimators = 100, #no of decision trees
    random_state = 42 #for reproducibility
)
model.fit(x,y)

joblib.dump(model,"co2_model.pkl")

print("Model trained successfully")
