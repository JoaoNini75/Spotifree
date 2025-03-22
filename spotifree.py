from pytubefix import Search, YouTube, Channel
from pytubefix.cli import on_progress
import requests 
import os


spotifyToken = ""


def downloadAudio(url, dir=""):
    yt = YouTube(url, on_progress_callback=on_progress)
    #print(yt.streams.filter(only_audio=True))
    print("\nDownloading: " + yt.title + "\nlink: " + url)

    stream = yt.streams.get_by_itag(251)
    path = "SpotifreeLibrary" + dir
    stream.download(output_path=path)
    #ys = yt.streams.get_audio_only()
    #ys.download(output_path="songs")


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
    print("api get track: " + statusCode)
    if statusCode == "401":
        authenticateSpotifyAPI(True)
        return getSongTitle(link)

    json = response.json()
    song = json["name"]
    artist = json["artists"][0]["name"]
    return song + " " + artist


def getPlaylist(link):
    # https://open.spotify.com/playlist/00LFxfOUZMurohHqzE2nFP?si=ea90148f3d4344fd
    spotifyId = link.split("playlist/")[1]
    if "?" in spotifyId:
        spotifyId = spotifyId.split("?")[0]

    requestLink = "https://api.spotify.com/v1/playlists/" + spotifyId
    headers = {"Authorization": "Bearer  " + spotifyToken}

    fields = "name,tracks(total,items(track(name,artists(name))))"
    limit = 50
    offset = 0 
    payload = {"fields": fields, "limit": limit, "offset": offset}

    response = requests.get(requestLink, headers=headers, params=payload)
    statusCode = str(response.status_code)
    print("api get playlist tracks: " + statusCode)
    if statusCode == "401":
        authenticateSpotifyAPI(True)
        return getPlaylist(link)

    json = response.json()
    playlistName = json["name"]
    songs = json["tracks"]["items"]
    totalSongNum = json["tracks"]["total"]
    print("totalSongNum: " + str(totalSongNum))

    # TODO: playlist com 50+ musicas, musica not found, age restriction

    '''
    while totalSongNum > len(songs):
        fields = "tracks(items(track(name,artists(name))))"
        offset += 50
        payload = {"fields": fields, "limit": limit, "offset": offset}
        response = requests.get(requestLink, headers=headers, params=payload)
        json = response.json()
        songs += json["tracks"]["items"]'
    '''

    info = {}
    songsTitles = []

    for song in songs:
        title = song["track"]["name"] + " " # song name
        title += song["track"]["artists"][0]["name"] # first artist name
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
    print("songTitle: " + songTitle)

    url = findFirstYoutubeLink(songTitle)
    downloadAudio(url)


def downloadSpotifyPlaylist():
    authenticateSpotifyAPI()
    playlistLink = input("Spotify playlist link: ")
    playlistInfo = getPlaylist(playlistLink) 
    songsTitles = playlistInfo["songsTitles"]
    playlistTitle = playlistInfo["title"]

    print("playlist title: " + playlistTitle)
    print("playlist song num: " + str(len(songsTitles)) + "\n")
    playlistDir = "/" + playlistTitle

    for songTitle in songsTitles:
        print(songTitle)
        #url = findFirstYoutubeLink(songTitle)
        #downloadAudio(url, playlistDir)


def readTokenFromFile():
    f = open("spotifyToken.txt", "r")
    token = f.read()
    f.close()
    if not token == "":
        print("token read from file")
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

    print("api authentication: " + str(response.status_code))
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

    print("Finished")


main()
