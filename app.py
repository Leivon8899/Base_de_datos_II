from flask import Flask, render_template, request, redirect, url_for
from routes.user_routes import user_bp
from routes.cart_routes import cart_bp
from routes.order_routes import order_bp
from routes.product_routes import product_bp
from utils.db import get_db
from models.product import Product
from models.cart import Cart

app = Flask(__name__)

# Registrar blueprints
app.register_blueprint(user_bp, url_prefix='/api')
app.register_blueprint(cart_bp, url_prefix='/api')
app.register_blueprint(order_bp, url_prefix='/api')
app.register_blueprint(product_bp, url_prefix='/api')

def get_cart_count():
    db = get_db()
    cart_model = Cart(db)
    items = cart_model.get_cart("default_cart")
    if items:
        return sum(item["quantity"] for item in items)
    return 0

@app.context_processor
def inject_cart_count():
    return dict(cart_count=get_cart_count())

@app.route('/')
def index():
    return "Welcome to the API"

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

@app.route('/add_to_cart', methods=['POST'])
def add_to_cart():
    product_id = request.form['product_id']
    quantity = int(request.form['quantity'])

    db = get_db()
    cart_model = Cart(db)
    
    cart_id = "default_cart"
    cart_model.add_to_cart(cart_id, product_id, quantity)
    
    return redirect(url_for('products_page'))

@app.route('/cart')
def view_cart():
    db = get_db()
    cart_model = Cart(db)
    items = cart_model.get_cart("default_cart")
    return render_template('cart.html', items=items)

@app.route('/checkout', methods=['GET'])
def checkout():
    db = get_db()
    cart_model = Cart(db)
    items = cart_model.get_cart("default_cart")
    total = sum(item['quantity'] * get_product_price(item['productId'], db) for item in items)
    return render_template('checkout.html', items=items, total=total)

def get_product_price(product_id, db):
    product_model = Product(db)
    product = product_model.get_product(product_id)
    return product['price']

@app.route('/process_payment', methods=['POST'])
def process_payment():
    payment_method = request.form['payment_method']
    installments = request.form.get('installments', '1')
    
    db = get_db()
    cart_model = Cart(db)
    items = cart_model.get_cart("default_cart")
    total = sum(item['quantity'] * get_product_price(item['productId'], db) for item in items)
    
    # Aquí es donde procesarías el pago usando una API de pago real.
    # Vamos a simularlo y simplemente registrar la información del pago en la base de datos.
    
    payment_info = {
        "payment_method": payment_method,
        "installments": int(installments),
        "total": total,
        "items": items
    }
    
    # Guardar la información del pago en una colección "payments" en MongoDB
    db.payments.insert_one(payment_info)
    
    # Vaciar el carrito después del pago
    cart_model.update_cart("default_cart", {"items": []})
    
    return render_template('payment_success.html', payment_info=payment_info)


@app.route('/remove_from_cart/<product_id>', methods=['POST'])
def remove_from_cart(product_id):
    db = get_db()
    cart_model = Cart(db)
    cart_id = "default_cart"
    cart_model.remove_from_cart(cart_id, product_id)
    return redirect(url_for('view_cart'))

@app.route('/test_mongo')
def test_mongo():
    db = get_db()
    try:
        db.command("ping")
        return "MongoDB connection successful!"
    except Exception as e:
        return str(e)

if __name__ == '__main__':
    app.run(debug=True)
