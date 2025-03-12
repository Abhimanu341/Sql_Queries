import psycopg2
import csv
import logging
from dotenv import load_dotenv
import os
from flask import Flask, render_template, request, redirect, url_for, flash, send_file, jsonify
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph
from reportlab.lib.styles import getSampleStyleSheet
from io import BytesIO
from flask_mail import Mail, Message
import secrets

# Load environment variables
load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY')  # Required for session management

# Database connection
def get_db_connection():
    try:
        conn = psycopg2.connect(
            host=os.getenv('DB_HOST'),
            database=os.getenv('DB_NAME'),
            user=os.getenv('DB_USER'),
            password=os.getenv('DB_PASSWORD')
        )
        print("Database connection successful!")  # Debug statement
        return conn
    except Exception as e:
        print(f"Error connecting to the database: {str(e)}")  # Debug statement
        return None

# Flask-Login setup
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "login"

class User(UserMixin):
    def __init__(self, user_id, email):
        self.id = user_id
        self.email = email

@login_manager.user_loader
def load_user(user_id):
    conn = get_db_connection()
    if not conn:
        return None
    cur = conn.cursor()
    cur.execute("SELECT * FROM users WHERE id = %s", (user_id,))
    user_data = cur.fetchone()
    cur.close()
    conn.close()
    if user_data:
        return User(user_data[0], user_data[1])
    return None

# Configure Flask-Mail
app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 587
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USERNAME'] = os.getenv('MAIL_USERNAME')  # Your email
app.config['MAIL_PASSWORD'] = os.getenv('MAIL_PASSWORD')  # Your email password
mail = Mail(app)

# Dictionary to store reset tokens (in production, use a database)
reset_tokens = {}

# Routes
@app.route("/")
def home():
    return render_template("home.html")

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        email = request.form["email"]
        password = request.form["password"]

        conn = get_db_connection()
        if not conn:
            flash("Database connection failed. Please try again later.", "error")
            return redirect(url_for("register"))

        cur = conn.cursor()

        # Check if the email already exists
        cur.execute("SELECT * FROM users WHERE email = %s", (email,))
        if cur.fetchone():
            flash("Email already exists. Please use a different email.", "error")
            cur.close()
            conn.close()
            return redirect(url_for("register"))

        # Hash the password
        hashed_password = generate_password_hash(password)

        try:
            cur.execute("INSERT INTO users (email, password) VALUES (%s, %s)", (email, hashed_password))
            conn.commit()
            flash("Registration successful! Please log in.", "success")
            return redirect(url_for("login"))
        except Exception as e:
            flash(f"An error occurred: {str(e)}", "error")
        finally:
            cur.close()
            conn.close()
    return render_template("register.html")

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form["email"]
        password = request.form["password"]

        conn = get_db_connection()
        if not conn:
            flash("Database connection failed. Please try again later.", "error")
            return redirect(url_for("login"))

        cur = conn.cursor()
        cur.execute("SELECT * FROM users WHERE email = %s", (email,))
        user_data = cur.fetchone()
        cur.close()
        conn.close()

        if user_data and check_password_hash(user_data[2], password):
            user = User(user_data[0], user_data[1])
            login_user(user)
            return redirect(url_for("dashboard"))
        else:
            flash("Invalid email or password", "error")
    return render_template("login.html")

@app.route("/forgot_password", methods=["GET", "POST"])
def forgot_password():
    if request.method == "POST":
        email = request.form["email"]

        conn = get_db_connection()
        if not conn:
            flash("Database connection failed. Please try again later.", "error")
            return redirect(url_for("forgot_password"))

        cur = conn.cursor()
        cur.execute("SELECT * FROM users WHERE email = %s", (email,))
        user = cur.fetchone()
        cur.close()
        conn.close()

        if user:
            # Generate a reset token
            reset_token = secrets.token_urlsafe(32)
            reset_tokens[reset_token] = email

            # Send reset email
            reset_link = url_for("reset_password", token=reset_token, _external=True)
            msg = Message("Password Reset Request", sender="noreply@sqldevelopers.com", recipients=[email])
            msg.body = f"To reset your password, click the following link: {reset_link}"
            mail.send(msg)

            flash("A password reset link has been sent to your email.", "success")
        else:
            flash("Email not found. Please check your email address.", "error")

    return render_template("forgot_password.html")

@app.route("/reset_password/<token>", methods=["GET", "POST"])
def reset_password(token):
    email = reset_tokens.get(token)
    if not email:
        flash("Invalid or expired reset token.", "error")
        return redirect(url_for("forgot_password"))

    if request.method == "POST":
        password = request.form["password"]
        confirm_password = request.form["confirm_password"]

        if password != confirm_password:
            flash("Passwords do not match.", "error")
            return redirect(url_for("reset_password", token=token))

        # Hash the new password
        hashed_password = generate_password_hash(password)

        conn = get_db_connection()
        if not conn:
            flash("Database connection failed. Please try again later.", "error")
            return redirect(url_for("reset_password", token=token))

        cur = conn.cursor()
        try:
            cur.execute("UPDATE users SET password = %s WHERE email = %s", (hashed_password, email))
            conn.commit()
            flash("Your password has been reset successfully.", "success")
            del reset_tokens[token]  # Remove the token after use
            return redirect(url_for("login"))
        except Exception as e:
            flash(f"An error occurred: {str(e)}", "error")
        finally:
            cur.close()
            conn.close()

    return render_template("reset_password.html")

@app.route("/logout")
@login_required
def logout():
    logout_user()
    flash("You have been logged out.", "success")
    return redirect(url_for("home"))

@app.route("/dashboard")
@login_required
def dashboard():
    return render_template("dashboard.html")

@app.route("/query", methods=["GET", "POST"])
@login_required
def query():
    exercise_id = request.args.get("exercise_id")  # Get exercise_id from the URL
    exercise_question = None
    if exercise_id:
        conn = get_db_connection()
        if not conn:
            flash("Database connection failed. Please try again later.", "error")
            return redirect(url_for("query"))

        cur = conn.cursor()
        cur.execute("SELECT question FROM exercises WHERE id = %s", (exercise_id,))
        exercise_question = cur.fetchone()[0]  # Fetch the exercise question
        cur.close()
        conn.close()

    if request.method == "POST":
        sql_query = request.form["sql_query"]

        conn = get_db_connection()
        if not conn:
            flash("Database connection failed. Please try again later.", "error")
            return redirect(url_for("query"))

        cur = conn.cursor()
        try:
            cur.execute(sql_query)
            result = cur.fetchall()
            columns = [desc[0] for desc in cur.description]
            cur.close()
            conn.close()
            return render_template("query.html", result=result, columns=columns, exercise_question=exercise_question)
        except Exception as e:
            cur.close()
            conn.close()
            return render_template("query.html", error=str(e), exercise_question=exercise_question)
    return render_template("query.html", exercise_question=exercise_question)

@app.route("/exercises")
@login_required
def exercises():
    conn = get_db_connection()
    if not conn:
        flash("Database connection failed. Please try again later.", "error")
        return redirect(url_for("dashboard"))

    cur = conn.cursor()
    try:
        cur.execute("SELECT * FROM exercises")
        exercises = cur.fetchall()
        print(f"Exercises: {exercises}")  # Debug statement
    except Exception as e:
        print(f"Error fetching exercises: {str(e)}")  # Debug statement
        exercises = []
    finally:
        cur.close()
        conn.close()

    return render_template("exercises.html", exercises=exercises)

@app.route("/submit_query/<int:exercise_id>", methods=["POST"])
@login_required
def submit_query(exercise_id):
    user_query = request.form["sql_query"]  # Get the user's query
    print(f"User Query: {user_query}")  # Debug statement

    conn = get_db_connection()
    if not conn:
        return jsonify({
            "message": "Database connection failed. Please try again later.",
            "user_query": user_query,
            "correct_query": "",
            "user_result": None,
            "correct_result": None
        })

    cur = conn.cursor()

    try:
        # Fetch the correct query for the exercise
        cur.execute("SELECT correct_query FROM exercises WHERE id = %s", (exercise_id,))
        correct_query = cur.fetchone()[0]
        print(f"Correct Query: {correct_query}")  # Debug statement

        # Execute the user's query
        cur.execute(user_query)
        user_result = cur.fetchall()
        user_columns = [desc[0] for desc in cur.description]
        print(f"User Query Result: {user_result}")  # Debug statement

        # Execute the correct query
        cur.execute(correct_query)
        correct_result = cur.fetchall()
        correct_columns = [desc[0] for desc in cur.description]
        print(f"Correct Query Result: {correct_result}")  # Debug statement

        # Compare the results
        is_correct = (user_result == correct_result)

        # Provide feedback to the user
        if is_correct:
            message = "Correct! Your query produced the expected results."
        else:
            message = "Incorrect. Your query did not produce the expected results."

        return jsonify({
            "message": message,
            "user_query": user_query,
            "correct_query": correct_query,
            "user_result": user_result,
            "correct_result": correct_result
        })

    except Exception as e:
        print(f"Query Error: {str(e)}")  # Debug statement
        error_message = str(e)
        if "column" in error_message and "does not exist" in error_message:
            error_message = "Invalid query: The column you referenced does not exist. Please check your query."
        return jsonify({
            "message": f"Error: {error_message}",
            "user_query": user_query,
            "correct_query": "",
            "user_result": None,
            "correct_result": None
        })
    finally:
        cur.close()
        conn.close()

@app.route("/download_pdf")
@login_required
def download_pdf():
    # Create a PDF
    buffer = BytesIO()
    pdf = SimpleDocTemplate(buffer, pagesize=letter)
    styles = getSampleStyleSheet()
    elements = []

    # Add a title
    title = Paragraph("Predefined Tables", styles['Title'])
    elements.append(title)

    # Fetch data from the database
    conn = get_db_connection()
    if not conn:
        flash("Database connection failed. Please try again later.", "error")
        return redirect(url_for("dashboard"))

    cur = conn.cursor()

    # Teams Table
    cur.execute("SELECT * FROM Teams")
    teams = cur.fetchall()
    teams_data = [["TeamID", "TeamName", "Country"]] + teams
    teams_table = Table(teams_data)
    teams_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
        ('GRID', (0, 0), (-1, -1), 1, colors.black),
    ]))
    elements.append(Paragraph("Teams Table", styles['Heading2']))
    elements.append(teams_table)

    # Players Table
    cur.execute("SELECT * FROM Players")
    players = cur.fetchall()
    players_data = [["PlayerID", "PlayerName", "TeamID", "Role"]] + players
    players_table = Table(players_data)
    players_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
        ('GRID', (0, 0), (-1, -1), 1, colors.black),
    ]))
    elements.append(Paragraph("Players Table", styles['Heading2']))
    elements.append(players_table)

    # Matches Table
    cur.execute("SELECT * FROM Matches")
    matches = cur.fetchall()
    matches_data = [["MatchID", "MatchDate", "Team1ID", "Team2ID", "Venue", "WinnerID"]] + matches
    matches_table = Table(matches_data)
    matches_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
        ('GRID', (0, 0), (-1, -1), 1, colors.black),
    ]))
    elements.append(Paragraph("Matches Table", styles['Heading2']))
    elements.append(matches_table)

    # Match Scores Table
    cur.execute("SELECT * FROM Match_Scores")
    match_scores = cur.fetchall()
    match_scores_data = [["ScoreID", "MatchID", "TeamID", "Runs", "Wickets", "Overs"]] + match_scores
    match_scores_table = Table(match_scores_data)
    match_scores_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
        ('GRID', (0, 0), (-1, -1), 1, colors.black),
    ]))
    elements.append(Paragraph("Match Scores Table", styles['Heading2']))
    elements.append(match_scores_table)

    # Match Results Table
    cur.execute("SELECT * FROM Match_Results")
    match_results = cur.fetchall()
    match_results_data = [["ResultID", "MatchID", "WinnerID", "WinningMargin"]] + match_results
    match_results_table = Table(match_results_data)
    match_results_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
        ('GRID', (0, 0), (-1, -1), 1, colors.black),
    ]))
    elements.append(Paragraph("Match Results Table", styles['Heading2']))
    elements.append(match_results_table)

    # Build the PDF
    pdf.build(elements)

    # Prepare the response
    buffer.seek(0)
    return send_file(buffer, as_attachment=True, download_name="predefined_tables.pdf", mimetype="application/pdf")

if __name__ == "__main__":
    app.run(debug=False)  # Disable debug mode for production