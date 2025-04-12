from pytubefix import Search, YouTube, Channel, Playlist 
from pytubefix.cli import on_progress
from pytubefix.exceptions import LiveStreamError
from flask import Flask, request, redirect
from dotenv import load_dotenv
import requests, os, math, re, os.path, webbrowser, threading, time, urllib.parse, base64


# TODO:
# age restriction?
# song not found -> enable another itag?
# + audio quality and/or less file size?
# refresh token / improve auth


load_dotenv()
SPOTIFREE_CLIENT_ID = os.environ["SPOTIFREE_CLIENT_ID"]
SPOTIFREE_CLIENT_SECRET = os.environ["SPOTIFREE_CLIENT_SECRET"]
SPOTIFREE_REDIRECT_URI = "http://127.0.0.1:3000/callback"
SCOPES = "playlist-read-private playlist-read-collaborative"
TOKENS_FILENAME = "tokens.txt"

API_PLAYLIST_SONG_LIMIT = 100
API_USER_PLAYLIST_LIMIT = 50
FILENAME_SIZE_LIMIT = 60

accessToken = ""
app = Flask(__name__)
authCode_event = threading.Event() # Event to signal when the auth code is received
authCode = ""


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
    global authCode

    authCode = request.args.get("code")
    if not authCode:
        return "Error: No authorization code received."

    # Signal the main thread that auth code is received
    authCode_event.set()
    saveTokensToFile()

    return "Authorization successful! You can close this window and return to the CLI."


def requestUserAuthorization():
    # Start Flask server in a separate thread
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()

    # Open the authorization URL in the user's browser
    time.sleep(1)  # Give Flask a moment to start
    webbrowser.open(f"http://127.0.0.1:3000/")

    # Wait for user authorization with timeout
    if not authCode_event.wait(timeout=60):  # Wait up to 60 seconds
        print("Error: Authorization timed out.")
        return requestUserAuthorization()
    

def printLog(text):
    print("\033[90mLog: " + text + "\033[0m")


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


def shortenFilename(title):
    if len(title) < FILENAME_SIZE_LIMIT:
        return title
    return title[:FILENAME_SIZE_LIMIT] + " (...)"


def downloadAudio(url, dir="/songs"):
    yt = YouTube(url, on_progress_callback=on_progress)
    #print(yt.streams.filter(only_audio=True))
   
    stream = yt.streams.get_by_itag(251)
    if stream is None:
        return False
        
    path = "SpotifreeLibrary" + dir
    safeTitle = shortenFilename(yt.title)
    filename = safeTitle + ".m4a" # for itag 251 
    
    print("\n\nDownloading: " + safeTitle + "\nLink: " + url)
    stream.download(output_path=path, filename=filename)
    
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
    headers = {"Authorization": "Bearer  " + accessToken}
    response = requests.get(requestLink, headers=headers)

    statusCode = str(response.status_code)
    printLog("API get track: " + statusCode)
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
    headers = {"Authorization": "Bearer  " + accessToken}
    fields = "name,tracks(total,items(track(name,artists(name))))"
    limit = API_PLAYLIST_SONG_LIMIT
    offset = 0 
    payload = {"fields": fields, "limit": limit, "offset": offset}

    response = requests.get(requestLink, headers=headers, params=payload)
    statusCode = str(response.status_code)
    printLog("API get playlist tracks: " + statusCode)

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
        return searchYoutubeManually()
    elif (resultNum == 1):
        url = findFirstYoutubeLink(query)
    else:
        url = searchYoutubeLinks(query, resultNum)

    downloadAudio(url)


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

    print("\n\nPlaylist downloaded successfully to folder: " + sanitizedName + "\n")


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


def downloadSpotifyPlaylist(playlistLink="", needConfirmation=True):
    if playlistLink == "":
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

    if needConfirmation:
        confirmation = input("\nDo you want to continue (y/n)? ")
        if confirmation.lower() == "n":
            return
    
    songsNotFound = []
    songIdx = 0

    for songTitle in songsTitles:
        songIdx += 1
        videos = getBestMatches(songTitle)
        # print("videos len: " + str(len(videos)))
        matchIdx = 0
        success = False
        
        while not success and matchIdx < len(videos):
            try:
                success = downloadAudio(videos[matchIdx].watch_url, playlistDir)
                matchIdx += 1
            except LiveStreamError:
                matchIdx += 1

        if success:
            print("Song: " + str(songIdx) + "/" + str(len(songsTitles)))
        else:
            songsNotFound.append(songTitle)

    if songsNotFound == []:
        print("\n\nPlaylist downloaded successfully to folder: " + sanitizedPlaylistTitle)
    else:
        print(f"\n\nIt was not possible to download these {len(songsNotFound)} songs. "
            "Please search Youtube manually (option 1).\n")

        for songTitle in songsNotFound:
            print(songTitle)


def downloadUserPlaylists():
    authenticateSpotifyAPI()

    requestLink = "https://api.spotify.com/v1/me/playlists"
    headers = {"Authorization": "Bearer  " + accessToken}
    payload = {"limit": API_USER_PLAYLIST_LIMIT, "offset": 0}

    response = requests.get(requestLink, headers=headers, params=payload)
    statusCode = str(response.status_code)
    printLog("API get user playlists: " + statusCode + "\n")

    if statusCode == "401":
        authenticateSpotifyAPI(True, True)
        return downloadUserPlaylists()

    json = response.json()
    playlists = json["items"]
    idx = 0

    for playlist in playlists:
        print(str(idx) + " - " + playlist["name"])
        idx += 1
    
    print("\nChoose the playlists you want to download using:")
    printPlaylistChoiceFormat()

    while True:
        answer = input("\nPlaylists to download: ")
        playlistsToDownload = getPlsToDownload(answer, len(playlists))

        if playlistsToDownload == []:
            print("Please check the format you are using:")
            printPlaylistChoiceFormat()
        else:
            break

    print()
    idx = -1

    for playlist in playlists:
        idx += 1
        if playlistsToDownload[idx]:
            print(playlist["name"])

    confirmation = input("\nDo you want to continue (y/n)? ")
    if confirmation.lower() == "n":
            return

    idx = -1
    print()

    for playlist in playlists:
        idx += 1
        if playlistsToDownload[idx]:
            # print(playlist["name"])
            downloadSpotifyPlaylist(playlist["external_urls"]["spotify"], False)

    print("\n\nThe download of your owned or followed Spotify playlists has finished.")


def printPlaylistChoiceFormat():
    print("Comma separated playlist numbers: 0,3,5")
    print("Or intervals: 2-4")
    print("Or a combination of both: 1-4,8-10,12-13")


def getPlsToDownload(answer, maxPlaylistNum):
    result = [False] * maxPlaylistNum
    noDownloads = True
    parts = answer.split(',')
    
    for part in parts:
        part = part.strip()
        if not part:
            continue
        if '-' in part:
            start, end = map(int, part.split('-'))
            for i in range(start, end + 1):
                if 0 <= i < maxPlaylistNum:
                    result[i] = True
                    noDownloads = False
        else:
            i = int(part)
            if 0 <= i < maxPlaylistNum:
                result[i] = True
                noDownloads = False

    if noDownloads:
        return []      
    return result


def readTokensFromFile():
    global authCode
    global accessToken

    if not os.path.isfile(TOKENS_FILENAME):
        f = open(TOKENS_FILENAME, "x")
        f.close()
        return { "authCode" : "", "accessToken" : "" }

    f = open(TOKENS_FILENAME, "r")
    tokens = f.readlines()
    f.close()

    if len(tokens) == 0:
        printLog("LEN == 0!!!")
        return { "authCode" : "", "accessToken" : "" }
    
    authCode = tokens[0]
    accessToken = tokens[1]
    return { "authCode" : tokens[0], "accessToken" : tokens[1] }


def saveTokensToFile():
    open(TOKENS_FILENAME, "w").close() # clear file contents
    f = open(TOKENS_FILENAME, "w")
    f.write(authCode + "\n")
    f.write(accessToken)
    f.close()


def validToken(token):
    return not token == "" and not token == "\n" 


def authenticateSpotifyAPI(tokenExpired=False, useAuthorizationCode=False):
    global authCode
    global accessToken

    tokens = readTokensFromFile()
    authCode = tokens["authCode"]
    accessToken = tokens["accessToken"]

    if validToken(accessToken) and not tokenExpired and not useAuthorizationCode:
        return
    
    if useAuthorizationCode and not validToken(authCode):
        if validToken(tokens["authCode"]):
            authCode = tokens["authCode"]
        else:
            requestUserAuthorization()
            
    clientId = os.environ["SPOTIFREE_CLIENT_ID"]
    clientSecret = os.environ["SPOTIFREE_CLIENT_SECRET"]

    requestLink = "https://accounts.spotify.com/api/token"

    if useAuthorizationCode:
        headers = {"Content-Type": "application/x-www-form-urlencoded",
                   "Authorization": 'Basic ' + base64.b64encode((f"{SPOTIFREE_CLIENT_ID}:{SPOTIFREE_CLIENT_SECRET}").encode()).decode()}
        body = {"grant_type": "authorization_code", "code": authCode, "redirect_uri": SPOTIFREE_REDIRECT_URI}
    else:
        headers = {"Content-Type": "application/x-www-form-urlencoded"}
        body = {"grant_type": "client_credentials", "client_id": clientId, "client_secret": clientSecret}

    response = requests.post(requestLink, headers=headers, data=body)
    json = response.json()
    statusCode = response.status_code

    printLog(f'API authentication (using authCode: {useAuthorizationCode}): ' + str(statusCode))
    printLog(json)

    if statusCode == 400 and json["error_description"] == "Invalid authorization code":
        requestUserAuthorization()
        return authenticateSpotifyAPI(useAuthorizationCode=True)

    accessToken = json["access_token"]
    saveTokensToFile()


def printOptions():
    print("0: Exit.")
    
    print("1: Search Youtube.")
    print("2: Download Youtube song using its link.")
    print("3: Download Youtube playlist using its link.")
    
    print("4: Download Spotify song using its link.")
    print("5: Download Spotify playlist using its link.")
    print("6: Download your owned or followed Spotify playlists.")
    print("")


def main():
    print("Welcome to Spotifree!\n")
    readTokensFromFile()
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

    print("Spotifree finished.\n")


main()
