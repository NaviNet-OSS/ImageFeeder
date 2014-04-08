#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os
import Queue
import sys
import threading
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


class WindowMatchingEventHandler(watchdir.CreationEventHandler):
    def __init__(self, stop_queue, **kwargs):
        """Initializes the event handler.

        Args:
            stop_queue: A Queue to fill when it is time to stop
                watching.

        Kwargs:
            eyes: An open Eyes instance.
        """
        self._eyes = kwargs.pop('eyes')
        self._stop_queue = stop_queue
        super(self.__class__, self).__init__()

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
                eyeswrapper.match_window(self._eyes, path)
            except exceptions.HTTPError:
                # The file wasn't a valid image.
                pass


def _run(path, stop_queue):
    """Sends new files to Eyes.

    Opens Eyes; watches for new files and sends them to Eyes; stops
    watching; closes Eyes.

    Args:
        path: The path to watch.
        stop_queue: A Queue to fill when it is time to stop
            watching.
    """
    with eyeswrapper.EyesWrapper() as eyes_wrapper:
        watchdir.watch(path, WindowMatchingEventHandler, stop_queue,
                        eyes=eyes_wrapper.eyes)


def main():
    paths = set([os.path.normcase(os.path.realpath(path))
                 for path in sys.argv[1:] or [os.curdir]])
    for path in paths:
        stop_queue = watchdir.prepare_to_watch(path)
        threading.Thread(target=lambda path=path, stop_queue=stop_queue: (
            _run(path, stop_queue))).start()
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        watchdir.stop_watching()


if __name__ == '__main__':
    main()
