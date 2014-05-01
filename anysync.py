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


__version__ = '0.9'


class AnytaskTask:
    def __init__(self, course, title, name):
        self._course = course
        self._title = title
        self._name = name

    @property
    def course_id(self):
        return self._course

    @property
    def title(self):
        return self._title

    @property
    def name(self):
        return self._name


class AnytaskStudent:
    def __init__(self, fullname, username):
        self._fullname = fullname
        self._username = username

    @property
    def name(self):
        return self._fullname

    @property
    def repo(self):
        return self._username


class AnytaskSVN:
    def __init__(self, path, review_id, revision):
        self._path = path
        self._reviewid = review_id
        self._revision = revision

    @property
    def path(self):
        return self._path

    @property
    def review_id(self):
        return self._reviewid

    @property
    def revision(self):
        return self._revision


class AnytaskSolution:
    def __init__(self, task, student):
        self._task = task
        self._student = student
        self._svn = None

    def add_svn_info(self, svn_info):
        self._svn = svn_info

    @property
    def task(self):
        return self._task

    @property
    def student(self):
        return self._student

    @property
    def svn(self):
        return self._svn


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
            return map(lambda s: s.strip(),
                self._config['COURSE']['ids'].split(','))
        except KeyError as e:
            logging.critical("Can't read courses information.\n%s", e)
            raise AnytaskParseError()

    def _load_courses(self, ids):
        self._courses = []

        for course in ids:
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
        for (course, item) in self._courses:
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

        self._task_names = {item[0]: Anytask._normalize(item[1], info)
            for item in info.items()}

    def _parse(self):
        self._load_tasks()

        logging.info("Building solutions list")
        self._tasks = {}
        self._students = {}
        self._solutions = []

        for (course, item) in self._courses:
            logging.info("Processing course #%s", course)

            if 'tasks' not in item:
                logging.error("No tasks in course #%s", course)
                continue

            for task in item['tasks']:
                if 'task_id' not in task:
                    logging.error("Invalid task in course #%s", course)
                    continue

                if 'title' not in task:
                    logging.error("Task #%s has no title", task['task_id'])
                    continue

                task_name = self._task_names[task['task_id']]
                task_title = task['title'].strip()

                logging.info("Processing task '%s'", task_name)

                if task_name not in self._tasks:
                    self._tasks[(course, task_name)] = AnytaskTask(
                        course, task_title, task_name)

                task_obj = self._tasks[(course, task_name)]

                if 'students' not in task:
                    logging.error("No students in task #%s/'%s'",
                        course, task_name)
                    continue

                for student in task['students']:
                    if 'user_name' not in student:
                        logging.error("Invalid student in task #%s/'%s'",
                            course, task_name)
                        continue

                    full_name = student['user_name']

                    if 'username' not in student:
                        logging.error(
                            "Invalid login of student '%s' in task #%s/'%s'",
                            full_name, course, task_name)
                        continue

                    username = student['username']

                    logging.info("Processing student '%s'", full_name)

                    if username not in self._students:
                        self._students[username] = AnytaskStudent(
                            full_name, username)

                    student_obj = self._students[username]
                    solution_obj = AnytaskSolution(task_obj, student_obj)

                    if ('svn' in student) and (student['svn'] is not None):
                        if (('svn_path' not in student['svn']) or
                            ('rb_review_id' not in student['svn']) or
                            ('svn_rev' not in student['svn'])):
                            logging.error("Invalid svn info of student '%s' in"
                                " task #%s/'%s'", full_name, course, task_name)
                        else:
                            solution_obj.add_svn_info(
                                AnytaskSVN(
                                    student['svn']['svn_path'],
                                    str(student['svn']['rb_review_id']),
                                    str(student['svn']['svn_rev'])))

                    self._solutions.append(solution_obj)

                    logging.info("Processing student complete")

                logging.info("Processing task '%s' complete", task_name)

            logging.info("Processing course #%s complete", course)

    def _save_config(self):
        with open(self._configfile, mode='w') as f:
            self._config.write(f, True)

    def __init__(self, configfile):
        self._configfile = configfile
        self._load_config(configfile)
        self._setup_auth()
        self._load_courses(self._parse_courses_id())
        self._parse()

    @property
    def solutions(self):
        return self._solutions

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

            self._config.set('RB_LINKS', *link)
            self._save_config()
        except Exception as e:
            logging.error("Failed to add link.\n%s", e)
            return

        logging.info("Link #%s to '%s' added", *link)

    def get_link(self, link):
        return self.get_config_safe('RB_LINKS', link)

    def remove_link(self, link):
        try:
            self._config.remove_option('RB_LINKS', link)
            self._save_config()
        except Exception as e:
            logging.error("Failed to remove link.\n%s", e)
            return

        logging.info("Link #%s removed", link)

    def get_students(self):
        return self._students.values()

    def get_tasks(self):
        cached = set()
        result = []

        for task_id in sorted(self._task_names.keys()):
            name = self._task_names[task_id]
            if name not in cached:
                cached.add(name)
                result.append(name)

        return result


class AnytaskSynchronizer:
    @staticmethod
    def _selected(selector, *values):
        return (selector is None) or (len(set(values) & set(selector)) != 0)

    def _make_destination(self, solution, forced=False):
        try:
            path = os.path.join(self._anytask.get_config('COURSE', 'name'),
                self._anytask.get_config('COURSE', 'unsorted') if forced else
                    solution.task.name,
                solution.student.name)

            if not os.path.isdir(path):
                os.makedirs(path)
        except (KeyError, OSError) as e:
            logging.error("Make directory error.\n%s", e)
            return None

        return path

    def _sync_solution(self, solution, args):
        logging.info("Checking solution of #%s/'%s' by '%s'",
            solution.task.course_id, solution.task.name, solution.student.name)

        if solution.svn is None:
            logging.info("SVN not found. Skip")
            return

        svn_path = solution.svn.path
        dest = None

        if svn_path in [None, '']:
            svn_path = self._anytask.get_link(solution.svn.review_id)

            if svn_path is None:
                logging.warning("Solution have only review id #%s",
                    solution.svn.review_id)

                if args.force:
                    repo = solution.student.repo

                    if repo in self._forced:
                        logging.info(
                            "Repository '%s' already downloaded. Skip", repo)
                        if args.ask_link:
                            self._ask_add_link(solution)
                        return

                    dest = self._make_destination(solution, True)
                    if dest is None:
                        return

                    svn_path = ""
                    self._forced.add(repo)
                else:
                    logging.warning("SVN path is not specified. Skip")
                    return
            else:
                logging.info("Review id #%s will be used",
                    solution.svn.review_id)
        else:
            rev_id = solution.svn.review_id

            if self._anytask.get_link(rev_id) is not None:
                logging.warning("ReviewBoard link to #%s is redundant", rev_id)

                if args.remove_links:
                    self._anytask.remove_link(rev_id)

        if dest is None:
            dest = self._make_destination(solution)

        if dest is not None:
            if self._download(solution, svn_path, dest):
                if (svn_path == "") and args.ask_link:
                    self._ask_add_link(solution)

    def _ask_add_link(self, solution):
        def get_dirs(path, *exclude):
            return filter(lambda d: (os.path.isdir(os.path.join(path, d)) and
                (d not in exclude)), os.listdir(path))

        choices = []
        try:
            rootdir = os.path.join(
                self._anytask.get_config('COURSE', 'name'),
                self._anytask.get_config('COURSE', 'unsorted'),
                solution.student.name)

            for _dir in get_dirs(rootdir, '.svn'):
                if _dir not in ['branches', 'tags', 'trunk']:
                    choices.append(_dir)

                choices += map(
                    lambda d: os.path.join(_dir, d),
                    get_dirs(os.path.join(rootdir, _dir), '.svn'))
        except (KeyError, OSError):
            return

        print("Select path to task '{}' or enter path manually:".format(
            solution.task.name))

        for item in enumerate(choices):
            print("{:2d} {}".format(item[0] + 1, item[1]))

        answer = input()
        if (len(choices) == 1) and (answer == ''):
            answer = '1'

        try:
            answer = int(answer)
            if not (0 < answer <= len(choices)):
                return None
            answer = choices[answer - 1]
        except ValueError:
            pass

        self._anytask.add_link([solution.svn.review_id, answer])

    def _download(self, solution, svnpath, destination):
        logging.info("SVN '%s' found, revision %s",
            svnpath, solution.svn.revision)

        try:
            url = urllib.parse.urljoin(
                self._anytask.get_config('COURSE', 'svn'),
                '/'.join([solution.student.repo, svnpath]))

            code = subprocess.call([
                "svn", "checkout",
                "--revision", solution.svn.revision,
                "--force",
                "--no-auth-cache",
                "--username", self._anytask.get_config('AUTH', 'username'),
                "--password", self._anytask.get_config('AUTH', 'password'),
                url,
                destination,
            ])

            if code != 0:
                logging.error("Download error: svn returns %s", code)
                return False
        except Exception as e:
            logging.error("Download error.\n{}", e)
            return False

        logging.info("Downloaded to '%s'", destination)
        return True

    def __init__(self, anytask):
        self._anytask = anytask
        self._forced = set()

    def synchronize(self, args):
        logging.info("Start synchronization")

        for solution in filter(
            lambda solution:
                AnytaskSynchronizer._selected(args.course,
                   solution.task.course_id) and
                AnytaskSynchronizer._selected(args.task,
                   solution.task.name, solution.task.title) and
                AnytaskSynchronizer._selected(args.student,
                   solution.student.name, solution.student.repo),
            self._anytask.solutions):
            self._sync_solution(solution, args)

        logging.info("Synchronization completed")


def main():
    parser = argparse.ArgumentParser(
        usage='%(prog)s [OPTIONS]',
        description='AnyTask SVN Synchronizer',
        epilog="""
            Report bugs to Victor Samun <victor.samun@gmail.com> and
            Nickolai Zhuravlev <znick@znick.ru>
        """,
        prefix_chars='-/')
    parser.add_argument(
        '-C', '--config',
        metavar='FILENAME',
        default='anysync.conf', help='configuration file')
    parser.add_argument(
        '-c', '--course',
        metavar='ID',
        action='append', help='specify course to synchronize')
    parser.add_argument(
        '-t', '--task',
        metavar='NAME',
        action='append', help='specify tasks to synchronize')
    parser.add_argument(
        '-s', '--student',
        metavar='NAME',
        action='append', help='specify student to synchronize')
    parser.add_argument(
        '-tl', '--tasks-list',
        action='store_true', help='print list of tasks')
    parser.add_argument(
        '-sl', '--students-list',
        action='store_true', help='print list of students')
    parser.add_argument(
        '-a', '--add-link', nargs=2,
        metavar=('RB_ID', 'SVN_PATH'),
        action='append', help='add link for force repo with empty `svn_path`')
    parser.add_argument(
        '-r', '--remove-links',
        action='store_true', help='remove redundant links')
    parser.add_argument(
        '-f', '--force',
        action='store_true', help='force download repos with empty `svn_path`')
    parser.add_argument(
        '-A', '--ask-link',
        action='store_true',
        help='ask link to add for force when `svn_path` is empty')
    parser.add_argument(
        '-q', '--quiet',
        action='store_true', help='quiet mode')
    parser.add_argument(
        '-v', '--verbose',
        action='store_true', help='print verbose information')
    parser.add_argument(
        '-V', '--version',
        action='store_true', help='print version and exit')
    args = parser.parse_args()

    if args.version:
        print("Anytask Synchronizer (AnySync) version {}".format(__version__))
        sys.exit()

    if args.ask_link and not args.force:
        parser.error("--ask-link requires --force")

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
        for student in sorted(anytask.get_students(), key=lambda x: x.name):
            print("{} ({})".format(student.name, student.repo))
        sys.exit()

    if args.tasks_list:
        for taskname in anytask.get_tasks():
            print(taskname)
        sys.exit()

    if args.add_link:
        for link in args.add_link:
            anytask.add_link(link)
        sys.exit()

    sync = AnytaskSynchronizer(anytask)
    sync.synchronize(args)


if __name__ == "__main__":
    main()
