#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""Wrapper for Applitools Eyes.
"""

from __future__ import print_function
import logging
import os
import sys

from applitools import _match_window_task
import applitools.eyes
from requests import exceptions
from selenium.webdriver.remote import webdriver


APP_NAME = 'app'
_DEFAULT_TEST_NAME = 'test'
TEST_NAME = None
LOGGER = logging.getLogger(__name__)


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
        LOGGER.warn('Invalid image: {}'.format(path))


def match_window(eyes, path):
    # pylint: disable=protected-access
    """Sends an image to Applitools for matching.

    Args:
        eyes: An open Eyes instance.
        path: The path of an image. The file name is used as the tag.
    """
    LOGGER.info('Matching file against baseline: {}'.format(path))
    if not eyes._running_session:
        eyes._start_session()
        eyes._match_window_task = _match_window_task.MatchWindowTask(
            eyes, eyes._agent_connector, eyes._running_session, None,
            eyes.match_timeout)
    with open(path, 'rb') as image_file:
        screenshot64 = image_file.read().encode('base64')
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
    # pylint: disable=too-few-public-methods

    def __init__(self, **kwargs):
        """Initializes the Eyes wrapper.

        Args:
            batch_info: A BatchInfo or None.
            host_app: A browser name or None.
            host_os: An OS name or None.
            overwrite_baseline: Whether to overwrite the baseline.
            test_name: The name of the Eyes test.
        """
        self._test_name = TEST_NAME or kwargs.pop('test_name',
                                                  _DEFAULT_TEST_NAME)
        self.eyes = applitools.eyes.Eyes()
        self.eyes.batch = kwargs.pop('batch_info', None)
        self.eyes.host_app = kwargs.pop('host_app', None)
        self.eyes.host_os = kwargs.pop('host_os', None)
        self.eyes.save_failed_tests = kwargs.pop('overwrite_baseline', False)

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
            # pylint: disable=too-many-public-methods

            def __init__(self):
                """Initializes capabilities.
                """
                # pylint: disable=super-init-not-called
                self._switch_to = None
                self.capabilities = {'takesScreenshot': True}

            def execute_script(self, script, *args):
                """Returns a fake viewport dimension.

                The only scripts that must be mocked are those that get
                the width and height of the viewport.

                Args:
                    script: A script to pretend to run.
                    args: Arguments to ignore.

                Returns:
                    A valid viewport dimension.
                """
                # pylint: disable=unused-argument
                return 0

        self.eyes.open(_FakeWebDriver(), APP_NAME, self._test_name)
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        """Closes the wrapped Eyes instance.

        Args:
            exc_type: The type of the raised exception.
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
    """Tests each directory given on the command line.
    """
    paths = _parse_args()
    for path, overwrite in paths:
        test(path, overwrite)


if __name__ == '__main__':
    main()
