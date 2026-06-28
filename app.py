import os
from flask import Flask, jsonify, request, render_template, redirect, session
from flask_cors import CORS
from models import db, World, Episode, EpisodePage, Character, News
import cloudinary, cloudinary.uploader

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', '')
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'sqlite:///lawren.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db.init_app(app)
CORS(app, resources={r"/api/*": {"origins": "*"}})  # 공개 API만 허용

# ★ 실제 값은 절대 여기 쓰지 않음 — Render 환경변수에서 주입
ADMIN_PASSWORD = os.environ.get('ADMIN_PASSWORD', '')
cloudinary.config(
    cloud_name = 'dmn9mxxqq',
    api_key    = '',
    api_secret = os.environ.get('CLOUDINARY_API_SECRET', '')
)

with app.app_context():
    db.create_all()

def guard():
    if not session.get('admin'):
        return redirect('/admin')

# ══ 공개 API ════════════════════════════════════

@app.route('/api/worlds')
def api_worlds():
    worlds = World.query.order_by(World.order).all()
    result = []
    for w in worlds:
        d = w.to_dict()
        d['characters'] = [c.to_dict() for c in
            Character.query.filter_by(world_id=w.id).order_by(Character.order).all()]
        result.append(d)
    return jsonify(result)

@app.route('/api/episodes')
def api_episodes():
    world_id = request.args.get('world_id')
    q = Episode.query.filter_by(is_public=True)
    if world_id:
        q = q.filter_by(world_id=int(world_id))
    eps = q.order_by(Episode.order).all()
    return jsonify([e.to_dict() for e in eps])

@app.route('/api/news')
def api_news():
    items = News.query.order_by(News.order).limit(3).all()
    return jsonify([n.to_dict() for n in items])

# ══ 로그인 ══════════════════════════════════════

@app.route('/admin', methods=['GET', 'POST'])
def admin_login():
    if session.get('admin'):
        return redirect('/admin/episodes')
    if request.method == 'POST':
        if request.form.get('password') == ADMIN_PASSWORD:
            session['admin'] = True
            return redirect('/admin/episodes')
        return render_template('login.html', error='비밀번호가 틀렸습니다.')
    return render_template('login.html')

@app.route('/admin/logout')
def admin_logout():
    session.clear()
    return redirect('/admin')

# ══ 이미지 업로드 ════════════════════════════════

@app.route('/admin/upload', methods=['POST'])
def upload_image():
    if not session.get('admin'):
        return jsonify({'error': 'unauthorized'}), 401
    file = request.files.get('file')
    if not file:
        return jsonify({'error': 'no file'}), 400
    try:
        result = cloudinary.uploader.upload(file, folder='lawren103')
        return jsonify({'url': result['secure_url']})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ══ 에피소드 ════════════════════════════════════

@app.route('/admin/episodes')
def admin_episodes():
    r = guard()
    if r: return r
    worlds   = World.query.order_by(World.order).all()
    episodes = Episode.query.order_by(Episode.world_id, Episode.order).all()
    return render_template('episodes.html', episodes=episodes, worlds=worlds)

@app.route('/admin/episodes/add', methods=['POST'])
def episode_add():
    r = guard()
    if r: return r
    title    = request.form.get('title', '').strip()
    world_id = request.form.get('world_id') or None
    is_pub   = request.form.get('is_public') == 'on'
    order    = int(request.form.get('order') or 0) or Episode.query.count() + 1
    if title:
        db.session.add(Episode(title=title, world_id=world_id, is_public=is_pub, order=order))
        db.session.commit()
    return redirect('/admin/episodes')

@app.route('/admin/episodes/toggle/<int:id>')
def episode_toggle(id):
    r = guard()
    if r: return r
    ep = Episode.query.get(id)
    if ep:
        ep.is_public = not ep.is_public
        db.session.commit()
    return redirect('/admin/episodes')

@app.route('/admin/episodes/edit/<int:id>', methods=['POST'])
def episode_edit(id):
    r = guard()
    if r: return r
    ep = Episode.query.get(id)
    if ep:
        ep.title    = request.form.get('title', ep.title).strip()
        ep.world_id = request.form.get('world_id') or None
        ep.order    = int(request.form.get('order') or ep.order)
        db.session.commit()
    return redirect('/admin/episodes')

@app.route('/admin/episodes/delete/<int:id>')
def episode_delete(id):
    r = guard()
    if r: return r
    ep = Episode.query.get(id)
    if ep:
        db.session.delete(ep)
        db.session.commit()
    return redirect('/admin/episodes')

# ── 에피소드 페이지 ──────────────────────────────

@app.route('/admin/episodes/<int:ep_id>/pages')
def episode_pages(ep_id):
    r = guard()
    if r: return r
    ep    = Episode.query.get_or_404(ep_id)
    pages = EpisodePage.query.filter_by(episode_id=ep_id).order_by(EpisodePage.order).all()
    return render_template('pages.html', ep=ep, pages=pages)

@app.route('/admin/episodes/<int:ep_id>/pages/add', methods=['POST'])
def page_add(ep_id):
    r = guard()
    if r: return r
    for url in request.form.getlist('image_url'):
        url = url.strip()
        if url:
            order = EpisodePage.query.filter_by(episode_id=ep_id).count() + 1
            db.session.add(EpisodePage(episode_id=ep_id, image_url=url, order=order))
    db.session.commit()
    return redirect(f'/admin/episodes/{ep_id}/pages')

@app.route('/admin/episodes/<int:ep_id>/pages/delete/<int:page_id>')
def page_delete(ep_id, page_id):
    r = guard()
    if r: return r
    p = EpisodePage.query.get(page_id)
    if p:
        db.session.delete(p)
        db.session.commit()
        for i, pg in enumerate(EpisodePage.query.filter_by(episode_id=ep_id).order_by(EpisodePage.order).all(), 1):
            pg.order = i
        db.session.commit()
    return redirect(f'/admin/episodes/{ep_id}/pages')

@app.route('/admin/episodes/<int:ep_id>/pages/reorder', methods=['POST'])
def page_reorder(ep_id):
    r = guard()
    if r: return r
    for item in request.json:
        p = EpisodePage.query.get(item['id'])
        if p and p.episode_id == ep_id:
            p.order = item['order']
    db.session.commit()
    return jsonify({'ok': True})

# ══ 세계관 ══════════════════════════════════════

@app.route('/admin/worlds/add', methods=['POST'])
def world_add():
    r = guard()
    if r: return r
    name = request.form.get('name', '').strip()
    if name:
        db.session.add(World(name=name, order=World.query.count() + 1))
        db.session.commit()
    return redirect(request.referrer or '/admin/characters')

@app.route('/admin/worlds/delete/<int:id>')
def world_delete(id):
    r = guard()
    if r: return r
    w = World.query.get(id)
    if w:
        db.session.delete(w)
        db.session.commit()
    return redirect('/admin/characters')

# ══ 캐릭터 ══════════════════════════════════════

@app.route('/admin/characters')
def admin_characters():
    r = guard()
    if r: return r
    worlds     = World.query.order_by(World.order).all()
    characters = Character.query.order_by(Character.world_id, Character.order).all()
    return render_template('characters.html', worlds=worlds, characters=characters)

@app.route('/admin/characters/add', methods=['POST'])
def character_add():
    r = guard()
    if r: return r
    name     = request.form.get('name', '').strip()
    world_id = int(request.form.get('world_id') or 0)
    if name and world_id:
        order = int(request.form.get('order') or 0) or Character.query.filter_by(world_id=world_id).count() + 1
        db.session.add(Character(
            name=name,
            description=request.form.get('description', '').strip(),
            image_url=request.form.get('image_url', '').strip(),
            world_id=world_id, order=order
        ))
        db.session.commit()
    return redirect('/admin/characters')

@app.route('/admin/characters/edit/<int:id>', methods=['POST'])
def character_edit(id):
    r = guard()
    if r: return r
    ch = Character.query.get(id)
    if ch:
        ch.name        = request.form.get('name', ch.name).strip()
        ch.description = request.form.get('description', ch.description).strip()
        ch.image_url   = request.form.get('image_url', ch.image_url).strip()
        ch.world_id    = int(request.form.get('world_id') or ch.world_id)
        ch.order       = int(request.form.get('order') or ch.order)
        db.session.commit()
    return redirect('/admin/characters')

@app.route('/admin/characters/delete/<int:id>')
def character_delete(id):
    r = guard()
    if r: return r
    ch = Character.query.get(id)
    if ch:
        db.session.delete(ch)
        db.session.commit()
    return redirect('/admin/characters')


# ══ 뉴스 관리 ══════════════════════════════════════

@app.route('/admin/news', methods=['GET'])
def admin_news():
    if not session.get('admin'):
        return redirect('/admin')
    items = News.query.order_by(News.order).all()
    return render_template('news.html', items=items)

@app.route('/admin/news/add', methods=['POST'])
def admin_news_add():
    if not session.get('admin'):
        return redirect('/admin')
    n = News(
        date=request.form.get('date',''),
        tag=request.form.get('tag','UPDATE'),
        text=request.form.get('text',''),
        url=request.form.get('url',''),
        order=int(request.form.get('order',0))
    )
    db.session.add(n)
    db.session.commit()
    return redirect('/admin/news')

@app.route('/admin/news/delete/<int:nid>')
def admin_news_delete(nid):
    if not session.get('admin'):
        return redirect('/admin')
    n = News.query.get_or_404(nid)
    db.session.delete(n)
    db.session.commit()
    return redirect('/admin/news')


if __name__ == '__main__':
    app.run(debug=True)
