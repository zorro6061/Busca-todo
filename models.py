from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

db = SQLAlchemy()

class Plano(db.Model):
    __tablename__ = 'planos'
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(100), nullable=False)
    imagen_path = db.Column(db.String(255), nullable=True) # El croquis/mapa
    ancho = db.Column(db.Integer, default=1000)
    alto = db.Column(db.Integer, default=1000)
    ubicaciones = db.relationship('Ubicacion', backref='plano', lazy=True)
    muebles = db.relationship('Mueble', backref='plano', lazy=True, cascade="all, delete-orphan")

class Ubicacion(db.Model):
    __tablename__ = 'ubicaciones'
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(100), nullable=False)
    imagen_path = db.Column(db.String(255), nullable=False)
    tags = db.Column(db.Text, nullable=True)
    fecha_creacion = db.Column(db.DateTime, default=datetime.utcnow)
    
    # OmniVision Fields
    plano_id = db.Column(db.Integer, db.ForeignKey('planos.id'), nullable=True)
    pos_x = db.Column(db.Integer, nullable=True) # Coordenada X en el plano
    pos_y = db.Column(db.Integer, nullable=True) # Coordenada Y en el plano
    pos_z = db.Column(db.Integer, default=0)    # Nivel o altura (0=suelo)
    items_json = db.Column(db.Text, nullable=True)  # JSON original de IA con bboxes
    
    objetos = db.relationship('Objeto', backref='ubicacion', lazy=True, cascade="all, delete-orphan")

    def __repr__(self):
        return f'<Ubicacion {self.nombre}>'

class Objeto(db.Model):
    __tablename__ = 'objetos'
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(100), nullable=False)
    categoria = db.Column(db.String(50), nullable=True)
    confianza = db.Column(db.Float, default=1.0)
    estado = db.Column(db.String(50), nullable=True)     # nuevo/usado/etc
    prioridad = db.Column(db.String(20), nullable=True)  # alta/media/baja
    ubicacion_id = db.Column(db.Integer, db.ForeignKey('ubicaciones.id'), nullable=False)
    fecha_indexacion = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relación con Zona (Mapa Anotado)
    zona_id = db.Column(db.Integer, db.ForeignKey('zonas.id'), nullable=True)

    def __repr__(self):
        return f'<Objeto {self.nombre}>'

class Zona(db.Model):
    __tablename__ = 'zonas'
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(100), nullable=False)
    tipo = db.Column(db.String(20), default='rect') # rect, poly
    
    # Coordenadas relativas (0-100%) en formato JSON: {"x": 10, "y": 20, "w": 30, "h": 15}
    coords_json = db.Column(db.Text, nullable=False)
    
    color = db.Column(db.String(20), default='#6366f1')
    plano_id = db.Column(db.Integer, db.ForeignKey('planos.id'), nullable=False)
    
    # Relación inversa
    objetos = db.relationship('Objeto', backref='zona', lazy=True)
    plano_rel = db.relationship('Plano', backref=db.backref('zonas', lazy=True))

class Mueble(db.Model):
    __tablename__ = 'muebles'
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(100), nullable=True) # Nombre personalizado (ex. Estante A1)
    tipo = db.Column(db.String(50), nullable=False) # estanteria, mesa, pared
    pos_x = db.Column(db.Float, default=0)
    pos_y = db.Column(db.Float, default=0)
    pos_z = db.Column(db.Float, default=0)
    ancho = db.Column(db.Float, default=10)
    alto = db.Column(db.Float, default=10)
    profundidad = db.Column(db.Float, default=10)
    rotacion_y = db.Column(db.Float, default=0)
    color = db.Column(db.String(20), default='#6366f1')
    estantes = db.Column(db.Integer, default=1) 
    material = db.Column(db.String(50), default='madera') # madera, metal, plastico
    plano_id = db.Column(db.Integer, db.ForeignKey('planos.id'), nullable=False)
