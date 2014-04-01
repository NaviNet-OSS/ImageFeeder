#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os
import Queue
import sys
import threading
import time

from requests import exceptions
from watchdog import events
from watchdog import observers

import eyes_wrapper


_QUEUE = Queue.Queue()

# See http://robotframework.googlecode.com/hg/doc/userguide/RobotFrameworkUserGuide.html#test-library-scope
ROBOT_LIBRARY_SCOPE = 'TEST SUITE'


class WindowMatchingEventHandler(events.FileSystemEventHandler):
    """Event handler that sends new images to Applitools.
    """

    def __init__(self, eyes):
        """Initializes the event handler.

        Args:
            eyes: An open Eyes instance to send images through.
        """
        self._eyes = eyes

    def on_created(self, event):
        """Sends a new image to Applitools.

        Does not send directories. Silently ignores errors from sending
        non-image files.

        Args:
            event: The file system event.
        """
        if os.path.isfile(event.src_path):
            try:
                eyes_wrapper.match_window(self._eyes, event.src_path)
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
    event_handler = WindowMatchingEventHandler(eyes)
    observer = observers.Observer()
    observer.schedule(event_handler, path)
    observer.start()
    queue.get()
    observer.stop()
    observer.join()


def watch_path(path):
    """Sends new files to Applitools in another thread.

    Watches a directory for files to send.

    Args:
        path: The name of the directory to watch.
    """
    threading.Thread(target=(lambda: eyes_wrapper.run_eyes(lambda eyes:
        _send_new_files(path, eyes, _QUEUE)))).start()


def stop_watching():
    """Stops watching all directories.
    """
    _QUEUE.put(None)  # The exact item doesn't matter


def main():
    try:
        path = sys.argv[1]
    except IndexError:
        path = os.curdir
    watch_path(path)
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        stop_watching()


if __name__ == '__main__':
    main()
