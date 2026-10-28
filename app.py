from flask import Flask, render_template, request, redirect, url_for, flash
import sqlite3
import os

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "bookstore-demo-key")
DB = os.environ.get("DATABASE_PATH", "bookstore.db")

def connect():
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    return con

def init_db():
    with connect() as con:
        con.execute("""CREATE TABLE IF NOT EXISTS books (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            author TEXT NOT NULL,
            price REAL NOT NULL,
            stock INTEGER NOT NULL DEFAULT 0
        )""")
        con.execute("""CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            customer TEXT NOT NULL,
            book_id INTEGER NOT NULL,
            quantity INTEGER NOT NULL,
            status TEXT NOT NULL DEFAULT 'Placed',
            FOREIGN KEY(book_id) REFERENCES books(id)
        )""")
        if con.execute("SELECT COUNT(*) FROM books").fetchone()[0] == 0:
            con.executemany(
                "INSERT INTO books(title, author, price, stock) VALUES (?, ?, ?, ?)",
                [
                    ("The Alchemist", "Paulo Coelho", 299.0, 10),
                    ("Wings of Fire", "A. P. J. Abdul Kalam", 250.0, 8),
                    ("Atomic Habits", "James Clear", 450.0, 12),
                ],
            )

@app.route("/", methods=["GET"])
def index():
    with connect() as con:
        books = con.execute("SELECT * FROM books ORDER BY id DESC").fetchall()
        orders = con.execute("""SELECT orders.*, books.title AS book_title
            FROM orders JOIN books ON books.id = orders.book_id
            ORDER BY orders.id DESC""").fetchall()
    return render_template("index.html", books=books, orders=orders)

@app.route("/books/add", methods=["POST"])
def add_book():
    title = request.form.get("title", "").strip()
    author = request.form.get("author", "").strip()
    try:
        price = float(request.form.get("price", "0"))
        stock = int(request.form.get("stock", "0"))
        if not title or not author or price < 0 or stock < 0:
            raise ValueError
        with connect() as con:
            con.execute(
                "INSERT INTO books(title, author, price, stock) VALUES (?, ?, ?, ?)",
                (title, author, price, stock),
            )
        flash("Book added successfully.")
    except (ValueError, TypeError):
        flash("Enter valid book details.")
    return redirect(url_for("index"))

@app.route("/books/<int:book_id>/update", methods=["POST"])
def update_book(book_id):
    title = request.form.get("title", "").strip()
    author = request.form.get("author", "").strip()
    try:
        price = float(request.form.get("price", "0"))
        stock = int(request.form.get("stock", "0"))
        if not title or not author or price < 0 or stock < 0:
            raise ValueError
        with connect() as con:
            con.execute(
                "UPDATE books SET title=?, author=?, price=?, stock=? WHERE id=?",
                (title, author, price, stock, book_id),
            )
        flash("Book updated.")
    except (ValueError, TypeError):
        flash("Enter valid book details.")
    return redirect(url_for("index"))

@app.route("/books/<int:book_id>/delete", methods=["POST"])
def delete_book(book_id):
    with connect() as con:
        # Keep books referenced by orders so order history remains valid.
        has_orders = con.execute(
            "SELECT 1 FROM orders WHERE book_id=? LIMIT 1", (book_id,)
        ).fetchone()
        if has_orders:
            flash("Cannot delete a book with orders. Update its stock instead.")
        else:
            con.execute("DELETE FROM books WHERE id=?", (book_id,))
            flash("Book deleted.")
    return redirect(url_for("index"))

@app.route("/orders/add", methods=["POST"])
def add_order():
    customer = request.form.get("customer", "").strip()
    try:
        book_id = int(request.form.get("book_id", "0"))
        quantity = int(request.form.get("quantity", "0"))
        if not customer or quantity <= 0:
            raise ValueError
        with connect() as con:
            book = con.execute(
                "SELECT stock FROM books WHERE id=?", (book_id,)
            ).fetchone()
            if not book:
                flash("Please select a valid book.")
            elif book["stock"] < quantity:
                flash("Insufficient stock for this order.")
            else:
                con.execute(
                    "INSERT INTO orders(customer, book_id, quantity) VALUES (?, ?, ?)",
                    (customer, book_id, quantity),
                )
                con.execute(
                    "UPDATE books SET stock=stock-? WHERE id=?",
                    (quantity, book_id),
                )
                flash("Order placed successfully.")
    except (ValueError, TypeError):
        flash("Enter a valid customer and quantity.")
    return redirect(url_for("index"))

# ── Database Dashboard ────────────────────────────────────────────────────────

def _get_tables(con):
    return [r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name").fetchall()]

@app.route("/database")
def db_dashboard():
    with connect() as con:
        tables = _get_tables(con)
        stats = {t: con.execute(f"SELECT COUNT(*) FROM [{t}]").fetchone()[0] for t in tables}
        schema = {t: con.execute(f"PRAGMA table_info([{t}])").fetchall() for t in tables}
    return render_template("database.html", tables=tables, stats=stats, schema=schema,
                           active_table=None, rows=None, columns=None, query="", query_result=None, error=None)

@app.route("/database/table/<table_name>")
def db_table(table_name):
    with connect() as con:
        tables = _get_tables(con)
        if table_name not in tables:
            flash("Table not found.")
            return redirect(url_for("db_dashboard"))
        stats  = {t: con.execute(f"SELECT COUNT(*) FROM [{t}]").fetchone()[0] for t in tables}
        schema = {t: con.execute(f"PRAGMA table_info([{t}])").fetchall() for t in tables}
        cur    = con.execute(f"SELECT * FROM [{table_name}] LIMIT 200")
        columns = [d[0] for d in cur.description]
        rows    = cur.fetchall()
    return render_template("database.html", tables=tables, stats=stats, schema=schema,
                           active_table=table_name, rows=rows, columns=columns,
                           query="", query_result=None, error=None)

@app.route("/database/query", methods=["POST"])
def db_query():
    sql = request.form.get("sql", "").strip()
    with connect() as con:
        tables = _get_tables(con)
        stats  = {t: con.execute(f"SELECT COUNT(*) FROM [{t}]").fetchone()[0] for t in tables}
        schema = {t: con.execute(f"PRAGMA table_info([{t}])").fetchall() for t in tables}
    columns, rows, error = None, None, None
    if sql:
        try:
            with connect() as con:
                cur = con.execute(sql)
                if cur.description:
                    columns = [d[0] for d in cur.description]
                    rows    = cur.fetchall()
                else:
                    flash(f"Query executed. Rows affected: {cur.rowcount}")
        except Exception as e:
            error = str(e)
    return render_template("database.html", tables=tables, stats=stats, schema=schema,
                           active_table=None, rows=rows, columns=columns,
                           query=sql, query_result=rows, error=error)

# ──────────────────────────────────────────────────────────────────────────────

@app.route("/orders/<int:order_id>/status", methods=["POST"])
def update_order_status(order_id):
    status = request.form.get("status", "Placed")
    if status not in {"Placed", "Processing", "Shipped", "Completed", "Cancelled"}:
        flash("Invalid order status.")
    else:
        with connect() as con:
            con.execute("UPDATE orders SET status=? WHERE id=?", (status, order_id))
        flash("Order status updated.")
    return redirect(url_for("index"))

with app.app_context():
    init_db()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=False)

    import os
from flask import send_file, abort

@app.route("/download-db")
def download_db():
    # Set this to the exact path your app uses
    db_path = os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        "bookstore.db"
    )

    if not os.path.isfile(db_path):
        abort(404, "Database file not found")

    return send_file(
        db_path,
        as_attachment=True,
        download_name="bookstore.db"
    )
