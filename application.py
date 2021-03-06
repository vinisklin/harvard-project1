import os
import requests

from flask import Flask, session, render_template, request, jsonify
from flask_session import Session
from sqlalchemy import create_engine
from sqlalchemy.orm import scoped_session, sessionmaker

app = Flask(__name__)

# Check for environment variable
if not os.getenv("DATABASE_URL"):
    raise RuntimeError("DATABASE_URL is not set")

# Configure session to use filesystem
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
app.config["SECRET_KEY"] = "OCML3BRawWEUeaxcuKHLpw"

Session(app)

# Set up database
engine = create_engine(os.getenv("DATABASE_URL"))
db = scoped_session(sessionmaker(bind=engine))

# Goodreads API Key
GOODREADS_KEY = 'DjzoXWaQ4YWq84BgHFECUA'


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        # Read user's inputs
        name = request.form.get("name")
        username = request.form.get("username")
        password = request.form.get("password")

        # Check if username is already used
        if db.execute("SELECT * FROM users_table WHERE username = :username", {"username": username}).rowcount != 0:
            return render_template("registration.html", message="Username is already in use. Try another one :)", notRegistration=False)
        else:
            # Insert new user in users's table
            db.execute("INSERT INTO users_table (name, username, password) VALUES (:name, :username, :password)",
                       {"name": name, "username": username, "password": password})
            db.commit()
            return render_template("registration.html", message="Registered successfully!", notRegistration=False)
    else:
        return render_template("registration.html", notRegistration=False)


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        # Read user's inputs
        username = request.form.get("username")
        password = request.form.get("password")

        user = db.execute("SELECT * FROM users_table WHERE username = :username",
                        {"username": username}).fetchone()
        # Check if username is in DB
        if user == None:
            return render_template("index.html", message="Invalid username")
        else:
            # Check if password is correct
            if user.password != password:
                return render_template("index.html", message="Invalid password")
            else:
                # Start session for user
                session["user_id"] = user.id
                return render_template("login.html", name=user.name, notRegistration=True)
    
    else:
        # Check if user is logged in
        if not session.get("user_id"):
            return render_template("index.html", message="Please log in first")
        else:
            return render_template("login.html", notRegistration=True)

@app.route("/logout")
def logout():
    session.pop("user_id", None)
    return render_template("index.html")

@app.route("/search-results", methods=["POST"])
def search():
    # Read user's inputs
    isbn = request.form.get("searchByISBN")
    title = request.form.get("searchByTitle")
    author = request.form.get("searchByAuthor")

    # Check if inputs aren't empty
    if (isbn == "" and title == "" and author == ""):
        return render_template("login.html", errorMessage='Please fill at least one field', notRegistration=True)

    books = []
    # Query to DB depending on user data
    if (isbn != ""):
        isbn = '%' + isbn + '%'
        books = db.execute(
            "SELECT * FROM books_table WHERE isbn LIKE :isbn", {"isbn": isbn}).fetchall()
    else:
        # User is searching only by title
        if (author == ""):
            title = '%' + title + '%'
            books = db.execute(
                "SELECT * FROM books_table WHERE title LIKE :title", {"title": title}).fetchall()
        # User is searching only by author
        elif (title == ""):
            author = '%' + author + '%'
            books = db.execute(
                "SELECT * FROM books_table WHERE author LIKE :author", {"author": author}).fetchall()
        # User is searching by title AND author
        else:
            title = '%' + title + '%'
            author = '%' + author + '%'
            books = db.execute("SELECT * FROM books_table WHERE author LIKE :author AND title LIKE :title",
                               {"author": author, "title": title}).fetchall()

    return render_template("search-results.html", books=books, notRegistration=True)


@app.route("/search-results/<string:isbn>", methods=["GET", "POST"])
def book(isbn):
    # Displaying infos
    if request.method == "GET":
        # Get infos about the book
        book = db.execute(
            "SELECT * FROM books_table WHERE isbn = :isbn", {"isbn": isbn}).fetchone()
        if book == None:
            return render_template("book-response.html", message="This book is not in our database", notRegistration=True)
        else:
            # Get book reviews
            reviews = db.execute(
                "SELECT name, rate, review FROM reviews_table JOIN books_table ON books_table.id=reviews_table.book_id JOIN users_table ON users_table.id=reviews_table.user_id WHERE isbn = :isbn", 
                {"isbn": isbn}).fetchall()

            # Get Goodreads review statistics
            res = requests.get("https://www.goodreads.com/book/review_counts.json", params={"key": GOODREADS_KEY, "isbns": isbn})
            if res.status_code == 200:
                goodreadsReviews = res.json()["books"][0]

            return render_template("book-page.html", book=book, reviews=reviews, goodreadsReviews=goodreadsReviews, notRegistration=True)

    # Posting review
    else:
        # Check if user is logged in
        user_id = session.get("user_id")
        if not user_id:
            return render_template("book-response.html", message="You need to log in to publish a review", notRegistration=True)

        # Get book's id
        book_id_row = db.execute("SELECT id FROM books_table WHERE isbn = :isbn", {"isbn": isbn}).fetchone()
        if book_id_row == None:
            return render_template("book-response.html", message="This book is not in our database", notRegistration=True)
        book_id = book_id_row.values().pop()

        # Read user's review
        rate = request.form.get("reviewRate")
        reviewText = request.form.get("reviewText")

        # Check if review is not empty
        if (reviewText == ""):
            return render_template("book-response.html", message="You didn't write anything :(", notRegistration=True)
        else:
            # Check if user already reviewed this book
            if db.execute("SELECT * FROM reviews_table WHERE user_id = :user_id AND book_id = :book_id", 
                        {"user_id": user_id, "book_id": book_id}).fetchone() != None:
                return render_template("book-response.html", message="You already reviewed this book!", notRegistration=True)

            # Add review to database
            db.execute("INSERT INTO reviews_table (user_id, book_id, rate, review) VALUES (:user_id, :book_id, :rate, :review)",
                       {"user_id": user_id, "book_id": book_id, "rate": rate, "review": reviewText})
            db.commit()
            return render_template("book-response.html", message="Your review has been published successfully, Thank you!", notRegistration=True)

@app.route("/api/<string:isbn>")
def api_get_json(isbn):
    # Get book info from DB
    book_row = db.execute("SELECT title, author, year FROM books_table WHERE isbn = :isbn", {"isbn": isbn}).fetchone()
    # Send an 404 if book is not on DB
    if book_row == None:
        return jsonify({"error": "Invalid isbn"}), 404
    title = book_row.values()[0]
    author = book_row.values()[1]
    year = book_row.values()[2]

    # Get review info from Goodreads
    res = requests.get("https://www.goodreads.com/book/review_counts.json", params={"key": GOODREADS_KEY, "isbns": isbn})
    if res.status_code != 200:
        raise Exception ("ERROR: API request unsuccessful.")

    review_count = res.json()["books"][0]["work_ratings_count"]
    average_score = res.json()["books"][0]["average_rating"]

    # Return JSON
    return jsonify ({
        "title": title,
        "author": author,
        "year": year,
        "isbn": isbn,
        "review_count": review_count,
        "average_score": average_score
    })