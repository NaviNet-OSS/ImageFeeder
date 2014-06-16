#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""Watches directories and sends images to Eyes.
"""

import argparse
from distutils import dir_util
import logging
import os
import re
import Queue
import shutil
import time

from applitools import errors
from applitools import eyes
import glob
from watchdog import events

import eyeswrapper
import watchdir

_DONE_BASE_NAME = 'done'
_FAILURE_DIR_NAME = 'FAILED'
_SUCCESS_DIR_NAME = 'DONE'
_ARRAY_BASE = 0
_DEFAULT_SEP = '_'
_LOGGER = logging.getLogger(__name__)

# The Applitools Eyes Team License limits the number of concurrent
# tests to n + 1, where n is the number of team members. (We have five
# members.) However, Applitools does not enforce this limit; until they
# do, we are free to test as much as we want.
_MAX_CONCURRENT_TESTS = 6
_CONCURRENT_TEST_QUEUE = None


def _make_empty_directory(path):
    """Clears a directory or deletes a regular file.

    Deletes whatever the path refers to (if anything) and creates an
    empty directory at that path.

    Args:
        path: The path to make point to an empty directory.
    """
    _LOGGER.debug('Clearing directory: {}'.format(path))
    if os.path.isdir(path):
        shutil.rmtree(path)
    elif os.path.exists(path):
        os.remove(path)
    dir_util.mkpath(path)


class DirectoryGlobEventHandler(events.FileSystemEventHandler):
    """Event handler for new directories matching a glob."""

    def __init__(self, stop_event, **kwargs):
        """Initializes the event handler.

        Args:
            stop_event: An Event to set to stop watching.
            batch_info: A BatchInfo or None.
            base_path: The literal existing part of the watched
                directory.
            host_app: A browser name or None.
            host_os: An OS name or None.
            overwrite_baseline: Whether to overwrite the baseline.
            patterns: An iterable of file name globs.
            sep: The host information separator, set by --sep.
            test_name: The name of the Eyes test.
        """
        self._patterns = kwargs.pop('patterns', ['*'])
        self._batch_info = kwargs.pop('batch_info', None)
        self._host_app = kwargs.pop('host_app', None)
        self._host_os = kwargs.pop('host_os', None)
        self._sep = kwargs.pop('sep', _DEFAULT_SEP)
        self._base_path = kwargs.pop('base_path')
        self._stop_event = stop_event
        processing_dir = os.path.join(os.path.dirname(self._base_path),
                                      watchdir.PROCESSING_DIR_NAME)
        if os.path.isfile(processing_dir):
            os.remove(processing_dir)
        _LOGGER.info('Processing directory: {}'.format(processing_dir))
        super(self.__class__, self).__init__(**kwargs)
        if (self._base_path == self._patterns[0] and
            os.path.isdir(self._base_path)):
            # Watch a non-glob immediately.
            self._watch(self._base_path)
            stop_event.set()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        pass

    def on_created(self, event):
        """Handles the creation of a new file.

        If the new file is a directory and it matches one of the event
        handler's globs, it watches it for new images to send to Eyes.

        Args:
            event: The Event representing the creation of a new file.
        """
        src_path = event.src_path
        matched_pattern = _matches_any_pattern(src_path, self._patterns)
        if matched_pattern:
            _LOGGER.info('Created: {} (matching {})'.format(src_path,
                                                            matched_pattern))
            if event.is_directory:
                self._watch(src_path)
            else:
                _LOGGER.warn('Not a directory: {}'.format(src_path))

    def _watch(self, src_path):
        """Watches a directory to send new images to Eyes.

        Args:
            src_path: The path to watch.
        """
        host_os, host_app = _get_app_environment(src_path, self._sep)
        watchdir.watch(src_path, WindowMatchingEventHandler,
                       base_path=self._base_path, batch_info=self._batch_info,
                       host_app=self._host_app or host_app,
                       host_os=self._host_os or host_os,
                       watched_path=src_path, test_name=src_path)


class _GrowingList(list):
    """List that grows when needed.
    """

    def __setitem__(self, index, value):
        """Sets the value at an index.

        If the index is out of bounds, grows the list to be long
        enough, filling unspecified indexes with None.

        Args:
            index: An index.
            value: A value.
        """
        if index >= len(self):
            self.extend([None] * (index + 1 - len(self)))
        super(self.__class__, self).__setitem__(index, value)


class WindowMatchingEventHandler(eyeswrapper.EyesWrapper,
                                 watchdir.CreationEventHandler):
    """Event handler for moving new files and uploading them to Eyes.
    """

    def __init__(self, stop_event, **kwargs):
        """Initializes the event handler.

        Args:
            stop_event: An Event to set when it is time to stop
                watching.
        """
        # pylint: disable=super-init-not-called
        self._next_index = _ARRAY_BASE
        self._path_cache = _GrowingList()
        self._stop_event = stop_event
        for base in self.__class__.__bases__:
            base.__init__(self, **kwargs)

    def _process(self):
        """Sends new files to Applitools.

        Each image file must include an integer index somewhere in its
        name. This method uploads them in order of their indexes,
        starting at 0. If two files include the same integer, only the
        first is used.

        Stops watching when the "done" file (set by --done) appears in
        the queue.

        Ignores files without indexes.
        """
        while not self.driver:
            # Wait for Eyes to have opened.
            time.sleep(0.1)
        _CONCURRENT_TEST_QUEUE.put(None)
        while True:
            path = self._backlog.get()
            basename = os.path.basename(path)
            if basename == _DONE_BASE_NAME:
                self._stop()
                break
            match = re.search(r'\d+', basename)
            if match:
                # The file has an index and should be uploaded.
                matched_index = int(match.group())
                if matched_index < self._next_index:
                    _LOGGER.warn(
                        'Ignoring file with repeated index: {}'.format(path))
                else:
                    self._path_cache[matched_index] = path
                    # Upload as many files from the cache as possible
                    # without skipping any indexes.
                    try:
                        while self._path_cache[self._next_index]:
                            eyeswrapper.match(
                                self.eyes, self._path_cache[self._next_index])
                            self._next_index += 1
                    except IndexError:
                        # We have run off the end of the cache. This is
                        # expected when the cache has no holes in it.
                        pass
            else:
                _LOGGER.warn('No index in file name: {}'.format(path))
            _LOGGER.debug('Wrong order cache: {}'.format(
                self._path_cache[self._next_index + 1:]))

    def _stop(self):
        """Stops watching.
        """
        # Upload whatever files are left.
        for path in self._path_cache[self._next_index:]:
            if path:
                eyeswrapper.match(self.eyes, path)
        # Stop watching the path.
        self._stop_event.set()
        # Allow another path to be watched.
        _CONCURRENT_TEST_QUEUE.get()
        _CONCURRENT_TEST_QUEUE.task_done()

    def __exit__(self, exc_type, exc_value, traceback):
        """Ends the Eyes test and moves files.

        Moves files on completion of a test. The destination directory
        depends on whether the Eyes test succeeded or failed.

        Args:
            exc_type: The type of the raised exception.
            exc_value: The raised exception.
            traceback: The traceback.
        """
        try:
            super(self.__class__, self).__exit__(exc_type, exc_value,
                                                 traceback)
        except errors.NewTestError as error:
            _LOGGER.info(error)
            final_dir_name = _SUCCESS_DIR_NAME
        except errors.TestFailedError as error:
            _LOGGER.info(error)
            final_dir_name = _FAILURE_DIR_NAME
        else:
            final_dir_name = _SUCCESS_DIR_NAME
        finally:
            final_dir = os.path.join(os.path.dirname(self._base_path),
                                     final_dir_name)
            base_path_final_copy = os.path.join(
                final_dir, os.path.basename(self._base_path))
            watched_path_final_copy = os.path.join(
                base_path_final_copy,
                os.path.relpath(self._watched_path, self._base_path))
            _make_empty_directory(watched_path_final_copy)
            _LOGGER.debug('Moving {} to {}'.format(
                self._watched_path_copy, watched_path_final_copy))
            if os.path.isdir(watched_path_final_copy):
                shutil.rmtree(watched_path_final_copy)
            elif os.path.exists(watched_path_final_copy):
                os.remove(watched_path_final_copy)
            os.rename(self._watched_path_copy, watched_path_final_copy)


def _get_app_environment(path, sep):
    """Get the host OS and browser.

    Finds the nearest parent directory of the watched path with two or
    more instances of sep and splits on it. The host OS and browser are
    the last two fields but one.

    Args:
        path: The path in which to find the host information.
        sep: The separator. If false, simply returns None for both.

    Returns:
        An iterable of two elements: the host OS and browser, which are
        both strings or both None.
    """
    prev_path = None
    while path != prev_path and sep:
        head, tail = os.path.split(path)
        fields = tail.split(sep)
        if len(fields) > 3:
            return fields[-3:-1]
        prev_path = path
        path = head
    return None, None


def _parse_args():
    """Parse command line arguments.

    Returns:
        A Namespace containing the parsed arguments.
    """
    parser = argparse.ArgumentParser()
    parser.add_argument(
        'patterns', nargs='*', default=[os.curdir],
        help='glob of paths to watch (default: current directory)',
        metavar='GLOB')

    baseline_group = parser.add_argument_group(
        'Eyes session arguments',
        'startInfo parameters for the new Eyes session')
    baseline_group.add_argument(
        '--batch', help='batch all directories together as BATCH')
    baseline_group.add_argument(
        '--app', default=eyeswrapper.APP_NAME,
        help='run against the APP baseline (default: %(default)s)')
    baseline_group.add_argument(
        '--test', help='set the test name (default: the path to watch)')
    baseline_group.add_argument(
        '--sep', default=_DEFAULT_SEP,
        help='find the nearest parent directory to the watched path with '
        'three or more instances of PATTERN, split on it, and set the host '
        'OS and browser to the last two fields but one (default: '
        '%(default)s)', metavar='PATTERN')
    baseline_group.add_argument('--browser',
                                help='set the host browser (overrides --sep)')
    baseline_group.add_argument('--os',
                                help='set the host OS (overrides --sep)')

    path_group = parser.add_argument_group(
        'file and directory name arguments')
    path_group.add_argument(
        '--done', default=_DONE_BASE_NAME,
        help='end a test when FILENAME is created (default: %(default)s)',
        metavar='FILENAME')
    path_group.add_argument('--failed', default=_FAILURE_DIR_NAME,
                            help='put files into DIRNAME when an Eyes test '
                            'fails (default: %(default)s)', metavar='DIRNAME')
    path_group.add_argument(
        '--in-progress', default=watchdir.PROCESSING_DIR_NAME,
        help='put files into DIRNAME for processing (default: %(default)s)',
        metavar='DIRNAME')
    path_group.add_argument(
        '--passed', default=_SUCCESS_DIR_NAME,
        help='put files into DIRNAME when an Eyes test passes (default: '
        '%(default)s)', metavar='DIRNAME')

    parser.add_argument('-a', '--api-key', required=True,
                        help='set the Applitools Eyes API key')
    parser.add_argument('--array-base', default=_ARRAY_BASE, type=int,
                        help='start uploading images from index N (default: '
                        '%(default)s)', metavar='N')
    parser.add_argument('--log', default='WARNING', type=str.upper,
                        help='set the logging level (default: %(default)s)',
                        metavar='LEVEL')
    parser.add_argument('-t', '--tests', default=_MAX_CONCURRENT_TESTS,
                        type=int, help='run N tests concurrently (N <= 0 '
                        'means unlimited; default: %(default)d)',
                        metavar='N')

    return parser.parse_args()


def _literal_existing_part(pattern):
    """Returns the literal existing part of a glob.

    The literal existing part is as many consecutive directories of the
    glob as possible which do not include any glob metacharacters ('*',
    '?', and '['). For example, the literal existing part of '/x/y/*/z/?'
    is '/x/y'.

    Args:
        pattern: A file glob.

    Returns:
        The literal existing part of the glob.
    """
    pattern += os.sep
    while True:
        dirname = os.path.dirname(pattern)
        if glob.has_magic(dirname) or not os.path.exists(dirname):
            pattern = dirname
        else:
            return dirname


def _matches_any_pattern(path, patterns):
    """Compares a path against a list of globs.

    Args:
        path: A path.
        patterns: An iterable of file name globs.

    Returns:
        The first pattern the path matches, or False if none matches.
    """
    normalized_path = os.path.normcase(os.path.normpath(path))
    for pattern in patterns:
        for matching_path in glob.glob(pattern):
            if (os.path.normcase(os.path.normpath(matching_path)) ==
                normalized_path):
                return pattern
    return False


def _set_up_logging(level):
    """Sets up logging.

    Args:
        level: The logging level.
    """
    _LOGGER.setLevel(level)
    handler = logging.StreamHandler()
    handler.setLevel(level)
    handler.setFormatter(
        logging.Formatter('%(asctime)s %(levelname)s %(message)s'))
    _LOGGER.addHandler(handler)
    _LOGGER.propagate = False
    if _LOGGER.getEffectiveLevel() <= logging.DEBUG:
        eyeswrapper.LOGGER = _LOGGER
        watchdir.LOGGER = _LOGGER
        from applitools import logger
        eyes_logger = logger.StdoutLogger()
        logger.set_logger(eyes_logger)
        requests_logger = logging.getLogger('requests.packages.urllib3')
        requests_logger.addHandler(handler)
        requests_logger.setLevel(logging.DEBUG)
        requests_logger.propagate = False


def main():
    """Watches directories and sends images to Eyes.

    Use --help for full command line option documentation.
    """
    # pylint: disable=global-statement
    global _ARRAY_BASE
    global _CONCURRENT_TEST_QUEUE
    global _DONE_BASE_NAME
    global _FAILURE_DIR_NAME
    global _MAX_CONCURRENT_TESTS
    global _SUCCESS_DIR_NAME
    args = _parse_args()

    # Logging
    _set_up_logging(args.log)
    _LOGGER.debug('Args: {}'.format(args))

    # Command line arguments
    batch_info = None
    if args.batch:
        batch_info = eyes.BatchInfo(args.batch)
    eyeswrapper.APP_NAME = args.app
    if args.test:
        eyeswrapper.TEST_NAME = args.test
    _DONE_BASE_NAME = args.done
    _FAILURE_DIR_NAME = args.failed
    watchdir.PROCESSING_DIR_NAME = args.in_progress
    _SUCCESS_DIR_NAME = args.passed
    eyes.Eyes.api_key = args.api_key
    _ARRAY_BASE = args.array_base
    _MAX_CONCURRENT_TESTS = args.tests
    _CONCURRENT_TEST_QUEUE = Queue.Queue(_MAX_CONCURRENT_TESTS)

    # Watching
    watched_paths = []
    for pattern in args.patterns:
        pattern = os.path.realpath(pattern)
        path = _literal_existing_part(pattern)
        normalized_path = os.path.normcase(path)
        if normalized_path in watched_paths:
            _LOGGER.info('Skipping {}: same as {}'.format(pattern,
                                                          normalized_path))
            continue
        watched_paths.append(normalized_path)
        watchdir.watch(normalized_path, DirectoryGlobEventHandler,
                       base_path=normalized_path,
                       patterns=[os.path.normcase(pattern)],
                       batch_info=batch_info, host_app=args.browser,
                       host_os=args.os, sep=args.sep)
    _LOGGER.info('Ready to start watching')
    try:
        while watchdir.is_running():
            time.sleep(1)
    except KeyboardInterrupt:
        watchdir.stop_watching()


if __name__ == '__main__':
    main()
