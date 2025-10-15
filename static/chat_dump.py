from openai import OpenAI
from dotenv import load_dotenv
import os
import json

load_dotenv()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
### print("API Key loaded:", os.getenv("OPENAI_API_KEY")[:20] + "...")

def generate_plan_with_ai(user_description, days_per_week):
    """Use AI to generate a smart 4-week training plan"""

    prompt = f"""You are an expert triathlon coach. Based on this athlete's description, create a detailed 4-week progressive training plan.

Athlete Description: {user_description}
Training Days Available: {days_per_week} days per week

Requirements:
- 4 weeks total (Week 4 should be a recovery week)
- Include swim, bike, run workouts
- Add strength training when volume is medium-high
- Focus more on the athlete's limiter sport
- Consider their current vs goal volume
- Include rest days
- Double training days are possible if needed
- Stretching is recovery, not a main workout

Return ONLY a JSON array with this exact structure:
[
  {{
    "week": 1,
    "day": 1,
    "activity": "swim",
    "duration": 45,
    "description": "Technique focus: 10min warm-up, 6x100m drills, 15min easy swim"
  }},
  ...
]

Make it {days_per_week * 4} workouts total (across 4 weeks). Be specific with workout details."""

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You are an expert triathlon coach who creates periodized training plans."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.7
        )

        plan_text = response.choices[0].message.content

        # Extract JSON from response (sometimes AI adds markdown formatting)
        if "```json" in plan_text:
            plan_text = plan_text.split("```json")[1].split("```")[0]
        elif "```" in plan_text:
            plan_text = plan_text.split("```")[1].split("```")[0]

        plan = json.loads(plan_text.strip())
        return plan

    except Exception as e:
        print(f"Error generating plan: {e}")
        print(f"Full error details: {type(e).__name__}")
        import traceback
        traceback.print_exc()
        return None
