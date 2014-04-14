#!/usr/bin/env python
# -*- coding: utf-8 -*-

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

    def __init__(self, stop_event, batch_info):
        """Initializes the event handler.

        Args:
            stop_event: An Event to set when it is time to stop
                watching.
        """
        self._next_index = _ARRAY_BASE
        self._path_cache = _GrowingList()
        self._stop_event = stop_event
        for base in self.__class__.__bases__:
            base.__init__(self, batch_info)

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
                # Upload whatever files are left
                for path in self._path_cache[self._next_index:]:
                    if path:
                        eyeswrapper.match(self.eyes, path)
                # Stop watching the path
                self._stop_event.set()
                # Allow another path to be watched
                _CONCURRENT_TEST_QUEUE.get()
                _CONCURRENT_TEST_QUEUE.task_done()
                break
            match = re.search(r'\d+', basename)
            if match:
                matched_index = int(match.group())
                if matched_index < self._next_index:
                    logging.warn(
                        'Ignoring file with repeated index: {}'.format(path))
                else:
                    self._path_cache[matched_index] = path
                    try:
                        while self._path_cache[self._next_index]:
                            eyeswrapper.match(
                                self.eyes, self._path_cache[self._next_index])
                            self._next_index += 1
                    except IndexError:
                        pass
            else:
                logging.warn('No index in file name: {}'.format(path))
            logging.debug('Wrong order cache: {}'.format(
                self._path_cache[self._next_index + 1:]))

    def __exit__(self, exc_type, exc_value, traceback):
        try:
            super(self.__class__, self).__exit__(exc_type, exc_value,
                                                 traceback)
        except errors.NewTestError as e:
            logging.info(e)
        except errors.TestFailedError as e:
            logging.info(e)
            raise watchdir.DestinationDirectoryException(_FAILURE_DIR_NAME)


def _parse_args():
    """Parse command line arguments.

    Returns:
        A Namespace containing the parsed arguments.
    """
    parser = argparse.ArgumentParser()
    parser.add_argument('--app', default=eyeswrapper.APP_NAME,
                        help='run against the APP baseline (default: '
                        '%(default)s)')
    parser.add_argument('--array-base', default=_ARRAY_BASE, type=int,
                        help='upload the image with index N first (default: '
                        '%(default)s)', metavar='N')
    parser.add_argument('--batch',
                        help='batch all directories together under BATCH')
    parser.add_argument('--done', default=_DONE_BASE_NAME,
                        help='end a test when FILENAME is created (default: '
                        '%(default)s)', metavar='FILENAME')
    parser.add_argument('--failed', default=_FAILURE_DIR_NAME,
                        help='put files into DIRNAME when an Eyes test fails '
                        '(default: %(default)s)', metavar='DIRNAME')
    parser.add_argument('--in-progress', default=watchdir.PROCESSING_DIR_NAME,
                        help='put files into DIRNAME for processing '
                        '(default: %(default)s)', metavar='DIRNAME')
    parser.add_argument('--log', default='WARNING', type=str.upper,
                        help='set the logging level (default: %(default)s)',
                        metavar='LEVEL')
    parser.add_argument('--passed', default=watchdir.DEFAULT_DIR_NAME,
                        help='put files into DIRNAME when an Eyes test '
                        'passes (default: %(default)s)', metavar='DIRNAME')
    parser.add_argument('-t', '--tests', default=_MAX_CONCURRENT_TESTS,
                        type=int, help='run N tests concurrently (N <= 0 '
                        'means unlimited; default: %(default)d)',
                        metavar='N')
    parser.add_argument('--test', default=eyeswrapper.TEST_NAME,
                        help='set the test name (default: %(default)s)')
    parser.add_argument('paths', nargs='*', default=[os.curdir],
                        help='path to watch (default: current directory)',
                        metavar='PATH')
    return parser.parse_args()


def main():
    global _CONCURRENT_TEST_QUEUE
    global _DONE_BASE_NAME
    global _FAILURE_DIR_NAME
    global _ARRAY_BASE
    global _MAX_CONCURRENT_TESTS
    args = _parse_args()
    logging.basicConfig(format='%(asctime)s %(levelname)s %(message)s',
                        level=args.log)
    eyeswrapper.APP_NAME = args.app
    _ARRAY_BASE = args.array_base
    batch_info = None
    if args.batch:
        batch_info = eyes.BatchInfo(args.batch)
    _DONE_BASE_NAME = args.done
    _FAILURE_DIR_NAME = args.failed
    watchdir.PROCESSING_DIR_NAME = args.in_progress
    watchdir.DEFAULT_DIR_NAME = args.passed
    _MAX_CONCURRENT_TESTS = args.tests
    _CONCURRENT_TEST_QUEUE = Queue.Queue(_MAX_CONCURRENT_TESTS)
    eyeswrapper.TEST_NAME = args.test
    paths = set([os.path.normcase(os.path.realpath(path))
                 for path in args.paths])
    for path in paths:
        watchdir.watch(path, WindowMatchingEventHandler, batch_info)
    logging.info('Ready to start watching')
    try:
        while watchdir.is_running():
            time.sleep(1)
    except KeyboardInterrupt:
        watchdir.stop_watching()


if __name__ == '__main__':
    main()
