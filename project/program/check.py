from google import genai

API_KEY = "AIzaSyCtYNJiiyOcHo3s0fL17siJAsf1CjcSniU"

client = genai.Client(api_key=API_KEY)

def generate_ai_suggestions(total_co2, total_energy, breakdown):

    prompt = f"""
You are an AI assistant helping reduce digital carbon footprint.

User CO2 today: {total_co2} kg
Energy consumed: {total_energy} kWh

Application usage:
{breakdown}

Provide 3–5 short suggestions to reduce digital carbon emissions.
Focus on reducing streaming energy, closing unused apps, and avoiding idle usage.
"""

    try:

        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt
        )

        return response.text

    except Exception as e:

        return f"AI suggestion error: {e}"