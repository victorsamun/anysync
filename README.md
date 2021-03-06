# anysync

Утилита синхронизации задач из SVN-репозиториев студентов AnyTask.
Предназначена для использования преподавателями.

Для работы требуется установленный `svn`.

Данная утилита позволяет автоматически скачать задачи из SVN-репозитариев студентов и рассортировать их по каталогам. Структура каталогов после синхронизации: `курс/задача/[подзадача_1/.../подзадача_N]/ФИ_студента/`.

## Быстрый старт

1. Установить `svn` и `python`, добавить в `PATH` путь до `svn`
2. Открыть файл `anysync.conf` и внести настройки (по аналогии с `Python.conf`):
  * В опции `AUTH:username` указать логин на AnyTask
  * В опции `AUTH:password` указать пароль на AnyTask
  * В опции `COURSE:name` указать название курса
  * В опции `COURSE:ids` указать номера курсов для сихронизации
3. Запустить приложение:
  * Простой запуск — `./anysync.py -C имя_файла.conf`
  * Просмотр обновлений репозиториев — `./anysync.py -C имя_файла.conf -U`
  * Загрузка только обновлений — `./anysync.py -C имя_файла.conf -u`

Для запуска авторы рекомендуют использовать `./anysync.py -C имя_файла.conf -v -u -f -a -X`.


## Файл настроек

Конфигурационный файл `.conf` имеет INI-формат описания курса на AnyTask.

Файл имеет следующие разделы:
* `AUTH`
* `COURSE`
* `RB_LINKS`
* `RELOCS`

Раздел `AUTH` содержит информацию для выполнения авторизации на AnyTask, опции раздела:
- `anytaskurl` url сайта AnyTask (http://anytask.urgu.org/)
- `username` логин
- `password` пароль

Раздел `COURSE` содержит информацию о курсе, опции раздела:
- `name` название курса (в каталог с данным названием будут складываться задачи)
- `unsorted` название каталога для невалидных репозиториев
- `svn` url общего SVN'а системы AnyTask (http://anytask.urgu.org/svn/)
- `ids` идентификаторы курсов (если несколько, можно указать через запятую)
- `ignore` содержит идентификаторы review, которые будут игнорироваться при синхронизации

Раздел `RB_LINKS` содержит привязки идентификатора задачи на Review Board к каталогу SVN-репозитория студента. Название опции — идентификатор, значение — путь к задаче в репозитарии. Опции необходимы в случае неуказания студентом на Review Board пути к задаче в SVN.

Раздел `RELOCS` содержит информацию о релокациях репозиториев. Название опции — логин студента, значение опции — название репозитория. Опции необходимы в случае несовпадения логина с названием репозитория (чего, вообще говоря, быть не должно).

## Запуск синхронизатора

Опция `-C` позволяет указать конфигурационный файл синхронизации.

Опции `-c`, `-t`, `-s` позволяют произвести выборочную синхронизацию (указать курс, задачу, студента соответственно).

Опции `-T`, `-S` позволяют вывести списки задач и студентов соответственно.

Опция `-i` позволяет добавить review в список игнорирования. Если параметр не указан, то автоматически будут добавлены те review, у которых не указан путь в репозитории и пользователь отклонил ввод пути (требуются опции `-f` и `-a`).

Опция `-I` позволяет удалить review из списка игнорирования.

Опции `-r` и `-R` позволяют добавить или удалить релокации репозиториев.

Опция `-l` позволяют добавить ссылку задачи с Review Board'а на каталог в репозитории, `-X` позволяет удалить из конфигурации лишние ссылки.

Опция `-f` позволяет загрузить целиком репозитории студентов, не указавших путь к задаче, в специальный каталог (см. опцию `unsorted`).

Опция `-a` допустима только с опцией `-f`, при загрузке репозитария студента целиком, синхронизатор в интерактивном режиме предлагает настроить необходимые ссылки. Можно либо выбрать один вариант из предложенных, либо ввести иной путь к задачу, либо ничего не вводить — в этом случае ссылки добавляться не будут.

Опции `-u` и `-U` позволяют загрузить только обновления репозиториев или показать репозитории, нуждающиеся в синхронизации, соответственно.

Опции `-q` и `-Q` включают тихий режим работы синхронизатора и svn соответственно.

Опция `-v` включает подробный режим работы синхронизатора.

Опции `-V` и `-h` выводят версию приложения или справку по использованию.

## Авторы

* Самунь Виктор, victor.samun@gmail.com
* Журавлёв Николай, znick@znick.ru
