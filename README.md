# Directory watcher and image uploader for use with Applitools Eyes


## Introduction

[Applitools Eyes](http://applitools.com/) provides automated visual comparison
of screenshots against a baseline. NaviNet uses this service to test
screenshots of its product on various OS/browser combinations.

These tools are written in Python, so they use Applitools's Python SDK,
[`eyes-selenium`](https://pypi.python.org/pypi/eyes-selenium). As the name
implies, `eyes-selenium` uses Selenium to take screenshots, but we take our
screenshots in another way, so we don't use that part of the SDK.

This utility consists of three Python files: `imagefeeder.py`,
`eyeswrapper.py`, and `watchdir.py`.

Usually, you will want to run `imagefeeder.py`. For example, from the Windows
command line:

```
python imagefeeder.py -a d8VXjWZAEaAmqxh5wo3cNdaPsGJrgkn --log debug --test
test5 'Logs\ABC\*\*\\assets\screenshots' 'Logs\DEF\*\*\\assets\screenshots'
```

This has utility has only been tested with Python 2.7.6 on Windows 7.


## `imagefeeder.py`


### Synopsis

<code>**eyes\_watcher.py** [**-h**] **-a** _API-key_ [**-i** _number_]
[**--log** _level_] [**-t** _number_] [**--batch** _batch_] [**--app** _app_]
[**--test** _test_] [**--sep** _pattern_] [**--browser** _browser_] [**--os**
_OS_] [**--done** _filename_] [**--failed** _directory_] [**--in-progress**
_directory_] [**--passed** _directory_] [_glob_ ...]</code>


### Requirements

* [`eyes-selenium==1.42`](https://pypi.python.org/pypi/eyes-selenium/1.42)
* [`watchdog`](https://pypi.python.org/pypi/watchdog)


### Installation

This script isn't in PyPI and doesn't need to be installed. Just run the main
executable file.


### Description

Watch directories and send new images to Applitools Eyes for comparison.

Each directory given on the command line is watched for new files. A directory
should only be specified once; duplicates are removed. If the directory
contains any glob characters (`*`, `?`, or `[`), it is treated as a pattern.
All directories which match that pattern are watched when they are created;
this means that preexisting directories will _not_ match the pattern.

As a special case, if the specified directory already exists and contains no
glob characters, it will be watched.

You may need to escape glob characters to prevent your shell from expanding
them. Putting the entire directory glob in single quotes will generally work.

`imagefeeder.py` creates holding directories for incoming files at the parent
of the lowest level that currently exists, called `IN-PROGRESS`, `DONE`, and
`FAILED`. These names can be customized with command line options. For example,
if the user runs:

    python imagefeeder.py 'Logs\ABC\*\*\\assets\screenshots'

the lowest level that exists is `Logs\ABC`, so this will be the directory
structure:

* `Log`
  * `ABC`
  * `DONE`
  * `FAILED`
  * `IN-PROGRESS`


When a new file appears in any directory matching
`Logs\ABC\\*\\*\\assets\screenshots`, `imagefeeder.py` will move it to
`IN-PROGRESS` and upload it to Applitools Eyes. When it stops watching, it
moves all files from `IN-PROGRESS` to `DONE` on success and `FAILED` on
failure. Failure means the images did not match the baseline. Success means the
images matched the baseline, or there was no baseline.

By default, images are uploaded in the order they appear in the directory. To
avoid race conditions, you can turn on indexing using, for example, `--index
0`. When using indexing, images are only uploaded in index order starting from
the specified number, where the index of a file is the first nonnegative
decimal integer appearing in its name; for example, the index of
`0123screenshot.png` is 123. If an image appears with index 5, it will only be
uploaded _after_ images 0 through 4. If another image 5 appears later, it is
ignored.

Our Applitools Eyes license only allows us to run 6 tests concurrently. (This
is not enforced, but it might be one day. For now, this limit can be overridden
with the `--tests` option.) If you try to watch too many directories, the extra
directories' incoming files will be placed in a backlog. As soon as the first
Eyes test is done, the next directory will upload its backlog. So basically,
you can watch as many directories as you want, and it will work, but they might
not all be uploaded concurrently.


There are three ways to stop watching a directory. After some time (5 minutes
by default) without a new file in a directory, it stops watching that
directory. Pressing Ctrl-C immediately uploads anything in the backlogs of all
directory watchers, waits for a response from Eyes, and then exits. A file
named `done` (configurable with `--done`) is taken as a signal to stop watching
the directory in which it is created.


### General arguments

* **-h**, **--help**
    * Display help and exit.
* **-a**, **--api-key**
    * Set the Eyes API key. This is required.
* **-i**, **--index**, **--array-base**
    * Start uploading images from the given index. By default, indexing is
      disabled.
* **--log**=_level_
    * Log progress. Legal values are `CRITICAL`, `ERROR`, `WARNING`, `INFO`,
      and `DEBUG`. The default is `WARNING`.
* **-t**, **--tests**=_number_
    * Set the maximum number of tests to run concurrently. The default is `6`.
      A nonpositive number means there is no limit.
* **--timeout**=_number_
    * Set the time-out interval in seconds. The default is `300`.


### Eyes session arguments

These arguments are passed as `startInfo` parameters to Eyes when starting a
new session. See [Applitools's
API](https://eyes.applitools.com/api/json/metadata?op=StartNewSession) for
the full list. The app, test, OS, and browser determine which baseline Eyes
will run against.

* **--batch**=_batch_
    * Batch all tests together as _batch_. If this is not set, the tests are
      not batched.
* **--app**=_appname_
    * Run against the given test's baseline. The default is derived from the
      watched directory path.
* **--test**=_testname_
    * Run against the given test's baseline. The default is derived from the
      watched directory path.
* **--sep**=_pattern_
    * Find the nearest directory to the watched directory with three or more
      instances of _pattern_, split on it, and set the host OS and browser to
      the last two fields but one. The default is `\_`. For example, if the
      directory is
      `D:\Tests\Robot\Logs\ABC\8ca2f6b5-ba87-43f7-a722-292ace426645\_Windows
      8\_chrome\_\1504d423550b4f719142897ae60d4ba0\assets\screenshots`, the
      nearest directory with two underscores is
      `8ca2f6b5-ba87-43f7-a722-292ace426645\_Windows 8\_chrome\_`, so the OS
      will be set to `windows 8` and the browser to `chrome`. This only works
      if the directory structure cooperates, so `--os` and `--browser` provide
      more fine-tuned customizability.
* **--browser**=_browser_
    * Set the host browser. It overrides the browser as determined by `--sep`.
* **--os**=_os_
    * Set the host OS. It overrides the OS as determined by `--sep`.


### File and directory name arguments

* **--done**=_filename_
    * Stop testing when a file with the given name appears. The default is
      `done`.
* **--failed**=_directory_
    * Move files here when the Eyes test fails. The default is `FAILED`.
* **--in-progress**=_directory_
    * Move files here during the Eyes test. The default is `IN-PROGRESS`.
* **--passed**=_directory_
    * Move files here when the Eyes test passes. The default is `DONE`.


## `eyeswrapper.py`


### Synopsis

<code>**eyeswrapper.py** [**-h**] [[**-o**] _directory_ ...]</code>


### Requirements

* [`eyes-selenium==1.42`](https://pypi.python.org/pypi/eyes-selenium/1.42)
  * Run `pip install --upgrade eyes-selenium==1.42`. The version is constrained
    because `eyeswrapper.py` hacks into the internals of Eyes. Applitools is
    working on a new Python SDK that will obviate such measures.


### Description

Upload directories full of images to Eyes.


### Arguments

* **-h**, **--help**
    * Display help and exit.
* **-o**, **--overwrite** _directory_
    * Overwrite the baseline in Eyes with the images in the directory. Without
     this flag, it compares against the baseline but does not overwrite it.


## `watchdir.py`


### Requirements

* [`watchdog`](https://pypi.python.org/pypi/watchdog)


### Description

This file is wrapper around `watchdog` for watching directories and moving new
files between IN-PROGRESS and DONE directories.
