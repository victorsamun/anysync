#!/usr/bin/env python3

import argparse
import configparser
import json
import logging
import os
import os.path
import subprocess
import sys
import urllib.parse
import urllib.request


def download(config, student, username, taskname, revision, svnpath, args):
    logging.info("SVN '%s' found, revision %s", svnpath, revision)

    try:
        path = os.path.join(config['COURSE']['name'], taskname, student)
        if not os.path.isdir(path):
            os.makedirs(path)
    except (KeyError, OSError) as e:
        logging.error("Download error.\n%s", e)
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
            logging.error("Download error: svn returns %s", code)
            return
    except Exception as e:
        logging.error("Download error.\n{}", e)
        return

    logging.info("Downloaded to '%s'", path)


def load_config(filename):
    logging.info("Loading configuration from '%s'", filename)
    config = configparser.ConfigParser()
    parsed = config.read(filename)
    if parsed == []:
        logging.critical("Can't load config file '%s'", filename)
        return None
    else:
        logging.info("Configuration loaded")

    return config


def setup_auth(config):
    logging.info("Prepare BasicHTTP authorization")
    try:
        pass_mgr = urllib.request.HTTPPasswordMgrWithDefaultRealm()
        pass_mgr.add_password(
            None,
            config['AUTH']['anytaskurl'],
            config['AUTH']['username'],
            config['AUTH']['password'])
    except KeyError as e:
        logging.critical("Can't read data for authentication.\n%s", e)
        return False

    urllib.request.install_opener(
        urllib.request.build_opener(
            urllib.request.HTTPBasicAuthHandler(pass_mgr)
        )
    )
    logging.info("BasicHTTP authorization ready")
    return True


def get_courses_id(config):
    logging.info("Parsing course identificators")
    try:
        return map(lambda s: s.strip(), config['COURSE']['ids'].split(','))
    except KeyError as e:
        logging.critical("Can't read courses information.\n%s", e)
        return None


def load_courses(courses_id, config):
    courses = []

    for course in courses_id:
        logging.info("Loading course #%s", course)
        try:
            url = urllib.parse.urljoin(
                config['AUTH']['anytaskurl'],
                '/'.join(['course', '{}?format=json'.format(course)]))

            with urllib.request.urlopen(url) as f:
                courses.append((course, json.loads(f.read().decode('utf8'))))
        except (KeyError, ValueError,
            urllib.error.HTTPError, urllib.error.URLError) as e:
            logging.error("Can't load course #%s.\n%s", course, e)

    return courses


def normalize(task, tasks):
    if task[0] is None:
        return task[1].strip()

    return os.path.join(normalize(tasks[task[0]], tasks), task[1].strip())


def get_task_names(courses):
    info = {}

    logging.info("Building tasks list")
    for (course, item) in courses:
        if 'tasks' not in item:
            logging.error("Invalid course #%s information", course)
            continue

        for task in item['tasks']:
            try:
                info[task['task_id']] = (task['parent_task_id'], task['title'])
            except KeyError as e:
                logging.error("Invalid course #%s information.\n%s", course, e)

    return {item[0]: normalize(item[1], info) for item in info.items()}


def check_select(selector, *values):
    return (selector is None) or (len(set(values) & set(selector)) != 0)


def sync_solution(student, task, config, args):
    full_name = student['user_name']
    user_name = student['username']
    if not check_select(args.student, full_name, user_name):
        return

    logging.info("Checking solution by '%s'", full_name)

    svn = student['svn']
    if svn is None:
        logging.info("SVN not found. Skip")
        return

    svn_rev = svn['svn_rev']
    svn_path = svn['svn_path']
    if svn_path is None or svn_path == "":
        logging.warning("SVN path is not specified. Skip")
        return

    download(config, full_name, user_name, task, svn_rev, svn_path, args)


def sync_task(task, tasks, config, args):
    name = tasks[task['task_id']]
    if not check_select(args.task, task['title'].strip(), name):
        return

    logging.info("Synchronization task '%s'", name)

    for student in task['students']:
        try:
            sync_solution(student, name, config, args)
        except KeyError as e:
            logging.error("Invalid solution information.\n%s", e)


def sync_course(course, tasks, config, args):
    for task in course['tasks']:
        try:
            sync_task(task, tasks, config, args)
        except KeyError as e:
            logging.error("Invalid task '%s' information.\n%s", course, e)


def synchronize(courses, tasks, config, args):
    logging.info("Start synchronization")

    for (course, item) in courses:
        if not check_select(args.course, course):
            continue

        logging.info("Synchronization course #%s", course)
        try:
            sync_course(item, tasks, config, args)
        except KeyError as e:
            logging.error("Invalid course #%s information.\n%s", course, e)


def get_students(courses):
    result = set()

    try:
        for (course, item) in courses:
            for task in item['tasks']:
                for student in task['students']:
                    result.add(student['user_name'])
    except KeyError as e:
        logging.error("Invalid courses information.\n%s", e)
        return set()

    return result


def get_tasks(courses, tasks):
    cached = set()
    result = []

    try:
        for (course, item) in courses:
            for task in item['tasks']:
                fullname = tasks[task['task_id']]
                if fullname not in cached:
                    cached.add(fullname)
                    result.append((fullname, task['title'].strip()))
    except KeyError as e:
        logging.error("Invalid courses information.\n%s", e)
        return []

    return result


def main():
    parser = argparse.ArgumentParser(description='AnyTask Synchronizer')
    parser.add_argument(
        '--config',
        default='anysync.conf', help='configuration file')
    parser.add_argument(
        '--course',
        action='append', help='specify course to synchronize')
    parser.add_argument(
        '--task',
        action='append', help='specify tasks to synchronize')
    parser.add_argument(
        '--student',
        action='append', help='specify student to synchronize')
    parser.add_argument(
        '--tasks-list',
        action='store_true', help='print list of tasks')
    parser.add_argument(
        '--students-list',
        action='store_true', help='print list of students')
    parser.add_argument(
        '--quiet',
        action='store_true', help='quiet mode')
    parser.add_argument(
        '-v', '--verbose',
        action='store_true', help='print verbose information')
    args = parser.parse_args()

    logging.basicConfig(format='[%(levelname)s] %(message)s')
    if args.verbose:
        logging.getLogger().setLevel(logging.NOTSET)
    elif args.quiet:
        logging.getLogger().setLevel(logging.CRITICAL)
    else:
        logging.getLogger().setLevel(logging.WARNING)

    config = load_config(args.config)
    if config is None:
        sys.exit(1)

    if not setup_auth(config):
        sys.exit(2)

    courses = get_courses_id(config)
    if courses is None:
        sys.exit(3)

    courses_data = load_courses(courses, config)
    if args.students_list:
        for student in sorted(get_students(courses_data)):
            print(student)
        sys.exit()

    tasks = get_task_names(courses_data)
    if args.tasks_list:
        for (fullname, shortname) in get_tasks(courses_data, tasks):
            print("'{}' ({})".format(shortname, fullname))
        sys.exit()

    synchronize(courses_data, tasks, config, args)


if __name__ == "__main__":
    main()
