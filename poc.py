#!/usr/bin/env python

import collections
import os
import os.path

import applitools.eyes
from applitools import _match_window_task
from selenium.common import exceptions
from selenium.webdriver.remote import webdriver


APP_NAME = 'app'
TEST_NAME = 'test'
EYES_SERVER = applitools.eyes.Eyes.DEFAULT_EYES_SERVER.rstrip('/')


def match_window(eyes, path):
    if not eyes._running_session:
        eyes._start_session()
        eyes._match_window_task = _match_window_task.MatchWindowTask(
            eyes, eyes._agent_connector, eyes._running_session, None,
            eyes.match_timeout)
    with open(path, 'rb') as f:
        screenshot64 = f.read().encode('base64')
    data = {'appOutput': {'title': '', 'screenshot64': screenshot64},
            'userInputs': [],
            'tag': None,
            'ignoreMismatch': False}
    eyes._match_window_task._agent_connector.match_window(
        eyes._match_window_task._running_session, data)


def test(path, overwrite_baseline=False):
    class FakeWebDriver(webdriver.WebDriver):
        def __init__(self):
            self.capabilities = {'takesScreenshot': True}

        def get_window_size(self):
            return collections.defaultdict(int)

        def execute_script(self, script):
            raise exceptions.WebDriverException

    try:
        paths = [os.path.join(path, f) for f in os.listdir(path)]
    except OSError:
        paths = [path]
    try:
        eyes = applitools.eyes.Eyes(EYES_SERVER)
        eyes.save_failed_tests = overwrite_baseline
        eyes.open(FakeWebDriver(), APP_NAME, TEST_NAME)
        for path in paths:
            match_window(eyes, path)
        eyes.close()
    finally:
        eyes.abort_if_not_closed()


def main():
    applitools.eyes.Eyes.api_key = (
        'XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX')
    test(r'C:\Users\DCorbett\Desktop\Applitools\Baseline', True)
    test(r'C:\Users\DCorbett\Desktop\Applitools\New')


if __name__ == '__main__':
    main()
