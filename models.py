from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()


class World(db.Model):
    id         = db.Column(db.Integer, primary_key=True)
    name       = db.Column(db.String(100), nullable=False)
    order      = db.Column(db.Integer, default=0)
    episodes   = db.relationship('Episode',   backref='world', lazy=True)
    characters = db.relationship('Character', backref='world', lazy=True, cascade='all, delete-orphan')

    def to_dict(self):
        return {'id': self.id, 'name': self.name}


class Episode(db.Model):
    id        = db.Column(db.Integer, primary_key=True)
    title     = db.Column(db.String(100), nullable=False)
    order     = db.Column(db.Integer, default=0)
    is_public = db.Column(db.Boolean, default=False)
    world_id  = db.Column(db.Integer, db.ForeignKey('world.id'), nullable=True)
    pages     = db.relationship('EpisodePage', backref='episode', lazy=True,
                                cascade='all, delete-orphan', order_by='EpisodePage.order')

    def to_dict(self):
        return {
            'id': self.id, 'title': self.title,
            'order': self.order, 'world_id': self.world_id,
            'pages': [p.to_dict() for p in self.pages]
        }


class EpisodePage(db.Model):
    id         = db.Column(db.Integer, primary_key=True)
    episode_id = db.Column(db.Integer, db.ForeignKey('episode.id'), nullable=False)
    image_url  = db.Column(db.String(500), nullable=False)
    order      = db.Column(db.Integer, default=0)

    def to_dict(self):
        return {'id': self.id, 'image_url': self.image_url, 'order': self.order}


class Character(db.Model):
    id          = db.Column(db.Integer, primary_key=True)
    name        = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text, default='')
    thumb_url   = db.Column(db.String(500), default='')   # 얼굴 썸네일 (버튼용)
    image_url   = db.Column(db.String(500), default='')   # 전신샷 (메인 뷰어용)
    world_id    = db.Column(db.Integer, db.ForeignKey('world.id'), nullable=False)
    order       = db.Column(db.Integer, default=0)
    is_public   = db.Column(db.Boolean, default=True)

    def to_dict(self):
        return {
            'id': self.id, 'name': self.name,
            'description': self.description,
            'thumb_url': self.thumb_url,
            'image_url': self.image_url,
            'world_id': self.world_id, 'order': self.order
        }


class News(db.Model):
    id        = db.Column(db.Integer, primary_key=True)
    date      = db.Column(db.String(20), nullable=False)   # 예: 2026.06.29
    tag       = db.Column(db.String(30), default='UPDATE') # UPDATE / EVENT 등
    text      = db.Column(db.String(200), nullable=False)
    url       = db.Column(db.String(500), default='')      # 선택적 링크
    order     = db.Column(db.Integer, default=0)

    def to_dict(self):
        return {
            'id': self.id, 'date': self.date,
            'tag': self.tag, 'text': self.text,
            'url': self.url, 'order': self.order
        }
