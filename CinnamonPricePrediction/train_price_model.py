import pandas as pd
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import LabelEncoder
from xgboost import XGBRegressor
from sklearn.metrics import mean_absolute_error, r2_score
import joblib
import os

# Load dataset
df = pd.read_csv("cinnamon_prices_2016_2026.csv")

# Remove rows with missing prices
df = df.dropna(subset=["Average_Price"])

# Encode Grade and District
grade_encoder = LabelEncoder()
district_encoder = LabelEncoder()

df["Grade"] = grade_encoder.fit_transform(df["Grade"])
df["District"] = district_encoder.fit_transform(df["District"])

# Features
X = df[[
    "Year",
    "Month",
    "Week",
    "District",
    "Grade"
]]

# Target
y = df["Average_Price"]

# Train/Test Split
X_train, X_test, y_train, y_test = train_test_split(
    X,
    y,
    test_size=0.2,
    random_state=42
)

# Train XGBoost
model = XGBRegressor(
    n_estimators=300,
    learning_rate=0.05,
    max_depth=6,
    random_state=42
)

model.fit(X_train, y_train)

# Evaluate
pred = model.predict(X_test)

print("MAE:", mean_absolute_error(y_test, pred))
print("R2 :", r2_score(y_test, pred))

# Save model
os.makedirs("models", exist_ok=True)

joblib.dump(model, "models/price_model.pkl")
joblib.dump(grade_encoder, "models/grade_encoder.pkl")
joblib.dump(district_encoder, "models/district_encoder.pkl")

print("\nModel saved successfully!")