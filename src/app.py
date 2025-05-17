from flask import *
from flask_mongoengine import MongoEngine
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user, AnonymousUserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
import os
from datetime import datetime
import time
from dotenv import load_dotenv

if not os.environ.get("SECRET_KEY") or os.environ.get("USE_DOTENV") == "true":
    load_dotenv()

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY")

# MongoDB connection setup
app.config['MONGODB_SETTINGS'] = {
    'host': f"mongodb+srv://{os.environ.get('MONGODB_USERNAME')}:{os.environ.get('MONGODB_PASSWORD')}@{os.environ.get('MONGODB_CLUSTER')}/fanmade?retryWrites=true&w=majority"
}

app.config["UPLOAD_FOLDER"] = "static/uploads"
app.config["MAX_CONTENT_LENGTH"] = 500 * 1024 ** 2
db = MongoEngine(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'

#region Models

class User(UserMixin, db.Document):
    artistName = db.StringField(max_length=80, unique=True, required=True)
    username = db.StringField(max_length=32, unique=True, required=True)
    email = db.StringField(max_length=256, unique=True, required=True)
    password_hash = db.StringField(max_length=128)
    enabled = db.BooleanField(default=True)
    is_admin = db.BooleanField(default=False)
    
    meta = {'collection': 'users'}
    
    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
        
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

class TrackFeaturing(db.EmbeddedDocument):
    user = db.ReferenceField(User)
    enabled = db.BooleanField(default=True)

class Credits(db.EmbeddedDocument):
    name = db.StringField(max_length=256, required=True)
    category = db.IntField(required=True)  # Reference to CreditsCategory by ID

class Track(db.Document):
    title = db.StringField(max_length=100, required=True)
    album = db.ReferenceField('Album', required=True)
    file_path = db.StringField(max_length=200, required=True)
    version_type = db.StringField(max_length=50, required=True)
    enabled = db.BooleanField(default=True)
    explicit = db.BooleanField(required=True)
    played = db.IntField(default=0)
    featuring = db.ListField(db.ReferenceField(User))
    credits = db.ListField(db.EmbeddedDocumentField(Credits))
    
    meta = {'collection': 'tracks'}

class Album(db.Document):
    title = db.StringField(max_length=100, required=True)
    user = db.ReferenceField(User, required=True)
    release_date = db.DateTimeField(required=True)
    record_label = db.StringField(max_length=100)
    language = db.StringField(max_length=50, required=True)
    primary_genre = db.StringField(max_length=50, required=True)
    secondary_genre = db.StringField(max_length=50)
    cover_image = db.StringField(max_length=200, required=True)
    created_at = db.DateTimeField(default=datetime.utcnow)
    explicit = db.BooleanField(required=True)
    enabled = db.BooleanField(default=True)
    
    meta = {'collection': 'albums'}

class CreditsCategory(db.Document):
    name = db.StringField(max_length=64, required=True, unique=True)
    
    meta = {'collection': 'credits_categories'}

class Follows(db.Document):
    follower = db.ReferenceField(User, required=True)
    followed = db.ReferenceField(User, required=True)
    
    meta = {
        'collection': 'follows',
        'indexes': [
            {'fields': ['follower', 'followed'], 'unique': True}
        ]
    }
    
    def clean(self):
        if self.follower.id == self.followed.id:
            abort(400)

@login_manager.user_loader
def load_user(user_id):
    return User.objects(id=user_id).first()

#endregion

# Utils

def is_admin(user):
    return not isinstance(user, AnonymousUserMixin) and user.is_admin

# Uploads management

@app.route("/tracks/<filename>")
def getupload(filename: str):
    file_path = os.path.join(app.root_path, 'static', 'uploads', 'tracks')
    if not os.path.exists(os.path.join(file_path, filename)):
        abort(404)

    track = Track.objects(file_path="/uploads/tracks/" + filename).first()
    if not track or (not track.enabled or not track.album.enabled) and not current_user.is_admin:
        abort(404)
    if (not track.enabled or not track.album.enabled) and current_user.is_admin:
        return send_from_directory(file_path, filename)

    track.played += 1
    track.save()
    return send_from_directory(file_path, filename)


# Webpage

@app.route("/")
def index():
    # Fetch latest releases
    if not is_admin(current_user):
        latest_releases = Album.objects(enabled=True, user__enabled=True).order_by('-created_at').limit(4)
    else:
        latest_releases = Album.objects.order_by('-created_at').limit(4)

    latest_releases = [
        (release, release.user, release.enabled and release.user.enabled)
        for release in latest_releases
    ]

    # Fetch most played tracks
    if not is_admin(current_user):
        most_played = Track.objects(played__gt=0, enabled=True, album__enabled=True, album__user__enabled=True).order_by('-played').limit(4)
    else:
        most_played = Track.objects(played__gt=0).order_by('-played').limit(4)

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
    
    if User.objects(artistName=artistName).first() \
       or User.objects(username=username).first() \
       or User.objects(email=email).first():
        abort(409)

    new_user = User(artistName=artistName, username=username, email=email)
    new_user.set_password(password)
    new_user.save()

    flash("Account created successfully! Please login.")
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
    user = User.objects(username=username).first()
    if user and user.check_password(password) and user.enabled:
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

@app.route("/album/<album_id>", methods=["GET", "POST"])
def album(album_id: str):
    album_data = Album.objects(id=album_id).first()
    if request.method == "GET":
        if album_data and (album_data.enabled or current_user.is_admin):
            user_data = album_data.user
            return render_template("album.html", title=album_data.title, album_data=album_data, user_data=user_data)
        else:
            abort(404)

    if not current_user.is_admin:
        abort(405)

    album_data.enabled = not album_data.enabled
    album_data.save()
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

    user = current_user

    if not user:
        abort(401)

    album = Album(
        title=request.form["album_title"],
        user=user,
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

    # Check if any track is explicit to mark the album
    album.explicit = False
    for i in range(track_count):
        try:
            request.form[f"is_explicit_{i}"]
            album.explicit = True
            break
        except:
            continue

    album.save()

    for i in range(track_count):
        confirmed_featurings = []
        if request.form.get(f'has_featuring_{i}'):
            featurings = request.form.getlist(f'featuring_{i}[]')

            for featuring in featurings:
                featuring_user = User.objects(artistName=featuring).first()
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
            album=album,
            version_type=request.form[f'version_type_{i}'],
            explicit=is_explicit
        )
        
        # Handle track file upload
        track_file = request.files[f'track_file_{i}']
        if track_file:
            filename = secure_filename(f"{user.artistName}_{album.title}_{track.title}_{time.time_ns()}.mp3")
            track_file.save(os.path.join(app.config['UPLOAD_FOLDER'], 'tracks', filename))
            track.file_path = "/uploads/tracks/" + filename
        
        # Add featuring users
        track.featuring = confirmed_featurings
        
        # Process credits
        written_by = request.form.getlist(f"written_by_{i}[]")
        produced_by = request.form.getlist(f"produced_by_{i}[]")
        metadata_by = request.form.getlist(f"metadata_by_{i}[]")

        if not written_by:
            written_by = [current_user.artistName]
            flash("You are required to insert a writer on the writer list. As it wasn't added, your artist name will be added.")

        track_credits = []
        for writer in written_by:
            track_credits.append(Credits(name=writer, category=2))

        for producer in produced_by:
            track_credits.append(Credits(name=producer, category=3))

        for metadata in metadata_by:
            track_credits.append(Credits(name=metadata, category=4))
            
        track.credits = track_credits
        track.save()

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
        user_data = User.objects(username=username).first()

    if not user_data or not user_data.enabled:
        abort(404)
    
    latest_releases = Album.objects(user=user_data, enabled=True).order_by('-created_at').limit(4)
    
    # Finding all albums where this user is featured
    featured_tracks = Track.objects(featuring=user_data)
    featured_album_ids = [track.album.id for track in featured_tracks]
    featurings = Album.objects(id__in=featured_album_ids).order_by('-created_at').limit(4)
    
    most_played = Track.objects(enabled=True, album__enabled=True, album__user=user_data).order_by('-played').first()
    follows = not (isinstance(current_user, AnonymousUserMixin) or not bool(Follows.objects(follower=current_user.id, followed=user_data.id).first()))

    return render_template("artist.html", follows=follows, current_data=current_user, title=user_data.artistName, latest_releases=latest_releases, featurings=featurings, user_data=user_data, most_played=most_played)

@app.route("/follow/<user_id>", methods=["POST"])
def follow(user_id: str):
    if isinstance(current_user, AnonymousUserMixin) or str(user_id) == str(current_user.id):
        abort(401)

    user = User.objects(id=user_id).first()
    if not user:
        flash(f"User with id {user_id} doesn't exist.")
        return redirect(url_for('index'))

    if Follows.objects(follower=current_user.id, followed=user.id).first():
        flash(f"You already follow {user.artistName}.")
    else:
        follow = Follows(follower=current_user.id, followed=user.id)
        follow.save()

    return redirect(url_for('artist', username="@" + user.username))

@app.route("/unfollow/<user_id>", methods=["POST"])
def unfollow(user_id: str):
    if isinstance(current_user, AnonymousUserMixin):
        abort(401)
        
    user = User.objects(id=user_id).first()
    if not user:
        flash(f"User with id {user_id} doesn't exist.")
        return redirect(url_for('index'))

    existing_follow = Follows.objects(follower=current_user.id, followed=user.id).first()
    if not existing_follow:
        flash(f"You don't follow {user.artistName}.")
    else:
        existing_follow.delete()

    return redirect(url_for('artist', username="@" + user.username))

@app.route('/search', methods=['GET'])
def search():
    query = request.args.get('query')  # Get search query
    results = []
    
    if query:
        try:
            # MongoEngine allows complex queries
            results = Album.objects(
                db.Q(title__icontains=query) | 
                db.Q(user__artistName__icontains=query) | 
                db.Q(user__username__icontains=query)
            )
        except Exception as e:
            print(f"Error during search: {e}")
    else:
        return redirect(url_for('index'))
    
    return render_template('search.html', query=query, results=results, title=f"\"{query}\"")

# API
@app.route("/api/v1/play/<track_id>")
def play(track_id: str):
    track = Track.objects(id=track_id).first()
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
        "album_id": str(album.id)
    }
    return jsonify(response)

@app.route("/api/v1/credits/<track_id>")
def track_credits(track_id: str):
    track_data = Track.objects(enabled=True, id=track_id).first()
    if not track_data:
        abort(404)

    credits = []

    # Get performers category name
    performers_category = CreditsCategory.objects(id=1).first()
    if performers_category:
        category_name = performers_category.name
        artists = [track_data.album.user.artistName]
        artists.extend([artist.artistName for artist in track_data.featuring])

        credits.append({
            "name": category_name,
            "artists": artists
        })

    # Process other credits from track credits list
    for credit in track_data.credits:
        category = CreditsCategory.objects(id=credit.category).first()
        if not category:
            continue
            
        existing_credit = next((item for item in credits if item["name"] == category.name), None)
        if existing_credit:
            existing_credit["artists"].append(credit.name)
        else:
            credits.append({
                "name": category.name,
                "artists": [credit.name]
            })

    return jsonify(credits)

@app.route("/api/v1/album/<album_id>")
def album_api(album_id: str):
    album = Album.objects(id=album_id).first_or_404()
    tracks = Track.objects(album=album)
    return jsonify({
        'title': album.title,
        'tracks': [str(track.id) for track in tracks]
    })

# Health check
@app.route("/health")
def health():
    return jsonify({"status": "ok"})

if __name__ == "__main__":
    # Initialize categories if they don't exist
    if not CreditsCategory.objects(id=1).first():
        CreditsCategory(id=1, name="Performers").save()
    if not CreditsCategory.objects(id=2).first():
        CreditsCategory(id=2, name="Written By").save()
    if not CreditsCategory.objects(id=3).first():
        CreditsCategory(id=3, name="Produced By").save()
    if not CreditsCategory.objects(id=4).first():
        CreditsCategory(id=4, name="Metadata By").save()
        
    app.run(debug=False, port=80)