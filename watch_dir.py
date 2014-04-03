#!/usr/bin/env python
# -*- coding: utf-8 -*-

import errno
import os
import Queue
import sys
import threading
import time

from requests import exceptions
from watchdog import events
from watchdog import observers

import eyes_wrapper


_QUEUES = []
DONE_BASE_NAME = 'done'
PROCESSING_DIR_NAME = 'processing'

# The Applitools Eyes Team License limits the number of concurrent
# tests to n + 1, where n is the number of team members. (We have five
# members.) However, Applitools does not enforce this limit; until they
# do, we are free to test as much as we want.
_MAX_CONCURRENT_TESTS = 6
_CONCURRENT_TEST_QUEUE = Queue.Queue(_MAX_CONCURRENT_TESTS)

# See http://robotframework.googlecode.com/hg/doc/userguide/RobotFrameworkUserGuide.html#test-library-scope
ROBOT_LIBRARY_SCOPE = 'TEST SUITE'


class WindowMatchingEventHandler(events.FileSystemEventHandler):
    """Event handler that sends new files to Applitools.
    """

    def __init__(self, eyes, queue):
        """Initializes the event handler.

        Args:
            eyes: An open Eyes instance to send images through.
            queue: A Queue to make non-empty when it is time to stop
                watching.
        """
        self._eyes = eyes
        self._queue = queue
        self._backlog = Queue.Queue()
        threading.Thread(target=self._send_new_files).start()

    def on_created(self, event):
        """Queues a new file for sending to Applitools.

        Does not queue directories.

        Args:
            event: The file system event.
        """
        if os.path.isfile(event.src_path):
            self._backlog.put(event.src_path)

    def _send_new_files(self):
        """Sends a new file to Applitools.

        Moves files to a processing subdirectory. Silently ignores
        errors from sending non-image files. Stops watching when a file
        called 'done' appears in the queue.
        """
        _CONCURRENT_TEST_QUEUE.put(None)
        while True:
            path = self._backlog.get()
            if os.path.basename(path) == DONE_BASE_NAME:
                # Stop watching the path
                self._queue.put(None)
                # Allow another path to be watched
                _CONCURRENT_TEST_QUEUE.get()
                _CONCURRENT_TEST_QUEUE.task_done()
                break
            head, tail = os.path.split(path)
            new_path = os.path.join(head,
                                    # PROCESSING_DIR_NAME, # TODO
                                    tail)
            # os.rename(path, new_path)
            try:
                eyes_wrapper.match_window(self._eyes, new_path)
            except exceptions.HTTPError:
                # The file wasn't a valid image.
                pass


def _send_new_files(path, eyes, queue):
    """Sends new files to Applitools.

    Watches a directory for files to send.

    Args:
        path: The name of the directory to watch.
        eyes: An open Eyes instance.
        queue: A Queue. When it becomes non-empty, it is time to stop
            watching for new files.
    """
    event_handler = WindowMatchingEventHandler(eyes, queue)
    observer = observers.Observer()
    observer.schedule(event_handler, path)
    observer.start()
    queue.get()
    observer.stop()
    observer.join()


def watch_path(path):
    """Sends new files to Applitools in another thread.

    Watches a directory for files to send. Moves new files to a
    processing subdirectory.

    Args:
        path: The name of the directory to watch.
    """
    try:
        os.makedirs(os.path.join(path, PROCESSING_DIR_NAME))
    except OSError as e:
        if e.errno != errno.EEXIST:
            raise
    queue = Queue.Queue()
    _QUEUES.append(queue)
    threading.Thread(target=lambda: eyes_wrapper.run_eyes(
        lambda eyes: _send_new_files(path, eyes, queue))).start()


def stop_watching():
    """Stops watching all directories.
    """
    for queue in _QUEUES:
        queue.put(None)  # The exact item doesn't matter


def main():
    paths = set([os.path.normcase(os.path.realpath(path))
                 for path in sys.argv[1:] or [os.curdir]])
    for path in paths:
        watch_path(path)
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        stop_watching()


if __name__ == '__main__':
    main()
