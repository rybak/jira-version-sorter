#!/usr/bin/env python3
# JIRA version sorter
# Copyright 2020 Andrei Rybak
# See README.md and LICENSE.md for details.

import time
from getpass import getpass
import requests
import json
from typing import List

import config


rest_session = requests.Session()
auth = None


# REST boilerplate
def get_auth():
    global auth
    if auth is None:
        print('url: {0}'.format(config.jira_url))
        print('login: {0}'.format(config.my_user_name))
        my_pass = getpass(prompt="jira pass:")
        auth = (config.my_user_name, my_pass)
    return auth


def reset_auth():
    global auth
    auth = None


def init_session() -> None:
    if auth is not None:
        return
    rest_session.auth = get_auth()
    rest_session.verify = config.verify


# JSON boilerplate
def pretty_print(json_obj):
    print(str(json.dumps(json_obj, indent=4, separators=(',', ': '))))


def save_json(json_obj, fn):
    with open(fn, 'w') as f:
        f.write(json.dumps(json_obj, separators=(',', ':')))


# JIRA REST APIs
def get_issue_url(issue_key: str) -> str:
    return config.jira_url + '/rest/api/2/issue/' + issue_key


# https://docs.atlassian.com/software/jira/docs/api/REST/7.1.6/#api/2/project-getProjectVersions
def get_versions_url(project_key: str) -> str:
    return config.jira_url + '/rest/api/2/project/' + project_key + '/versions'


# main methods
cache={}
def download_versions(project_key: str):
    if project_key in cache:
        return cache[project_key]
    versions_url = get_versions_url(project_key)
    while True:
        try:
            init_session()
            r = rest_session.get(versions_url)
            if r.status_code != 200:
                print(r)
                print("Versions download failed for {}".format(project_key))
                if r.status_code == 401:
                    print("Wrong password")
                    reset_auth()
                    # go into while True again, ask for password one more time
                    continue
                if r.status_code == 403:
                    print("Need to enter CAPTCHA in the web JIRA interface")
                    reset_auth()
                    continue
                if r.status_code == 404:
                    print("No project {}".format(project_key))
                    return None
            else:
                cache[project_key] = r.json()
                return r.json()
        except requests.exceptions.ConnectionError as ce:
            print("Connection error: {}".format(ce))
            print("You might need to define 'verify' in config.py.")
            print("Current value: config.verify =", config.verify)
            time.sleep(5)
            return None


# https://docs.atlassian.com/software/jira/docs/api/REST/7.1.6/#api/2/version-moveVersion
def move_version(to_move, prev):
    move_url = '{}/rest/api/2/version/{}/move'.format(config.jira_url, to_move['id'])
    init_session()
    r = rest_session.post(move_url, json={
        "after": prev['self']
    })
    print(r)


def logged_download(key):
    vs = download_versions(key)
    print(key + ' START')
    pretty_print(vs)
    print(key + ' FINISH')
    return vs


def find_version(s, vs):
    for v in vs:
        if v['name'] == s:
            return v
    return None


# special value, which isn't used in practice (all numbers in versions are non-negative)
NON_NUMBER = -100


def extact_major(n: str, version_part_scheme) -> int:
    parts = n.split('.')
    if len(parts) != version_part_scheme:
        return NON_NUMBER
    try:
        return int(parts[0])
    except:
        return NON_NUMBER


def extact_minor(n: str, version_part_scheme) -> int:
    parts = n.split('.')
    if len(parts) != version_part_scheme:
        return NON_NUMBER
    try:
        return int(parts[1])
    except:
        return NON_NUMBER


def is_ordered(v_old: str, v_new: str, vs, version_part_scheme):
    try:
        old_idx = vs.index(v_old)
        new_idx = vs.index(v_new)
        old_major = extact_major(v_old, version_part_scheme)
        new_major = extact_major(v_new, version_part_scheme)
        if old_major != new_major:
            return old_idx < new_idx
        if version_part_scheme == 3:
            old_minor = extact_minor(v_old, version_part_scheme)
            new_minor = extact_minor(v_new, version_part_scheme)
            if old_minor != new_minor:
                return old_idx < new_idx
        return old_idx + 1 == new_idx
    except Exception as e:
        print("WARNING: could not find version in the list " + str(e))
        return None


def dict_versions(vs):
    # strip() is needed, because sometimes there are typos in versions
    return { v['name'].strip(): v for v in vs }


def clean_up_release(key, major_versions, version_part_scheme=3):
    vs = download_versions(key)
    m = dict_versions(vs)
    for v in vs:
        if v['name'].split('.') == version_part_scheme and ' ' in v['name']:
            print("WARNING: probable typo in version name '{}'".format(v['name']))
    names = [v['name'] for v in vs]


    release_ns = list(filter(lambda v: extact_major(v, version_part_scheme) in major_versions, names))

    # sort as tuples to avoid lexicographic order
    parsed = sorted([tuple(map(int, n.split('.'))) for n in release_ns])

    def format_three(p):
        return '{}.{}.{}'.format(p[0], p[1], p[2])
    def format_two(p):
        return '{}.{}'.format(p[0], p[1])
    format_version = None
    if version_part_scheme == 3:
        format_version = format_three
    elif version_part_scheme == 2:
        format_version = format_two
    sorted_ns = list(map(format_version, parsed))
    moved_counter = 0
    for (ovn, nvn) in list(zip(sorted_ns, sorted_ns[1:])):
        if not is_ordered(ovn, nvn, release_ns, version_part_scheme):
            if nvn[-2:] == '.0':
                print("Not moving a first build " + nvn)
                continue
            print(key + ": Moving " + nvn + " to be after " + ovn)
            ov = m[ovn]
            nv = m[nvn]
            old_index = release_ns.index(ovn)
            new_index = release_ns.index(nvn)
            release_ns[old_index], release_ns[new_index] = release_ns[new_index], release_ns[old_index]
            move_version(nv, ov)
            moved_counter += 1
    del cache[key]
    return moved_counter

ret = 0
while True:
    # ret = clean_up_release('BSERV', list(range(450, 500)), 2)
    # ret = clean_up_release('TEST', list(range(1960, 1990)), 3)
    if ret == 0:
        break
