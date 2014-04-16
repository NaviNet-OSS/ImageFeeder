#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""Watches directories and sends images to Eyes.
"""

import argparse
import logging
import os
import re
import Queue
import time

from applitools import errors
from applitools import eyes

import eyeswrapper
import watchdir

_DONE_BASE_NAME = 'done'
_FAILURE_DIR_NAME = 'FAILED'
_ARRAY_BASE = 0
_LOGGER = logging.getLogger(__name__)

# The Applitools Eyes Team License limits the number of concurrent
# tests to n + 1, where n is the number of team members. (We have five
# members.) However, Applitools does not enforce this limit; until they
# do, we are free to test as much as we want.
_MAX_CONCURRENT_TESTS = 6
_CONCURRENT_TEST_QUEUE = None


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


class WindowMatchingEventHandler(watchdir.CreationEventHandler,
                                 eyeswrapper.EyesWrapper):
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
        try:
            super(self.__class__, self).__exit__(exc_type, exc_value,
                                                 traceback)
        except errors.NewTestError as error:
            _LOGGER.info(error)
        except errors.TestFailedError as error:
            _LOGGER.info(error)
            raise watchdir.DestinationDirectoryException(_FAILURE_DIR_NAME)


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
    sep = os.path.normcase(sep)
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
    parser.add_argument('paths', nargs='*', default=[os.curdir],
                        help='path to watch (default: current directory)',
                        metavar='PATH')

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
        '--sep', default='_',
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
        '--passed', default=watchdir.DEFAULT_DIR_NAME,
        help='put files into DIRNAME when an Eyes test passes (default: '
        '%(default)s)', metavar='DIRNAME')

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
    args = _parse_args()

    # Logging
    _LOGGER.setLevel(args.log)
    handler = logging.StreamHandler()
    handler.setLevel(args.log)
    handler.setFormatter(
        logging.Formatter('%(asctime)s %(levelname)s %(message)s'))
    _LOGGER.addHandler(handler)
    _LOGGER.propagate = False
    if _LOGGER.getEffectiveLevel() <= logging.DEBUG:
        from applitools import logger
        eyes_logger = logger.StdoutLogger()
        # pylint: disable=protected-access
        eyes_logger._logger.propagate = False
        # pylint: enable=protected-access
        logger.set_logger(eyes_logger)
        requests_logger = logging.getLogger('requests.packages.urllib3')
        requests_logger.addHandler(handler)
        requests_logger.setLevel(logging.DEBUG)
        requests_logger.propagate = False

    # Command line arguments
    eyeswrapper.APP_NAME = args.app
    _ARRAY_BASE = args.array_base
    batch_info = None
    if args.batch:
        batch_info = eyes.BatchInfo(args.batch)
    _DONE_BASE_NAME = args.done
    _FAILURE_DIR_NAME = args.failed
    watchdir.PROCESSING_DIR_NAME = args.in_progress
    watchdir.DEFAULT_DIR_NAME = args.passed
    if args.test:
        eyeswrapper.TEST_NAME = args.test
    _MAX_CONCURRENT_TESTS = args.tests
    _CONCURRENT_TEST_QUEUE = Queue.Queue(_MAX_CONCURRENT_TESTS)

    # Watching
    paths = set([os.path.normcase(os.path.realpath(path))
                 for path in args.paths])
    for path in paths:
        host_os, host_app = _get_app_environment(path, args.sep)
        watchdir.watch(path, WindowMatchingEventHandler,
                       batch_info=batch_info,
                       host_app=args.browser or host_app,
                       host_os=args.os or host_os,
                       test_name=args.test or path)
    _LOGGER.info('Ready to start watching')
    try:
        while watchdir.is_running():
            time.sleep(1)
    except KeyboardInterrupt:
        watchdir.stop_watching()


if __name__ == '__main__':
    main()
