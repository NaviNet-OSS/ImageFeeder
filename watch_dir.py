# -*- coding: utf-8 -*-

from distutils import dir_util
import os
import Queue
import shutil
import threading
import time

from watchdog import events
from watchdog import observers


_STOP_EVENTS = []
DONE_BASE_NAME = 'done'
PROCESSING_DIR_NAME = 'IN-PROGRESS'
SUCCESS_DIR_NAME = 'DONE'
FAILURE_DIR_NAME = 'FAILED'

# See http://robotframework.googlecode.com/hg/doc/userguide/RobotFrameworkUserGuide.html#test-library-scope
ROBOT_LIBRARY_SCOPE = 'TEST SUITE'


class CreationEventHandler(events.FileSystemEventHandler):
    """Event handler for moving new files.
    """

    def __init__(self):
        """Initializes the event handler.
        """
        self._backlog = Queue.Queue()
        thread = threading.Thread(target=self._process)
        thread.daemon = True
        thread.start()

    def on_created(self, event):
        """Queues a new file for processing.

        Does not queue directories. Moves files to a processing
        directory.

        Args:
            event: The file system event.
        """
        src_path = event.src_path
        if os.path.isfile(src_path):
            head, tail = os.path.split(src_path)
            new_path = os.path.join(os.path.dirname(head),
                                    PROCESSING_DIR_NAME, tail)
            if os.path.exists(new_path):
                os.remove(new_path)
            shutil.move(src_path, new_path)
            while os.path.exists(src_path):
                time.sleep(0.1)
            self._backlog.put(new_path)

    def _process(self):
        """Process the backlog.
        """
        raise NotImplementedError


def prepare_to_watch(path):
    """Prepare to watch a path.

    Creates three processing directories.

    Args:
        path: The name of the directory to watch, without a trailing
            directory separator.

    Returns:
        An Event that signals when to stop watching the path.
    """
    # If path has a trailing directory separator, dirname won't work
    parent = os.path.dirname(path)
    for new_dir_name in [PROCESSING_DIR_NAME, SUCCESS_DIR_NAME,
                         FAILURE_DIR_NAME]:
        new_dir_path = os.path.join(parent, new_dir_name)
        if os.path.isdir(new_dir_path):
            shutil.rmtree(new_dir_path)
        elif os.path.exists(new_dir_path):
            os.remove(new_dir_path)
        dir_util.mkpath(new_dir_path)
    stop_event = threading.Event()
    _STOP_EVENTS.append(stop_event)
    return stop_event


def watch(path, event_handler_class, stop_event, **kwargs):
    """Watches a directory for files to send.

    Args:
        path: The name of the directory to watch.
        event_handler_class: The class of the event handler to use.
        **kwargs: Arbitrary keyword arguments for the event handler's
            initializer. 'stop_event' is also set to an Event, if not
            in the dictionary.

    Kwargs:
        stop_event: An Event which signals when to stop watching.
    """
    event_handler = event_handler_class(stop_event, **kwargs)
    observer = observers.Observer()
    observer.schedule(event_handler, path)
    observer.start()
    stop_event.wait()
    observer.stop()
    observer.join()
    src = os.path.join(os.path.dirname(path), PROCESSING_DIR_NAME)
    dst = os.path.join(os.path.dirname(path), SUCCESS_DIR_NAME)
    dir_util.remove_tree(dst)
    dir_util.copy_tree(src, dst)
    for base_name in os.listdir(src):
        path = os.path.join(src, base_name)
        if os.path.isfile(path):
            os.remove(path)


def stop_watching():
    """Stops watching all directories.
    """
    for stop_event in _STOP_EVENTS:
        stop_event.set()
