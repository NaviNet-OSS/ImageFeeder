#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os
import Queue
import sys
import threading
import time

from requests import exceptions

import eyes_wrapper
import watch_dir


class WindowMatchingEventHandler(watch_dir.CreationEventHandler):
    def __init__(self, stop_event, **kwargs):
        """Initializes the event handler.

        Args:
            stop_event: An Event to set when it is time to stop
                watching.

        Kwargs:
            eyes: An open Eyes instance.
        """
        self._eyes = kwargs.pop('eyes')
        self._stop_event = stop_event
        super(self.__class__, self).__init__()

    def _process(self):
        """Sends a new file to Applitools.

        Silently ignores errors from sending non-image files. Stops
        watching when a file called 'done' appears in the queue.
        """
        _CONCURRENT_TEST_QUEUE.put(None)
        while True:
            path = self._backlog.get()
            if os.path.basename(path) == watch_dir.DONE_BASE_NAME:
                # Stop watching the path
                self._stop_event.set()
                # Allow another path to be watched
                _CONCURRENT_TEST_QUEUE.get()
                _CONCURRENT_TEST_QUEUE.task_done()
                break
            try:
                eyes_wrapper.match_window(self._eyes, path)
            except exceptions.HTTPError:
                # The file wasn't a valid image.
                pass


# The Applitools Eyes Team License limits the number of concurrent
# tests to n + 1, where n is the number of team members. (We have five
# members.) However, Applitools does not enforce this limit; until they
# do, we are free to test as much as we want.
_MAX_CONCURRENT_TESTS = 2
_CONCURRENT_TEST_QUEUE = Queue.Queue(_MAX_CONCURRENT_TESTS)


def main():
    paths = set([os.path.normcase(os.path.realpath(path))
                 for path in sys.argv[1:] or [os.curdir]])
    for path in paths:
        stop_event = watch_dir.prepare_to_watch(path)
        threading.Thread(
            target=(lambda path=path, stop_event=stop_event:
                    eyes_wrapper.run_eyes(lambda eyes: watch_dir.watch(
                    path, WindowMatchingEventHandler, stop_event,
                    eyes=eyes)))).start()
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        watch_dir.stop_watching()


if __name__ == '__main__':
    main()
