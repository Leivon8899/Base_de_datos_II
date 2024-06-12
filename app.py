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
from models.invoice import Invoice
from decorator.decorators import admin_required
import os
from bson import json_util, ObjectId
from datetime import datetime, timedelta

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
    db = get_db()
    product_model = Product(db)
    products = product_model.get_active_products()  
    return render_template('home.html', products=products)

@app.route('/products')
def products_page():
    db = get_db()
    product_model = Product(db)
    products = product_model.get_active_products()
    return render_template('products.html', products=products)

@app.route('/product/<product_id>')
def product_detail(product_id):
    db = get_db()
    product_model = Product(db)
    product = product_model.get_product(product_id)
    if not product:
        return "Product not found", 404
    return render_template('product_detail.html', product=product)

@app.route('/search')
def search():
    query = request.args.get('q')
    db = get_db()
    product_model = Product(db)
    products = list(product_model.collection.find({"name": {"$regex": query, "$options": "i"}}))
    return render_template('products.html', products=products)

@app.route('/admin/products')
@admin_required
def admin_products_page():
    db = get_db()
    product_model = Product(db)
    products = product_model.get_active_products_admin()
    return render_template('admin_products.html', products=products)

@app.route('/admin/add_product', methods=['GET', 'POST'])
@admin_required
def add_product():
    if request.method == 'POST':
        name = request.form['name']
        price = float(request.form['price'])
        description = request.form['description']
        stock = int(request.form['stock'])

        images = request.form.get('images').split(',')
        videos = request.form.get('videos').split(',')

        db = get_db()
        product_model = Product(db)
        product_data = {
            "productId": str(ObjectId()),  # Crear un nuevo productId
            "name": name,
            "price": price,
            "description": description,
            "stock": stock,
            "images": images,
            "videos": videos,
            "isDeleted": False
        }
        product_model.add_product(product_data)

        # Registrar acción en auditoría
        user_id = get_redis_client().get(f"session:{session['token']}").decode('utf-8')
        log_audit("create", product_data["productId"], user_id, f"Product '{name}' created")

        return redirect(url_for('admin_products_page'))

    return render_template('add_product.html')

@app.route('/admin/edit_product/<product_id>', methods=['GET', 'POST'])
@admin_required
def edit_product(product_id):
    db = get_db()
    product_model = Product(db)
    
    if request.method == 'POST':
        product = product_model.get_product(product_id)
        
        name = request.form['name']
        price = float(request.form['price'])
        description = request.form['description']
        stock = int(request.form['stock'])
        images = request.form.get('images').split(',')
        videos = request.form.get('videos').split(',')

        changes = []
        if name != product["name"]:
            changes.append({"field": "name", "old": product["name"], "new": name})
        if price != product["price"]:
            changes.append({"field": "price", "old": product["price"], "new": price})
        if stock != product["stock"]:
            changes.append({"field": "stock", "old": product["stock"], "new": stock})
        if description != product["description"]:
            changes.append({"field": "description", "old": product["description"], "new": description})
        if images != product["images"]:
            changes.append({"field": "images", "old": product["images"], "new": images})
        if videos != product["videos"]:
            changes.append({"field": "videos", "old": product["videos"], "new": videos})

        product_data = {
            "name": name,
            "price": price,
            "description": description,
            "stock": stock,
            "images": images,
            "videos": videos
        }
        product_model.update_product(product_id, product_data)

        # Registrar acción en auditoría
        user_id = get_redis_client().get(f"session:{session['token']}").decode('utf-8')
        log_audit("edit", product_id, user_id, f"Product '{name}' updated", changes)

        return redirect(url_for('admin_products_page'))

    product = product_model.get_product(product_id)
    return render_template('edit_product.html', product= product)

@app.route('/admin/delete_product/<product_id>', methods=['POST'])
@admin_required
def delete_product(product_id):
    db = get_db()
    product_model = Product(db)
    product = product_model.get_product(product_id)

    if product:
        product_model.delete_product(product_id)

        # Registrar acción en auditoría
        user_id = get_redis_client().get(f"session:{session['token']}").decode('utf-8')
        log_audit("delete", product_id, user_id, f"Product '{product['name']}' deleted")

    return redirect(url_for('admin_products_page'))

# Función para registrar auditoría
def log_audit(action, product_id, user_id, details, changes=None):
    db = get_db()
    audit_log = {
        "action": action,
        "product_id": product_id,
        "user_id": user_id,
        "timestamp": datetime.utcnow(),
        "details": details,
        "changes": changes  # Nuevo campo para registrar los cambios
    }
    db.audit_logs.insert_one(audit_log)

@app.route('/admin/audit_logs')
@admin_required
def view_audit_logs():
    db = get_db()
    audit_logs = list(db.audit_logs.find().sort("timestamp", -1))
    return render_template('admin_audit_logs.html', audit_logs=audit_logs)

@app.route('/admin/audit_logs/<product_id>')
@admin_required
def view_product_audit_logs(product_id):
    db = get_db()
    audit_logs = list(db.audit_logs.find({"product_id": product_id}).sort("timestamp", -1))
    product = db.products.find_one({"productId": product_id})
    return render_template('product_audit_logs.html', audit_logs=audit_logs, product=product)

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

@app.route('/checkout/<order_number>', methods=['GET'])
def checkout(order_number):
    if 'token' not in session:
        return redirect(url_for('auth.login'))
    
    redis_client = get_redis_client()
    user_id = redis_client.get(f"session:{session['token']}").decode('utf-8')
    db = get_db()
    
    order_model = Order(db)
    order = order_model.get_order(order_number)

    if not order:
        return "Order not found", 404

    # Obtener detalles del producto
    product_model = Product(db)
    detailed_items = []
    for item in order['items']:
        product = product_model.get_product(item['productId'])
        item_details = {
            "name": product['name'],
            "price": product['price'],
            "quantity": item['quantity']
        }
        detailed_items.append(item_details)

    total = sum(item['quantity'] * get_product_price(item['productId'], db) for item in order['items'])
    return render_template('checkout.html', items=detailed_items, total=total, order_number=order_number)

@app.route('/reset_password', methods=['GET', 'POST'])
def reset_password():
    if request.method == 'POST':
        name = request.form['name']
        dni = request.form['id_number']
        new_password = request.form['password']
        
        # Verificar que el nombre y el DNI coinciden
        user_id = redis_client.get(f"user_id:{name}:{dni}")
        if user_id:
            email = user_id.decode('utf-8')
            # Hashear la nueva contraseña
            hashed_password = generate_password_hash(new_password)
            # Actualizar la contraseña en Redis
            redis_client.hset(f"user:{email}", "password", hashed_password)
            return "Your password has been reset successfully."
        else:
            return "Invalid name or DNI."
    return render_template('reset_password.html')

def get_product_price(product_id, db):
    product_model = Product(db)
    product = product_model.get_product(product_id)
    return product['price']

@app.route('/error')
def error():
    return render_template('error.html')



@app.route('/process_payment/<order_number>', methods=['POST'])
def process_payment(order_number):
    if 'token' not in session:
        return redirect(url_for('auth.login'))
    
    redis_client = get_redis_client()
    user_id = redis_client.get(f"session:{session['token']}").decode('utf-8')

    user_name = redis_client.hget(f"user:{user_id}", "name").decode('utf-8')
    user_address = redis_client.hget(f"user:{user_id}", "address").decode('utf-8')

    payment_method = request.form['payment_method']
    installments = request.form.get('installments', '1')
    iva_value = float(request.form.get('iva_value', 0))
    final_total = float(request.form.get('final_total', 0))

    db = get_db()
    payment_model = Payment(db)
    order_model = Order(db)
    product_model = Product(db)
    invoice_model = Invoice(db) 
    iva_condition = request.form.get('iva_condition')  

    order = order_model.get_order(order_number)
    if not order:
        return "Order not found", 404

    total = order['total']
    
    # Aplicar recargo del 15% si el método de pago es tarjeta de crédito
    if payment_method == 'credit':
        total += total * 0.15

    payment_info = {
        "user_id": user_id,
        "payment_method": payment_method,
        "installments": int(installments),
        "total": total,
        "final_total": final_total,
        "items": order['items'],
        "order_number": int(order_number),
        "iva": iva_value
    }

    invoice_number = invoice_model.get_next_invoice_number()

    invoice_info = {
        "invoice_number": invoice_number,
        "user_id": user_id,
        "payment_method": payment_method,
        "installments": int(installments),
        "total": total,
        "final_total": final_total,
        "items": order['items'],
        "order_number": int(order_number),
        "iva": iva_value,
        "iva_condition": iva_condition
    }

    # Utilizar el modelo Payment para guardar la información del pago
    payment_model.insert_payment(payment_info)

    # Actualizar el estado de la orden a "Pagado"
    order_model.update_order_status(int(order_number), "Pagado")

    invoice_id = invoice_model.create_invoice(invoice_info)

    # Establecer un indicador de que el pago fue exitoso y guardar la información de pago en la sesión
    session['payment_completed'] = True
    session['payment_info'] = json_util.dumps(payment_info)  # Convertir a JSON
    session['invoice_id'] = invoice_id

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

@app.route('/admin/orders')
@admin_required
def view_all_orders():
    db = get_db()
    order_model = Order(db)
    orders = order_model.get_all_orders()
    return render_template('admin_orders.html', orders=orders)

@app.route('/user/orders')
def user_orders():
    if 'token' not in session:
        return redirect(url_for('auth.login'))
    
    redis_client = get_redis_client()
    user_id = redis_client.get(f"session:{session['token']}").decode('utf-8')
    
    db = get_db()
    order_model = Order(db)
    
    # Obtener las órdenes del usuario
    orders = order_model.get_orders_by_user(user_id)
    
    return render_template('user_orders.html', orders=orders)

@app.route('/create_order', methods=['POST'])
def create_order():
    if 'token' not in session:
        return redirect(url_for('auth.login'))
    
    redis_client = get_redis_client()
    db = get_db()

    user_id = redis_client.get(f"session:{session['token']}").decode('utf-8')
    user_name = redis_client.hget(f"user:{user_id}", "name").decode('utf-8')
    user_address = redis_client.hget(f"user:{user_id}", "address").decode('utf-8')

    order_number = redis_client.incr('order_number')
    print(order_number)

    cart_model = Cart(db)
    order_model = Order(db)
    product_model = Product(db)

    cart_model = Cart(db)
    cart_id = f"{user_id}"
    items = cart_model.get_cart(cart_id)  # Implementa esta función según tu lógica
    total = sum(item['quantity'] * get_product_price(item['productId'], db) for item in items)

    for item in items:
        item["productId"] = str(item["productId"])
        product = product_model.get_product(item["productId"])        
        if product["stock"] < item["quantity"]:
            # Maneja el caso donde no hay suficiente stock
            #products = product_model.get_active_products()
            return redirect(url_for('error')) #render_template('products.html', products=products)

    for item in items:
        product_model.decrement_stock(item["productId"], item["quantity"])

    order_info = {
        "order_number": order_number,
        "user_id": user_id,
        "name": user_name,
        "address": user_address,
        "items": items,
        "total": total,
        "status": "Pendiente de pago"
    }
        # Utilizar el modelo Order para guardar la información de la orden
    order_model.insert_order(order_info)
    cart_model.update_cart(cart_id, {"items": []})
    
    return redirect(url_for('view_order_details', order_id=order_number))


@app.route('/order/<order_id>') 
def view_order_details(order_id):
    if 'token' not in session:
        return redirect(url_for('auth.login'))
    
    db = get_db()
    order_model = Order(db)
    order = order_model.get_order(order_id)
    if not order:
        return "Order not found", 404
    return render_template('user_order_details.html', order=order)


@app.route('/admin/order/<order_id>') 
@admin_required
def view_admin_order_details(order_id):
    db = get_db()
    order_model = Order(db)
    order = order_model.get_order(order_id)
    if not order:
        return "Order not found", 404
    return render_template('admin_order_details.html', order=order)


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