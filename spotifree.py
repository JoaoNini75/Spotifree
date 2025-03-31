from pytubefix import Search, YouTube, Channel
from pytubefix.cli import on_progress
import requests, os, math, re

# TODO:
# song not found -> enable another itag?
# age restriction

API_PLAYLIST_SONG_LIMIT = 100
spotifyToken = ""


def sanitizePlaylistname(dir_name: str) -> str:
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
        print("It is not possible to download this playlist :(")
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
        print("Song downloaded successfully.")
    else:
        print("It was not possible to download this song. Please search Youtube manually (option 1).")


def downloadSpotifyPlaylist():
    authenticateSpotifyAPI()
    playlistLink = input("Spotify playlist link: ")

    playlistInfo = getPlaylist(playlistLink) 
    if (playlistInfo == {}):
        return

    songsTitles = playlistInfo["songsTitles"]
    sanitizedPlaylistTitle = sanitizePlaylistname(playlistInfo["title"])
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
        print("\nPlaylist downloaded successfully to folder: " + sanitizedPlaylistTitle)
    else:
        print(f"It was not possible to download these {len(songsNotFound)} songs. "
            "Please search Youtube manually (option 1).\n")

        for songTitle in songsNotFound:
            print(songTitle)


def readTokenFromFile():
    f = open("spotifyToken.txt", "r")
    token = f.read()
    f.close()

    if not token == "":
        print("Token read from file.")

    return token

def writeTokenToFile(token):
    f = open("spotifyToken.txt", "w")
    f.write(token)
    f.close()


def authenticateSpotifyAPI(tokenExpired=False):
    global spotifyToken
    spotifyToken = readTokenFromFile()
    if not spotifyToken == "" and not tokenExpired:
        return
    
    print("authenticating in Spotify API...")
    clientId = os.environ["SPOTIFREE_CLIENT_ID"]
    clientSecret = os.environ["SPOTIFREE_CLIENT_SECRET"]

    requestLink = "https://accounts.spotify.com/api/token"
    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    body = {"grant_type": "client_credentials", "client_id": clientId, "client_secret": clientSecret}
    response = requests.post(requestLink, headers=headers, data=body)

    print("API authentication: " + str(response.status_code))
    spotifyToken = response.json()["access_token"]
    writeTokenToFile(spotifyToken)


def printOptions():
    print("0: Exit.")
    print("1: Search Youtube manually.")
    print("2: Download Spotify song using its link.")
    print("3: Download Spotify playlist using its link.")
    print("")


def main():
    print("Welcome to Spotifree!\n")

    option = 999
    while not option == 0:
        printOptions()
        option = int(input("Your choice: "))
        
        match option:
            case 1: searchYoutubeManually() 
            case 2: donwloadSpotifySong()
            case 3: downloadSpotifyPlaylist()
            
        print("\n")        

    print("Finished.")


main()
