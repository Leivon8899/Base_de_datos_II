from flask import Flask, render_template, request, redirect, url_for, session
from routes.user_routes import user_bp
from routes.cart_routes import cart_bp
from routes.order_routes import order_bp
from routes.product_routes import product_bp
from routes.auth_routes import auth_bp
from utils.db import get_db
from utils.redis_client import get_redis_client
from models.product import Product
from models.cart import Cart
from models.payment import Payment
from models.order import Order
from decorator.decorators import admin_required
import os
from bson import json_util

secret_key = os.urandom(24)

app = Flask(__name__)
app.secret_key = secret_key  # Necesario para usar sesiones en Flask

# Registrar blueprints
app.register_blueprint(user_bp, url_prefix='/api')
app.register_blueprint(cart_bp, url_prefix='/api')
app.register_blueprint(order_bp, url_prefix='/api')
app.register_blueprint(product_bp, url_prefix='/api')
app.register_blueprint(auth_bp, url_prefix='/auth')

def get_cart_count():
    if 'token' not in session:
        return 0
    redis_client = get_redis_client()
    user_id = redis_client.get(f"session:{session['token']}").decode('utf-8')
    db = get_db()
    cart_model = Cart(db)
    cart_id = f"{user_id}"
    items = cart_model.get_cart(cart_id)
    if items:
        return sum(item["quantity"] for item in items)
    return 0

@app.context_processor
def inject_user_role():
    if 'token' not in session:
        return dict(user_role=None)
    
    redis_client = get_redis_client()
    user_id = redis_client.get(f"session:{session['token']}").decode('utf-8')
    user_role = redis_client.hget(f"user:{user_id}", "role").decode('utf-8')
    
    return dict(user_role=user_role)

@app.context_processor
def inject_cart_count():
    return dict(cart_count=get_cart_count())

@app.route('/')
def index():
    return render_template('home.html')

@app.route('/products')
def products_page():
    db = get_db()
    product_model = Product(db)
    products = product_model.get_all_products()
    return render_template('products.html', products=products)

@app.route('/product/<product_id>')
def product_detail(product_id):
    db = get_db()
    product_model = Product(db)
    product = product_model.get_product(product_id)
    return render_template('product_detail.html', product=product)

@app.route('/admin/products')
@admin_required
def admin_products_page():
    db = get_db()
    product_model = Product(db)
    products = product_model.get_all_products()
    return render_template('admin_products.html', products=products)

@app.route('/admin/add_product', methods=['GET', 'POST'])
@admin_required
def add_product():
    if request.method == 'POST':
        name = request.form['name']
        price = float(request.form['price'])
        description = request.form['description']
        images = request.form.getlist('images')
        videos = request.form.getlist('videos')

        db = get_db()
        product_model = Product(db)
        product_data = {
            "name": name,
            "price": price,
            "description": description,
            "images": images,
            "videos": videos
        }
        product_model.add_product(product_data)
        return redirect(url_for('admin_products_page'))

    return render_template('add_product.html')

@app.route('/admin/edit_product/<product_id>', methods=['GET', 'POST'])
@admin_required
def edit_product(product_id):
    db = get_db()
    product_model = Product(db)
    
    if request.method == 'POST':
        name = request.form['name']
        price = float(request.form['price'])
        description = request.form['description']
        images = request.form.getlist('images')
        videos = request.form.getlist('videos')

        product_data = {
            "name": name,
            "price": price,
            "description": description,
            "images": images,
            "videos": videos
        }
        product_model.update_product(product_id, product_data)
        return redirect(url_for('admin_products_page'))

    product = product_model.get_product(product_id)
    return render_template('edit_product.html', product=product)

@app.route('/admin/delete_product/<product_id>', methods=['POST'])
@admin_required
def delete_product(product_id):
    db = get_db()
    product_model = Product(db)
    product_model.delete_product(product_id)
    return redirect(url_for('admin_products_page'))


@app.route('/add_to_cart', methods=['POST'])
def add_to_cart():
    if 'token' not in session:
        return redirect(url_for('auth.login'))
    
    redis_client = get_redis_client()
    user_id = redis_client.get(f"session:{session['token']}").decode('utf-8')
    product_id = request.form['product_id']
    product_name = request.form['name']
    quantity = int(request.form['quantity'])

    db = get_db()
    cart_model = Cart(db)
    cart_id = f"{user_id}"
    cart_model.add_to_cart(cart_id, product_id, quantity, product_name)
    
    return redirect(url_for('products_page'))

@app.route('/cart')
def view_cart():
    if 'token' not in session:
        return redirect(url_for('auth.login'))
    
    redis_client = get_redis_client()
    user_id = redis_client.get(f"session:{session['token']}").decode('utf-8')
    db = get_db()
    cart_model = Cart(db)
    cart_id = f"{user_id}"
    items = cart_model.get_cart(cart_id)
    return render_template('cart.html', items=items)

@app.route('/update_cart', methods=['POST'])
def update_cart():
    if 'token' not in session:
        return redirect(url_for('auth.login'))
    redis_client = get_redis_client()
    user_id = redis_client.get(f"session:{session['token']}").decode('utf-8')
    product_id = request.form['product_id']
    quantity = int(request.form['quantity'])

    db = get_db()
    cart_model = Cart(db)
    cart_id = f"{user_id}"
    cart_model.update_cart_quantity(cart_id, product_id, quantity)
    
    return redirect(url_for('view_cart'))

@app.route('/remove_from_cart/<product_id>', methods=['POST'])
def remove_from_cart(product_id):
    if 'token' not in session:
        return redirect(url_for('auth.login'))
    redis_client = get_redis_client()
    user_id = redis_client.get(f"session:{session['token']}").decode('utf-8')
    db = get_db()
    cart_model = Cart(db)
    cart_id = f"{user_id}"
    cart_model.remove_from_cart(cart_id, product_id)
    return redirect(url_for('view_cart'))

@app.route('/checkout', methods=['GET'])
def checkout():
    if 'token' not in session:
        return redirect(url_for('auth.login'))
    redis_client = get_redis_client()
    user_id = redis_client.get(f"session:{session['token']}").decode('utf-8')
    db = get_db()
    cart_model = Cart(db)
    cart_id = f"{user_id}"
    items = cart_model.get_cart(cart_id)

    # Obtener detalles del producto
    product_model = Product(db)
    detailed_items = []
    for item in items:
        product = product_model.get_product(item['productId'])
        item_details = {
            "name": product['name'],
            "price": product['price'],
            "quantity": item['quantity']
        }
        detailed_items.append(item_details)

    total = sum(item['quantity'] * get_product_price(item['productId'], db) for item in items)
    return render_template('checkout.html', items=detailed_items, total=total)

def get_product_price(product_id, db):
    product_model = Product(db)
    product = product_model.get_product(product_id)
    return product['price']

@app.route('/process_payment', methods=['POST'])
def process_payment():
    if 'token' not in session:
        return redirect(url_for('auth.login'))
    
    redis_client = get_redis_client()
    user_id = redis_client.get(f"session:{session['token']}").decode('utf-8')
    payment_method = request.form['payment_method']
    installments = request.form.get('installments', '1')
    db = get_db()
    cart_model = Cart(db)
    payment_model = Payment(db)
    order_model = Order(db)
    
    cart_id = f"{user_id}"
    items = cart_model.get_cart(cart_id)
    total = sum(item['quantity'] * get_product_price(item['productId'], db) for item in items)
    
    # Convertir ObjectId a string
    for item in items:
        item["productId"] = str(item["productId"])
        
    # Aplicar recargo del 15% si el método de pago es tarjeta de crédito
    if payment_method == 'credit':
        total += total * 0.15

    # Generar un número de orden único
    order_number = redis_client.incr('order_number')
        
    payment_info = {
        "user_id": user_id,
        "payment_method": payment_method,
        "installments": int(installments),
        "total": total,
        "items": items,
        "order_number": order_number
    }
        
    # Utilizar el modelo Payment para guardar la información del pago
    payment_model.insert_payment(payment_info)
        
    # Crear y guardar la orden en la colección "orders"
    order_info = {
        "order_number": order_number,
        "user_id": user_id,
        "items": items,
        "total": total,
        "payment_method": payment_method,
        "installments": int(installments),
        "status": "completed"
    }
        
    # Utilizar el modelo Order para guardar la información de la orden
    order_model.insert_order(order_info)
        
    # Vaciar el carrito después del pago
    cart_model.update_cart(cart_id, {"items": []})
    
    # Establecer un indicador de que el pago fue exitoso y guardar la información de pago en la sesión
    session['payment_completed'] = True
    session['payment_info'] = json_util.dumps(payment_info)  # Convertir a JSON
    
    return redirect(url_for('payment_success'))

@app.route('/payment_success')
def payment_success():
    # Verificar si el pago fue completado
    if 'payment_completed' in session and session['payment_completed']:
        # Obtener información de la sesión y luego eliminar el indicador de la sesión
        payment_info = json_util.loads(session.get('payment_info'))
        session.pop('payment_completed', None)
        session.pop('payment_info', None)
        return render_template('payment_success.html', payment_info=payment_info)
    else:
        return redirect(url_for('index'))

@app.route('/test_mongo')
def test_mongo():
    db = get_db()
    try:
        db.command("ping")
        return "MongoDB connection successful!"
    except Exception as e:
        return str(e)
    
@app.route('/test_redis')
def test_redis():
    redis = get_redis_client()
    try:
        redis.ping()
        return "Conexión a Redis exitosa."
    except Exception as e:
        return str(e)

if __name__ == '__main__':
    app.run(debug=True)
