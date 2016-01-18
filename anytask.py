from collections import namedtuple, defaultdict
import urllib.request as ureq
import urllib.parse as uparse
import json

from utils import local_ns


__all__ = []


AnytaskStudent = namedtuple('AnytaskStudent', ('name', 'account'))
AnytaskTask = namedtuple('AnytaskTask', ('task_id', 'name'))
AnytaskSolution = namedtuple(
    'AnytaskSolution',
    ('task_id', 'student', 'svn_rev', 'svn_path'))
AnytaskData = namedtuple('AnytaskData', ('students', 'tasks', 'solutions'))


class AnytaskParseError(Exception):
    def __init__(self, msg):
        self.message = msg

    def __str__(self):
        return self.message


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
                return (['Tasks not found'], [])

            errors = []
            result = []
            for task in data[_.TASKS]:
                (e, t) = _._filter_task(task)
                errors.extend(e)
                if t:
                    result.append(t)

            return (errors, result)

    @staticmethod
    def _filter_task(task):
        with local_ns(_AnytaskParser) as _:
            result = {}

            def _add(field):
                result[field] = task[field]

            if _.TASK_ID not in task:
                return (['Task ID not found'], {})
            _add(_.TASK_ID)

            id_ = task[_.TASK_ID]

            if _.TASK_TITLE not in task:
                return (['Task #{} has not title'.format(id_)], {})
            _add(_.TASK_TITLE)

            errors = []
            if _.TASK_PARENT not in task:
                errors.append('Task #{} has not parent'.format(id_))
                result[_.TASK_PARENT] = None
            else:
                _add(_.TASK_PARENT)

            if _.STUDENTS not in task:
                errors.append('Task #{} has not students'.format(id_))
                result[_.STUDENTS] = []
                return (errors, result)

            students = []
            for student in task[_.STUDENTS]:
                (e, s) = _._filter_students(student, id_)
                errors.extend(e)
                if s:
                    students.append(s)

            result[_.STUDENTS] = students

            return (errors, result)

    @staticmethod
    def _filter_students(student, task_id):
        with local_ns(_AnytaskParser) as _:
            result = {}

            def _add(field):
                result[field] = student[field]

            if _.STUDENT_ACC not in student:
                return (['Task #{}: student login not found'.format(task_id)],
                        {})
            _add(_.STUDENT_ACC)

            if _.STUDENT_NAME not in student:
                return (['Task #{}: student {} has not name'.format(
                    task_id, student[_.STUDENT_ACC])], {})
            _add(_.STUDENT_NAME)
            sname = student[_.STUDENT_NAME]

            if _.SCORE not in student:
                return (['Task #{}: student "{}" has not score'.format(
                    task_id, sname)], {})
            if not student[_.SCORE]:
                return (['Task #{}: student "{}" not scored'.format(
                    task_id, sname)], {})

            if _.SVN not in student:
                return (['Task #{}: student "{}" has not svn'.format(
                    task_id, sname)], {})
            if not student[_.SVN]:
                result[_.SVN] = None
                return (['Task #{}: student "{}" didn\'t link svn'.format(
                    task_id, sname)], result)

            _svn = {}
            errors = []

            svn = student[_.SVN]
            if _.SVN_PATH not in svn:
                errors.append('Task #{}, student "{}": wrong svn path'.format(
                    task_id, sname))
                _svn[_.SVN_PATH] = ''
            else:
                _svn[_.SVN_PATH] = svn[_.SVN_PATH]

            if _.REV_ID not in svn:
                errors.append(
                    'Task #{}, student "{}": wrong svn revision'.format(
                        task_id, sname))
                _svn[_.REV_ID] = None
            else:
                _svn[_.REV_ID] = svn[_.REV_ID]

            result[_.SVN] = _svn

            return (errors, result)

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

            return AnytaskData(list(students.values()), tasks, solutions)


class AnytaskDataProvider:
    def __init__(self, url):
        self._url = url

    def authenticate(self, username, password):
        pm = ureq.HTTPPasswordMgrWithDefaultRealm()
        pm.add_password(None, self._url, username, password)
        ureq.install_opener(ureq.build_opener(ureq.HTTPBasicAuthHandler(pm)))

    def load_course(self, course_id):
        url = uparse.urljoin(self._url,
                             'course/{}?format=json'.format(course_id))

        with ureq.urlopen(url) as f:
            data = json.loads(f.read().decode('utf8'))

        (errors, data) = _AnytaskParser.filter_valid(data)
        return (errors, _AnytaskParser.parse(data))
