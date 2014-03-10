#!/usr/bin/env python

from applitools.eyes import Eyes
from applitools._match_window_task import MatchWindowTask
from collections import defaultdict
from selenium import webdriver
from selenium.common.exceptions import WebDriverException
from selenium.webdriver.remote.webdriver import WebDriver


Eyes.api_key = 'XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX'


def match_window(eyes, tag, path):
    if not eyes._running_session:
        eyes._start_session()
        eyes._match_window_task = MatchWindowTask(eyes, eyes._agent_connector,
                                                  eyes._running_session, None,
                                                  eyes.match_timeout)
    with open(path, 'rb') as f:
        screenshot64 = f.read().encode('base64')
    data = {'appOutput': {'title': '', 'screenshot64': screenshot64},
            'userInputs': [],
            'tag': tag,
            'ignoreMismatch': False}
    eyes._match_window_task._agent_connector.match_window(
        eyes._match_window_task._running_session, data)


def test(tags, paths):
    class FakeWebDriver(WebDriver):
        def __init__(self):
            pass

        def get_window_size(self):
            return defaultdict(int)

        def execute_script(self, script):
            raise WebDriverException

    try:
        eyes = Eyes()
        eyes.open(driver=FakeWebDriver(), app_name='c', test_name='baseline')
        for tag, path in zip(tags, paths):
            match_window(eyes, tag, path)
        eyes.close()
    finally:
        eyes.abort_if_not_closed()


def main():
    test(['Screen 1', 'Screen 2'],
         ['C:\\Users\\DCorbett\\Desktop\\Applitools\\New\\'
          'selenium-screenshot-1.png',
          'C:\\Users\\DCorbett\\Desktop\\Applitools\\New\\'
          'selenium-screenshot-2.png'])


if __name__ == '__main__':
    main()
