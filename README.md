# SpotifyPlaylistSync
Synchronize several Spotify Playlists.

This script will synchronize from a playlist or your saved songs to another playlist. If you delete a song in the destination playlist it will not be readded. This is useful to automatically have a playlist which is a subset of another playlist (e.g. to be able to have a subset of your saved songs for offline use). Another usecase is to archive your discover weekly playlist.

## Installation
Copy `spotisync.ini.template` to `spotisync.ini`. Create a new app in the developer portal of Spotify. Enter the app id and app secret in the ini file. Call `./spotisync.py --playlists` to get a list of your playlists. Enter the displayed ids for the desired playlists in the ini file.

The first time you run the script it will require authentication. In the browser which opens just click accept. You will be redirected to a page on localhost which does not exist. Copy the whole url into the terminal window. The script now has a token and should not require further authentication. If it should not work anymore just set `token` and `refresh_token` in the ini file to the empty string.

You can have several syncs at a time. Just number them in the ini file, each one consists of `src#` and `dst#` where they represent the id of the source and destination playlists. If you want to use your saved songs as the source just leave it empty.
