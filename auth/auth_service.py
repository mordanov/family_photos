import os
import psycopg2
import jwt
import datetime
from flask import Flask, request, jsonify
from google.auth.transport.requests import Request
from google.oauth2 import id_token

app = Flask(__name__)
app.config["SECRET_KEY"] = "super-secret-key"

# Get PostgreSQL credentials from environment variables
POSTGRES_HOST = os.getenv("POSTGRES_HOST", "db-service")  # Default to Docker service name
POSTGRES_USER = os.getenv("POSTGRES_USER", "pguser")
POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD", "password")  # Secure value expected
POSTGRES_DB = os.getenv("POSTGRES_DB", "auth_db")


# Utility function: Get a PostgreSQL connection
def get_db_connection():
    try:
        return psycopg2.connect(
            host=POSTGRES_HOST,
            database=POSTGRES_DB,
            user=POSTGRES_USER,
            password=POSTGRES_PASSWORD
        )
    except psycopg2.Error as e:
        print(f"Error connecting to PostgreSQL: {e}")
        raise


# Initialize PostgreSQL Database
def init_db():
    try:
        connection = get_db_connection()
        cursor = connection.cursor()

        # Create users table if it doesn't exist
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY,
                email TEXT UNIQUE NOT NULL
            )
            """
        )
        connection.commit()

        print("Database initialized successfully.")
    except psycopg2.Error as e:
        print(f"Database initialization error: {e}")
    finally:
        if connection:
            cursor.close()
            connection.close()


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
        try:
            connection = get_db_connection()
            cursor = connection.cursor()
            cursor.execute("SELECT email FROM users WHERE email = %s", (email,))
            user = cursor.fetchone()
        finally:
            if connection:
                cursor.close()
                connection.close()

        if not user:
            return jsonify({"error": "Unauthorized user"}), 403

        # Generate JWT
        payload = {
            "email": email,
            "exp": datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=1),
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
        connection = get_db_connection()
        cursor = connection.cursor()
        cursor.execute("INSERT INTO users (email) VALUES (%s)", (email,))
        connection.commit()

        return jsonify({"message": f"User {email} added successfully."})

    except psycopg2.IntegrityError:
        return jsonify({"error": f"User {email} is already authorized."}), 400

    except psycopg2.Error as e:
        return jsonify({"error": str(e)}), 500

    finally:
        if connection:
            cursor.close()
            connection.close()


if __name__ == "__main__":
    init_db()
    app.run(host="0.0.0.0", port=5000)