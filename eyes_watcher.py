#!/usr/bin/env python
# -*- coding: utf-8 -*-

import argparse
import errno
import os
import Queue
import time

from applitools import errors
from requests import exceptions

import eyeswrapper
import watchdir

_DONE_BASE_NAME = 'done'
_FAILURE_DIR_NAME = 'FAILED'

# The Applitools Eyes Team License limits the number of concurrent
# tests to n + 1, where n is the number of team members. (We have five
# members.) However, Applitools does not enforce this limit; until they
# do, we are free to test as much as we want.
_MAX_CONCURRENT_TESTS = 6
_CONCURRENT_TEST_QUEUE = None


class WindowMatchingEventHandler(watchdir.CreationEventHandler,
                                 eyeswrapper.EyesWrapper):
    def __init__(self, stop_queue):
        """Initializes the event handler.

        Args:
            stop_queue: A Queue to fill when it is time to stop
                watching.
        """
        self._stop_queue = stop_queue
        for base in self.__class__.__bases__:
            base.__init__(self)

    def _process(self):
        """Sends a new file to Applitools.

        Silently ignores errors from sending non-image files. Stops
        watching when a file called 'done' appears in the queue.
        """
        _CONCURRENT_TEST_QUEUE.put(None)
        while True:
            path = self._backlog.get()
            if os.path.basename(path) == _DONE_BASE_NAME:
                # Stop watching the path
                self._stop_queue.put(True)
                # Allow another path to be watched
                _CONCURRENT_TEST_QUEUE.get()
                _CONCURRENT_TEST_QUEUE.task_done()
                break
            try:
                eyeswrapper.match_window(self.eyes, path)
            except exceptions.HTTPError:
                # The file wasn't a valid image
                pass
            except IOError as e:
                # If the file does not exist, it must have been moved
                # to the failure directory. This is expected, so there
                # is no need to crash.
                if e.errno != errno.ENOENT:
                    raise

    def __exit__(self, exc_type, exc_value, traceback):
        try:
            super(self.__class__, self).__exit__(exc_type, exc_value,
                                                 traceback)
        except errors.TestFailedError:
            raise watchdir.DestinationDirectoryException(_FAILURE_DIR_NAME)


def _parse_args():
    """Parse command line arguments.

    Returns:
        A Namespace containing the parsed arguments.
    """
    parser = argparse.ArgumentParser()
    parser.add_argument('paths', nargs='*', default=[os.curdir],
                        help='path to watch (default: current directory)',
                        metavar='PATH')
    parser.add_argument('--done', default=_DONE_BASE_NAME,
                        help='set the file name which signals the end of a '
                        'test (default: %(default)s)', metavar='FILENAME')
    parser.add_argument('--failed', default=_FAILURE_DIR_NAME,
                        help='set the name of the directory to put files '
                        'into when an Eyes test fails (default: %(default)s)',
                        metavar='DIRNAME')
    parser.add_argument('--in-progress', default=watchdir.PROCESSING_DIR_NAME,
                        help='set the name of the directory to put files '
                        'into for processing (default: %(default)s)',
                        metavar='DIRNAME')
    parser.add_argument('--passed', default=watchdir.DEFAULT_DIR_NAME,
                        help='set the name of the directory to put files '
                        'into when an Eyes test passes (default: '
                        '%(default)s)', metavar='DIRNAME')
    parser.add_argument('-t', '--tests',
                        default=_MAX_CONCURRENT_TESTS, type=int, metavar='N',
                        help='set the number of tests to run concurrently '
                        '(default: %(default)d)')
    parser.add_argument('-v', '--verbose', action='store_true',
                        help='print a message when ready to start watching')
    return parser.parse_args()


def main():
    global _CONCURRENT_TEST_QUEUE
    global _DONE_BASE_NAME
    global _FAILURE_DIR_NAME
    global _MAX_CONCURRENT_TESTS
    args = _parse_args()
    _DONE_BASE_NAME = args.done
    _FAILURE_DIR_NAME = args.failed
    watchdir.PROCESSING_DIR_NAME = args.in_progress
    watchdir.DEFAULT_DIR_NAME = args.passed
    _MAX_CONCURRENT_TESTS = args.tests
    _CONCURRENT_TEST_QUEUE = Queue.Queue(_MAX_CONCURRENT_TESTS)
    paths = set([os.path.normcase(os.path.realpath(path))
                 for path in args.paths])
    for path in paths:
        watchdir.watch(path, WindowMatchingEventHandler)
    if args.verbose:
        print('Ready to start watching')
    try:
        while watchdir.is_running():
            time.sleep(1)
    except KeyboardInterrupt:
        watchdir.stop_watching()


if __name__ == '__main__':
    main()
