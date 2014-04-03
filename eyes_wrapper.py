#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os.path

from applitools import _match_window_task
from applitools import errors
import applitools.eyes
from selenium.webdriver.remote import webdriver


applitools.eyes.Eyes.api_key = (
    'XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX')
APP_NAME = 'app'
TEST_NAME = 'test'


def match_window(eyes, path):
    """Sends an image to Applitools for matching.

    Args:
        eyes: An open Eyes instance.
        path: The path of an image. The file name is used as the tag.
    """
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


def run_eyes(callback, overwrite_baseline=False):
    """Runs Eyes with a callback.

    Opens Eyes, calls the callback, and closes Eyes.

    Args:
        callback: A function taking an open Eyes instance.
        overwrite_baseline: Whether to overwrite the baseline.
    """
    class _FakeWebDriver(webdriver.WebDriver):
        """A fake web driver.

        Applitools currently requires Selenium to work, so we need a
        web driver to trick it into working.

        Attributes:
            capabilities: A dictionary of capability names to booleans.
                The only one that matters is 'takesScreenshot', which
                must be True, or else Applitools will try (and fail) to
                take screenshots itself.
        """

        def __init__(self):
            """Initializes capabilities."""
            self.capabilities = {'takesScreenshot': True}

        def execute_script(self, script, params=None):
            """Returns a fake viewport dimension.

            The only scripts that must be mocked are those that get the
            width and height of the viewport.

            Returns:
                A valid viewport dimension.
            """
            return 0

    try:
        eyes = applitools.eyes.Eyes()
        eyes.save_failed_tests = overwrite_baseline
        eyes.open(_FakeWebDriver(), APP_NAME, TEST_NAME)
        callback(eyes)
        eyes.close()
    except errors.TestFailedError as e:
        print(e)
    finally:
        eyes.abort_if_not_closed()


def test(path, overwrite_baseline=False):
    """Matches images against the baseline.

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
    def callback(eyes):
        for path in paths:
            match_window(eyes, path)
    run_eyes(callback, overwrite_baseline)


def main():
    test(r'C:\Users\DCorbett\Desktop\Applitools\Baseline', True)
    test(r'C:\Users\DCorbett\Desktop\Applitools\New')


if __name__ == '__main__':
    main()
