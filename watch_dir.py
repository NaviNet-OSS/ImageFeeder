#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os
import sys
import time

from requests import exceptions
from watchdog import events
from watchdog import observers

import eyes_wrapper


class WindowMatchingEventHandler(events.FileSystemEventHandler):
    """Event handler that sends new or modified images to Applitools.
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


def watch_path(path, eyes):
    """Sends new or modified files to Applitools.

    Watches a directory for files to send. Stops watching on
    KeyboardInterrupt.

    Args:
      path: The name of the directory to watch.
      eyes: An open Eyes instance.
    """
    event_handler = WindowMatchingEventHandler(eyes)
    observer = observers.Observer()
    observer.schedule(event_handler, path)
    observer.start()
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
    observer.join()


def main():
    try:
        path = sys.argv[1]
    except IndexError:
        path = os.curdir
    eyes_wrapper.run_eyes(lambda eyes: watch_path(path, eyes))


if __name__ == '__main__':
    main()
