from pytubefix import Search, YouTube, Channel, Playlist
from pytubefix.cli import on_progress
from flask import Flask, request, redirect
import requests, os, math, re, os.path, webbrowser, threading, time, urllib.parse, base64


# TODO:
# refresh token
# song not found -> enable another itag?
# age restriction?
# + audio quality and/or less file size?


SPOTIFREE_CLIENT_ID = os.environ["SPOTIFREE_CLIENT_ID"]
SPOTIFREE_CLIENT_SECRET = os.environ["SPOTIFREE_CLIENT_SECRET"]
SPOTIFREE_REDIRECT_URI = "http://127.0.0.1:3000/callback"
SCOPES = "playlist-read-private playlist-read-collaborative"
SPOTIFY_TOKEN_FILENAME = "spotifyToken.txt"

API_PLAYLIST_SONG_LIMIT = 100
API_USER_PLAYLIST_LIMIT = 50

spotifyToken = ""
app = Flask(__name__)
auth_code_event = threading.Event() # Event to signal when the auth code is received
auth_code = None


def run_flask():
    app.run(port=3000, threaded=True)


@app.route("/")
def loginSpotify():
    auth_url = "https://accounts.spotify.com/authorize?"
    params = {
        "client_id": SPOTIFREE_CLIENT_ID,
        "response_type": "code",
        "redirect_uri": SPOTIFREE_REDIRECT_URI,
        "scope": SCOPES
    }
    return redirect(auth_url + urllib.parse.urlencode(params))


@app.route("/callback")
def callback():
    global auth_code

    auth_code = request.args.get("code")
    if not auth_code:
        return "Error: No authorization code received."

    # Signal the main thread that auth code is received
    auth_code_event.set()

    return "Authorization successful! You can close this window and return to the CLI."


def requestUserAuthorization():
    global auth_code
    global spotifyToken

    spotifyToken = readTokenFromFile()
    if not spotifyToken == "":
        return

    # Start Flask server in a separate thread
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()

    # Open the authorization URL in the user's browser
    time.sleep(1)  # Give Flask a moment to start
    webbrowser.open(f"http://127.0.0.1:3000/")

    # Wait for user authorization with timeout
    if not auth_code_event.wait(timeout=60):  # Wait up to 60 seconds
        print("Error: Authorization timed out.")
        return

    # Exchange authorization code for an access token
    token_url = "https://accounts.spotify.com/api/token"
    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    data = {
        "grant_type": "authorization_code",
        "code": auth_code,
        "redirect_uri": SPOTIFREE_REDIRECT_URI,
        "client_id": SPOTIFREE_CLIENT_ID,
        "client_secret": SPOTIFREE_CLIENT_SECRET
    }

    response = requests.post(token_url, headers=headers, data=data)
    print("Token exchange status: ", response.status_code)

    if response.status_code == 200:
        token_data = response.json()
        spotifyToken = token_data["access_token"]
        writeTokenToFile(spotifyToken)
    else:
        print("Error:\n", response.json())


def sanitizePlaylistName(dir_name: str) -> str:
    # Define characters to replace
    invalid_chars = r'[\\/:"*?<>|]'  # Windows forbidden characters
    
    # Replace invalid characters with an underscore
    sanitized_name = re.sub(invalid_chars, '_', dir_name)
    
    # Remove trailing spaces and periods
    sanitized_name = sanitized_name.rstrip(' .')
    
    # Optionally replace spaces with underscores (uncomment if needed)
    # sanitized_name = sanitized_name.replace(' ', '_')
    
    return sanitized_name


def downloadAudio(url, dir="/songs"):
    yt = YouTube(url, on_progress_callback=on_progress)
    #print(yt.streams.filter(only_audio=True))

    stream = yt.streams.get_by_itag(251)
    if stream is None:
        return False

    print("\n\nDownloading: " + yt.title + "\nLink: " + url)
    path = "SpotifreeLibrary" + dir
    stream.download(output_path=path)
    #ys = yt.streams.get_audio_only()
    #ys.download(output_path="songs")
    return True


def getBestMatches(query):
    return Search(query).videos


def findFirstYoutubeLink(query):
    return Search(query).videos[0].watch_url
    

def searchYoutubeLinks(query, max_results):
    results = Search(query)
    counter = 1
    print("\n")

    for video in results.videos:
        if counter > max_results:
            break

        print("Video #" + str(counter))
        print(f'Title: {video.title}')
        
        c = Channel(video.channel_url)
        print(f'Channel name: {c.channel_name}')

        print(f'URL: {video.watch_url}')
        print(f'Duration: {video.length} sec')
        print('\n')
        counter += 1

    option = ""
    while not (option == "1" or option == "2" or option == "3" or option == "0"):
        option = input("Download video 1, 2 or 3?\nType 0 if you want more results. ")

    if (option == "1" or option == "2" or option == "3"):
        opt = int(option) - 1

    if (option == "0"):
        return searchYoutubeLinks(query, 10)

    return results.videos[opt].watch_url


def getSongTitle(link):
    # https://open.spotify.com/intl-pt/track/4fiOTntQKr24p07FvQDHZE?si=840a4f2c981242e5
    spotifyId = link.split("track/")[1]
    if "?" in spotifyId:
        spotifyId = spotifyId.split("?")[0]

    requestLink = "https://api.spotify.com/v1/tracks/" + spotifyId
    headers = {"Authorization": "Bearer  " + spotifyToken}
    response = requests.get(requestLink, headers=headers)

    statusCode = str(response.status_code)
    print("API get track: " + statusCode)
    if statusCode == "401":
        authenticateSpotifyAPI(True)
        return getSongTitle(link)

    json = response.json()
    song = json["name"]
    artist = json["artists"][0]["name"]
    return artist + " " + song


def getPlaylist(link):
    # https://open.spotify.com/playlist/00LFxfOUZMurohHqzE2nFP?si=ea90148f3d4344fd
    spotifyId = link.split("playlist/")[1]
    if "?" in spotifyId:
        spotifyId = spotifyId.split("?")[0]

    requestLink = "https://api.spotify.com/v1/playlists/" + spotifyId
    headers = {"Authorization": "Bearer  " + spotifyToken}
    fields = "name,tracks(total,items(track(name,artists(name))))"
    limit = API_PLAYLIST_SONG_LIMIT
    offset = 0 
    payload = {"fields": fields, "limit": limit, "offset": offset}

    response = requests.get(requestLink, headers=headers, params=payload)
    statusCode = str(response.status_code)
    print("API get playlist tracks: " + statusCode)

    if statusCode == "401":
        authenticateSpotifyAPI(True)
        return getPlaylist(link)

    if statusCode == "404":
        print("It is not possible to download a private or Spotify-owned playlist :(")
        return {}

    json = response.json()
    #print(json)

    playlistName = json["name"]
    songs = json["tracks"]["items"]
    totalSongNum = json["tracks"]["total"]

    additionalRequestNum = math.ceil((totalSongNum - API_PLAYLIST_SONG_LIMIT) / API_PLAYLIST_SONG_LIMIT)
    #print("totalSongNum: " + str(totalSongNum))
    #print("additionalRequestNum: " + str(additionalRequestNum))

    fields = "items(track(name,artists(name)))"
    requestLink += "/tracks"

    for addtReq in range(additionalRequestNum):
        offset += API_PLAYLIST_SONG_LIMIT
        payload = {"fields": fields, "limit": limit, "offset": offset}
        response = requests.get(requestLink, headers=headers, params=payload)
    
        #print("additional Request num " + str(addtReq+1) + " status code: " + str(response.status_code))
        #print("offset: " + str(offset))
        #print("limit: " + str(limit) + "\n")

        json = response.json()
        #print(json)
        songs += json["items"]

    info = {}
    songsTitles = []

    for song in songs:
        title = song["track"]["artists"][0]["name"] + " " # first artist name
        title += song["track"]["name"] # song name
        songsTitles.append(title)

    info["songsTitles"] = songsTitles
    info["title"] = playlistName

    return info


def searchYoutubeManually():
    resultNum = int(input("Type the number of results you want to choose from.\n(1 chooses automatically the best match): "))
    query = input("Search: ")
    url = ""

    if (resultNum < 1):
        print("Bruh")
        return
    elif (resultNum == 1):
        url = findFirstYoutubeLink(query)
    else:
        url = searchYoutubeLinks(query, resultNum)

    downloadAudio(url)


def donwloadSpotifySong():
    authenticateSpotifyAPI()

    songSpotifyLink = input("Spotify song link: ")
    songTitle = getSongTitle(songSpotifyLink)
    print("Song Title: " + songTitle)

    videos = getBestMatches(songTitle)
    # print("videos len: " + str(len(videos)))
    idx = 0
    success = False
    
    while not success and idx < len(videos):
        success = downloadAudio(videos[idx].watch_url)
        idx += 1

    if success:
        print("\n\nSong downloaded successfully.")
    else:
        print("\n\nIt was not possible to download this song. Please search Youtube manually (option 1).")


def downloadSpotifyPlaylist():
    authenticateSpotifyAPI()
    playlistLink = input("Spotify playlist link: ")

    playlistInfo = getPlaylist(playlistLink) 
    if (playlistInfo == {}):
        return

    songsTitles = playlistInfo["songsTitles"]
    sanitizedPlaylistTitle = sanitizePlaylistName(playlistInfo["title"])
    playlistDir = "/playlists/" + sanitizedPlaylistTitle

    print("\nTitle: " + sanitizedPlaylistTitle)
    print("Number of songs: " + str(len(songsTitles)))
    print("First song title: " + songsTitles[0])
    print("Last song title: " + songsTitles[len(songsTitles)-1])

    confirmation = input("\nDo you want to continue (y/n)? ")
    if confirmation.lower() == "n":
        return
    
    songsNotFound = []
    
    for songTitle in songsTitles:
        videos = getBestMatches(songTitle)
        # print("videos len: " + str(len(videos)))
        idx = 0
        success = False
        
        while not success and idx < len(videos):
            success = downloadAudio(videos[idx].watch_url, playlistDir)
            idx += 1

        if not success:
            songsNotFound.append(songTitle)

    if songsNotFound == []:
        print("\n\nPlaylist downloaded successfully to folder: " + sanitizedPlaylistTitle)
    else:
        print(f"\n\nIt was not possible to download these {len(songsNotFound)} songs. "
            "Please search Youtube manually (option 1).\n")

        for songTitle in songsNotFound:
            print(songTitle)


def downloadUserPlaylists():
    requestUserAuthorization()
    print("downloadUserPlaylists")
    # authenticateSpotifyAPI(authorizationCode=True)

    requestLink = "https://api.spotify.com/v1/me/playlists"
    headers = {"Authorization": "Bearer  " + spotifyToken}
    payload = {"limit": API_USER_PLAYLIST_LIMIT, "offset": 0}

    response = requests.get(requestLink, headers=headers, params=payload)
    statusCode = str(response.status_code)
    print("API get user playlists: " + statusCode)

    if statusCode == "401":
        authenticateSpotifyAPI(True)
        return downloadUserPlaylists()

    json = response.json()
    print(json)


def downloadYoutubeSong():
    url = input("Youtube song link: ")
    downloadAudio(url)
    print("\n\nSong downloaded successfully.")


def downloadYoutubePlaylist():
    url = input("Youtube playlist link: ")
    playlist = Playlist(url)
    
    sanitizedName = sanitizePlaylistName(playlist.title)
    playlistDir = "/playlists/" + sanitizedName
    videos = playlist.videos

    print("\nTitle: " + sanitizedName)
    print("Number of songs: " + str(len(videos)))
    print("First song title: " + videos[0].title)
    print("Last song title: " + videos[len(videos) - 1].title)

    confirmation = input("\nDo you want to continue (y/n)? ")
    if confirmation.lower() == "n":
        return

    for video in videos:
        downloadAudio(video.watch_url, playlistDir)

    print("\n\nPlaylist downloaded successfully to folder: " + sanitizedName)


def readTokenFromFile():
    if not os.path.isfile(SPOTIFY_TOKEN_FILENAME):
        f = open(SPOTIFY_TOKEN_FILENAME, "x")
        f.close()
        return ""

    f = open(SPOTIFY_TOKEN_FILENAME, "r")
    token = f.read()
    f.close()

    #if not token == "":
        # print("Token read from file.")

    return token

def writeTokenToFile(token):
    f = open(SPOTIFY_TOKEN_FILENAME, "w")
    f.write(token)
    f.close()


def authenticateSpotifyAPI(tokenExpired=False, authorizationCode=False):
    global spotifyToken
    spotifyToken = readTokenFromFile()
    if not spotifyToken == "" and not tokenExpired:
        return
    
    # print("authenticating in Spotify API...")
    clientId = os.environ["SPOTIFREE_CLIENT_ID"]
    clientSecret = os.environ["SPOTIFREE_CLIENT_SECRET"]

    requestLink = "https://accounts.spotify.com/api/token"

    if authorizationCode:
        headers = {"Content-Type": "application/x-www-form-urlencoded",
                   "Authorization": 'Basic ' + base64.b64encode((f"{SPOTIFREE_CLIENT_ID}:{SPOTIFREE_CLIENT_SECRET}").encode()).decode()}
        body = {"grant_type": "authorization_code", "code": auth_code, "redirect_uri": SPOTIFREE_REDIRECT_URI}
    else:
        headers = {"Content-Type": "application/x-www-form-urlencoded"}
        body = {"grant_type": "client_credentials", "client_id": clientId, "client_secret": clientSecret}

    response = requests.post(requestLink, headers=headers, data=body)

    print(f'API authentication (authCode: {authorizationCode}): ' + str(response.status_code))
    json = response.json()
    print(json)
    spotifyToken = json["access_token"]
    writeTokenToFile(spotifyToken)


def printOptions():
    print("0: Exit.")
    print("")
    print("1: Search Youtube.")
    print("2: Download Youtube song using its link.")
    print("3: Download Youtube playlist using its link.")
    print("")
    print("4: Download Spotify song using its link.")
    print("5: Download Spotify playlist using its link.")
    print("6: Download your owned or followed Spotify playlists.")
    print("")


def main():
    print("Welcome to Spotifree!\n")

    option = 999
    while not option == 0:
        printOptions()
        option = int(input("Your choice: "))
        
        match option:
            case 1: searchYoutubeManually() 
            case 2: downloadYoutubeSong()
            case 3: downloadYoutubePlaylist()

            case 4: donwloadSpotifySong()
            case 5: downloadSpotifyPlaylist()
            case 6: downloadUserPlaylists()
            
        print("\n")        

    print("Finished.")


main()
