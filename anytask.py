from collections import namedtuple, defaultdict
import json
import logging
import urllib.request as ureq
import urllib.parse as uparse

from utils import local_ns


__all__ = [
    'AnytaskStudent',
    'AnytaskTask',
    'AnytaskSolution',
    'AnytaskData',

    'AnytaskDataProvider',

    'LOGGER_NAME'
]


AnytaskStudent = namedtuple('AnytaskStudent', ('name', 'account'))
AnytaskTask = namedtuple('AnytaskTask', ('task_id', 'name'))
AnytaskSolution = namedtuple(
    'AnytaskSolution',
    ('task_id', 'student', 'svn_rev', 'svn_path'))
AnytaskData = namedtuple('AnytaskData', ('students', 'tasks', 'solutions'))

LOGGER_NAME = 'anytask.parser'
LOGGER = logging.getLogger(LOGGER_NAME)


class _AnytaskParser:
    TASKS = 'tasks'
    TASK_ID = 'task_id'
    TASK_PARENT = 'parent_task_id'
    TASK_TITLE = 'title'

    STUDENTS = 'students'
    SCORE = 'score'
    STATUS = 'status'
    STUDENT_ACC = 'username'
    STUDENT_NAME = 'user_name'
    SVN = 'svn'

    SVN_PATH = 'svn_path'
    REV_ID = 'svn_rev'

    @staticmethod
    def filter_valid(data):
        with local_ns(_AnytaskParser) as _:
            if _.TASKS not in data:
                LOGGER.error('Tasks not found')
                return []

            return list(filter(None, map(_._filter_task, data[_.TASKS])))

    @staticmethod
    def _filter_task(task):
        with local_ns(_AnytaskParser) as _:
            result = {}

            def _add(field):
                result[field] = task[field]

            if _.TASK_ID not in task:
                LOGGER.error('Task ID not found')
                return None
            _add(_.TASK_ID)

            id_ = task[_.TASK_ID]

            if _.TASK_TITLE not in task:
                LOGGER.error('Task #%s has not title', id_)
                return None
            _add(_.TASK_TITLE)

            if _.TASK_PARENT not in task:
                LOGGER.warn('Task #%s has not parent', id_)
                result[_.TASK_PARENT] = None
            else:
                _add(_.TASK_PARENT)

            if _.STUDENTS not in task:
                LOGGER.warn('Task #%s has not students', id_)
                result[_.STUDENTS] = []
                return result

            result[_.STUDENTS] = list(filter(
                None, map(lambda s: _._filter_students(s, id_),
                          task[_.STUDENTS])))

            return result

    @staticmethod
    def _filter_students(student, task_id):
        with local_ns(_AnytaskParser) as _:
            result = {}

            def _add(field):
                result[field] = student[field]

            if _.STUDENT_ACC not in student:
                LOGGER.error('Task #%s: student login not found', task_id)
                return None
            _add(_.STUDENT_ACC)

            if _.STUDENT_NAME not in student:
                LOGGER.error('Task #%s: student %s has not name',
                             task_id, student[_.STUDENT_ACC])
                return None
            _add(_.STUDENT_NAME)
            sname = student[_.STUDENT_NAME]

            if _.SCORE not in student:
                LOGGER.error('Task #%s: student "%s" has not score',
                             task_id, sname)
                return None
            if not student[_.SCORE]:
                LOGGER.error('Task #%s: student "%s" not scored',
                             task_id, sname)
                return None

            if _.SVN not in student:
                LOGGER.error('Task #%s: student "%s" has not svn',
                             task_id, sname)
                return None
            if not student[_.SVN]:
                result[_.SVN] = None
                LOGGER.error('Task #%s: student "%s" didn\'t link svn',
                             task_id, sname)
                return result

            _svn = {}

            svn = student[_.SVN]
            if _.SVN_PATH not in svn:
                LOGGER.warn('Task #%s, student "%s": wrong svn path',
                            task_id, sname)
                _svn[_.SVN_PATH] = ''
            else:
                _svn[_.SVN_PATH] = svn[_.SVN_PATH]

            if _.REV_ID not in svn:
                LOGGER.warn('Task #%s, student "%s": wrong svn revision',
                            task_id, sname)
                _svn[_.REV_ID] = None
            else:
                _svn[_.REV_ID] = svn[_.REV_ID]

            result[_.SVN] = _svn

            return result

    @staticmethod
    def _linearize_tasks(data):
        with local_ns(_AnytaskParser) as _:
            task_names = {}
            inv_idx = defaultdict(list)

            for task in data:
                task_names[task[_.TASK_ID]] = (task[_.TASK_TITLE],)
                if task[_.TASK_PARENT]:
                    inv_idx[task[_.TASK_PARENT]].append(task[_.TASK_ID])

            for (parent, childs) in inv_idx.items():
                for child in childs:
                    task_names[child] = task_names[parent] + task_names[child]

            return task_names

    @staticmethod
    def parse(data):
        LOGGER.info('Parsing anytask answer')
        with local_ns(_AnytaskParser) as _:
            task_names = _._linearize_tasks(data)

            tasks = [AnytaskTask(*item) for item in task_names.items()]
            students = {}
            solutions = []

            for task in data:
                for student in task[_.STUDENTS]:
                    with local_ns(student[_.STUDENT_ACC]) as s_acc:
                        if s_acc not in students:
                            students[s_acc] = AnytaskStudent(
                                student[_.STUDENT_NAME], s_acc)
                        stud = students[s_acc].account

                    svn = student[_.SVN] or defaultdict(lambda: None)
                    solutions.append(AnytaskSolution(
                        task[_.TASK_ID], stud, svn[_.REV_ID], svn[_.SVN_PATH]))

            LOGGER.info(
                'Parsing complete. %s tasks, %s students, %s solutions '
                ' processed', len(tasks), len(students), len(solutions))
            return AnytaskData(list(students.values()), tasks, solutions)


class AnytaskDataProvider:
    def __init__(self, url):
        self._url = url

    def authenticate(self, username, password):
        LOGGER.info('Authenticating "%s"', username)
        pm = ureq.HTTPPasswordMgrWithDefaultRealm()
        pm.add_password(None, self._url, username, password)
        ureq.install_opener(ureq.build_opener(ureq.HTTPBasicAuthHandler(pm)))

    def load_course(self, course_id):
        LOGGER.info('Loading course #%s', course_id)
        url = uparse.urljoin(self._url,
                             'course/{}?format=json'.format(course_id))

        with ureq.urlopen(url) as f:
            data = json.loads(f.read().decode('utf8'))

        return _AnytaskParser.parse(_AnytaskParser.filter_valid(data))
