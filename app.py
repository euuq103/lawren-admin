import os
import time
import json
from io import BytesIO
from flask import Flask, jsonify, request, render_template, redirect, session, send_file
from flask_cors import CORS
from sqlalchemy import text
from models import db, World, Episode, EpisodePage, Character, News
import cloudinary, cloudinary.uploader

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'lawren103secret')
_db_url = os.environ.get('DATABASE_URL', 'sqlite:///lawren.db')
if _db_url.startswith('postgres://'):
    _db_url = _db_url.replace('postgres://', 'postgresql://', 1)
app.config['SQLALCHEMY_DATABASE_URI'] = _db_url
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# 쿠키 보안 (운영 = postgres 사용 중일 때만 SECURE 강제, 로컬 sqlite 개발은 http 허용)
_is_prod = _db_url.startswith('postgresql://')
app.config['SESSION_COOKIE_SECURE']   = _is_prod
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
db.init_app(app)
CORS(app, resources={r"/api/*": {"origins": "*"}})  # 공개 API만 허용

# ★ 실제 값은 절대 여기 쓰지 않음 — Render 환경변수에서 주입
ADMIN_PASSWORD = os.environ.get('ADMIN_PASSWORD', 'your_password_here')  # ← 여기 비번 입력
cloudinary.config(
    cloud_name = 'dmn9mxxqq',
    api_key    = os.environ.get('CLOUDINARY_API_KEY', ''),
    api_secret = os.environ.get('CLOUDINARY_API_SECRET', '')
)

def _try_migrate(sql):
    """기존 DB에 신규 컬럼을 안전하게 추가 (이미 있으면 조용히 무시)"""
    try:
        from sqlalchemy import text
        with db.engine.connect() as con:
            con.execute(text(sql))
            con.commit()
    except Exception:
        pass

with app.app_context():
    db.create_all()
    # 기존 DB 호환용 컬럼 마이그레이션 (이미 컬럼이 있으면 그냥 실패하고 넘어감)
    _try_migrate('ALTER TABLE character ADD COLUMN thumb_url VARCHAR(500) DEFAULT \'\'')
    _try_migrate('ALTER TABLE character ADD COLUMN is_public BOOLEAN DEFAULT 1')
    _try_migrate('ALTER TABLE character ADD COLUMN alias VARCHAR(300) DEFAULT \'\'')
    _try_migrate('ALTER TABLE episode ADD COLUMN alias VARCHAR(300) DEFAULT \'\'')

def guard():
    if not session.get('admin'):
        return redirect('/admin')

# ── 로그인 시도 제한 (메모리 기반, 간단한 무차별 대입 방어) ──
_login_attempts = {}   # ip -> {'count': int, 'locked_until': float}
MAX_LOGIN_ATTEMPTS = 5
LOCKOUT_SECONDS = 300  # 5분

def _client_ip():
    fwd = request.headers.get('X-Forwarded-For', '')
    return fwd.split(',')[0].strip() if fwd else request.remote_addr

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
    world_id   = request.args.get('world_id')
    world_name = request.args.get('world_name')
    q = Episode.query.filter_by(is_public=True)
    if world_id:
        q = q.filter_by(world_id=int(world_id))
    elif world_name:
        w = World.query.filter(World.name.ilike(world_name)).first()
        if w:
            q = q.filter_by(world_id=w.id)
    eps = q.order_by(Episode.order).all()
    return jsonify([e.to_dict() for e in eps])

@app.route('/api/characters')
def api_characters():
    worlds = World.query.order_by(World.order).all()
    result = []
    for w in worlds:
        chars = Character.query.filter_by(world_id=w.id, is_public=True).order_by(Character.order).all()
        result.append({
            'world_id': w.id,
            'world_name': w.name,
            'characters': [{
                'id': c.id,
                'name': c.name,
                'description': c.description,
                'image_url': c.image_url,
                'thumb_url': c.thumb_url,
                'order': c.order,
                'alias': c.alias or ''
            } for c in chars]
        })
    return jsonify(result)

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
        ip = _client_ip()
        rec = _login_attempts.get(ip, {'count': 0, 'locked_until': 0})
        now = time.time()
        if rec['locked_until'] > now:
            wait = int(rec['locked_until'] - now)
            return render_template('login.html', error=f'너무 많이 틀렸어요. {wait}초 후 다시 시도하세요.')
        if request.form.get('password') == ADMIN_PASSWORD:
            session['admin'] = True
            _login_attempts.pop(ip, None)
            return redirect('/admin/episodes')
        rec['count'] += 1
        if rec['count'] >= MAX_LOGIN_ATTEMPTS:
            rec['locked_until'] = now + LOCKOUT_SECONDS
            rec['count'] = 0
        _login_attempts[ip] = rec
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
    alias    = request.form.get('alias', '').strip()
    order    = int(request.form.get('order') or 0) or Episode.query.count() + 1
    if title:
        db.session.add(Episode(title=title, world_id=world_id, is_public=is_pub, alias=alias, order=order))
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
        ep.alias    = request.form.get('alias', ep.alias).strip()
        ep.order    = int(request.form.get('order') or ep.order)
        db.session.commit()
    return redirect('/admin/episodes')

@app.route('/admin/episodes/delete/<int:id>', methods=['POST'])
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

@app.route('/admin/episodes/<int:ep_id>/pages/delete/<int:page_id>', methods=['POST'])
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

@app.route('/admin/worlds/delete/<int:id>', methods=['POST'])
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
            thumb_url=request.form.get('thumb_url', '').strip(),
            image_url=request.form.get('image_url', '').strip(),
            alias=request.form.get('alias', '').strip(),
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
        ch.thumb_url   = request.form.get('thumb_url', ch.thumb_url).strip()
        ch.alias       = request.form.get('alias', ch.alias).strip()
        ch.world_id    = int(request.form.get('world_id') or ch.world_id)
        ch.order       = int(request.form.get('order') or ch.order)
        db.session.commit()
    return redirect('/admin/characters')

@app.route('/admin/characters/delete/<int:id>', methods=['POST'])
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

@app.route('/admin/news/delete/<int:nid>', methods=['POST'])
def admin_news_delete(nid):
    if not session.get('admin'):
        return redirect('/admin')
    n = News.query.get_or_404(nid)
    db.session.delete(n)
    db.session.commit()
    return redirect('/admin/news')


# ══ 백업 / 복원 ════════════════════════════════════

@app.route('/admin/backup')
def admin_backup():
    if not session.get('admin'):
        return redirect('/admin')
    data = {
        'worlds': [{'id': w.id, 'name': w.name, 'order': w.order} for w in World.query.all()],
        'characters': [{
            'id': c.id, 'name': c.name, 'description': c.description,
            'thumb_url': c.thumb_url, 'image_url': c.image_url,
            'world_id': c.world_id, 'order': c.order,
            'is_public': c.is_public, 'alias': c.alias
        } for c in Character.query.all()],
        'episodes': [{
            'id': e.id, 'title': e.title, 'order': e.order,
            'is_public': e.is_public, 'world_id': e.world_id, 'alias': e.alias,
            'pages': [{'id': p.id, 'image_url': p.image_url, 'order': p.order} for p in e.pages]
        } for e in Episode.query.all()],
        'news': [{
            'id': n.id, 'date': n.date, 'tag': n.tag,
            'text': n.text, 'url': n.url, 'order': n.order
        } for n in News.query.all()]
    }
    buf = BytesIO(json.dumps(data, ensure_ascii=False, indent=2).encode('utf-8'))
    filename = 'lawren103_backup_' + time.strftime('%Y%m%d_%H%M%S') + '.json'
    return send_file(buf, mimetype='application/json', as_attachment=True, download_name=filename)


@app.route('/admin/backup-page')
def admin_backup_page():
    if not session.get('admin'):
        return redirect('/admin')
    msg = ''
    if request.args.get('success'):
        msg = '<p style="color:#4caf50">✅ 복원 완료!</p>'
    elif request.args.get('error'):
        msg = '<p style="color:#f44336">❌ 오류: JSON 파일을 확인해주세요.</p>'
    # DB 만료일: Render 무료 Postgres는 생성 후 30일 뒤 만료.
    # Render 대시보드 > DB > Info 배너에서 정확한 날짜 확인 후 아래 값만 갱신하면 됨.
    DB_EXPIRE_DATE = "2026-07-29"

    return f'''
    <html><body style="font-family:sans-serif;padding:30px;background:#111;color:#eee">
      <h2>백업 / 복원</h2>
      {msg}
      <div id="expireBox" style="padding:12px 16px;border-radius:6px;margin-bottom:20px;font-size:15px;"></div>
      <p><a href="/admin/backup" style="color:#4caf50;font-size:18px">📥 지금 백업 다운로드</a></p>
      <hr style="border-color:#333">
      <form method="POST" action="/admin/restore" enctype="multipart/form-data"
            onsubmit="return confirm('현재 DB 데이터를 전부 지우고 백업 파일 내용으로 교체합니다. 계속할까요?')">
        <p>⚠ 복원하면 현재 DB 내용은 전부 지워지고 백업 파일 내용으로 바뀝니다.</p>
        <input type="file" name="backup_file" accept="application/json" required>
        <button type="submit" style="background:#f44336;color:#fff;padding:6px 14px;border:none;border-radius:4px;">복원 실행</button>
      </form>
      <p style="margin-top:30px"><a href="/admin" style="color:#888">← 관리자 메인으로</a></p>
      <script>
        (function(){{
          var expire = new Date("{DB_EXPIRE_DATE}T00:00:00");
          var today = new Date();
          today.setHours(0,0,0,0);
          var days = Math.ceil((expire - today) / 86400000);
          var box = document.getElementById('expireBox');
          var color, text;
          if (days < 0) {{
            color = '#f44336'; text = '⚠ DB 만료일(' + "{DB_EXPIRE_DATE}" + ')이 지났어요! 대시보드 확인 필요';
          }} else if (days <= 5) {{
            color = '#f44336'; text = '🚨 DB 만료까지 D-' + days + ' (' + "{DB_EXPIRE_DATE}" + ') — 지금 백업하고 업그레이드 검토하세요';
          }} else if (days <= 10) {{
            color = '#ff9800'; text = '⏳ DB 만료까지 D-' + days + ' (' + "{DB_EXPIRE_DATE}" + ')';
          }} else {{
            color = '#4caf50'; text = '✅ DB 만료까지 D-' + days + ' (' + "{DB_EXPIRE_DATE}" + ') — 아직 여유 있음';
          }}
          box.style.background = color + '22';
          box.style.border = '1px solid ' + color;
          box.style.color = color;
          box.textContent = text;
        }})();
      </script>
    </body></html>
    '''


@app.route('/admin/restore', methods=['POST'])
def admin_restore():
    if not session.get('admin'):
        return redirect('/admin')
    f = request.files.get('backup_file')
    if not f:
        return redirect('/admin/backup-page?error=1')
    try:
        data = json.load(f)
    except Exception:
        return redirect('/admin/backup-page?error=1')

    # 기존 데이터 전체 삭제 (자식 테이블부터)
    EpisodePage.query.delete()
    Episode.query.delete()
    Character.query.delete()
    World.query.delete()
    News.query.delete()
    db.session.commit()

    for w in data.get('worlds', []):
        db.session.add(World(id=w['id'], name=w['name'], order=w.get('order', 0)))
    db.session.commit()

    for c in data.get('characters', []):
        db.session.add(Character(
            id=c['id'], name=c['name'], description=c.get('description', ''),
            thumb_url=c.get('thumb_url', ''), image_url=c.get('image_url', ''),
            world_id=c['world_id'], order=c.get('order', 0),
            is_public=c.get('is_public', True), alias=c.get('alias', '')
        ))
    db.session.commit()

    for e in data.get('episodes', []):
        db.session.add(Episode(
            id=e['id'], title=e['title'], order=e.get('order', 0),
            is_public=e.get('is_public', False), world_id=e.get('world_id'),
            alias=e.get('alias', '')
        ))
        db.session.commit()
        for p in e.get('pages', []):
            db.session.add(EpisodePage(id=p['id'], episode_id=e['id'],
                                        image_url=p['image_url'], order=p.get('order', 0)))
    db.session.commit()

    for n in data.get('news', []):
        db.session.add(News(
            id=n['id'], date=n['date'], tag=n.get('tag', 'UPDATE'),
            text=n['text'], url=n.get('url', ''), order=n.get('order', 0)
        ))
    db.session.commit()

    # PostgreSQL auto-increment 시퀀스 복원된 id 이후로 재조정
    for tbl, seq in [('world', 'world_id_seq'), ('character', 'character_id_seq'),
                      ('episode', 'episode_id_seq'), ('episode_page', 'episode_page_id_seq'),
                      ('news', 'news_id_seq')]:
        try:
            db.session.execute(text(f"SELECT setval('{seq}', COALESCE((SELECT MAX(id) FROM {tbl}), 1))"))
        except Exception:
            pass
    db.session.commit()

    return redirect('/admin/backup-page?success=1')


if __name__ == '__main__':
    app.run(debug=True)
