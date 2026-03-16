from google import genai
import time

API_KEY = "AIzaSyDRnLm-QLJKrklSKszIuW51UvWCSTSOVyE"

client = genai.Client(api_key=API_KEY)

# Cache variables
cached_suggestions = "Analyzing usage..."
last_update = 0

CACHE_DURATION = 300  # seconds (5 minutes)


def generate_ai_suggestions(total_co2, total_energy, breakdown):

    global cached_suggestions
    global last_update

    current_time = time.time()

    # Return cached result if still valid
    if current_time - last_update < CACHE_DURATION:
        return cached_suggestions

    prompt = f"""
You are an AI assistant helping reduce digital carbon footprint.

User CO2 today: {total_co2} kg
Energy consumed: {total_energy} kWh

Application usage:
{breakdown}

Provide 3–5 short suggestions to reduce digital carbon emissions.
Focus on reducing streaming energy, closing unused apps, and avoiding idle usage.
Only give suggestions ,nothing else.
"""

    try:

        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt
        )

        cached_suggestions = response.text
        last_update = current_time

        return cached_suggestions

    except Exception as e:

        return f"AI suggestion error: {e}"