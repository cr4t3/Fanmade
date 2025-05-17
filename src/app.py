from flask import *
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user, AnonymousUserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from sqlalchemy import CheckConstraint
import os
from datetime import datetime
import time
import argparse
from dotenv import load_dotenv

parser = argparse.ArgumentParser()

parser.add_argument("--debug", "-d", action="store_true")

args = parser.parse_args()

if not os.environ["SECRET_KEY"]:
    load_dotenv()

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ["SECRET_KEY"]
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///main.db"
app.config["UPLOAD_FOLDER"] = "static/uploads"
app.config["MAX_CONTENT_LENGTH"] = 500 * 1024 ** 2
db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'

#region Models

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    artistName = db.Column(db.String(80), unique=True, nullable=False)
    username = db.Column(db.String(32), unique=True, nullable=False)
    email = db.Column(db.String(256), unique=True, nullable=False)
    password_hash = db.Column(db.String(128))
    enabled = db.Column(db.Boolean(), default=True, nullable=False)
    is_admin = db.Column(db.Boolean(), default=False, nullable=False)
    albums = db.relationship('Album', back_populates='user', lazy=True)  # Usando back_populates
    followers = db.relationship('Follows', foreign_keys='Follows.followed_id', backref='followed', lazy=True)
    following = db.relationship('Follows', foreign_keys='Follows.follower_id', backref='follower', lazy=True)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
        
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

class Album(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    release_date = db.Column(db.DateTime, nullable=False)
    record_label = db.Column(db.String(100))
    language = db.Column(db.String(50), nullable=False)
    primary_genre = db.Column(db.String(50), nullable=False)
    secondary_genre = db.Column(db.String(50))
    cover_image = db.Column(db.String(200), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    explicit = db.Column(db.Boolean(), nullable=False)
    enabled = db.Column(db.Boolean(), default=True, nullable=False)
    tracks = db.relationship('Track', backref='album', lazy=True)
    user = db.relationship('User', back_populates='albums')  # Relación inversa con back_populates


class Track(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100), nullable=False)
    album_id = db.Column(db.Integer, db.ForeignKey('album.id'), nullable=False)
    file_path = db.Column(db.String(200), nullable=False)
    version_type = db.Column(db.String(50), nullable=False)
    enabled = db.Column(db.Boolean(), default=True, nullable=False)
    explicit = db.Column(db.Boolean(), nullable=False)
    played = db.Column(db.Integer, default=0, nullable=False)
    featuring = db.relationship('User', secondary='track_featuring')
    credits = db.relationship('Credits', backref='track', lazy=True)

class TrackFeaturing(db.Model):
    track_id = db.Column(db.Integer, db.ForeignKey('track.id'), primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), primary_key=True)
    enabled = db.Column(db.Boolean(), default=True, nullable=False)

class CreditsCategory(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(64), nullable=False, unique=True)
    credits = db.relationship('Credits', backref='category_rel', lazy=True)

class Credits(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(256), nullable=False, unique=False)
    track_id = db.Column(db.Integer, db.ForeignKey('track.id'), nullable=False)
    category = db.Column(db.Integer, db.ForeignKey('credits_category.id'), nullable=False)

class Follows(db.Model):
    follower_id = db.Column(db.Integer, db.ForeignKey('user.id'), primary_key=True)
    followed_id = db.Column(db.Integer, db.ForeignKey('user.id'), primary_key=True)

    __table_args__ = (
        CheckConstraint('follower_id != followed_id', name='no_self_follow'),
    )

@login_manager.user_loader
def load_user(id):
    return User.query.get(int(id))

#endregion

# Utils

def is_admin(user):
    return not isinstance(user, AnonymousUserMixin) and user.is_admin

# Uploads managment

@app.route("/tracks/<filename>")
def getupload(filename: str):
    file_path = os.path.join(app.root_path, 'static', 'uploads', 'tracks')
    if not os.path.exists(os.path.join(file_path, filename)):
        abort(404)

    track = Track.query.filter_by(file_path="/uploads/tracks/" + filename).first()
    if not track or (not track.enabled or not track.album.enabled) and not current_user.is_admin:
        abort(404)
    if (not track.enabled or not track.album.enabled) and current_user.is_admin:
        return send_from_directory(file_path, filename)

    track.played += 1
    db.session.commit()
    return send_from_directory(file_path, filename)


# Webpage

@app.route("/")
def index():
    # Fetch latest releases
    latest_releases = Album.query
    if not is_admin(current_user):
        latest_releases = latest_releases.filter_by(enabled=True).join(User).filter(User.enabled)

    latest_releases = latest_releases.order_by(Album.created_at.desc()).limit(4).all()
    latest_releases = [
        (release, release.user, release.enabled and release.user.enabled)
        for release in latest_releases
    ]

    # Fetch most played tracks
    most_played = Track.query.filter(Track.played > 0)
    if not is_admin(current_user):
        most_played = most_played.join(Album).join(User).filter(User.enabled).filter_by(enabled=True).filter(Album.enabled)

    most_played = most_played.order_by(Track.played.desc()).limit(4).all()
    most_played = [
        (track, track.album.user, track.enabled and track.album.enabled and track.album.user.enabled) 
        for track in most_played
    ]

    return render_template("index.html", latest_releases=latest_releases, most_played=most_played)

@app.route("/register", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    if request.method == "GET":
        return render_template("register.html", player_unavilable=True)
    
    if set(request.form.keys()) != {"artistName", "username", "email", "password"}:
        abort(400)
    
    artistName = request.form["artistName"]
    username = request.form["username"].lower()
    email = request.form["email"]
    password = request.form["password"]
    
    if any([c in [" ", "\n", "!", "@", "<", ">"] for c in username]):
        abort(400)

    if not (1 <= len(artistName) <= 80) \
       or not (3 <= len(username) <= 32)\
       or not (5 <= len(email) <= 256) \
       or not (6 <= len(password)):
        abort(400)
    
    if User.query.filter_by(artistName=artistName).first() \
       or User.query.filter_by(username=username).first() \
       or User.query.filter_by(email=email).first():
        abort(409)

    new_user = User(artistName=artistName, username=username, email=email)
    new_user.set_password(password)
    db.session.add(new_user)
    db.session.commit()

    flash("Account created succesfully! Please login.")
    return redirect(url_for('login'))

@app.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('index'))

    if request.method == "GET":
        return render_template("login.html")
    
    if set(request.form.keys()) != {"username", "password"}:
        abort(400)

    username = request.form["username"].lower()
    password = request.form["password"]
    user: User = User.query.filter_by(username=username).first()
    if user and user.check_password(password) and user.enabled:
        print(user.enabled)
        login_user(user)
        return redirect(url_for('index'))
    else:
        flash("Invalid username or password")
        return redirect(url_for('login'))

@app.route("/logout")
@login_required
def logout():
    logout_user()
    flash("You logged out of your account.")
    return redirect(url_for('index'))

@app.route("/album/<int:album_id>", methods=["GET", "POST"])
def album(album_id: int):
    album_data = Album.query.filter_by(id=album_id).first()
    if request.method == "GET":
        if album_data and (album_data.enabled or current_user.is_admin):
            user_data = User.query.filter_by(id=album_data.user_id).first()
            return render_template("album.html", title = album_data.title, album_data = album_data, user_data = user_data)
        else:
            abort(404)

    if not current_user.is_admin:
        abort(405)

    print(not album_data.enabled)

    album_data.enabled = not album_data.enabled
    db.session.commit()
    return redirect(url_for('album', _method="GET", album_id=album_id))

@app.route('/upload', methods=['GET', 'POST'])
@login_required
def upload():
	if request.method == 'GET':
		return render_template("upload.html", player_unavilable=True)

	track_count = int(request.form['track_count'])
	if any([len(request.form[f"track_title_{i}"]) < 1 for i in range(track_count)]):
		flash("There can't be a track without a name.")
		return redirect(url_for('upload'))

	user: User = current_user

	if not user:
		abort(401)

	album = Album(
		title=request.form["album_title"],
		user_id=user.id,
		release_date=datetime.strptime(request.form['release_date'], '%Y-%m-%d'),
		record_label=request.form.get('record_label'),
		language=request.form['language'],
		primary_genre=request.form['primary_genre'],
		secondary_genre=request.form.get('secondary_genre')
	)

	cover_image = request.files['cover_image']
	if cover_image:
		filename = secure_filename(f"{user.artistName}_{album.title}_{time.time_ns()}_cover.jpg")
		cover_image.save(os.path.join(app.config['UPLOAD_FOLDER'], 'covers', filename))
		album.cover_image = "/uploads/covers/" + filename

	for i in range(track_count):
		try:
			print(request.form[f"is_explicit_{i}"])
			album.explicit = True
			break
		except:
			continue
	else:
		album.explicit = False

	db.session.add(album)
	db.session.commit()

	for i in range(track_count):
		print(i)
		confirmed_featurings = []
		if request.form.get(f'has_featuring_{i}'):
			featurings = request.form.getlist(f'featuring_{i}[]')

			for featuring in featurings:
				featuring_user = User.query.filter_by(artistName=featuring).first()
				if featuring_user.id == user.id:
					flash(f"You tried to add yourself as a featuring, we skipped it.")
				elif featuring_user and featuring_user.enabled:
					confirmed_featurings.append(featuring_user)
				else:
					flash(f"User with artist name '{featuring}' doesn't exist. Ask them to create a account in Fanmade.")
					return redirect(url_for('upload'))

		is_explicit = False
		try:
			request.form[f"is_explicit_{i}"]
			is_explicit = True
		except:
			pass

		track = Track(
			title=request.form[f'track_title_{i}'],
			album_id=album.id,
			version_type=request.form[f'version_type_{i}'],
			explicit=is_explicit
		)
		
		# Handle track file upload
		track_file = request.files[f'track_file_{i}']
		if track_file:
			filename = secure_filename(f"{user.artistName}_{album.title}_{track.title}_{time.time_ns()}.mp3")
			track_file.save(os.path.join(app.config['UPLOAD_FOLDER'], 'tracks', filename))
			track.file_path = "/uploads/tracks/" + filename
		
		db.session.add(track)
		db.session.commit()

		written_by = request.form.getlist(f"written_by_{i}[]")
		produced_by = request.form.getlist(f"produced_by_{i}[]")
		metadata_by = request.form.getlist(f"metadata_by_{i}[]")

		if not written_by:
			written_by = [current_user.artistName]
			flash("You are required to insert a writer on the writer list. As it wasn't added, your artist name will be added.")

		for writer in written_by:
			credits = Credits(track_id=track.id, category=2, name=writer)
			db.session.add(credits)

		for producer in produced_by:
			credits = Credits(track_id=track.id, category=3, name=producer)
			db.session.add(credits)

		for metadata in metadata_by:
			credits = Credits(track_id=track.id, category=4, name=metadata)
			db.session.add(credits)

		db.session.commit()

		for featuring_user in confirmed_featurings:
			trackFeaturing = TrackFeaturing(track_id=track.id, user_id=featuring_user.id)
			db.session.add(trackFeaturing)

	db.session.commit()
	flash('Album uploaded successfully!')
	return redirect(url_for('index'))

@app.route("/new_upload")
def new_upload():
    if not (current_user.is_authenticated and current_user.is_admin):
        abort(404)

    return render_template("new_upload.html", today=datetime.now().strftime("%Y-%m-%d"))

@app.route("/artist/<username>")
def artist(username: str):
    if not username.startswith("@"):
        abort(400)
    else:
        username = username.replace("@", "").lower()
        user_data = User.query.filter_by(username=username).first()

    if not user_data or not user_data.enabled:
        abort(404)
    
    latest_releases = Album.query.filter_by(user_id=user_data.id, enabled=True).order_by(Album.created_at.desc()).limit(4).all()
    featurings = albums = Album.query.join(Track).join(TrackFeaturing, Track.id == TrackFeaturing.track_id)  .filter(TrackFeaturing.user_id == user_data.id).order_by(Album.created_at.desc()).distinct().limit(4).all()
    most_played = Track.query.filter_by(enabled=True).join(Album).filter(Album.enabled).filter(Album.user_id == user_data.id).order_by(Track.played.desc()).first()
    follows = not (isinstance(current_user, AnonymousUserMixin) or not bool(Follows.query.filter_by(follower_id=current_user.id, followed_id=user_data.id).first()))

    return render_template("artist.html", follows=follows, current_data=current_user, title=user_data.artistName, latest_releases=latest_releases, featurings=featurings, user_data=user_data, most_played=most_played)

@app.route("/follow/<int:id>", methods=["POST"])
def follow(id: int):
    if isinstance(current_user, AnonymousUserMixin) or id == current_user.id:
        abort(401)

    user = User.query.filter_by(id=id).first()
    if not user:
        flash(f"User with id {id} doesn't exist.")
        return redirect(url_for('index'))

    if Follows.query.filter_by(follower_id=current_user.id, followed_id=user.id).first():
        flash(f"You already follow {user.artistName}.")
    else:
        follow = Follows(follower_id=current_user.id, followed_id=user.id)
        db.session.add(follow)
        db.session.commit()

    return redirect(url_for('artist', username="@" + user.username))

@app.route("/unfollow/<int:id>", methods=["POST"])
def unfollow(id: int):
    if isinstance(current_user, AnonymousUserMixin):
        abort(401)
        
    user = User.query.filter_by(id=id).first()
    if not user:
        flash(f"User with id {id} doesn't exist.")
        return redirect(url_for('index'))

    if not Follows.query.filter_by(follower_id=current_user.id, followed_id=user.id).first():
        flash(f"You don't follow {user.artistName}.")
    else:
        follow = Follows.query.filter_by(follower_id=current_user.id, followed_id=user.id).first()
        db.session.delete(follow)
        db.session.commit()

    return redirect(url_for('artist', username="@" + user.username))

@app.route('/search', methods=['GET'])
def search():
    query = request.args.get('query')  # Obtiene la consulta de búsqueda
    results = []
    
    if query:
        try:
            results = Album.query.filter(
                (Album.title.ilike(f'%{query}%') |
                 Album.user.artistName.ilike(f'%{query}%') |
                 Album.user.username.ilike(f'%{query}%'))
            ).all()
        except Exception as e:
            # Puedes registrar el error si es necesario
            print(f"Error al realizar la búsqueda: {e}")
    else:
        return redirect(url_for('index'))
    
    return render_template('search.html', query=query, results=results, title=f"\"{query}\"")

# API
@app.route("/api/v1/play/<int:track_id>")
def play(track_id: int):
    track = Track.query.filter_by(id=track_id).first()
    if not track or not track.enabled:
        abort(404)
    
    album = track.album
    user = album.user
    response = {
        "track_title": track.title,
        "track_url": "/tracks/" + track.file_path.replace("/uploads/tracks/", ""),
        "album_title": album.title,
        "artist_name": user.artistName,
        "cover_image": url_for('static', filename=album.cover_image),
        "album_id": album.id
    }
    return jsonify(response)

@app.route("/api/v1/credits/<int:track_id>")
def track_credits(track_id: int):
    track_data = Track.query.filter_by(enabled=True).filter_by(id=track_id).first()
    if not track_data:
        abort(404)

    credits = []

    category_name = CreditsCategory.query.filter_by(id=1).first_or_404().name
    artists = [track_data.album.user.artistName]
    artists.extend([artist.artistName for artist in track_data.featuring])

    credits.append({
        "name": category_name,
        "artists": artists
    })

    for credit in track_data.credits:
        existing_credit = next((item for item in credits if item["name"] == credit.category_rel.name), None)
        if existing_credit:
            existing_credit["artists"].append(credit.name)
        else:
            credits.append({
                "name": credit.category_rel.name,
                "artists": [credit.name]
        })


    return jsonify(credits)

@app.route("/api/v1/album/<int:album_id>")
def album_api(album_id: int):
    album = Album.query.filter_by(id=album_id).first_or_404()
    return jsonify({
        'title': album.title,
        'tracks': [track.id for track in album.tracks]
    })

if __name__ == "__main__":
    with app.app_context():
        db.create_all()
    app.run(debug = args.debug, port = 80)