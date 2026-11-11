"""
VSV Store - Main Flask Application
====================================
A full-featured grocery / supermart web application built with Flask.

Features:
  - Product catalog with categories
  - Shopping cart & checkout
  - Inventory management (admin)
  - User authentication (customer & admin)
  - Order history
  - Admin dashboard with sales statistics

Author : VSV Store Team
Stack  : Flask · SQLAlchemy · SQLite · Flask-Login
"""

import os
from datetime import datetime
from functools import wraps

from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    flash,
    jsonify,
    abort,
    session,
)
from flask_sqlalchemy import SQLAlchemy
from flask_login import (
    LoginManager,
    UserMixin,
    login_user,
    logout_user,
    login_required,
    current_user,
)
from werkzeug.security import generate_password_hash, check_password_hash

# ---------------------------------------------------------------------------
# App Configuration
# ---------------------------------------------------------------------------

basedir = os.path.abspath(os.path.dirname(__file__))

app = Flask(__name__)
app.config['SECRET_KEY'] = 'vsv-store-secret-key-change-in-production'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(basedir, 'vsv_store.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'
login_manager.login_message = 'Please log in to access this page.'
login_manager.login_message_category = 'warning'

# ---------------------------------------------------------------------------
# Database Models
# ---------------------------------------------------------------------------


class User(UserMixin, db.Model):
    """Represents a registered user (customer or admin)."""

    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False, index=True)
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(256), nullable=False)
    is_admin = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationships
    cart_items = db.relationship('CartItem', backref='user', lazy='dynamic',
                                cascade='all, delete-orphan')
    orders = db.relationship('Order', backref='user', lazy='dynamic',
                             cascade='all, delete-orphan')

    def set_password(self, password):
        """Hash and store the user's password."""
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        """Verify a plaintext password against the stored hash."""
        return check_password_hash(self.password_hash, password)

    def __repr__(self):
        return f'<User {self.username}>'


class Category(db.Model):
    """Product category (e.g. Fruits & Vegetables, Dairy & Eggs)."""

    __tablename__ = 'categories'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    description = db.Column(db.String(255), default='')
    image_url = db.Column(db.String(255), default='')

    # Relationships
    products = db.relationship('Product', backref='category', lazy='dynamic',
                               cascade='all, delete-orphan')

    def __repr__(self):
        return f'<Category {self.name}>'


class Product(db.Model):
    """A product listed in the store."""

    __tablename__ = 'products'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False, index=True)
    description = db.Column(db.Text, default='')
    price = db.Column(db.Float, nullable=False)            # Price in INR (₹)
    stock = db.Column(db.Integer, default=0)
    image_url = db.Column(db.String(255), default='')
    category_id = db.Column(db.Integer, db.ForeignKey('categories.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f'<Product {self.name} ₹{self.price}>'


class CartItem(db.Model):
    """An item in a user's shopping cart."""

    __tablename__ = 'cart_items'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=False)
    quantity = db.Column(db.Integer, default=1)

    # Relationship to product
    product = db.relationship('Product', backref='cart_items')

    def __repr__(self):
        return f'<CartItem user={self.user_id} product={self.product_id} qty={self.quantity}>'


class Order(db.Model):
    """A placed order."""

    __tablename__ = 'orders'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    total_amount = db.Column(db.Float, nullable=False)
    status = db.Column(db.String(20), default='pending')   # pending / confirmed / delivered / cancelled
    address = db.Column(db.Text, nullable=False)
    phone = db.Column(db.String(20), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationships
    items = db.relationship('OrderItem', backref='order', lazy='dynamic',
                            cascade='all, delete-orphan')

    def __repr__(self):
        return f'<Order #{self.id} ₹{self.total_amount} [{self.status}]>'


class OrderItem(db.Model):
    """A single line-item within an order."""

    __tablename__ = 'order_items'

    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey('orders.id'), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    price = db.Column(db.Float, nullable=False)            # Price at time of purchase

    # Relationship to product
    product = db.relationship('Product', backref='order_items')

    def __repr__(self):
        return f'<OrderItem order={self.order_id} product={self.product_id}>'


# ---------------------------------------------------------------------------
# Flask-Login User Loader
# ---------------------------------------------------------------------------

@login_manager.user_loader
def load_user(user_id):
    """Callback used by Flask-Login to reload a user from the session."""
    return User.query.get(int(user_id))


# ---------------------------------------------------------------------------
# Decorators
# ---------------------------------------------------------------------------

def admin_required(f):
    """Decorator that restricts a route to admin users only."""
    @wraps(f)
    @login_required
    def decorated_function(*args, **kwargs):
        if not current_user.is_admin:
            flash('Access denied. Admin privileges required.', 'danger')
            return redirect(url_for('home'))
        return f(*args, **kwargs)
    return decorated_function


# ---------------------------------------------------------------------------
# Context Processors
# ---------------------------------------------------------------------------

@app.context_processor
def inject_cart_count():
    """Make the cart item count available in every template."""
    if current_user.is_authenticated:
        count = CartItem.query.filter_by(user_id=current_user.id).count()
    else:
        count = 0
    return dict(cart_count=count)


@app.context_processor
def inject_categories():
    """Make all categories available in every template for the navbar."""
    categories = Category.query.order_by(Category.name).all()
    return dict(all_categories=categories)


# ---------------------------------------------------------------------------
# Public Routes
# ---------------------------------------------------------------------------

@app.route('/')
def home():
    """Landing page – show featured products and categories."""
    categories = Category.query.order_by(Category.name).all()
    featured_products = Product.query.filter(Product.stock > 0).limit(8).all()
    return render_template('home.html',
                           categories=categories,
                           featured_products=featured_products)


@app.route('/products')
def products():
    """List all products, optionally filtered by category or search query."""
    category_id = request.args.get('category', type=int)
    search_query = request.args.get('q', '').strip()
    sort_by = request.args.get('sort', 'name')  # name, price_low, price_high

    query = Product.query

    # Filter by category
    if category_id:
        query = query.filter_by(category_id=category_id)

    # Search by name or description
    if search_query:
        like_pattern = f'%{search_query}%'
        query = query.filter(
            db.or_(
                Product.name.ilike(like_pattern),
                Product.description.ilike(like_pattern),
            )
        )

    # Sorting
    if sort_by == 'price_low':
        query = query.order_by(Product.price.asc())
    elif sort_by == 'price_high':
        query = query.order_by(Product.price.desc())
    else:
        query = query.order_by(Product.name.asc())

    products_list = query.all()
    categories = Category.query.order_by(Category.name).all()
    active_category = Category.query.get(category_id) if category_id else None

    return render_template('products.html',
                           products=products_list,
                           categories=categories,
                           active_category=active_category,
                           search_query=search_query,
                           sort_by=sort_by)


@app.route('/product/<int:product_id>')
def product_detail(product_id):
    """Show detailed view of a single product."""
    product = Product.query.get_or_404(product_id)
    related_products = (
        Product.query
        .filter(Product.category_id == product.category_id,
                Product.id != product.id)
        .limit(4)
        .all()
    )
    return render_template('product_detail.html',
                           product=product,
                           related_products=related_products)


@app.route('/category/<int:category_id>')
def category_products(category_id):
    """Show all products in a specific category."""
    category = Category.query.get_or_404(category_id)
    products_list = Product.query.filter_by(category_id=category_id).order_by(Product.name).all()
    return render_template('category.html',
                           category=category,
                           products=products_list)


# ---------------------------------------------------------------------------
# Authentication Routes
# ---------------------------------------------------------------------------

@app.route('/register', methods=['GET', 'POST'])
def register():
    """Register a new customer account."""
    if current_user.is_authenticated:
        return redirect(url_for('home'))

    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '')
        confirm_password = request.form.get('confirm_password', '')

        # Validation
        errors = []
        if not username or len(username) < 3:
            errors.append('Username must be at least 3 characters.')
        if not email or '@' not in email:
            errors.append('Please enter a valid email address.')
        if not password or len(password) < 6:
            errors.append('Password must be at least 6 characters.')
        if password != confirm_password:
            errors.append('Passwords do not match.')
        if User.query.filter_by(username=username).first():
            errors.append('Username already taken.')
        if User.query.filter_by(email=email).first():
            errors.append('Email already registered.')

        if errors:
            for error in errors:
                flash(error, 'danger')
            return render_template('register.html')

        # Create new user
        user = User(username=username, email=email)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()

        flash('Registration successful! Please log in.', 'success')
        return redirect(url_for('login'))

    return render_template('register.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    """Log in an existing user."""
    if current_user.is_authenticated:
        return redirect(url_for('home'))

    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')

        user = User.query.filter_by(username=username).first()

        if user and user.check_password(password):
            login_user(user)
            flash(f'Welcome back, {user.username}!', 'success')
            next_page = request.args.get('next')
            return redirect(next_page or url_for('home'))
        else:
            flash('Invalid username or password.', 'danger')

    return render_template('login.html')


@app.route('/logout')
@login_required
def logout():
    """Log out the current user."""
    logout_user()
    flash('You have been logged out.', 'info')
    return redirect(url_for('home'))


# ---------------------------------------------------------------------------
# Shopping Cart Routes
# ---------------------------------------------------------------------------

@app.route('/cart')
@login_required
def cart():
    """View the current user's shopping cart."""
    cart_items = (
        CartItem.query
        .filter_by(user_id=current_user.id)
        .join(Product)
        .all()
    )
    total = sum(item.product.price * item.quantity for item in cart_items)
    return render_template('cart.html', cart_items=cart_items, total=total)


@app.route('/cart/add/<int:product_id>', methods=['POST'])
@login_required
def add_to_cart(product_id):
    """Add a product to the cart (or increase quantity if already present)."""
    product = Product.query.get_or_404(product_id)
    quantity = request.form.get('quantity', 1, type=int)

    if quantity < 1:
        quantity = 1

    if product.stock < quantity:
        flash(f'Sorry, only {product.stock} units of "{product.name}" available.', 'warning')
        return redirect(url_for('product_detail', product_id=product_id))

    # Check if item already in cart
    cart_item = CartItem.query.filter_by(
        user_id=current_user.id, product_id=product_id
    ).first()

    if cart_item:
        new_qty = cart_item.quantity + quantity
        if new_qty > product.stock:
            flash(f'Cannot add more. Only {product.stock} units available.', 'warning')
            return redirect(url_for('cart'))
        cart_item.quantity = new_qty
    else:
        cart_item = CartItem(
            user_id=current_user.id,
            product_id=product_id,
            quantity=quantity,
        )
        db.session.add(cart_item)

    db.session.commit()
    flash(f'"{product.name}" added to your cart!', 'success')
    return redirect(url_for('cart'))


@app.route('/cart/update/<int:item_id>', methods=['POST'])
@login_required
def update_cart(item_id):
    """Update the quantity of a cart item."""
    cart_item = CartItem.query.get_or_404(item_id)

    # Ensure the item belongs to the current user
    if cart_item.user_id != current_user.id:
        abort(403)

    quantity = request.form.get('quantity', 1, type=int)

    if quantity < 1:
        # Remove item if quantity is zero or negative
        db.session.delete(cart_item)
        flash('Item removed from cart.', 'info')
    elif quantity > cart_item.product.stock:
        flash(f'Only {cart_item.product.stock} units available.', 'warning')
        cart_item.quantity = cart_item.product.stock
    else:
        cart_item.quantity = quantity

    db.session.commit()
    return redirect(url_for('cart'))


@app.route('/cart/remove/<int:item_id>', methods=['POST'])
@login_required
def remove_from_cart(item_id):
    """Remove an item from the cart entirely."""
    cart_item = CartItem.query.get_or_404(item_id)

    if cart_item.user_id != current_user.id:
        abort(403)

    db.session.delete(cart_item)
    db.session.commit()
    flash('Item removed from cart.', 'info')
    return redirect(url_for('cart'))


# ---------------------------------------------------------------------------
# Checkout & Order Routes
# ---------------------------------------------------------------------------

@app.route('/checkout', methods=['GET', 'POST'])
@login_required
def checkout():
    """Checkout – place an order from cart contents."""
    cart_items = (
        CartItem.query
        .filter_by(user_id=current_user.id)
        .join(Product)
        .all()
    )

    if not cart_items:
        flash('Your cart is empty.', 'warning')
        return redirect(url_for('products'))

    if request.method == 'POST':
        address = request.form.get('address', '').strip()
        phone = request.form.get('phone', '').strip()

        if not address:
            flash('Please enter a delivery address.', 'danger')
            total = sum(item.product.price * item.quantity for item in cart_items)
            return render_template('checkout.html', cart_items=cart_items, total=total)

        if not phone:
            flash('Please enter a phone number.', 'danger')
            total = sum(item.product.price * item.quantity for item in cart_items)
            return render_template('checkout.html', cart_items=cart_items, total=total)

        # Verify stock availability
        for item in cart_items:
            if item.quantity > item.product.stock:
                flash(f'"{item.product.name}" has only {item.product.stock} units left.', 'danger')
                return redirect(url_for('cart'))

        # Calculate total
        total_amount = sum(item.product.price * item.quantity for item in cart_items)

        # Create order
        order = Order(
            user_id=current_user.id,
            total_amount=total_amount,
            status='pending',
            address=address,
            phone=phone,
        )
        db.session.add(order)
        db.session.flush()  # Get order.id before adding items

        # Create order items and decrease stock
        for item in cart_items:
            order_item = OrderItem(
                order_id=order.id,
                product_id=item.product_id,
                quantity=item.quantity,
                price=item.product.price,
            )
            db.session.add(order_item)

            # Decrease product stock
            item.product.stock -= item.quantity

        # Clear the user's cart
        CartItem.query.filter_by(user_id=current_user.id).delete()

        db.session.commit()

        flash(f'Order #{order.id} placed successfully! Total: ₹{total_amount:.2f}', 'success')
        return redirect(url_for('order_detail', order_id=order.id))

    total = sum(item.product.price * item.quantity for item in cart_items)
    return render_template('checkout.html', cart_items=cart_items, total=total)


@app.route('/orders')
@login_required
def order_history():
    """View the current user's order history."""
    orders = (
        Order.query
        .filter_by(user_id=current_user.id)
        .order_by(Order.created_at.desc())
        .all()
    )
    return render_template('orders.html', orders=orders)


@app.route('/order/<int:order_id>')
@login_required
def order_detail(order_id):
    """View details of a specific order."""
    order = Order.query.get_or_404(order_id)

    # Customers can only view their own orders; admins can view any
    if order.user_id != current_user.id and not current_user.is_admin:
        abort(403)

    order_items = order.items.all()
    return render_template('order_detail.html', order=order, order_items=order_items)


# ---------------------------------------------------------------------------
# Admin Routes
# ---------------------------------------------------------------------------

@app.route('/admin')
@admin_required
def admin_dashboard():
    """Admin dashboard with key statistics."""
    total_products = Product.query.count()
    total_orders = Order.query.count()
    total_users = User.query.filter_by(is_admin=False).count()
    total_revenue = db.session.query(db.func.sum(Order.total_amount)).scalar() or 0

    recent_orders = (
        Order.query
        .order_by(Order.created_at.desc())
        .limit(10)
        .all()
    )

    low_stock_products = (
        Product.query
        .filter(Product.stock < 10)
        .order_by(Product.stock.asc())
        .all()
    )

    # Orders by status
    pending_orders = Order.query.filter_by(status='pending').count()
    confirmed_orders = Order.query.filter_by(status='confirmed').count()
    delivered_orders = Order.query.filter_by(status='delivered').count()
    cancelled_orders = Order.query.filter_by(status='cancelled').count()

    return render_template('admin/dashboard.html',
                           total_products=total_products,
                           total_orders=total_orders,
                           total_users=total_users,
                           total_revenue=total_revenue,
                           recent_orders=recent_orders,
                           low_stock_products=low_stock_products,
                           pending_orders=pending_orders,
                           confirmed_orders=confirmed_orders,
                           delivered_orders=delivered_orders,
                           cancelled_orders=cancelled_orders)


# --- Admin Product Management ---

@app.route('/admin/products')
@admin_required
def admin_products():
    """List all products for admin management."""
    products_list = Product.query.order_by(Product.name).all()
    return render_template('admin/products.html', products=products_list)


@app.route('/admin/product/add', methods=['GET', 'POST'])
@admin_required
def admin_add_product():
    """Add a new product."""
    categories = Category.query.order_by(Category.name).all()

    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        description = request.form.get('description', '').strip()
        price = request.form.get('price', 0, type=float)
        stock = request.form.get('stock', 0, type=int)
        image_url = request.form.get('image_url', '').strip()
        category_id = request.form.get('category_id', type=int)

        # Validation
        if not name:
            flash('Product name is required.', 'danger')
            return render_template('admin/product_form.html',
                                   categories=categories, action='Add')

        if price <= 0:
            flash('Price must be greater than zero.', 'danger')
            return render_template('admin/product_form.html',
                                   categories=categories, action='Add')

        if not category_id:
            flash('Please select a category.', 'danger')
            return render_template('admin/product_form.html',
                                   categories=categories, action='Add')

        product = Product(
            name=name,
            description=description,
            price=price,
            stock=stock,
            image_url=image_url,
            category_id=category_id,
        )
        db.session.add(product)
        db.session.commit()

        flash(f'Product "{name}" added successfully!', 'success')
        return redirect(url_for('admin_products'))

    return render_template('admin/product_form.html',
                           categories=categories, action='Add')


@app.route('/admin/product/edit/<int:product_id>', methods=['GET', 'POST'])
@admin_required
def admin_edit_product(product_id):
    """Edit an existing product."""
    product = Product.query.get_or_404(product_id)
    categories = Category.query.order_by(Category.name).all()

    if request.method == 'POST':
        product.name = request.form.get('name', '').strip()
        product.description = request.form.get('description', '').strip()
        product.price = request.form.get('price', 0, type=float)
        product.stock = request.form.get('stock', 0, type=int)
        product.image_url = request.form.get('image_url', '').strip()
        product.category_id = request.form.get('category_id', type=int)

        if not product.name:
            flash('Product name is required.', 'danger')
            return render_template('admin/product_form.html',
                                   product=product, categories=categories,
                                   action='Edit')

        if product.price <= 0:
            flash('Price must be greater than zero.', 'danger')
            return render_template('admin/product_form.html',
                                   product=product, categories=categories,
                                   action='Edit')

        db.session.commit()
        flash(f'Product "{product.name}" updated successfully!', 'success')
        return redirect(url_for('admin_products'))

    return render_template('admin/product_form.html',
                           product=product, categories=categories,
                           action='Edit')


@app.route('/admin/product/delete/<int:product_id>', methods=['POST'])
@admin_required
def admin_delete_product(product_id):
    """Delete a product."""
    product = Product.query.get_or_404(product_id)
    product_name = product.name

    db.session.delete(product)
    db.session.commit()

    flash(f'Product "{product_name}" deleted.', 'success')
    return redirect(url_for('admin_products'))


# --- Admin Category Management ---

@app.route('/admin/categories')
@admin_required
def admin_categories():
    """List all categories for admin management."""
    categories = Category.query.order_by(Category.name).all()
    return render_template('admin/categories.html', categories=categories)


@app.route('/admin/category/add', methods=['GET', 'POST'])
@admin_required
def admin_add_category():
    """Add a new category."""
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        description = request.form.get('description', '').strip()
        image_url = request.form.get('image_url', '').strip()

        if not name:
            flash('Category name is required.', 'danger')
            return render_template('admin/category_form.html', action='Add')

        if Category.query.filter_by(name=name).first():
            flash('A category with that name already exists.', 'danger')
            return render_template('admin/category_form.html', action='Add')

        category = Category(name=name, description=description, image_url=image_url)
        db.session.add(category)
        db.session.commit()

        flash(f'Category "{name}" added successfully!', 'success')
        return redirect(url_for('admin_categories'))

    return render_template('admin/category_form.html', action='Add')


@app.route('/admin/category/edit/<int:category_id>', methods=['GET', 'POST'])
@admin_required
def admin_edit_category(category_id):
    """Edit an existing category."""
    category = Category.query.get_or_404(category_id)

    if request.method == 'POST':
        category.name = request.form.get('name', '').strip()
        category.description = request.form.get('description', '').strip()
        category.image_url = request.form.get('image_url', '').strip()

        if not category.name:
            flash('Category name is required.', 'danger')
            return render_template('admin/category_form.html',
                                   category=category, action='Edit')

        db.session.commit()
        flash(f'Category "{category.name}" updated successfully!', 'success')
        return redirect(url_for('admin_categories'))

    return render_template('admin/category_form.html',
                           category=category, action='Edit')


@app.route('/admin/category/delete/<int:category_id>', methods=['POST'])
@admin_required
def admin_delete_category(category_id):
    """Delete a category (and all its products)."""
    category = Category.query.get_or_404(category_id)
    cat_name = category.name

    db.session.delete(category)
    db.session.commit()

    flash(f'Category "{cat_name}" and all its products deleted.', 'success')
    return redirect(url_for('admin_categories'))


# --- Admin Order Management ---

@app.route('/admin/orders')
@admin_required
def admin_orders():
    """List all orders for admin management."""
    status_filter = request.args.get('status', '')
    query = Order.query

    if status_filter:
        query = query.filter_by(status=status_filter)

    orders = query.order_by(Order.created_at.desc()).all()
    return render_template('admin/orders.html', orders=orders,
                           status_filter=status_filter)


@app.route('/admin/order/<int:order_id>/update-status', methods=['POST'])
@admin_required
def admin_update_order_status(order_id):
    """Update the status of an order."""
    order = Order.query.get_or_404(order_id)
    new_status = request.form.get('status', '').strip()

    valid_statuses = ['pending', 'confirmed', 'delivered', 'cancelled']
    if new_status not in valid_statuses:
        flash('Invalid status.', 'danger')
        return redirect(url_for('admin_orders'))

    old_status = order.status
    order.status = new_status

    # If cancelling, restore stock
    if new_status == 'cancelled' and old_status != 'cancelled':
        for item in order.items:
            item.product.stock += item.quantity

    db.session.commit()
    flash(f'Order #{order.id} status updated to "{new_status}".', 'success')
    return redirect(url_for('admin_orders'))


# --- Admin Users ---

@app.route('/admin/users')
@admin_required
def admin_users():
    """List all registered users."""
    users = User.query.order_by(User.created_at.desc()).all()
    return render_template('admin/users.html', users=users)


# ---------------------------------------------------------------------------
# Error Handlers
# ---------------------------------------------------------------------------

@app.errorhandler(404)
def not_found(e):
    """Handle 404 errors."""
    return render_template('errors/404.html'), 404


@app.errorhandler(403)
def forbidden(e):
    """Handle 403 errors."""
    return render_template('errors/403.html'), 403


@app.errorhandler(500)
def server_error(e):
    """Handle 500 errors."""
    return render_template('errors/500.html'), 500


# ---------------------------------------------------------------------------
# Seed Data
# ---------------------------------------------------------------------------

def seed_database():
    """
    Populate the database with initial categories, sample products, and
    a default admin user.  Runs only when the database is empty.
    """

    # Skip if data already exists
    if User.query.first() is not None:
        return

    print('[VSV Store] Seeding database with initial data …')

    # ── Default admin user ──────────────────────────────────────────────
    admin = User(
        username='admin',
        email='admin@vsvstore.com',
        is_admin=True,
    )
    admin.set_password('admin123')
    db.session.add(admin)

    # ── Categories ──────────────────────────────────────────────────────
    categories_data = [
        {
            'name': 'Fruits & Vegetables',
            'description': 'Fresh fruits and vegetables sourced daily',
            'image_url': '/static/images/categories/fruits-vegetables.jpg',
        },
        {
            'name': 'Dairy & Eggs',
            'description': 'Milk, cheese, butter, eggs and more',
            'image_url': '/static/images/categories/dairy-eggs.jpg',
        },
        {
            'name': 'Snacks & Beverages',
            'description': 'Chips, biscuits, juices, soft drinks and more',
            'image_url': '/static/images/categories/snacks-beverages.jpg',
        },
        {
            'name': 'Household & Cleaning',
            'description': 'Detergents, cleaners, and household essentials',
            'image_url': '/static/images/categories/household-cleaning.jpg',
        },
        {
            'name': 'Bakery',
            'description': 'Fresh bread, cakes, pastries and baked goods',
            'image_url': '/static/images/categories/bakery.jpg',
        },
        {
            'name': 'Personal Care',
            'description': 'Soaps, shampoos, skincare and grooming products',
            'image_url': '/static/images/categories/personal-care.jpg',
        },
    ]

    category_objects = {}
    for cat_data in categories_data:
        cat = Category(**cat_data)
        db.session.add(cat)
        category_objects[cat_data['name']] = cat

    db.session.flush()  # Assign IDs to categories

    # ── Sample Products (prices in INR ₹) ──────────────────────────────
    products_data = [
        # Fruits & Vegetables
        {'name': 'Fresh Bananas (1 dozen)', 'description': 'Ripe yellow bananas, perfect for smoothies and snacking.', 'price': 40.00, 'stock': 100, 'image_url': '/static/images/products/bananas.jpg', 'category': 'Fruits & Vegetables'},
        {'name': 'Red Tomatoes (1 kg)', 'description': 'Juicy red tomatoes, ideal for curries and salads.', 'price': 30.00, 'stock': 80, 'image_url': '/static/images/products/tomatoes.jpg', 'category': 'Fruits & Vegetables'},
        {'name': 'Fresh Spinach (500 g)', 'description': 'Organic green spinach leaves, washed and ready to cook.', 'price': 25.00, 'stock': 60, 'image_url': '/static/images/products/spinach.jpg', 'category': 'Fruits & Vegetables'},
        {'name': 'Royal Gala Apples (1 kg)', 'description': 'Crisp and sweet imported apples.', 'price': 180.00, 'stock': 50, 'image_url': '/static/images/products/apples.jpg', 'category': 'Fruits & Vegetables'},

        # Dairy & Eggs
        {'name': 'Amul Toned Milk (1 L)', 'description': 'Pasteurised toned milk, 3% fat.', 'price': 54.00, 'stock': 120, 'image_url': '/static/images/products/milk.jpg', 'category': 'Dairy & Eggs'},
        {'name': 'Amul Butter (500 g)', 'description': 'Creamy salted butter, great for parathas and toast.', 'price': 270.00, 'stock': 40, 'image_url': '/static/images/products/butter.jpg', 'category': 'Dairy & Eggs'},
        {'name': 'Farm Fresh Eggs (12 pcs)', 'description': 'Free-range brown eggs, protein-rich.', 'price': 84.00, 'stock': 90, 'image_url': '/static/images/products/eggs.jpg', 'category': 'Dairy & Eggs'},

        # Snacks & Beverages
        {'name': 'Lay\'s Classic Salted Chips (130 g)', 'description': 'Crispy salted potato chips, a timeless snack.', 'price': 40.00, 'stock': 150, 'image_url': '/static/images/products/lays.jpg', 'category': 'Snacks & Beverages'},
        {'name': 'Coca-Cola (750 ml)', 'description': 'Chilled sparkling cola drink.', 'price': 38.00, 'stock': 200, 'image_url': '/static/images/products/coke.jpg', 'category': 'Snacks & Beverages'},
        {'name': 'Parle-G Biscuits (800 g)', 'description': 'India\'s favourite glucose biscuits — value family pack.', 'price': 74.00, 'stock': 180, 'image_url': '/static/images/products/parleg.jpg', 'category': 'Snacks & Beverages'},

        # Household & Cleaning
        {'name': 'Surf Excel Matic (2 kg)', 'description': 'Front-load washing machine detergent powder.', 'price': 410.00, 'stock': 45, 'image_url': '/static/images/products/surf.jpg', 'category': 'Household & Cleaning'},
        {'name': 'Vim Dishwash Gel (750 ml)', 'description': 'Lemon-fresh dishwashing liquid.', 'price': 125.00, 'stock': 70, 'image_url': '/static/images/products/vim.jpg', 'category': 'Household & Cleaning'},

        # Bakery
        {'name': 'Whole Wheat Bread (400 g)', 'description': 'Soft whole wheat sandwich bread, preservative-free.', 'price': 45.00, 'stock': 60, 'image_url': '/static/images/products/bread.jpg', 'category': 'Bakery'},
        {'name': 'Chocolate Muffins (Pack of 4)', 'description': 'Soft and moist chocolate chip muffins.', 'price': 120.00, 'stock': 35, 'image_url': '/static/images/products/muffins.jpg', 'category': 'Bakery'},

        # Personal Care
        {'name': 'Dove Soap (3 × 100 g)', 'description': 'Moisturising beauty bar with ¼ cream.', 'price': 171.00, 'stock': 80, 'image_url': '/static/images/products/dove.jpg', 'category': 'Personal Care'},
        {'name': 'Head & Shoulders Shampoo (340 ml)', 'description': 'Anti-dandruff shampoo for clean, flake-free hair.', 'price': 289.00, 'stock': 55, 'image_url': '/static/images/products/shampoo.jpg', 'category': 'Personal Care'},
        {'name': 'Colgate MaxFresh Toothpaste (150 g)', 'description': 'Cooling crystal toothpaste for fresh breath.', 'price': 95.00, 'stock': 110, 'image_url': '/static/images/products/colgate.jpg', 'category': 'Personal Care'},
    ]

    for prod_data in products_data:
        cat_name = prod_data.pop('category')
        product = Product(**prod_data, category_id=category_objects[cat_name].id)
        db.session.add(product)

    db.session.commit()
    print(f'[VSV Store] Seeded {len(categories_data)} categories and '
          f'{len(products_data)} products.')


# ---------------------------------------------------------------------------
# Application Entry Point
# ---------------------------------------------------------------------------

with app.app_context():
    db.create_all()
    seed_database()


if __name__ == '__main__':
    app.run(debug=True, port=5000)
