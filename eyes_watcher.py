#!/usr/bin/env python
# -*- coding: utf-8 -*-

import errno
import os
import Queue
import sys
import time

from requests import exceptions

import eyeswrapper
import watchdir

DONE_BASE_NAME = 'done'

# The Applitools Eyes Team License limits the number of concurrent
# tests to n + 1, where n is the number of team members. (We have five
# members.) However, Applitools does not enforce this limit; until they
# do, we are free to test as much as we want.
_MAX_CONCURRENT_TESTS = 6
_CONCURRENT_TEST_QUEUE = Queue.Queue(_MAX_CONCURRENT_TESTS)


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
            if os.path.basename(path) == DONE_BASE_NAME:
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


def main():
    paths = set([os.path.normcase(os.path.realpath(path))
                 for path in sys.argv[1:] or [os.curdir]])
    for path in paths:
        watchdir.watch(path, WindowMatchingEventHandler)
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        watchdir.stop_watching()


if __name__ == '__main__':
    main()
