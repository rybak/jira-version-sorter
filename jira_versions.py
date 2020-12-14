#!/usr/bin/env python3
# JIRA version sorter
# Copyright 2020 Andrei Rybak
# See README.md and LICENSE.md for details.

import time
from getpass import getpass
import requests
import json

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
def download_versions(project_key: str):
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
                return r.json()
        except requests.exceptions.ConnectionError as ce:
            print("Connection error: {}".format(ce))
            print("You might need to define 'verify' in config.py.")
            print("Current value: config.verify =", config.verify)
            time.sleep(5)
            return None


# https://docs.atlassian.com/software/jira/docs/api/REST/7.1.6/#api/2/version-moveVersion
def move_version(to_move, prev):
    print("Moving {} to be after {}".format(to_move['name'], prev['name']))
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


def dict_versions(vs):
    # strip() is needed, because sometimes there are typos in versions
    return { v['name'].strip(): v for v in vs }


def parse_name(n):
    return list(map(int, n.split('.')))


# returns 'name' of the version, that should be previous to `n` in a lineage
def get_shoud_prev(n, format_version):
    p = parse_name(n)
    p[-1] = p[-1] - 1  # just decrement the last component
    return format_version(tuple(p))


def clean_up_release(key, major_versions, version_part_scheme=3):
    vs = download_versions(key)
    for v in vs:
        if v['name'].split('.') == version_part_scheme and ' ' in v['name']:
            print("WARNING: probable typo in version name '{}'".format(v['name']))

    def format_three(p):
        return '{}.{}.{}'.format(p[0], p[1], p[2])
    def format_two(p):
        return '{}.{}'.format(p[0], p[1])

    format_version = None
    format_lineage_prefix = None
    if version_part_scheme == 3:
        format_version = format_three
        format_lineage_prefix = format_two
    elif version_part_scheme == 2:
        format_version = format_two
        format_lineage_prefix = lambda p: str(p[0])

    m = dict_versions(vs)
    names = [v['name'] for v in vs]
    for major in major_versions:
        major_prefix = str(major) + '.'
        to_sort = filter(lambda n: n.startswith(major_prefix), names)
        for n in to_sort:
            if n[-2:] == '.0':
                # in a lineage, there is no previous version for a zeroth version
                continue
            should_prev = get_shoud_prev(n, format_version)
            try:
                prev_idx = names.index(should_prev)
                curr_idx = names.index(n)
            except ValueError as e:
                # if version that should be previous is missing for some reason, just ignore this
                continue
            if curr_idx != prev_idx + 1:
                p = parse_name(n)
                lineage_prefix = format_lineage_prefix(p)
                major_release_names = list(filter(lambda n: n.startswith(lineage_prefix), names))
                major_release_order = list(sorted(list(map(lambda n: tuple(parse_name(n)), major_release_names))))

                moved_counter = 0
                for (prev, curr) in list(zip(major_release_order, major_release_order[1:])):
                    if curr[-1] == 0:
                        continue
                    curr_v = m[format_version(curr)]
                    prev_v = m[format_version(prev)]
                    move_version(curr_v, prev_v)
                    moved_counter += 1
                print("Project {}: moved {} versions in the lineage for major version {}".format(key,
                    moved_counter, major))
                return moved_counter

    print("Project {}: nothing to move in versions {}".format(key, list(major_versions)))
    return 0

ret = 0
while True:
    ret = 0
    # ret = ret + clean_up_release('BSERV', list(range(450, 500)), 2)
    # ret = ret + clean_up_release('TEST', list(range(1960, 1990)), 3)
    if ret == 0:
        print("No more versions to move.")
        break
