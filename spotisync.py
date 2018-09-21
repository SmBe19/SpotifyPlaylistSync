#!/usr/bin/env python3

import argparse
import base64
import configparser
import json
import os
import re
import requests
import urllib
import webbrowser

os.chdir(os.path.dirname(os.path.abspath(__file__)))

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

    def save_data(self):
        with open('spotisync.dat', 'w') as f:
            json.dump(self.data, f)

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
        if not self.refresh_token:
            self.do_oauth()
        else:
            self.do_refresh_token()

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
        m = re.match('http://127.0.0.1:65010/authorize_callback\?code=([^&]*)&state=whatev', code)
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
        r.raise_for_status()
        rj = r.json()
        items = rj['items']
        while rj['next']:
            r = requests.get(rj['next'], headers=self.get_auth_header())
            r.raise_for_status()
            rj = r.json()
            items.extend(rj['items'])
        return items

    def list_playlists(self):
        r = requests.get('https://api.spotify.com/v1/me/playlists', {
            'limit': 50
        }, headers=self.get_auth_header())
        lists = self.get_all_pages(r)
        for l in lists:
            print("{} - {}".format(l['id'], l['name']))

    def get_playlist_tracks(self, id):
        r = requests.get('https://api.spotify.com/v1/playlists/{}/tracks'.format(id), {
            'limit': 50
        }, headers=self.get_auth_header())
        return self.get_all_pages(r)

    def get_user_tracks(self):
        r = requests.get('https://api.spotify.com/v1/me/tracks', headers=self.get_auth_header())
        return self.get_all_pages(r)

    def playlist_contains(self, tracks, id):
        for track in tracks:
            if id == track['track']['id']:
                return True
        return False

    def synchronize_playlist(self, src, dst):
        src_tracks = self.get_playlist_tracks(src) if src else self.get_user_tracks()
        dst_tracks = self.get_playlist_tracks(dst)
        k = src + '#' + dst
        if k not in self.data:
            self.data[k] = []
        synced = self.data[k]
        to_add = []
        if not src:
            src_tracks = src_tracks[::-1]
        for track in src_tracks:
            id = track['track']['id']
            if id not in synced:
                synced.append(id)
                if self.playlist_contains(dst_tracks, id):
                    continue
                to_add.append(track['track']['uri'])
        for st in range(0, len(to_add), 100):
            r = requests.post('https://api.spotify.com/v1/playlists/{}/tracks'.format(dst), json={
                'uris': to_add[st:min(st+100, len(to_add))]
            }, headers=self.get_auth_header())
            r.raise_for_status()

        self.data[k] = synced
        self.save_data()
        print("Synced {} tracks".format(len(to_add)))

    def synchronize_playlists(self):
        for key in self.config['syncs']:
            if key.startswith('src') and 'dst' + key[3:] in self.config['syncs']:
                self.synchronize_playlist(self.config['syncs'][key], self.config['syncs']['dst' + key[3:]])


def main():
    parser = argparse.ArgumentParser(description="Synchronize Spotify Playlists")
    parser.add_argument('--playlists', action='store_true', help="list playlists")
    args = parser.parse_args()
    s = Spotify()
    s.check_oauth()
    if args.playlists:
        s.list_playlists()
    else:
        s.synchronize_playlists()

if __name__ == '__main__':
    main()
