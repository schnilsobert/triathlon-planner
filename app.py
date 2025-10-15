from flask import Flask, render_template, request, session, redirect
from flask_session import Session
from cs50 import SQL
from openai import OpenAI
from dotenv import load_dotenv
import os
import json
import time

load_dotenv()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

app = Flask(__name__)
app.config["SECRET_KEY"] = "bd58440c97a51ab2a1cd41a9ccf5ddec"
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

db = SQL("sqlite:///triathlon.db")

def generate_plan_with_ai(user_description, days_per_week):
    """Generate 4 weeks at a time - fast enough to avoid timeout"""
    all_workouts = []

    for week_num in range(1, 5):  # Just 4 weeks = ~8-12 seconds
        prompt = f"""Create week {week_num} of a 4-week triathlon training plan for this athlete:

{user_description}

Training frequency: {days_per_week} days per week

Important guidelines:
- This is week {week_num} of 4 (progressive build)
- If the athlete mentions a weekly training volume (like "20 hours per week"), respect that volume goal
- For high-volume athletes (15+ hours/week), use double training days strategically (same day number twice)
- For beginners with no stated volume, use appropriate beginner volumes (5-8 hours/week)
- Generate exactly 7 days (days 1-7)
- Rest days should have activity "rest" with duration 0

Double training day example:
{{"week": {week_num}, "day": 3, "activity": "swim", "duration": 60, "description": "Morning technique session"}}
{{"week": {week_num}, "day": 3, "activity": "run", "duration": 45, "description": "Easy evening run"}}

Write workout descriptions naturally - be specific and motivating without being repetitive.

Return ONLY a valid JSON array: [{{"week": {week_num}, "day": 1, "activity": "swim", "duration": 90, "description": "..."}}]
"""

        try:
            print(f"Generating week {week_num}...")
            response = client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {
                        "role": "system",
                        "content": "You are an experienced triathlon coach. Write workout descriptions naturally - be specific and motivating without repeating phrases."
                    },
                    {"role": "user", "content": prompt}
                ],
                max_tokens=2000,
                temperature=0.85
            )

            content = response.choices[0].message.content

            if not content or len(content.strip()) == 0:
                print(f"⚠️ Week {week_num}: Empty response")
                return None

            start = content.find('[')
            end = content.rfind(']') + 1

            if start == -1 or end == 0:
                print(f"⚠️ Week {week_num}: No JSON array found")
                return None

            json_str = content[start:end]

            try:
                week_workouts = json.loads(json_str)
            except json.JSONDecodeError as e:
                print(f"⚠️ Week {week_num}: JSON parse error: {e}")
                return None

            if not isinstance(week_workouts, list) or len(week_workouts) == 0:
                print(f"⚠️ Week {week_num}: Invalid workout list")
                return None

            # Validate required fields
            for workout in week_workouts:
                required = ["week", "day", "activity", "duration", "description"]
                if not all(key in workout for key in required):
                    print(f"⚠️ Week {week_num}: Missing required fields")
                    return None

            all_workouts.extend(week_workouts)
            print(f"✅ Week {week_num}: {len(week_workouts)} workouts")

            time.sleep(0.5)

        except Exception as e:
            print(f"❌ Error generating week {week_num}: {e}")
            return None

    print(f"✅ Total: {len(all_workouts)} workouts generated")
    return all_workouts


@app.route("/")
def index():
    return redirect("/setup")


@app.route("/setup", methods=["GET", "POST"])
def setup():
    if request.method == "POST":
        description = request.form.get("description", "").strip()
        days = request.form.get("days", "").strip()

        # Validation
        if not description or len(description) < 20:
            return render_template("error.html",
                message="Please provide a more detailed description (at least 20 characters)."), 400

        if not days or days not in ["3", "4", "5", "6", "7"]:
            return render_template("error.html",
                message="Please select a valid number of training days (3-7)."), 400

        # Save to database
        try:
            user_id = db.execute(
                "INSERT INTO users (days_per_week, fitness_level, goal) VALUES (?, ?, ?)",
                days, description, "AI-Generated"
            )
        except Exception as e:
            print(f"Database error: {e}")
            return render_template("error.html",
                message="Database error. Please try again."), 500

        session["user_id"] = user_id
        return redirect("/plan")
    else:
        return render_template("setup.html")


@app.route("/plan")
def plan():
    if "user_id" not in session:
        return redirect("/setup")

    user_id = session["user_id"]

    # Get user data
    try:
        user = db.execute("SELECT * FROM users WHERE id = ?", user_id)
        if not user:
            session.pop("user_id", None)
            return redirect("/setup")
        user = user[0]
    except Exception as e:
        print(f"Database error: {e}")
        return render_template("error.html",
            message="Error loading your data."), 500

    # Check for existing plan
    existing_plan = db.execute(
        "SELECT * FROM plans WHERE user_id = ? ORDER BY week_number, day_number",
        user_id
    )

    if not existing_plan:
        print(f"Generating new plan for user {user_id}...")

        # Generate AI plan
        ai_plan = generate_plan_with_ai(user["fitness_level"], user["days_per_week"])

        if not ai_plan or not isinstance(ai_plan, list) or len(ai_plan) == 0:
            print("❌ AI plan generation failed")
            return render_template("error.html",
                message="Could not generate training plan. Please try again in a moment."), 503

        print(f"Saving {len(ai_plan)} workouts...")

        saved_count = 0
        for workout in ai_plan:
            try:
                db.execute("""
                    INSERT INTO plans
                    (user_id, week_number, day_number, activity_type, duration, description)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, user_id, workout["week"], workout["day"],
                workout["activity"], workout["duration"], workout["description"])
                saved_count += 1
            except Exception as e:
                print(f"Error saving workout: {e}")
                continue

        if saved_count == 0:
            return render_template("error.html",
                message="Failed to save your plan. Please try again."), 500

        print(f"✅ Saved {saved_count} workouts!")

        existing_plan = db.execute(
            "SELECT * FROM plans WHERE user_id = ? ORDER BY week_number, day_number",
            user_id
        )

    return render_template("plan.html", plan=existing_plan, user=user)


@app.route("/complete/<int:workout_id>", methods=["POST"])
def complete_workout(workout_id):
    if "user_id" not in session:
        return redirect("/setup")

    try:
        # Verify workout belongs to this user
        workout = db.execute(
            "SELECT * FROM plans WHERE id = ? AND user_id = ?",
            workout_id, session["user_id"]
        )

        if not workout:
            return redirect("/plan")

        # Toggle completion
        current = workout[0]
        new_status = 0 if current["completed"] == 1 else 1
        db.execute("UPDATE plans SET completed = ? WHERE id = ?", new_status, workout_id)

    except Exception as e:
        print(f"Error toggling workout: {e}")

    return redirect("/plan")


if __name__ == "__main__":
    app.run(debug=False)
