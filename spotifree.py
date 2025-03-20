from pytubefix import Search, YouTube, Channel
from pytubefix.cli import on_progress


def downloadAudio(url):
    yt = YouTube(url, on_progress_callback=on_progress)
    print(yt.streams.filter(only_audio=True))
    print("\nDownloading: " + yt.title + "\nlink: " + url)

    stream = yt.streams.get_by_itag(251)
    stream.download(output_path="MyMusic")
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


def getSongTitleFromSpotifyLink(link):
    print("todo")


def searchYoutubeManually():
    resultNum = int(input("Type the number of results you want to choose from.\n(1 chooses automatically the best match): "))
    query = input("Search: ")
    url = ""

    if (resultNum == 1):
        url = findFirstYoutubeLink(query)
    else:
        url = searchYoutubeLinks(query, resultNum)

    downloadAudio(url)


def donwloadSpotifySong():
    songSpotifyLink = input("Spotify song link: ")
    songTitle = getSongTitleFromSpotifyLink(songSpotifyLink)
    url = findFirstYoutubeLink(songTitle)
    downloadAudio(url)


def downloadSpotifyPlaylist():
    #query = input("Spotify playlist link: ")
    #url = search(query)
    #downloadAudio(url)
    print("Not implemented yet.")


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
