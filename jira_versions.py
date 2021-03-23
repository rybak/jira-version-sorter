#!/usr/bin/env python3
# JIRA version sorter
# Copyright 2020 Andrei Rybak
# See README.md and LICENSE.md for details.

from functools import cmp_to_key
import re
import sys
import time
from getpass import getpass
import requests
import json

import config


rest_session = requests.Session()
auth = None
DEBUG = '-d' in sys.argv
TEST = '-t' in sys.argv


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


def dict_versions(vs):
    # strip() is needed, because sometimes there are typos in versions
    return { v['name'].strip(): v for v in vs }


def order_of_jira_versions(vs):
    res = {}
    for i, v in enumerate(vs):
        # strip() is needed, because sometimes there are typos in versions
        res[v['name'].strip()] = i
    return res


def parse_name(n):
    if '-' in n:
        n = n.split('-')[0]
    return list(map(int, n.split('.')))


# returns 'name' of the version, that should be previous to `n` in a lineage
def get_shoud_prev(n, format_version):
    p = parse_name(n)
    p[-1] = p[-1] - 1  # just decrement the last component
    return format_version(tuple(p))


def clean_up_release(key, major_versions, predicate, comparator):
    vs = download_versions(key)
    for v in vs:
        if '.' in v['name'] and ' ' in v['name']:
            print("WARNING: probable typo in version name '{}'".format(v['name']))
    m = dict_versions(vs)

    o = order_of_jira_versions(vs)
    names = [v['name'] for v in vs]
    for major in major_versions:
        if DEBUG:
            print("Checking version lineage {}".format(major))
        to_sort = list(filter(lambda v: predicate(str(major), v), names))
        if DEBUG:
            print("Before:")
            print(to_sort)
        proper_order = list(sorted(to_sort, key=cmp_to_key(comparator)))
        if DEBUG:
            print("Sorted:")
            print(proper_order)

        for (prev, curr) in zip(proper_order, proper_order[1:]):
            if DEBUG:
                print("Checking order: {} should be before {}".format(prev, curr))
            if o[prev] > o[curr]:
                print("Version " + prev + " is not before " + curr + ", which is incorrect")

                moved_counter = 0
                for (p, c) in zip(proper_order, proper_order[1:]):
                    move_version(m[c], m[p])
                    moved_counter += 1
                print("Project {}: moved {} versions in the lineage for major version {}".format(key,
                    moved_counter, major))
                return moved_counter

    print("Project {}: nothing to move in versions {}".format(key, list(major_versions)))
    return 0


def predicate_starts_with(major, name):
    return name.startswith(major + '.')


def predicate_release_branch(major, name):
    return ('release/' + major + '_') in name


def predicate_default(major, name):
    return predicate_starts_with(major, name) or predicate_release_branch(major, name)


FAKE_VERSION = (NON_NUMBER, NON_NUMBER, NON_NUMBER, NON_NUMBER)


# Format like release/140_3_codename
# where 140 is major, 3 is minor
def version_tokens(name):
    if '-' in name:
        (dotted, suffix) = tuple(name.split('-'))
        tmp = list(map(int, dotted.split('.')))
        maybeNum = re.search("\d+", suffix)
        try:
            tmp.append(int(maybeNum.group()))
        except:
            tmp.append(9000)
        return tuple(tmp)
    if '.' in name:
        return tuple(map(int, name.split('.')))
    if 'release/' in name:
        try:
            major = int(re.search("release/(\d+)", name).group(1))
            try:
                minor = int(re.search("_(\d+)_", name).group(1))
            except:
                minor = 0
            return (major, minor, 9000)
        except:
            print("ERROR when parsing " + name)
            return FAKE_VERSION
    return FAKE_VERSION


def comparator_default(a, b):
    tokens_a = version_tokens(a)
    tokens_b = version_tokens(b)
    if (len(tokens_a) > len(tokens_b)):
        return -comparator_default(b, a)
    if (len(tokens_b) > len(tokens_a)):
        short_b = tokens_b[:len(tokens_a)]
        if tokens_a < short_b:
            if DEBUG:
                print("DEBUG {} ? {}".format(a, b))
            return -1
        return 1
    if tokens_a < tokens_b:
        return -1
    else:
        return 1


if TEST:
    cs = [
            ("140.0.4", "140.0.3"),
            ("140.0.3", "140.0.4"),
            ("140.0.0", "140.1.0"),
            ("140.0.0-nightly0", "140.0.0"),
            ("140.1.0-nightly0", "140.0.0"),
            ("140.0.0-nightly0", "Release (release/140_0_asdf)"),
            ("140.0.0", "Release (release/140_0_asdf)"),
            ("140.1.0", "Release (release/140_0_asdf)"),
            ("Patch (release/140_1_asdf)", "Release (release/140_0_asdf)"),
            ("Sunflower (release/1969_1_sunflower)", "1970.0.8"),
            ("Sunflower (release/1969_0_sunflower)", "1969.1.0"),
    ]
    for (a, b) in cs:
        sign = ""
        if comparator_default(a, b) < 0:
            sign = " < "
        else:
            sign = " > "
        print(a + sign + b)
    sys.exit(0)


ret = 0
while True:
    ret = 0
    # ret = ret + clean_up_release('BSERV', list(range(450, 500)), predicate_default, comparator_default)
    # ret = ret + clean_up_release('TEST', list(range(1960, 1990)), predicate_default, comparator_default)
    if ret == 0:
        print("No more versions to move.")
        break
