#!/usr/bin/env python3

import configparser
import json
import os
import os.path
import subprocess
import sys
import urllib.parse
import urllib.request


def debug(message, level=0, *opts):
    sys.stdout.write("{}{}\n".format('  '*level, message))
    sys.stdout.writelines(
        map(lambda o: "{}\t{}\n".format('  '*level, str(o)), opts))


def warn(message='Unknown warning', *opts):
    sys.stderr.write("Warning: {}\n".format(message))
    sys.stderr.writelines(map(lambda o: "\t{}\n".format(str(o)), opts))


def error(code, message='Unknown error', *opts):
    sys.stderr.write("Error: {}\n".format(message))
    sys.stderr.writelines(map(lambda o: "\t{}\n".format(str(o)), opts))
    sys.exit(code)


def normalize(task, tasks):
    if task[0] is None:
        return task[1].strip()

    return os.path.join(normalize(tasks[task[0]], tasks), task[1].strip())


def check_cache(path, revision):
    filename = os.path.join(path, ".anysync")
    last_rev = -1

    if os.path.exists(filename):
        with open(filename) as f:
            last_rev = f.read().strip()

    current_rev = str(revision)
    with open(filename, mode='w') as f:
        f.write(current_rev)

    return last_rev == current_rev


def download(config, student, username, taskname, revision, svnpath):
    debug("Downloading '{}' revision #{}".format(svnpath, revision), level=3)

    path = os.path.join(config['COURSE']['name'], taskname, student)
    if not os.path.isdir(path):
        try:
            os.makedirs(path)
        except OSError as e:
            warn("Can't make directory '{}'".format(path), e)
            return

    if check_cache(path, revision):
        debug("Found in cache. Skip", level=4)
        return

    try:
        url = urllib.parse.urljoin(
            config['COURSE']['svn'],
            '/'.join([username, svnpath]))

        code = subprocess.call([
            "svn", "checkout",
            "--force",
            "--username", config['AUTH']['username'],
            "--password", config['AUTH']['password'],
            url,
            path,
        ])

        if code != 0:
            debug("Error {}".format(code), level=4)
    except Exception as e:
        warn("Download error", e)
        return

    debug("OK", level=4)


def main():
    config = configparser.ConfigParser()
    config_file = sys.argv[1] if len(sys.argv) > 1 else 'anysync.conf'
    parsed = config.read(config_file)
    if parsed == []:
        error(1, "can't load config file '{}'".format(config_file))

    try:
        pass_mgr = urllib.request.HTTPPasswordMgrWithDefaultRealm()
        pass_mgr.add_password(
            None,
            config['AUTH']['anytaskurl'],
            config['AUTH']['username'],
            config['AUTH']['password'])
    except KeyError:
        error(2, "can't read data for authentication")

    urllib.request.install_opener(
        urllib.request.build_opener(
            urllib.request.HTTPBasicAuthHandler(pass_mgr)))

    try:
        courses = config['COURSE']['ids'].split(',')
    except KeyError:
        error(3, "can't read courses information")

    json_data = []
    for course in courses:
        try:
            with urllib.request.urlopen(
                urllib.parse.urljoin(
                    config['AUTH']['anytaskurl'],
                    '/'.join(['course', "{}?format=json".format(course)])
                )) as f:
                json_data.append((course, json.loads(f.read().decode('utf8'))))
        except ValueError as e:
            warn("can't load course #{}".format(course), e)
        except (urllib.error.HTTPError, urllib.error.URLError) as e:
            warn("can't load course #{}".format(course), e)

    _tasks = {}
    for (course, item) in json_data:
        for task in item['tasks']:
            _tasks[task['task_id']] = [task['parent_task_id'], task['title']]

    tasks = {item[0]: normalize(item[1], _tasks) for item in _tasks.items()}

    for (course, item) in json_data:
        debug("Checking course {}".format(course), level=0)
        for task in item['tasks']:
            task_name = tasks[task['task_id']]
            debug("Checking task '{}'".format(task_name), level=1)

            for student in task['students']:
                student_name = student['user_name']
                user_name = student['username']
                debug("Checking student '{}'".format(student_name), level=2)

                svn = student['svn']
                if svn is None:
                    debug("SVN not found. Skip", level=3)
                    continue

                svn_rev = svn['svn_rev']
                svn_path = svn['svn_path']
                if svn_path is None:
                    debug("SVN path is not specified. Skip", level=3)
                    continue

                download(
                    config,
                    student_name, user_name,
                    task_name,
                    svn_rev, svn_path)


if __name__ == "__main__":
    main()
