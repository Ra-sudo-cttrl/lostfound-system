import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Konfigurasi aplikasi
app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-secret-key-ubah-ini')
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'sqlite:///lostfound.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER'] = 'static/uploads'
app.config['MAX_CONTENT_LENGTH'] = 2 * 1024 * 1024
app.config['ALLOWED_EXTENSIONS'] = {'jpg', 'jpeg', 'png'}
import os
from datetime import datetime
from flask import Flask, render_template, redirect, url_for, flash, request, abort, session
from flask_sqlalchemy import SQLAlchemy
from flask_wtf import FlaskForm
from flask_wtf.file import FileField, FileAllowed
from wtforms import StringField, TextAreaField, SelectField, PasswordField
from wtforms.validators import DataRequired, Length, Regexp
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
import secrets

# Cek apakah PIL/Pillow tersedia
try:
    from PIL import Image
    HAS_PIL = True
except ImportError:
    HAS_PIL = False
    print("Peringatan: Pillow tidak terinstall. Gambar akan disimpan tanpa resize.")

# Konfigurasi aplikasi
app = Flask(__name__)
app.config['SECRET_KEY'] = 'dev-secret-key-ubah-di-production'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///lostfound.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER'] = 'static/uploads'
app.config['MAX_CONTENT_LENGTH'] = 2 * 1024 * 1024  # 2MB max file size
app.config['ALLOWED_EXTENSIONS'] = {'jpg', 'jpeg', 'png'}

# Pastikan folder uploads ada
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

db = SQLAlchemy(app)

# ===================== MODELS =====================
class User(db.Model):
    """Model untuk user (admin/mahasiswa)"""
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(120), nullable=False)
    is_admin = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationship
    items = db.relationship('Item', backref='author', lazy=True)
    
    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
    
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

class Item(db.Model):
    """Model untuk item hilang/ditemukan"""
    id = db.Column(db.Integer, primary_key=True)
    type = db.Column(db.String(10), nullable=False)  # 'lost' atau 'found'
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text, nullable=False)
    location = db.Column(db.String(100), nullable=False)
    contact = db.Column(db.String(20), nullable=False)
    image = db.Column(db.String(200), nullable=True)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    
    def __repr__(self):
        return f'<Item {self.name}>'

# ===================== FORMS =====================
class LoginForm(FlaskForm):
    """Form untuk login"""
    username = StringField('Username', validators=[DataRequired()])
    password = PasswordField('Password', validators=[DataRequired()])

class ItemForm(FlaskForm):
    """Form untuk input/edit item"""
    type = SelectField('Jenis', choices=[('lost', 'Barang Hilang'), ('found', 'Barang Ditemukan')], 
                      validators=[DataRequired()])
    name = StringField('Nama Barang', validators=[DataRequired(), Length(max=100)])
    description = TextAreaField('Deskripsi', validators=[DataRequired()])
    location = SelectField('Lokasi', choices=[
        ('', 'Pilih Lokasi'),
        ('gedung_a', 'Gedung A - Fakultas Teknik'),
        ('gedung_b', 'Gedung B - Fakultas Ekonomi'),
        ('gedung_c', 'Gedung C - Fakultas Hukum'),
        ('perpustakaan', 'Perpustakaan Pusat'),
        ('kantin', 'Kantin Utama'),
        ('lab_komputer', 'Lab Komputer'),
        ('auditorium', 'Auditorium'),
        ('lapangan', 'Lapangan Olahraga'),
        ('parkiran', 'Area Parkir'),
        ('lainnya', 'Lainnya (ketik sendiri)')
    ], validators=[DataRequired()])
    contact = StringField('Nomor WhatsApp', validators=[
        DataRequired(),
        Regexp(r'^[0-9+\-\s]{10,15}$', message='Format nomor tidak valid')
    ])
    image = FileField('Foto Barang', validators=[
        FileAllowed(['jpg', 'jpeg', 'png'], 'Hanya file gambar (JPG, JPEG, PNG) yang diizinkan')
    ])

# ===================== HELPER FUNCTIONS =====================
def allowed_file(filename):
    """Cek apakah ekstensi file diizinkan"""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']

def save_image(file):
    """Simpan gambar dengan nama random dan resize jika PIL tersedia"""
    if not file or file.filename == '':
        return None
    
    if allowed_file(file.filename):
        # Generate random filename
        random_hex = secrets.token_hex(8)
        _, f_ext = os.path.splitext(file.filename)
        filename = random_hex + f_ext
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        
        try:
            # Simpan file terlebih dahulu
            file.save(filepath)
            
            # Resize jika PIL tersedia
            if HAS_PIL:
                try:
                    output_size = (800, 800)
                    img = Image.open(filepath)
                    img.thumbnail(output_size)
                    img.save(filepath)
                except Exception as e:
                    print(f"Gagal resize gambar: {e}")
                    # Lanjutkan dengan gambar asli
            else:
                # Jika PIL tidak tersedia, simpan saja tanpa resize
                pass
                
        except Exception as e:
            print(f"Error menyimpan gambar: {e}")
            return None
        
        return filename
    return None

def get_location_value(form_location, request_form):
    """Ambil nilai lokasi dari form (bisa dari select atau input custom)"""
    # Cek apakah ada input custom dari request
    custom_location = request_form.get('location_custom', '').strip()
    
    if custom_location:
        # Gunakan nilai custom jika ada
        return custom_location
    elif form_location == 'lainnya':
        # Jika pilih "lainnya" tapi tidak isi custom, gunakan string kosong
        return ''
    else:
        # Gunakan nilai dari select
        return form_location

# ===================== ROUTES =====================
@app.route('/')
def index():
    """Halaman utama"""
    # Ambil 6 item terbaru dari masing-masing tipe
    lost_items = Item.query.filter_by(type='lost').order_by(Item.timestamp.desc()).limit(3).all()
    found_items = Item.query.filter_by(type='found').order_by(Item.timestamp.desc()).limit(3).all()
    
    return render_template('index.html', 
                         lost_items=lost_items, 
                         found_items=found_items)

@app.route('/login', methods=['GET', 'POST'])
def login():
    """Halaman login"""
    form = LoginForm()
    
    if form.validate_on_submit():
        user = User.query.filter_by(username=form.username.data).first()
        
        if user and user.check_password(form.password.data):
            # Simpan user di session
            session['user_id'] = user.id
            session['username'] = user.username
            session['is_admin'] = user.is_admin
            
            flash('Login berhasil!', 'success')
            return redirect(url_for('index'))
        else:
            flash('Username atau password salah!', 'danger')
    
    return render_template('login.html', form=form)

@app.route('/logout')
def logout():
    """Logout user"""
    session.clear()
    flash('Anda telah logout.', 'info')
    return redirect(url_for('index'))

@app.route('/add', methods=['GET', 'POST'])
def add_item():
    """Tambah item baru"""
    # Cek apakah user sudah login
    if 'user_id' not in session:
        flash('Harap login terlebih dahulu.', 'warning')
        return redirect(url_for('login'))
    
    form = ItemForm()
    
    if form.validate_on_submit():
        # Simpan gambar jika ada
        image_filename = None
        if form.image.data:
            image_filename = save_image(form.image.data)
        
        # Ambil nilai lokasi (bisa dari select atau input custom)
        location_value = get_location_value(form.location.data, request.form)
        
        if not location_value:
            flash('Harap isi lokasi.', 'danger')
            return render_template('add_item.html', form=form)
        
        # Buat item baru
        new_item = Item(
            type=form.type.data,
            name=form.type.data.capitalize() + ': ' + form.name.data,
            description=form.description.data,
            location=location_value,
            contact=form.contact.data.replace(' ', '').replace('-', '').replace('+', ''),
            image=image_filename,
            user_id=session['user_id']
        )
        
        db.session.add(new_item)
        db.session.commit()
        
        flash('Item berhasil ditambahkan!', 'success')
        return redirect(url_for('list_items', type=form.type.data))
    
    return render_template('add_item.html', form=form)

@app.route('/list/<string:type>')
def list_items(type):
    """List items dengan filter dan pagination"""
    if type not in ['lost', 'found']:
        abort(404)
    
    # Ambil parameter filter
    page = request.args.get('page', 1, type=int)
    search = request.args.get('search', '')
    location_filter = request.args.get('location', '')
    
    # Query dasar
    query = Item.query.filter_by(type=type)
    
    # Apply search filter
    if search:
        query = query.filter(Item.name.contains(search) | Item.description.contains(search))
    
    # Apply location filter
    if location_filter:
        query = query.filter_by(location=location_filter)
    
    # Pagination
    items = query.order_by(Item.timestamp.desc()).paginate(page=page, per_page=6, error_out=False)
    
    # Ambil semua lokasi unik untuk dropdown filter
    locations = db.session.query(Item.location).distinct().all()
    location_choices = [loc[0] for loc in locations]
    
    return render_template('list_items.html', 
                         items=items, 
                         type=type,
                         search=search,
                         location_filter=location_filter,
                         location_choices=location_choices)

@app.route('/item/<int:item_id>')
def item_detail(item_id):
    """Detail item"""
    item = Item.query.get_or_404(item_id)
    template = 'detail_lost.html' if item.type == 'lost' else 'detail_found.html'
    
    return render_template(template, item=item)

@app.route('/edit/<int:item_id>', methods=['GET', 'POST'])
def edit_item(item_id):
    """Edit item (admin only)"""
    # Cek apakah admin
    if not session.get('is_admin'):
        abort(403)
    
    item = Item.query.get_or_404(item_id)
    form = ItemForm(obj=item)
    
    # Atur nilai awal
    if request.method == 'GET':
        form.type.data = item.type
        form.name.data = item.name.replace(item.type.capitalize() + ': ', '')
        form.description.data = item.description
        
        # Tentukan apakah lokasi adalah custom atau dari pilihan
        predefined_locations = ['gedung_a', 'gedung_b', 'gedung_c', 'perpustakaan', 'kantin', 
                               'lab_komputer', 'auditorium', 'lapangan', 'parkiran', 'lainnya']
        
        if item.location in predefined_locations:
            form.location.data = item.location
        else:
            # Jika lokasi custom, set ke 'lainnya'
            form.location.data = 'lainnya'
        
        form.contact.data = item.contact
    
    if form.validate_on_submit():
        # Update data
        item.type = form.type.data
        item.name = form.type.data.capitalize() + ': ' + form.name.data
        item.description = form.description.data
        
        # Ambil nilai lokasi (bisa dari select atau input custom)
        location_value = get_location_value(form.location.data, request.form)
        if location_value:
            item.location = location_value
        
        item.contact = form.contact.data.replace(' ', '').replace('-', '').replace('+', '')
        
        # Update gambar jika ada yang baru
        if form.image.data:
            # Hapus gambar lama jika ada
            if item.image:
                old_image_path = os.path.join(app.config['UPLOAD_FOLDER'], item.image)
                if os.path.exists(old_image_path):
                    os.remove(old_image_path)
            
            # Simpan gambar baru
            item.image = save_image(form.image.data)
        
        db.session.commit()
        flash('Item berhasil diupdate!', 'success')
        return redirect(url_for('item_detail', item_id=item.id))
    
    return render_template('edit_item.html', form=form, item=item)

@app.route('/delete/<int:item_id>', methods=['POST'])
def delete_item(item_id):
    """Hapus item (admin only)"""
    # Cek apakah admin
    if not session.get('is_admin'):
        abort(403)
    
    item = Item.query.get_or_404(item_id)
    
    # Hapus gambar jika ada
    if item.image:
        image_path = os.path.join(app.config['UPLOAD_FOLDER'], item.image)
        if os.path.exists(image_path):
            os.remove(image_path)
    
    db.session.delete(item)
    db.session.commit()
    
    flash('Item berhasil dihapus!', 'success')
    return redirect(url_for('list_items', type=item.type))

# ===================== ERROR HANDLERS =====================
@app.errorhandler(404)
def not_found_error(error):
    return render_template('404.html'), 404

@app.errorhandler(403)
def forbidden_error(error):
    return render_template('403.html'), 403

# ===================== INITIAL SETUP =====================
def create_tables():
    """Buat tabel database"""
    with app.app_context():
        db.create_all()
        
        # Buat admin default jika belum ada
        if not User.query.filter_by(username='admin').first():
            admin = User(username='admin', is_admin=True)
            admin.set_password('admin123')
            db.session.add(admin)
        
        # Buat user mahasiswa contoh
        if not User.query.filter_by(username='mahasiswa').first():
            student = User(username='mahasiswa', is_admin=False)
            student.set_password('student123')
            db.session.add(student)
        
        db.session.commit()

if __name__ == '__main__':
    create_tables()
    app.run(debug=True)