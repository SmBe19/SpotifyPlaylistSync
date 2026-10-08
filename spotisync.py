#!/usr/bin/env python3

import argparse
import base64
import configparser
import json
import os
import re
import requests
import sys
import traceback
import urllib
import webbrowser

os.chdir(os.path.dirname(os.path.abspath(__file__)))

def eprint(*args, **kwargs):
    print(*args, file=sys.stderr, **kwargs)

class Spotify:

    def __init__(self):
        self.config = configparser.ConfigParser()
        self.config.read('spotisync.ini')
        self.clientid = self.config['spotisync']['clientid']
        self.clientsecret = self.config['spotisync']['clientsecret']
        self.load_tokens()
        self.load_data()

    def load_data(self):
        try:
            with open('spotisync.dat') as f:
                self.data = json.load(f)
        except FileNotFoundError:
            self.data = {}
        try:
            with open('spotisync_tracks.dat') as f:
                self.track_data = json.load(f)
        except FileNotFoundError:
            self.track_data = {}

    def save_data(self):
        with open('spotisync.dat', 'w') as f:
            json.dump(self.data, f)
        with open('spotisync_tracks.dat', 'w') as f:
            json.dump(self.track_data, f)

    def load_tokens(self):
        try:
            self.token = self.config['oauth']['token']
            self.refresh_token = self.config['oauth']['refresh_token']
        except KeyError:
            self.token = None
            self.refresh_token = None

    def get_basic_auth_header(self):
        basic = self.clientid + ':' + self.clientsecret
        basic_enc = basic.encode('utf8')
        return {'Authorization': 'Basic ' + base64.b64encode(basic_enc).decode('utf8')}

    def get_auth_header(self):
        return {'Authorization': 'Bearer ' + self.token}

    def set_tokens(self, token=None, refresh_token=None):
        self.token = token or self.token
        self.refresh_token = refresh_token or self.refresh_token
        if 'oauth' not in self.config:
            self.config['oauth'] = {}
        self.config['oauth']['token'] = self.token
        self.config['oauth']['refresh_token'] = self.refresh_token
        with open('spotisync.ini', 'w') as f:
            self.config.write(f)

    def check_oauth(self):
        if self.refresh_token:
            try:
                self.do_refresh_token()
                return
            except Exception as e:
                eprint("Refreshing token failed", e)
        self.do_oauth()

    def do_refresh_token(self):
        r = requests.post('https://accounts.spotify.com/api/token', {
            'grant_type': 'refresh_token',
            'refresh_token': self.refresh_token
        }, headers=self.get_basic_auth_header())
        r.raise_for_status()
        rj = r.json()
        token = rj['access_token']
        self.set_tokens(token)

    def do_oauth(self):
        query = urllib.parse.urlencode({
            'client_id': self.clientid,
            'response_type': 'code',
            'redirect_uri': 'http://127.0.0.1:65010/authorize_callback',
            'state': 'whatev',
            'scope': 'user-library-read,playlist-modify-public,playlist-read-private,playlist-modify-private'
        })
        url = 'https://accounts.spotify.com/authorize?' + query
        webbrowser.open(url)
        code = input("Give me code:")
        m = re.match('http://127.0.0.1:65010/authorize_callback\\?code=([^&]*)&state=whatev', code)
        if m:
            code = m.group(1)
        r = requests.post('https://accounts.spotify.com/api/token', {
            'grant_type': 'authorization_code',
            'code': code,
            'redirect_uri': 'http://127.0.0.1:65010/authorize_callback'
        }, headers=self.get_basic_auth_header())
        r.raise_for_status()
        rj = r.json()
        token = rj['access_token']
        refresh_token = rj['refresh_token']
        self.set_tokens(token, refresh_token)

    def get_all_pages(self, r):
        retries = 20
        r.raise_for_status()
        rj = r.json()
        items = rj['items']
        while rj['next']:
            r = requests.get(rj['next'], headers=self.get_auth_header())
            if 400 <= r.status_code < 600 and retries > 0:
                retries -= 1
                continue
            r.raise_for_status()
            rj = r.json()
            items.extend(rj['items'])
        return items

    def list_playlists(self):
        r = requests.get('https://api.spotify.com/v1/me/playlists', {
            'limit': 50
        }, headers=self.get_auth_header())
        lists = self.get_all_pages(r)
        print("Playlists")
        for l in lists:
            print("{} - {}".format(l['id'], l['name']))

    def extract_track_data(self, track):
        item = track['item']
        album = item['album']
        return {
            'id': item['id'],
            'name': item['name'],
            'duration_ms': item['duration_ms'],
            'external_ids': item['external_ids'],
            'disc_number': item['disc_number'],
            'track_number': item['track_number'],
            'album': {
                'id': album['id'],
                'name': album['name'],
                'release_date': album['release_date'],
                'artists': [{
                    'id': artist['id'],
                    'name': artist['name'],
                } for artist in album['artists']]
            },
            'artists': [{
                'id': artist['id'],
                'name': artist['name'],
            } for artist in album['artists']]
        }
    
    def list_playlist(self, id):
        r = requests.get('https://api.spotify.com/v1/playlists/{}'.format(id), headers=self.get_auth_header())
        list_meta = r.json()
        print("Playlist {} - {} by {}".format(list_meta['id'], list_meta['name'], list_meta['owner']['display_name']))
        tracks = self.get_playlist_tracks(id)
        for track in tracks:
            print("{} by {}".format(track['item']['name'], ",".join(artist['name'] for artist in track['item']['artists'])))

    def get_playlist_tracks(self, id):
        r = requests.get('https://api.spotify.com/v1/playlists/{}/items'.format(id), {
            'limit': 50
        }, headers=self.get_auth_header())
        return self.get_all_pages(r)

    def get_user_tracks(self):
        r = requests.get('https://api.spotify.com/v1/me/tracks', headers=self.get_auth_header())
        return self.get_all_pages(r)

    def playlist_contains(self, tracks, id):
        for track in tracks:
            if id == track['item']['id']:
                return True
        return False

    def synchronize_playlist(self, src, dst):
        src_tracks = self.get_playlist_tracks(src) if src else self.get_user_tracks()
        dst_tracks = self.get_playlist_tracks(dst)
        k = src + '#' + dst
        if k not in self.data:
            self.data[k] = []
        synced = set(self.data[k])
        to_add = []
        if not src:
            src_tracks = src_tracks[::-1]
        for track in src_tracks:
            if 'item' not in track:
                track['item'] = track['track']
            id = track['item']['id']
            self.track_data[id] = self.extract_track_data(track)
            if id not in synced:
                synced.add(id)
                if self.playlist_contains(dst_tracks, id):
                    continue
                to_add.append(track['item']['uri'])
        for st in range(0, len(to_add), 100):
            r = requests.post('https://api.spotify.com/v1/playlists/{}/items'.format(dst), json={
                'uris': to_add[st:min(st+100, len(to_add))]
            }, headers=self.get_auth_header())
            r.raise_for_status()

        self.data[k] = list(synced)
        self.save_data()
        print("Synced {} tracks".format(len(to_add)))

    def synchronize_playlists(self):
        for key in self.config['syncs']:
            if key.startswith('src') and 'dst' + key[3:] in self.config['syncs']:
                try:
                    self.synchronize_playlist(self.config['syncs'][key], self.config['syncs']['dst' + key[3:]])
                except Exception as e:
                    eprint("Synchronizing playlists failed", e)
                    eprint(traceback.format_exc())


def main():
    parser = argparse.ArgumentParser(description="Synchronize Spotify Playlists")
    parser.add_argument('--playlists', action='store_true', help="list playlists")
    parser.add_argument('--playlist', help="list tracks in playlist")
    args = parser.parse_args()
    s = Spotify()
    s.check_oauth()
    if args.playlists:
        s.list_playlists()
    elif args.playlist:
        s.list_playlist(args.playlist)
    else:
        s.synchronize_playlists()

if __name__ == '__main__':
    main()
