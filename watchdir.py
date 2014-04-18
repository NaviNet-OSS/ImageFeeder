# -*- coding: utf-8 -*-

"""Watches directories.
"""

from distutils import dir_util
import errno
import logging
import os
import Queue
import shutil
import threading
import time

from watchdog import events
from watchdog.observers import polling

_WATCHER_THREADS = []
_STOP_EVENTS = []
PROCESSING_DIR_NAME = 'IN-PROGRESS'
DEFAULT_DIR_NAME = 'DONE'
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
    try:
        os.rename(src, dst)
    except OSError as error:
        if error.errno != errno.ENOENT:
            raise
    while os.path.exists(src):
        time.sleep(0.1)


class CreationEventHandler(events.FileSystemEventHandler):
    """Event handler for moving new files.
    """
    # pylint: disable=abstract-class-not-used

    def __init__(self, watched, **kwargs):
        """Initializes the event handler.

        Args:
            watched: The directory which is being watched.
        """
        # pylint: disable=unused-argument
        self._watched = watched
        self._processing_dir = os.path.join(os.path.dirname(watched),
                                            PROCESSING_DIR_NAME,
                                            os.path.basename(watched))
        LOGGER.debug('Processing dir: {}'.format(self._processing_dir))
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
            LOGGER.debug('Created file: {}'.format(src_path))
            new_path = os.path.join(self._processing_dir,
                                    os.path.relpath(src_path, self._watched))
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


def _make_empty_directory(path):
    """Clears a directory or deletes a regular file.

    Deletes whatever the path refers to (if anything) and creates an
    empty directory at that path.

    Args:
        path: The path to make point to an empty directory.
    """
    LOGGER.debug('Clearing directory: {}'.format(path))
    if os.path.isdir(path):
        shutil.rmtree(path)
    elif os.path.exists(path):
        os.remove(path)
    dir_util.mkpath(path)


def watch(base, path, context_manager, **kwargs):
    """Watches a directory in another thread.

    Args:
        base: The parent directory of the directories to move files
            into, or a false value to not move anything.
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
                              args=(base, path, context_manager, stop_event),
                              kwargs=kwargs)
    thread.start()
    _WATCHER_THREADS.append(thread)


def _watch(base, path, context_manager, stop_event, **kwargs):
    """Watches a directory.

    Moves files on completion of a test if base is true. If the test
    (including entering and exiting the context manager) raises a
    DestinationDirectoryException, the new directory is the error
    message. Otherwise, it is DONE.

    Args:
        base: The parent directory of the directories to move files
            into, or a false value to not move anything.
        path: The name of the directory to watch.
        context_manager: A context manager which takes an Event and
            some keyword arguments and produces an event handler.
        stop_event: An Event to set to stop watching. It is passed as
            the first argument to the event handler's initializer.
        kwargs: Keyword arguments for context_manager.
    """
    LOGGER.info('Watching directory: {}'.format(path))
    if base:  # TODO: base and watched are redundant
        src = os.path.join(os.path.dirname(base), PROCESSING_DIR_NAME)
        _make_empty_directory(src)
    try:
        with context_manager(stop_event, **kwargs) as event_handler:
            observer = polling.PollingObserver()
            observer.schedule(event_handler, path, True)
            observer.start()
            stop_event.wait()
            observer.stop()
            observer.join()
    except DestinationDirectoryException as error:
        dst_dir = error.message
    else:
        dst_dir = DEFAULT_DIR_NAME
    if base:
        dst = os.path.join(os.path.dirname(base), dst_dir)
        _make_empty_directory(dst)
        LOGGER.debug('Moving {} to {}'.format(src, dst))
        if os.path.isdir(dst):
            shutil.rmtree(dst)
        elif os.path.exists(dst):
            os.remove(dst)
        os.rename(src, dst)


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
