import sqlite3
import jwt
import datetime
from flask import Flask, request, jsonify
from google.auth.transport.requests import Request
from google.oauth2 import id_token

app = Flask(__name__)
app.config["SECRET_KEY"] = "super-secret-key"


# Initialize SQLite Database
def init_db():
    with sqlite3.connect("auth.db") as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT UNIQUE NOT NULL
            )
            """
        )
        conn.commit()


@app.route("/login", methods=["GET"])
def login():
    """Validate Google OAuth Token and issue JWT to authorized users."""
    token = request.args.get("id_token")
    if not token:
        return jsonify({"error": "Missing id_token"}), 400

    try:
        # Validate Google ID token
        idinfo = id_token.verify_oauth2_token(token, Request())
        email = idinfo["email"]

        # Check if the user is on the authorized list
        with sqlite3.connect("auth.db") as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT email FROM users WHERE email = ?", (email,))
            user = cursor.fetchone()

        if not user:
            return jsonify({"error": "Unauthorized user"}), 403

        # Generate JWT
        payload = {
            "email": email,
            "exp": datetime.datetime.now(datetime.UTC) + datetime.timedelta(hours=1),
        }
        token = jwt.encode(payload, app.config["SECRET_KEY"], algorithm="HS256")

        return jsonify({"token": token})

    except ValueError as e:
        return jsonify({"error": str(e)}), 400


@app.route("/validate-token", methods=["POST"])
def validate_token():
    """Validate a JWT and return its claims."""
    auth_header = request.headers.get("Authorization")
    if not auth_header:
        return jsonify({"error": "Missing Authorization header"}), 400

    token = auth_header.split(" ")[1]

    try:
        # Decode the JWT
        payload = jwt.decode(token, app.config["SECRET_KEY"], algorithms=["HS256"])
        return jsonify({"email": payload["email"]})

    except jwt.ExpiredSignatureError:
        return jsonify({"error": "Token has expired"}), 401

    except jwt.InvalidTokenError:
        return jsonify({"error": "Invalid token"}), 401


@app.route("/add-user", methods=["POST"])
def add_user():
    """Add a user to the authorized list (admin use only)."""
    data = request.json
    if "email" not in data:
        return jsonify({"error": "Missing email field"}), 400

    email = data["email"]

    try:
        with sqlite3.connect("auth.db") as conn:
            cursor = conn.cursor()
            cursor.execute("INSERT INTO users (email) VALUES (?)", (email,))
            conn.commit()

        return jsonify({"message": f"User {email} added successfully."})

    except sqlite3.IntegrityError:
        return jsonify({"error": f"User {email} is already authorized."}), 400


if __name__ == "__main__":
    init_db()
    app.run(host="0.0.0.0", port=5000)