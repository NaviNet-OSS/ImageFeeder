# -*- coding: utf-8 -*-

"""Watches directories.
"""

from distutils import dir_util
import errno
import logging
import os
import Queue
import threading
import time

from watchdog import events
from watchdog.observers import polling
from watchdog.utils import dirsnapshot

_WATCHER_THREADS = []
_STOP_EVENTS = []
PROCESSING_DIR_NAME = 'IN-PROGRESS'
LOGGER = logging.getLogger(__name__)


def _mv_f(src, dst):
    """Moves a regular file.

    Overwrites the destination if it exists but is not a directory.

    Args:
        src: The path of the source file.
        dst: The path of the destination.
    """
    LOGGER.debug('Moving {} to {}'.format(src, dst))
    while os.path.exists(dst):
        try:
            os.remove(dst)
        except OSError as error:
            if error.errno != errno.ENOENT:
                raise
    while os.path.exists(dst):
        time.sleep(0.1)  # Wait for the removal to complete
    dir_util.mkpath(os.path.dirname(dst))
    while os.path.exists(src):
        try:
            os.rename(src, dst)
        except OSError as error:
            if error.errno not in [errno.ENOENT, errno.EACCES]:
                raise
        time.sleep(0.1)


class CreationEventHandler(events.FileSystemEventHandler):
    """Event handler for moving new files.
    """
    # pylint: disable=abstract-class-not-used

    def __init__(self, watched_path, **kwargs):
        """Initializes the event handler.

        Args:
            watched_path: The directory which is being watched.
            base_path: The source path.
        """
        self._watched_path = watched_path
        base_path = kwargs.pop('base_path')
        self._base_path = base_path
        self._processing_dir = os.path.join(os.path.dirname(base_path),
                                            PROCESSING_DIR_NAME)
        self._base_path_copy = os.path.join(
            self._processing_dir, os.path.basename(base_path))
        self._watched_path_copy = os.path.join(
            self._base_path_copy, os.path.relpath(watched_path, base_path))
        self._backlog = Queue.Queue()
        initial_snapshot = dirsnapshot.DirectorySnapshot(watched_path, False)
        for path in initial_snapshot.paths:
            self._queue_file(path)
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
        self._queue_file(event.src_path)

    def _queue_file(self, src_path):
        """Queues a file for processing.

        Does not queue directories. Moves files to a processing
        directory.

        Args:
            src_path: The path of the file to queue.
        """
        if os.path.isfile(src_path):
            LOGGER.debug('Created file: {}'.format(src_path))
            new_path = os.path.join(self._watched_path_copy,
                                    os.path.relpath(src_path,
                                                    self._watched_path))
            _mv_f(src_path, new_path)
            self._backlog.put(new_path)

    def _process(self):
        """Process the backlog.
        """
        raise NotImplementedError


class DestinationDirectoryException(Exception):
    """Exception for custom destination directory names.

    Attributes:
        message: The name of the directory to move files into.
    """


def watch(path, context_manager, **kwargs):
    """Watches a directory in another thread.

    Args:
        path: The name of the directory to watch, without a trailing
            directory separator.
        context_manager: A context manager which takes an Event and
            some keyword arguments and produces an event handler.
        kwargs: Keyword arguments for context_manager.
    """
    # If path has a trailing directory separator, dirname won't work
    stop_event = threading.Event()
    _STOP_EVENTS.append(stop_event)
    thread = threading.Thread(target=_watch,
                              args=(path, context_manager, stop_event),
                              kwargs=kwargs)
    thread.start()
    _WATCHER_THREADS.append(thread)


def _watch(path, context_manager, stop_event, **kwargs):
    """Watches a directory.

    Args:
        path: The name of the directory to watch.
        context_manager: A context manager which takes an Event and
            some keyword arguments and produces an event handler.
        stop_event: An Event to set to stop watching. It is passed as
            the first argument to the event handler's initializer.
        kwargs: Keyword arguments for context_manager.
    """
    LOGGER.info('Watching directory: {}'.format(path))
    with context_manager(stop_event, **kwargs) as event_handler:
        observer = polling.PollingObserver()
        observer.schedule(event_handler, path, True)
        observer.start()
        stop_event.wait()
        observer.stop()
        observer.join()


def stop_watching():
    """Stops watching all directories.
    """
    for stop_event in _STOP_EVENTS:
        stop_event.set()
    while _WATCHER_THREADS:
        _WATCHER_THREADS.pop().join()


def is_running():
    """Checks whether any test is still running.

    Returns:
        Whether any test is still running.
    """
    for thread in _WATCHER_THREADS:
        if thread.is_alive():
            return True
    return False
