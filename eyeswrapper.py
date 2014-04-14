#!/usr/bin/env python
# -*- coding: utf-8 -*-

from __future__ import print_function
import logging
import os
import sys

from applitools import _match_window_task
import applitools.eyes
from requests import exceptions
from selenium.webdriver.remote import webdriver


applitools.eyes.Eyes.api_key = (
    'XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX')
APP_NAME = 'app'
TEST_NAME = 'test'


def match(eyes, path):
    """Sends a file to Applitools for matching.

    Ignores errors from sending non-image files.

    Args:
        eyes: An open Eyes instance.
        path: The path of an image. The file name is used as the tag.
    """
    try:
        match_window(eyes, path)
    except exceptions.HTTPError:
        logging.warn('Invalid image: {}'.format(path))


def match_window(eyes, path):
    """Sends an image to Applitools for matching.

    Args:
        eyes: An open Eyes instance.
        path: The path of an image. The file name is used as the tag.
    """
    logging.info('Matching file against baseline: {}'.format(path))
    if not eyes._running_session:
        eyes._start_session()
        eyes._match_window_task = _match_window_task.MatchWindowTask(
            eyes, eyes._agent_connector, eyes._running_session, None,
            eyes.match_timeout)
    with open(path, 'rb') as f:
        screenshot64 = f.read().encode('base64')
    data = {'appOutput': {'title': '', 'screenshot64': screenshot64},
            'userInputs': [],
            'tag': os.path.basename(path),
            'ignoreMismatch': False}
    eyes._match_window_task._agent_connector.match_window(
        eyes._match_window_task._running_session, data)


class EyesWrapper(object):
    """A wrapper for Applitools Eyes.

    The eyes-selenium package makes it inconvenient to upload
    preexisting images directly. This wrapper abstracts the set-up and
    tear-down processes.

    Attributes:
        eyes: The wrapped Eyes instance.
    """
    def __init__(self, overwrite_baseline=False):
        """Initializes the Eyes wrapper.

        Args:
            overwrite_baseline: Whether to overwrite the baseline.
        """
        self._overwrite_baseline = overwrite_baseline

    def __enter__(self):
        """Opens an Eyes instance.

        Returns:
            The EyesWrapper.
        """
        class _FakeWebDriver(webdriver.WebDriver):
            """A fake web driver.

            Applitools currently requires Selenium to work, so we need
            a web driver to trick it into working.

            Attributes:
                _switch_to: Anything. It must exist, though.
                capabilities: A dictionary of capability names to
                    booleans. The only one that matters is
                    'takesScreenshot', which must be True, or else
                    Applitools will try (and fail) to take screenshots
                    itself.
            """

            def __init__(self):
                """Initializes capabilities.
                """
                self._switch_to = None
                self.capabilities = {'takesScreenshot': True}

            def execute_script(self, script, params=None):
                """Returns a fake viewport dimension.

                The only scripts that must be mocked are those that get
                the width and height of the viewport.

                Returns:
                    A valid viewport dimension.
                """
                return 0

        self.eyes = applitools.eyes.Eyes()
        self.eyes.save_failed_tests = self._overwrite_baseline
        self.eyes.open(_FakeWebDriver(), APP_NAME, TEST_NAME)
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        """Closes the wrapped Eyes instance.

        Args:
            exc_type: Type of the raised exception.
            exc_value: The raised exception.
            traceback: The traceback.
        """
        try:
            self.eyes.close()
        finally:
            self.eyes.abort_if_not_closed()


def test(path, overwrite_baseline=False):
    """Matches an image against the baseline.

    Matches a single image or a directory of images against the
    baseline in Applitools. If there is no baseline for this app, it
    creates one. If the test did not pass, it prints Applitools's error
    output.

    Args:
        path: The path of either an image or a directory of images.
        overwrite_baseline: Whether to overwrite the baseline with the
            results of this test.
    """
    try:
        paths = [os.path.join(path, f) for f in os.listdir(path)]
    except OSError:
        paths = [path]
    with EyesWrapper(overwrite_baseline) as eyes_wrapper:
        for path in paths:
            match_window(eyes_wrapper.eyes, path)


def _usage_and_exit(status=None):
    """Prints a usage statement and exits.

    If status is omitted, None, or 0, the usage statement is printed to
    standard output. Otherwise, it is printed to standard error.

    Args:
        status: An exit status.
    """
    if status:
        stream = sys.stderr
    else:
        stream = sys.stdout
    print('Usage:\n'
          '    {} [[-o | --overwrite] directory ...]'.format(sys.argv[0]),
          file=stream)
    sys.exit(status)


def _parse_args():
    """Parses the command-line arguments.

    Returns:
        A list of 2-tuples, each of a path and a boolean, where the
        boolean indicates whether the file at the associated path
        should overwrite the baseline.
    """
    paths = []
    i = 1
    while i < len(sys.argv):
        overwrite = False
        if sys.argv[i] in ['-o', '--overwrite']:
            i += 1
            overwrite = True
        elif sys.argv[i] in ['-h', '--help']:
            _usage_and_exit()
        try:
            paths.append((sys.argv[i], overwrite))
            i += 1
        except IndexError:
            _usage_and_exit(1)
    return paths

def main():
    paths = _parse_args()
    for path, overwrite in paths:
        test(path, overwrite)


if __name__ == '__main__':
    main()
