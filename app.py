import os
import re
import secrets
import sqlite3
import unicodedata
import uuid
from functools import wraps
from pathlib import Path

from flask import (Flask, abort, flash, g, redirect, render_template, request,
                   send_from_directory, session, url_for)
from werkzeug.security import check_password_hash, generate_password_hash

BASE_DIR = Path(__file__).parent
# Em produção, aponte DATA_DIR para um disco/volume persistente.
DATA_DIR = Path(os.environ.get("DATA_DIR", BASE_DIR / "data"))
UPLOAD_DIR = DATA_DIR / "uploads"
DB_PATH = DATA_DIR / "ivone.db"
DATA_DIR.mkdir(parents=True, exist_ok=True)
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

ADMIN_USER = os.environ.get("ADMIN_USER", "ivone")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "")
ADMIN_HASH = generate_password_hash(ADMIN_PASSWORD) if ADMIN_PASSWORD else None
STORE_NAME = os.environ.get("STORE_NAME", "Ivone Lanches")
# WhatsApp que recebe os pedidos: só dígitos, com país e DDD. Ex.: 5581999999999
WHATSAPP_NUMBER = re.sub(r"\D", "", os.environ.get("WHATSAPP_NUMBER", ""))
MAX_QTY = 99

# Extensão -> assinatura (magic bytes) para validar que é imagem de verdade
IMAGE_SIGNATURES = {
    "jpg": [b"\xff\xd8\xff"],
    "jpeg": [b"\xff\xd8\xff"],
    "png": [b"\x89PNG\r\n\x1a\n"],
    "gif": [b"GIF87a", b"GIF89a"],
    "webp": [b"RIFF"],
}


def _secret_key():
    env = os.environ.get("SECRET_KEY")
    if env:
        return env
    key_file = DATA_DIR / "secret.key"
    if not key_file.exists():
        key_file.write_text(secrets.token_hex(32))
    return key_file.read_text().strip()


app = Flask(__name__)
app.config.update(
    SECRET_KEY=_secret_key(),
    MAX_CONTENT_LENGTH=6 * 1024 * 1024,  # 6 MB por envio
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=os.environ.get("COOKIE_SECURE", "0") == "1",
)


# ---------- Banco de dados ----------
def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


@app.teardown_appcontext
def close_db(_exc):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    db = sqlite3.connect(DB_PATH)
    db.executescript(
        """
        CREATE TABLE IF NOT EXISTS categories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            slug TEXT NOT NULL UNIQUE
        );
        CREATE TABLE IF NOT EXISTS items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            description TEXT NOT NULL DEFAULT '',
            price_cents INTEGER NOT NULL DEFAULT 0,
            category_id INTEGER NOT NULL REFERENCES categories(id),
            image TEXT,
            available INTEGER NOT NULL DEFAULT 1,
            track_stock INTEGER NOT NULL DEFAULT 0,
            stock INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        """
    )
    # Migração: bancos criados na versão anterior não tinham os campos de estoque
    cols = {row[1] for row in db.execute("PRAGMA table_info(items)")}
    if "track_stock" not in cols:
        db.execute("ALTER TABLE items ADD COLUMN track_stock INTEGER NOT NULL DEFAULT 0")
    if "stock" not in cols:
        db.execute("ALTER TABLE items ADD COLUMN stock INTEGER NOT NULL DEFAULT 0")
    if db.execute("SELECT COUNT(*) FROM categories").fetchone()[0] == 0:
        db.executemany(
            "INSERT INTO categories (name, slug) VALUES (?, ?)",
            [("Salgados", "salgados"), ("Doces", "doces")],
        )
    db.commit()
    db.close()


init_db()


# ---------- Utilidades ----------
def slugify(text):
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-") or "categoria"


def parse_price(raw):
    """Aceita '5', '5,50', '5.50', 'R$ 5,50' e devolve centavos (ou None)."""
    raw = (raw or "").replace("R$", "").strip().replace(" ", "")
    if "," in raw:
        raw = raw.replace(".", "").replace(",", ".")
    try:
        value = round(float(raw) * 100)
    except ValueError:
        return None
    return value if 0 <= value <= 10_000_000 else None


def format_price(cents):
    reais, centavos = divmod(int(cents), 100)
    return f"R$ {reais:,}".replace(",", ".") + f",{centavos:02d}"


def item_status(item):
    """'ok' (à venda), 'soldout' (estoque zerado) ou 'unavailable' (marcado indisponível)."""
    if not item["available"]:
        return "unavailable"
    if item["track_stock"] and item["stock"] <= 0:
        return "soldout"
    return "ok"


app.jinja_env.filters["brl"] = format_price
app.jinja_env.globals["item_status"] = item_status
app.jinja_env.globals["max_qty"] = lambda item: (
    min(item["stock"], MAX_QTY) if item["track_stock"] else MAX_QTY
)


def save_image(file_storage):
    """Valida e salva a imagem. Devolve o nome do arquivo, '' se não enviou, ou None se inválida."""
    if not file_storage or not file_storage.filename:
        return ""
    ext = file_storage.filename.rsplit(".", 1)[-1].lower() if "." in file_storage.filename else ""
    if ext not in IMAGE_SIGNATURES:
        return None
    head = file_storage.stream.read(12)
    file_storage.stream.seek(0)
    if not any(head.startswith(sig) for sig in IMAGE_SIGNATURES[ext]):
        return None
    if ext == "webp" and head[8:12] != b"WEBP":
        return None
    name = f"{uuid.uuid4().hex}.{ext}"
    file_storage.save(UPLOAD_DIR / name)
    return name


def delete_image(name):
    if name:
        try:
            (UPLOAD_DIR / name).unlink()
        except FileNotFoundError:
            pass


# ---------- Segurança: login + CSRF ----------
def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("admin"):
            return redirect(url_for("login", next=request.path))
        return view(*args, **kwargs)

    return wrapped


@app.before_request
def csrf_protect():
    if request.method == "POST":
        token = session.get("csrf")
        if not token or token != request.form.get("csrf"):
            abort(400, "Sessão expirada. Volte e tente de novo.")


@app.context_processor
def inject_globals():
    if "csrf" not in session:
        session["csrf"] = secrets.token_hex(16)
    return {
        "csrf_token": session["csrf"],
        "store_name": STORE_NAME,
        "is_admin": bool(session.get("admin")),
        "whatsapp": WHATSAPP_NUMBER,
    }


# ---------- Área pública ----------
@app.route("/")
def index():
    db = get_db()
    categories = db.execute("SELECT * FROM categories ORDER BY name").fetchall()
    selected = request.args.get("cat", "")
    # Todos os itens são enviados à página (o filtro esconde os de fora da categoria);
    # assim o carrinho continua válido ao trocar de categoria.
    items = db.execute(
        "SELECT i.*, c.name AS category_name, c.slug AS category_slug FROM items i "
        "JOIN categories c ON c.id = i.category_id ORDER BY c.name, i.name"
    ).fetchall()
    visible = sum(1 for it in items if not selected or it["category_slug"] == selected)
    return render_template("index.html", items=items, categories=categories, selected=selected, visible=visible)


@app.route("/uploads/<path:filename>")
def uploads(filename):
    return send_from_directory(UPLOAD_DIR, filename, max_age=60 * 60 * 24 * 30)


@app.route("/healthz")
def healthz():
    return "ok"


# ---------- Login ----------
@app.route("/login", methods=["GET", "POST"])
def login():
    if ADMIN_HASH is None:
        return render_template("login.html", error="ADMIN_PASSWORD não configurada no servidor."), 503
    error = None
    if request.method == "POST":
        user = request.form.get("user", "").strip()
        password = request.form.get("password", "")
        if user == ADMIN_USER and check_password_hash(ADMIN_HASH, password):
            session.clear()
            session["admin"] = True
            session["csrf"] = secrets.token_hex(16)
            nxt = request.args.get("next", "")
            return redirect(nxt if nxt.startswith("/admin") else url_for("admin"))
        error = "Usuário ou senha incorretos."
    return render_template("login.html", error=error)


@app.route("/logout", methods=["POST"])
def logout():
    session.clear()
    return redirect(url_for("index"))


# ---------- Admin ----------
@app.route("/admin")
@login_required
def admin():
    db = get_db()
    items = db.execute(
        "SELECT i.*, c.name AS category_name FROM items i "
        "JOIN categories c ON c.id = i.category_id ORDER BY i.created_at DESC, i.id DESC"
    ).fetchall()
    categories = db.execute(
        "SELECT c.*, (SELECT COUNT(*) FROM items WHERE category_id = c.id) AS total "
        "FROM categories c ORDER BY c.name"
    ).fetchall()
    return render_template("admin.html", items=items, categories=categories)


def _read_item_form():
    name = request.form.get("name", "").strip()
    description = request.form.get("description", "").strip()
    price = parse_price(request.form.get("price"))
    category_id = request.form.get("category_id", type=int)
    available = 1 if request.form.get("available") else 0
    track_stock = 1 if request.form.get("track_stock") else 0
    stock = request.form.get("stock", type=int)
    errors = []
    if not name:
        errors.append("Informe o nome do item.")
    if price is None:
        errors.append("Preço inválido. Exemplo: 5,50")
    if not category_id or not get_db().execute("SELECT 1 FROM categories WHERE id = ?", (category_id,)).fetchone():
        errors.append("Escolha uma categoria.")
    if track_stock:
        if stock is None or stock < 0 or stock > 100_000:
            errors.append("Informe a quantidade em estoque (0 ou mais).")
    else:
        stock = 0
    return (
        dict(name=name, description=description, price=price, category_id=category_id,
             available=available, track_stock=track_stock, stock=stock or 0),
        errors,
    )


@app.route("/admin/item/novo", methods=["POST"])
@login_required
def item_new():
    data, errors = _read_item_form()
    image = save_image(request.files.get("image"))
    if image is None:
        errors.append("Foto inválida. Use JPG, PNG, WEBP ou GIF de até 6 MB.")
    if errors:
        for e in errors:
            flash(e, "error")
        delete_image(image)
        return redirect(url_for("admin"))
    db = get_db()
    db.execute(
        "INSERT INTO items (name, description, price_cents, category_id, image, available, track_stock, stock) "
        "VALUES (?,?,?,?,?,?,?,?)",
        (data["name"], data["description"], data["price"], data["category_id"], image or None,
         data["available"], data["track_stock"], data["stock"]),
    )
    db.commit()
    flash(f"“{data['name']}” adicionado.", "ok")
    return redirect(url_for("admin"))


@app.route("/admin/item/<int:item_id>/editar", methods=["GET", "POST"])
@login_required
def item_edit(item_id):
    db = get_db()
    item = db.execute("SELECT * FROM items WHERE id = ?", (item_id,)).fetchone()
    if item is None:
        abort(404)
    if request.method == "POST":
        data, errors = _read_item_form()
        image = save_image(request.files.get("image"))
        if image is None:
            errors.append("Foto inválida. Use JPG, PNG, WEBP ou GIF de até 6 MB.")
        if errors:
            for e in errors:
                flash(e, "error")
            delete_image(image)
            return redirect(url_for("item_edit", item_id=item_id))
        new_image = image or item["image"]
        if image and item["image"]:
            delete_image(item["image"])
        db.execute(
            "UPDATE items SET name=?, description=?, price_cents=?, category_id=?, image=?, "
            "available=?, track_stock=?, stock=? WHERE id=?",
            (data["name"], data["description"], data["price"], data["category_id"], new_image,
             data["available"], data["track_stock"], data["stock"], item_id),
        )
        db.commit()
        flash("Item atualizado.", "ok")
        return redirect(url_for("admin"))
    categories = db.execute("SELECT * FROM categories ORDER BY name").fetchall()
    return render_template("item_edit.html", item=item, categories=categories)


@app.route("/admin/item/<int:item_id>/alternar", methods=["POST"])
@login_required
def item_toggle(item_id):
    db = get_db()
    db.execute("UPDATE items SET available = 1 - available WHERE id = ?", (item_id,))
    db.commit()
    return redirect(url_for("admin"))


@app.route("/admin/item/<int:item_id>/estoque", methods=["POST"])
@login_required
def item_stock(item_id):
    """Ajuste rápido da quantidade em estoque (só para itens com controle de estoque)."""
    stock = request.form.get("stock", type=int)
    if stock is None or stock < 0 or stock > 100_000:
        flash("Quantidade inválida. Use 0 ou mais.", "error")
        return redirect(url_for("admin"))
    db = get_db()
    db.execute("UPDATE items SET stock = ? WHERE id = ? AND track_stock = 1", (stock, item_id))
    db.commit()
    flash("Estoque atualizado.", "ok")
    return redirect(url_for("admin"))


@app.route("/admin/item/<int:item_id>/excluir", methods=["POST"])
@login_required
def item_delete(item_id):
    db = get_db()
    item = db.execute("SELECT image FROM items WHERE id = ?", (item_id,)).fetchone()
    if item:
        delete_image(item["image"])
        db.execute("DELETE FROM items WHERE id = ?", (item_id,))
        db.commit()
        flash("Item excluído.", "ok")
    return redirect(url_for("admin"))


@app.route("/admin/categoria/nova", methods=["POST"])
@login_required
def category_new():
    name = request.form.get("name", "").strip()
    if not name:
        flash("Informe o nome da categoria.", "error")
        return redirect(url_for("admin"))
    db = get_db()
    try:
        db.execute("INSERT INTO categories (name, slug) VALUES (?, ?)", (name, slugify(name)))
        db.commit()
        flash(f"Categoria “{name}” criada.", "ok")
    except sqlite3.IntegrityError:
        flash("Já existe uma categoria com esse nome.", "error")
    return redirect(url_for("admin"))


@app.route("/admin/categoria/<int:cat_id>/excluir", methods=["POST"])
@login_required
def category_delete(cat_id):
    db = get_db()
    total = db.execute("SELECT COUNT(*) FROM items WHERE category_id = ?", (cat_id,)).fetchone()[0]
    if total:
        flash("Essa categoria ainda tem itens. Mova ou exclua os itens antes.", "error")
    else:
        db.execute("DELETE FROM categories WHERE id = ?", (cat_id,))
        db.commit()
        flash("Categoria excluída.", "ok")
    return redirect(url_for("admin"))


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=os.environ.get("DEBUG") == "1")
