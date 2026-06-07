from google import genai
import time
from dotenv import load_dotenv
import os
load_dotenv()
API_KEY = os.getenv("API_KEY")

client = genai.Client(api_key=API_KEY)

cached_suggestions = "Analyzing usage..."
last_update = 0

CACHE_DURATION = 300 


def generate_ai_suggestions(total_co2, total_energy, breakdown):

    global cached_suggestions
    global last_update

    current_time = time.time()

    if current_time - last_update < CACHE_DURATION:
        return cached_suggestions

    prompt = f"""
You are an AI assistant helping reduce digital carbon footprint.

User CO2 today: {total_co2} kg
Energy consumed: {total_energy} kWh

Application usage:
{breakdown}

First, convert ONLY the total CO2 value into a simple real-world NON-DIGITAL analogy.

Guidelines for analogy:

* Use meaningful and realistic comparisons only
* Avoid very small or impractical values (e.g., centimeters of driving)
* Use driving distance ONLY if the value is large enough to be expressed in meters or kilometers clearly
* For smaller CO2 values, prefer alternatives like:

  * minutes of LED bulb usage
  * grams of fuel burned
  * other simple physical activities

Do NOT use application usage data for the analogy.
Do NOT use any digital-related comparisons.

Then provide 3–5 short, practical suggestions to reduce digital carbon emissions.

Output format:

* First line: real-world analogy (non-digital, meaningful scale)
* Then: only bullet-point suggestions

Do not include explanations or extra text.



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
        print(f" AI suggestion error: {e}")
        if cached_suggestions and cached_suggestions != "Analyzing usage...":
            return cached_suggestions
        return "AI suggestions temporarily unavailable. Please try again later."