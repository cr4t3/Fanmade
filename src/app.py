from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, abort, send_from_directory
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user, AnonymousUserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
import os
from datetime import datetime
import time
#import argparse
from dotenv import load_dotenv
from pymongo import MongoClient
from bson.objectid import ObjectId

#parser = argparse.ArgumentParser()
#parser.add_argument("--debug", "-d", action="store_true")
#args = parser.parse_args()

if not os.environ.get("SECRET_KEY"):
    load_dotenv()

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ["SECRET_KEY"]
app.config["UPLOAD_FOLDER"] = "static/uploads"
app.config["MAX_CONTENT_LENGTH"] = 500 * 1024 ** 2

# MongoDB connection
mongo_client = MongoClient(f"mongodb+srv://{os.environ.get('MONGODB_USERNAME')}:{os.environ.get('MONGODB_PASSWORD')}@{os.environ.get('MONGODB_CLUSTER')}/?retryWrites=true&w=majority&appName=Cluster0")
db = mongo_client.fanmade_db
login_manager = LoginManager(app)
login_manager.login_view = 'login'

#region Models

class User(UserMixin):
    def __init__(self, user_data):
        self.user_data = user_data
        
    @property
    def id(self):
        return str(self.user_data.get('_id'))
    
    @property
    def artistName(self):
        return self.user_data.get('artistName')
    
    @property
    def username(self):
        return self.user_data.get('username')
    
    @property
    def email(self):
        return self.user_data.get('email')
    
    @property
    def enabled(self):
        return self.user_data.get('enabled', True)
    
    @property
    def is_admin(self):
        return self.user_data.get('is_admin', False)
    
    @property
    def password_hash(self):
        return self.user_data.get('password_hash')
    
    def set_password(self, password):
        self.user_data['password_hash'] = generate_password_hash(password)
        
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)
    
    def get_albums(self):
        return db.albums.find({'user_id': self.id, 'enabled': True})
    
    def get_followers(self):
        return db.follows.find({'followed_id': self.id})
    
    def get_following(self):
        return db.follows.find({'follower_id': self.id})
    
    def save(self):
        if '_id' in self.user_data:
            db.users.update_one({'_id': self.user_data['_id']}, {'$set': self.user_data})
        else:
            result = db.users.insert_one(self.user_data)
            self.user_data['_id'] = result.inserted_id
        return self

@login_manager.user_loader
def load_user(user_id):
    user_data = db.users.find_one({'_id': ObjectId(user_id)})
    if not user_data:
        return None
    return User(user_data)

#endregion

# Utils

def is_admin(user):
    return not isinstance(user, AnonymousUserMixin) and user.is_admin

def get_album_by_id(album_id):
    try:
        return db.albums.find_one({'_id': ObjectId(album_id)})
    except:
        return None

def get_track_by_id(track_id):
    try:
        return db.tracks.find_one({'_id': ObjectId(track_id)})
    except:
        return None

def get_user_by_id(user_id):
    try:
        user_data = db.users.find_one({'_id': ObjectId(user_id)})
        if user_data:
            return User(user_data)
        return None
    except:
        return None

def get_user_by_username(username):
    user_data = db.users.find_one({'username': username.lower()})
    if user_data:
        return User(user_data)
    return None

def get_user_by_artist_name(artist_name):
    user_data = db.users.find_one({'artistName': artist_name})
    if user_data:
        return User(user_data)
    return None

# Uploads management

@app.route("/tracks/<filename>")
def getupload(filename: str):
    file_path = os.path.join(app.root_path, 'static', 'uploads', 'tracks')
    if not os.path.exists(os.path.join(file_path, filename)):
        abort(404)

    track = db.tracks.find_one({'file_path': "/uploads/tracks/" + filename})
    if not track:
        abort(404)
        
    album = get_album_by_id(track['album_id'])
    if not album:
        abort(404)
        
    user = get_user_by_id(album['user_id'])
    if not user:
        abort(404)
        
    if (not track.get('enabled', True) or not album.get('enabled', True)) and not current_user.is_admin:
        abort(404)
        
    if (not track.get('enabled', True) or not album.get('enabled', True)) and current_user.is_admin:
        return send_from_directory(file_path, filename)

    # Update play count
    db.tracks.update_one({'_id': track['_id']}, {'$inc': {'played': 1}})
    return send_from_directory(file_path, filename)


# Webpage

@app.route("/")
def index():
    # Fetch latest releases
    if not is_admin(current_user):
        latest_releases_query = {'enabled': True}
    else:
        latest_releases_query = {}
        
    latest_releases_data = list(db.albums.find(latest_releases_query).sort('created_at', -1).limit(4))
    
    latest_releases = []
    for release in latest_releases_data:
        user = get_user_by_id(release['user_id'])
        if user and (user.enabled or is_admin(current_user)):
            latest_releases.append((
                release,
                user,
                release.get('enabled', True) and user.enabled
            ))

    # Fetch most played tracks
    if not is_admin(current_user):
        most_played_query = {'played': {'$gt': 0}, 'enabled': True}
    else:
        most_played_query = {'played': {'$gt': 0}}
        
    most_played_data = list(db.tracks.find(most_played_query).sort('played', -1).limit(4))
    
    most_played = []
    for track in most_played_data:
        album = get_album_by_id(track['album_id'])
        if album:
            user = get_user_by_id(album['user_id'])
            if user and (user.enabled or is_admin(current_user)):
                most_played.append((
                    track,
                    user,
                    track.get('enabled', True) and album.get('enabled', True) and user.enabled
                ))

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
    
    # Check if user already exists
    if db.users.find_one({'artistName': artistName}) \
       or db.users.find_one({'username': username}) \
       or db.users.find_one({'email': email}):
        abort(409)

    # Create new user
    user_data = {
        'artistName': artistName,
        'username': username,
        'email': email,
        'enabled': True,
        'is_admin': False
    }
    new_user = User(user_data)
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
    user = get_user_by_username(username)
    
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
    album_data = get_album_by_id(album_id)
    if not album_data:
        abort(404)
        
    if request.method == "GET":
        if album_data and (album_data.get('enabled', True) or current_user.is_admin):
            user_data = get_user_by_id(album_data['user_id'])
            if not user_data:
                abort(404)
            return render_template("album.html", title=album_data['title'], album_data=album_data, user_data=user_data)
        else:
            abort(404)

    if not current_user.is_admin:
        abort(405)

    # Toggle album enabled status
    db.albums.update_one(
        {'_id': ObjectId(album_id)},
        {'$set': {'enabled': not album_data.get('enabled', True)}}
    )
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

    # Create album
    album = {
        'title': request.form["album_title"],
        'user_id': user.id,
        'release_date': datetime.strptime(request.form['release_date'], '%Y-%m-%d'),
        'record_label': request.form.get('record_label'),
        'language': request.form['language'],
        'primary_genre': request.form['primary_genre'],
        'secondary_genre': request.form.get('secondary_genre'),
        'created_at': datetime.utcnow(),
        'enabled': True
    }

    # Handle cover image
    cover_image = request.files['cover_image']
    if cover_image:
        filename = secure_filename(f"{user.artistName}_{album['title']}_{time.time_ns()}_cover.jpg")
        cover_image.save(os.path.join(app.config['UPLOAD_FOLDER'], 'covers', filename))
        album['cover_image'] = "/uploads/covers/" + filename

    # Check if any track is explicit
    for i in range(track_count):
        try:
            request.form[f"is_explicit_{i}"]
            album['explicit'] = True
            break
        except:
            pass
    else:
        album['explicit'] = False

    # Insert album to database
    album_id = db.albums.insert_one(album).inserted_id

    # Process tracks
    for i in range(track_count):
        confirmed_featurings = []
        if request.form.get(f'has_featuring_{i}'):
            featurings = request.form.getlist(f'featuring_{i}[]')

            for featuring in featurings:
                featuring_user = get_user_by_artist_name(featuring)
                if featuring_user and featuring_user.id == user.id:
                    flash(f"You tried to add yourself as a featuring, we skipped it.")
                elif featuring_user and featuring_user.enabled:
                    confirmed_featurings.append(featuring_user.id)
                else:
                    flash(f"User with artist name '{featuring}' doesn't exist. Ask them to create an account in Fanmade.")
                    return redirect(url_for('upload'))

        is_explicit = False
        try:
            request.form[f"is_explicit_{i}"]
            is_explicit = True
        except:
            pass

        track = {
            'title': request.form[f'track_title_{i}'],
            'album_id': str(album_id),
            'version_type': request.form[f'version_type_{i}'],
            'explicit': is_explicit,
            'enabled': True,
            'played': 0,
            'featuring': confirmed_featurings
        }
        
        # Handle track file upload
        track_file = request.files[f'track_file_{i}']
        if track_file:
            filename = secure_filename(f"{user.artistName}_{album['title']}_{track['title']}_{time.time_ns()}.mp3")
            track_file.save(os.path.join(app.config['UPLOAD_FOLDER'], 'tracks', filename))
            track['file_path'] = "/uploads/tracks/" + filename
        
        # Insert track to database
        track_id = db.tracks.insert_one(track).inserted_id

        # Process credits
        written_by = request.form.getlist(f"written_by_{i}[]")
        produced_by = request.form.getlist(f"produced_by_{i}[]")
        metadata_by = request.form.getlist(f"metadata_by_{i}[]")

        if not written_by:
            written_by = [current_user.artistName]
            flash("You are required to insert a writer on the writer list. As it wasn't added, your artist name will be added.")

        credits = []
        for writer in written_by:
            credits.append({
                'track_id': str(track_id),
                'category': 2,  # Writer
                'name': writer
            })

        for producer in produced_by:
            credits.append({
                'track_id': str(track_id),
                'category': 3,  # Producer
                'name': producer
            })

        for metadata in metadata_by:
            credits.append({
                'track_id': str(track_id),
                'category': 4,  # Metadata
                'name': metadata
            })

        if credits:
            db.credits.insert_many(credits)

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
        user_data = get_user_by_username(username)

    if not user_data or not user_data.enabled:
        abort(404)
    
    # Get latest releases
    latest_releases = list(db.albums.find({'user_id': user_data.id, 'enabled': True}).sort('created_at', -1).limit(4))
    
    # Get featuring albums
    # This is a bit tricky without SQL joins, so we'll handle it differently
    featuring_tracks = list(db.tracks.find({'featuring': user_data.id}))
    featuring_album_ids = [track['album_id'] for track in featuring_tracks]
    featurings = []
    if featuring_album_ids:
        featurings = list(db.albums.find({'_id': {'$in': [ObjectId(aid) for aid in featuring_album_ids]}, 'enabled': True}).sort('created_at', -1).limit(4))
    
    # Get most played track
    most_played = db.tracks.find_one(
        {'enabled': True, 'album_id': {'$in': [str(album['_id']) for album in latest_releases]}},
        sort=[('played', -1)]
    )
    
    # Check if current user follows the artist
    follows = False
    if not isinstance(current_user, AnonymousUserMixin):
        follows = bool(db.follows.find_one({'follower_id': current_user.id, 'followed_id': user_data.id}))

    return render_template("artist.html", follows=follows, current_data=current_user, title=user_data.artistName, 
                          latest_releases=latest_releases, featurings=featurings, user_data=user_data, most_played=most_played)

@app.route("/follow/<user_id>", methods=["POST"])
def follow(user_id: str):
    if isinstance(current_user, AnonymousUserMixin) or user_id == current_user.id:
        abort(401)

    user = get_user_by_id(user_id)
    if not user:
        flash(f"User with id {user_id} doesn't exist.")
        return redirect(url_for('index'))

    if db.follows.find_one({'follower_id': current_user.id, 'followed_id': user_id}):
        flash(f"You already follow {user.artistName}.")
    else:
        db.follows.insert_one({
            'follower_id': current_user.id,
            'followed_id': user_id
        })

    return redirect(url_for('artist', username="@" + user.username))

@app.route("/unfollow/<user_id>", methods=["POST"])
def unfollow(user_id: str):
    if isinstance(current_user, AnonymousUserMixin):
        abort(401)
        
    user = get_user_by_id(user_id)
    if not user:
        flash(f"User with id {user_id} doesn't exist.")
        return redirect(url_for('index'))

    if not db.follows.find_one({'follower_id': current_user.id, 'followed_id': user_id}):
        flash(f"You don't follow {user.artistName}.")
    else:
        db.follows.delete_one({'follower_id': current_user.id, 'followed_id': user_id})

    return redirect(url_for('artist', username="@" + user.username))

@app.route('/search', methods=['GET'])
def search():
    query = request.args.get('query')  # Get search query
    results = []
    
    if query:
        try:
            # Search for albums by title
            title_results = list(db.albums.find({'title': {'$regex': query, '$options': 'i'}}))
            
            # Search for artists by name or username
            artist_ids = []
            artists = list(db.users.find({
                '$or': [
                    {'artistName': {'$regex': query, '$options': 'i'}},
                    {'username': {'$regex': query, '$options': 'i'}}
                ]
            }))
            
            for artist in artists:
                artist_ids.append(str(artist['_id']))
                
            # Get albums by these artists
            artist_albums = list(db.albums.find({'user_id': {'$in': artist_ids}}))
            
            # Combine results
            results = title_results + artist_albums
            
            # Remove duplicates
            seen_ids = set()
            unique_results = []
            for album in results:
                if str(album['_id']) not in seen_ids:
                    seen_ids.add(str(album['_id']))
                    unique_results.append(album)
                    
            results = unique_results
            
        except Exception as e:
            # You can log the error if needed
            print(f"Error performing search: {e}")
    else:
        return redirect(url_for('index'))
    
    return render_template('search.html', query=query, results=results, title=f"\"{query}\"")

# API
@app.route("/api/v1/play/<track_id>")
def play(track_id: str):
    track = get_track_by_id(track_id)
    if not track or not track.get('enabled', True):
        abort(404)
    
    album = get_album_by_id(track['album_id'])
    if not album:
        abort(404)
        
    user_data = get_user_by_id(album['user_id'])
    if not user_data:
        abort(404)
        
    response = {
        "track_title": track['title'],
        "track_url": "/tracks/" + track['file_path'].replace("/uploads/tracks/", ""),
        "album_title": album['title'],
        "artist_name": user_data.artistName,
        "cover_image": url_for('static', filename=album['cover_image']),
        "album_id": str(album['_id'])
    }
    return jsonify(response)

@app.route("/api/v1/credits/<track_id>")
def track_credits(track_id: str):
    track_data = get_track_by_id(track_id)
    if not track_data or not track_data.get('enabled', True):
        abort(404)

    album = get_album_by_id(track_data['album_id'])
    if not album:
        abort(404)
        
    user_data = get_user_by_id(album['user_id'])
    if not user_data:
        abort(404)

    credits = []

    # Get performers (main artist + featuring artists)
    performers_category = db.credits_categories.find_one({'id': 1})
    category_name = performers_category['name'] if performers_category else "Performed by"
    
    artists = [user_data.artistName]
    for featuring_id in track_data.get('featuring', []):
        featuring_user = get_user_by_id(featuring_id)
        if featuring_user:
            artists.append(featuring_user.artistName)

    credits.append({
        "name": category_name,
        "artists": artists
    })

    # Get other credits
    track_credits = list(db.credits.find({'track_id': track_id}))
    categories = list(db.credits_categories.find())
    
    categories_dict = {cat['id']: cat['name'] for cat in categories}
    
    for credit in track_credits:
        category_name = categories_dict.get(credit['category'], f"Category {credit['category']}")
        existing_credit = next((item for item in credits if item["name"] == category_name), None)
        if existing_credit:
            existing_credit["artists"].append(credit['name'])
        else:
            credits.append({
                "name": category_name,
                "artists": [credit['name']]
            })

    return jsonify(credits)

@app.route("/api/v1/album/<album_id>")
def album_api(album_id: str):
    album = get_album_by_id(album_id)
    if not album:
        abort(404)
        
    tracks = list(db.tracks.find({'album_id': str(album['_id'])}))
    
    return jsonify({
        'title': album['title'],
        'tracks': [str(track['_id']) for track in tracks]
    })

# Health check
@app.route("/health")
def health():
    return jsonify({"status": "ok"})

# Initialize database
def init_db():
    # Create credit categories if they don't exist
    categories = [
        {"id": 1, "name": "Performed by"},
        {"id": 2, "name": "Written by"},
        {"id": 3, "name": "Produced by"},
        {"id": 4, "name": "Metadata by"}
    ]
    
    for category in categories:
        if not db.credits_categories.find_one({"id": category["id"]}):
            db.credits_categories.insert_one(category)
            
    # Create indexes for better performance
    db.users.create_index("username", unique=True)
    db.users.create_index("artistName", unique=True)
    db.users.create_index("email", unique=True)
    db.albums.create_index("user_id")
    db.albums.create_index("created_at")
    db.tracks.create_index("album_id")
    db.tracks.create_index("played")
    db.credits.create_index("track_id")
    db.follows.create_index([("follower_id", 1), ("followed_id", 1)], unique=True)

if __name__ == "__main__":
    init_db()
    app.run(debug=False, port=80)