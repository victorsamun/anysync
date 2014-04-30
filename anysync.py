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


class ConfigParseError(Exception):
    pass


class AuthenticationError(Exception):
    pass


class AnytaskParseError(Exception):
    pass


class Anytask:
    def _load_config(self, filename):
        logging.info("Loading configuration from '%s'", filename)
        self._config = configparser.ConfigParser()

        parsed = self._config.read(filename)
        if parsed == []:
            logging.critical("Can't load config file '%s'", filename)
            raise ConfigParseError()

        logging.info("Configuration loaded")

    def _setup_auth(self):
        logging.info("Prepare BasicHTTP authorization")
        try:
            pass_mgr = urllib.request.HTTPPasswordMgrWithDefaultRealm()
            pass_mgr.add_password(
                None,
                self._config['AUTH']['anytaskurl'],
                self._config['AUTH']['username'],
                self._config['AUTH']['password'])
        except KeyError as e:
            logging.critical("Can't read data for authentication.\n%s", e)
            raise AuthenticationError()

        urllib.request.install_opener(
            urllib.request.build_opener(
                urllib.request.HTTPBasicAuthHandler(pass_mgr)))
        logging.info("BasicHTTP authorization ready")

    def _parse_courses_id(self):
        logging.info("Parsing course identificators")
        try:
            self._courses_id = map(
                lambda s: s.strip(),
                self._config['COURSE']['ids'].split(','))
        except KeyError as e:
            logging.critical("Can't read courses information.\n%s", e)
            raise AnytaskParseError()

    def _load_courses(self):
        self._courses = []

        for course in self._courses_id:
            logging.info("Loading course #%s", course)
            try:
                url = urllib.parse.urljoin(
                    self._config['AUTH']['anytaskurl'],
                    '/'.join(['course', '{}?format=json'.format(course)]))

                with urllib.request.urlopen(url) as f:
                    self._courses.append(
                        (course, json.loads(f.read().decode('utf8'))))
            except (KeyError, ValueError,
                urllib.error.HTTPError, urllib.error.URLError) as e:
                logging.error("Can't load course #%s.\n%s", course, e)

    @staticmethod
    def _normalize(task, tasks):
        if task[0] is None:
            return task[1].strip()

        return os.path.join(
            Anytask._normalize(tasks[task[0]], tasks), task[1].strip())

    def _load_tasks(self):
        info = {}

        logging.info("Building tasks list")
        for (course, item) in self.courses:
            if 'tasks' not in item:
                logging.error("Invalid course #%s information", course)
                continue

            for task in item['tasks']:
                try:
                    info[task['task_id']] = (
                        task['parent_task_id'], task['title'])
                except KeyError as e:
                    logging.error(
                        "Invalid course #%s information.\n%s", course, e)

        self._tasks = {item[0]: Anytask._normalize(item[1], info)
            for item in info.items()}

    def __init__(self, configfile):
        self._configfile = configfile
        self._load_config(configfile)
        self._setup_auth()
        self._parse_courses_id()
        self._load_courses()
        self._load_tasks()

    @property
    def courses(self):
        return self._courses

    def get_config(self, section, key):
        return self._config[section][key]

    def get_config_safe(self, section, key, default=None):
        try:
            return self.get_config(section, key)
        except KeyError:
            return default

    def add_link(self, link):
        try:
            if not self._config.has_section('RB_LINKS'):
                self._config.add_section('RB_LINKS')

            self._config.set('RB_LINKS', *link.split(':', 2))
            with open(self._configfile, mode='w') as f:
                self._config.write(f, True)
        except Exception as e:
            logging.error("Failed to add link.\n%s", e)
            return False

        return True

    def get_students(self):
        result = set()

        try:
            for (course, item) in self._courses:
                for task in item['tasks']:
                    for student in task['students']:
                        result.add(student['user_name'])
        except KeyError as e:
            logging.error("Invalid courses information.\n%s", e)
            return set()

        return result

    def get_task(self, taskid):
        return self._tasks[taskid]

    def get_tasks(self):
        cached = set()
        result = []

        try:
            for (course, item) in self._courses:
                for task in item['tasks']:
                    fullname = self._tasks[task['task_id']]
                    if fullname not in cached:
                        cached.add(fullname)
                        result.append((fullname, task['title'].strip()))
        except KeyError as e:
            logging.error("Invalid courses information.\n%s", e)
            return []

        return result


class AnytaskSynchronizer:
    @staticmethod
    def _selected(selector, *values):
        return (selector is None) or (len(set(values) & set(selector)) != 0)

    def _sync_course(self, course, args):
        for task in course['tasks']:
            try:
                self._sync_task(task, args)
            except KeyError as e:
                logging.error("Invalid task '%s' information.\n%s", course, e)

    def _sync_task(self, task, args):
        name = self._anytask.get_task(task['task_id'])
        if not AnytaskSynchronizer._selected(
            args.task, task['title'].strip(), name):
            return

        logging.info("Synchronization task '%s'", name)

        for student in task['students']:
            try:
                self._sync_solution(student, name, args)
            except KeyError as e:
                logging.error("Invalid solution information.\n%s", e)

    def _sync_solution(self, student, task, args):
        fullname = student['user_name']
        username = student['username']
        if not AnytaskSynchronizer._selected(args.student, fullname, username):
            return

        logging.info("Checking solution by '%s'", fullname)

        svn = student['svn']
        if svn is None:
            logging.info("SVN not found. Skip")
            return

        svn_rev = str(svn['svn_rev'])
        svn_path = svn['svn_path']
        rb_id = str(svn['rb_review_id'])
        dest = None
        if svn_path is None or svn_path == "":
            svn_path = self._anytask.get_config_safe('RB_LINKS', rb_id)
            if svn_path is None:
                if args.force:
                    logging.warning("Task '%s' by '%s' has only rb_id=%s",
                        task, fullname, rb_id)

                    if username in self._forced:
                        logging.info("Repository #%s already downloaded. Skip")
                        return

                    dest = self._make_destination(task, fullname, True)
                    svn_path = ""
                    self._forced.add(username)
                else:
                    logging.warning("SVN path is not specified. Skip")
                    return
            else:
                logging.info("SVN path is not specified, `rb_id` will be used")
                dest = self._make_destination(task, fullname)
        else:
            dest = self._make_destination(task, fullname)

            if self._anytask.get_config_safe('RB_LINKS', rb_id) is not None:
                logging.warning("Review board id '%s' is ambiguous", rb_id)

        if dest is not None:
            self._download(username, svn_rev, svn_path, dest, args)

    def _make_destination(self, taskname, fullname, forced=False):
        if forced:
            return self._make_destination(
                self._anytask.get_config('COURSE', 'unsorted'), fullname)

        try:
            path = os.path.join(
                self._anytask.get_config('COURSE', 'name'), taskname, fullname)
            if not os.path.isdir(path):
                os.makedirs(path)
        except (KeyError, OSError) as e:
            logging.error("Make directory error.\n%s", e)
            return None

        return path

    def _download(self, username, revision, svnpath, path, args):
        logging.info("SVN '%s' found, revision %s", svnpath, revision)

        try:
            url = urllib.parse.urljoin(
                self._anytask.get_config('COURSE', 'svn'),
                '/'.join([username, svnpath]))

            code = subprocess.call([
                "svn", "checkout",
                "--force",
                "--username", self._anytask.get_config('AUTH', 'username'),
                "--password", self._anytask.get_config('AUTH', 'password'),
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

    def __init__(self, anytask):
        self._anytask = anytask
        self._forced = set()

    def synchronize(self, args):
        logging.info("Start synchronization")

        for (course, item) in self._anytask.courses:
            if not AnytaskSynchronizer._selected(args.course, course):
                continue

            logging.info("Synchronization course #%s", course)
            try:
                self._sync_course(item, args)
            except KeyError as e:
                logging.error("Invalid course #%s information.\n%s", course, e)


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
        '--add-link',
        action='append', help='add link for force repo with empty `svn_path`')
    parser.add_argument(
        '--force',
        action='store_true', help='force download repos with empty `svn_path`')
    parser.add_argument(
        '--quiet',
        action='store_true', help='quiet mode')
    parser.add_argument(
        '--verbose',
        action='store_true', help='print verbose information')
    args = parser.parse_args()

    logging.basicConfig(format='[%(levelname)s] %(message)s')
    if args.verbose:
        logging.getLogger().setLevel(logging.NOTSET)
    elif args.quiet:
        logging.getLogger().setLevel(logging.CRITICAL)
    else:
        logging.getLogger().setLevel(logging.WARNING)

    try:
        anytask = Anytask(args.config)
    except ConfigParseError:
        sys.exit(1)
    except AuthenticationError:
        sys.exit(2)
    except AnytaskParseError:
        sys.exit(3)

    if args.students_list:
        for student in sorted(anytask.get_students()):
            print(student)
        sys.exit()

    if args.tasks_list:
        for (fullname, shortname) in anytask.get_tasks():
            print("'{}' ({})".format(shortname, fullname))
        sys.exit()

    if args.add_link:
        for link in args.add_link:
            if anytask.add_link(link):
                logging.info("Link '%s' added", link)
        sys.exit()

    sync = AnytaskSynchronizer(anytask)
    sync.synchronize(args)


if __name__ == "__main__":
    main()
