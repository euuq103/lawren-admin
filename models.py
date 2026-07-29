from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()


class AppMeta(db.Model):
    """DB 생성일 자동 기록용 (만료일 자동 계산을 위해 사용)"""
    id          = db.Column(db.Integer, primary_key=True)
    db_created  = db.Column(db.String(20), nullable=False)  # YYYY-MM-DD


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
    alias     = db.Column(db.String(300), default='')   # 검색용 별칭, 쉼표로 구분 (예: "사월,砂月")
    pages     = db.relationship('EpisodePage', backref='episode', lazy=True,
                                cascade='all, delete-orphan', order_by='EpisodePage.order')

    def to_dict(self):
        return {
            'id': self.id, 'title': self.title,
            'order': self.order, 'world_id': self.world_id,
            'alias': self.alias or '',
            'pages': [p.to_dict() for p in self.pages]
        }


class EpisodePage(db.Model):
    id           = db.Column(db.Integer, primary_key=True)
    episode_id   = db.Column(db.Integer, db.ForeignKey('episode.id'), nullable=False)
    image_url    = db.Column(db.String(500), nullable=False)          # 한국어 (기본)
    image_url_en = db.Column(db.String(500), default='')              # 영어
    image_url_ja = db.Column(db.String(500), default='')              # 일본어
    image_url_ru = db.Column(db.String(500), default='')              # 러시아어
    order        = db.Column(db.Integer, default=0)

    def to_dict(self):
        return {
            'id': self.id,
            'image_url': self.image_url,
            'image_url_en': self.image_url_en or '',
            'image_url_ja': self.image_url_ja or '',
            'image_url_ru': self.image_url_ru or '',
            'order': self.order
        }


class Character(db.Model):
    id          = db.Column(db.Integer, primary_key=True)
    name        = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text, default='')
    thumb_url   = db.Column(db.String(500), default='')   # 얼굴 썸네일 (버튼용)
    image_url   = db.Column(db.String(500), default='')   # 전신샷 (메인 뷰어용)
    world_id    = db.Column(db.Integer, db.ForeignKey('world.id'), nullable=False)
    order       = db.Column(db.Integer, default=0)
    is_public   = db.Column(db.Boolean, default=True)
    alias       = db.Column(db.String(300), default='')   # 검색용 별칭, 쉼표로 구분 (예: "사월,砂月")

    def to_dict(self):
        return {
            'id': self.id, 'name': self.name,
            'description': self.description,
            'thumb_url': self.thumb_url,
            'image_url': self.image_url,
            'world_id': self.world_id, 'order': self.order,
            'alias': self.alias or ''
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
