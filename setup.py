#!/usr/bin/env python
#encoding: utf8

import os
import re

from setuptools import setup
from setuptools import find_packages
from setuptools.command.test import test as TestCommand

try:
    import colorama
    colorama.init()
    from colorama import Fore
    RESET = Fore.RESET
    GREEN = Fore.GREEN
    RED = Fore.RED
except ImportError:
    RESET = ''
    GREEN = ''
    RED = ''

import inspect
from os.path import join, dirname, abspath
OWN_PATH = abspath(inspect.getfile(inspect.currentframe()))
EXAMPLES_DIR = join(dirname(OWN_PATH), 'examples')

v = open(os.path.join(os.path.dirname(__file__), 'spyne', '__init__.py'), 'r')
VERSION = re.match(r".*__version__ = '(.*?)'", v.read(), re.S).group(1)

SHORT_DESC="""A transport and architecture agnostic rpc library that focuses on
exposing public services with a well-defined API."""

LONG_DESC = """Spyne aims to save the protocol implementers the hassle of
implementing their own remote procedure call api and the application programmers
the hassle of jumping through hoops just to expose their services using multiple
protocols and transports.
"""

try:
    os.stat('CHANGELOG.rst')
    LONG_DESC += "\n\n" + open('CHANGELOG.rst', 'r').read()
except OSError:
    pass


###############################
# Testing stuff

def call_test(f, a, tests):
    import spyne.test
    from glob import glob
    from itertools import chain
    from multiprocessing import Process, Queue

    tests_dir = os.path.dirname(spyne.test.__file__)
    a.extend(chain(*[glob(join(tests_dir, test)) for test in tests]))

    queue = Queue()
    p = Process(target=_wrapper(f), args=[a, queue])
    p.start()
    p.join()

    ret = queue.get()
    if ret == 0:
        print(tests, "OK")
    else:
        print(tests, "FAIL")

    return ret


def _wrapper(f):
    def _(args, queue):
        try:
            retval = f(args)
        except TypeError: # it's a pain to call trial.
            sys.argv = ['trial']
            sys.argv.extend(args)
            retval = f()
        queue.put(retval)
    return _


_ctr = 0

def call_pytest(*tests):
    global _ctr
    import pytest
    import spyne.test
    from glob import glob
    from itertools import chain

    _ctr += 1
    file_name = 'test_result.%d.xml' % _ctr
    if os.path.isfile(file_name):
        os.unlink(file_name)

    tests_dir = os.path.dirname(spyne.test.__file__)

    args = ['--tb=short', '--junitxml=%s' % file_name]
    args.extend(chain(*[glob("%s/%s" % (tests_dir, test)) for test in tests]))

    return pytest.main(args)


def call_pytest_subprocess(*tests):
    global _ctr
    import pytest
    _ctr += 1
    file_name = 'test_result.%d.xml' % _ctr
    if os.path.isfile(file_name):
        os.unlink(file_name)
    return call_test(pytest.main, ['--tb=line', '--junitxml=%s' % file_name], tests)

def call_trial(*tests):
    import spyne.test
    from glob import glob
    from itertools import chain

    global _ctr
    _ctr += 1
    file_name = 'test_result.%d.subunit' % _ctr
    with SubUnitTee(file_name):
        tests_dir = os.path.dirname(spyne.test.__file__)
        sys.argv = ['trial', '--reporter=subunit']
        sys.argv.extend(chain(*[glob(join(tests_dir, test)) for test in tests]))

        from twisted.scripts.trial import Options
        from twisted.scripts.trial import _makeRunner
        from twisted.scripts.trial import _getSuite

        config = Options()
        config.parseOptions()

        trialRunner = _makeRunner(config)
        suite = _getSuite(config)
        test_result = trialRunner.run(suite)

    subunit2junitxml(_ctr)

    return int(not test_result.wasSuccessful())


class InstallTestDeps(TestCommand):
    pass


def subunit2junitxml(ctr):
    from testtools import ExtendedToStreamDecorator
    from testtools import StreamToExtendedDecorator

    from subunit import StreamResultToBytes
    from subunit.filters import filter_by_result
    from subunit.filters import run_tests_from_stream

    from spyne.util.six import BytesIO

    from junitxml import JUnitXmlResult

    sys.argv = ['subunit-1to2']
    subunit1_file_name = 'test_result.%d.subunit' % ctr

    subunit2 = BytesIO()
    run_tests_from_stream(open(subunit1_file_name, 'rb'),
                    ExtendedToStreamDecorator(StreamResultToBytes(subunit2)))
    subunit2.seek(0)

    sys.argv = ['subunit2junitxml']
    sys.stdin = subunit2

    def f(output):
        return StreamToExtendedDecorator(JUnitXmlResult(output))

    junit_file_name = 'test_result.%d.xml' % ctr

    filter_by_result(f, junit_file_name, True, False, protocol_version=2,
                                passthrough_subunit=True, input_stream=subunit2)

class RunTests(TestCommand):
    def finalize_options(self):
        TestCommand.finalize_options(self)

        self.test_args = []
        self.test_suite = True

    def run_tests(self):
        print("running tests")
        sys.path.append(join(EXAMPLES_DIR, 'django'))
        os.environ['DJANGO_SETTINGS_MODULE'] = 'rpctest.settings'
        ret = 0
        ret = call_pytest('interface', 'model', 'protocol',
                          'test_null_server.py', 'test_service.py',
                          'test_soft_validation.py', 'test_util.py',
                          'test_sqlalchemy.py',
                          'test_sqlalchemy_deprecated.py',
                          'interop/test_django.py') or ret
        ret = call_pytest_subprocess('interop/test_httprpc.py') or ret
        ret = call_pytest_subprocess('interop/test_soap_client_http.py') or ret
        ret = call_pytest_subprocess('interop/test_soap_client_zeromq.py') or ret
        ret = call_pytest_subprocess('interop/test_suds.py') or ret
        ret = call_trial('interop/test_soap_client_http_twisted.py',
                         'transport/test_msgpack.py') or ret

        if ret == 0:
            print(GREEN + "All that glisters is not gold." + RESET)
        else:
            print(RED + "Something is rotten in the state of Denmark." + RESET)


        raise SystemExit(ret)

test_reqs = [
    'pytest', 'werkzeug', 'sqlalchemy', 'coverage',
    'lxml>=2.3', 'pyyaml', 'pyzmq', 'twisted', 'colorama',
    'msgpack-python', 'webtest', 'django<1.5.99', 'pytest_django',
    'python-subunit', 'junitxml', # to get junitxml output from trial
]

import sys
if sys.version_info < (3,0):
    test_reqs.extend(['pyparsing<1.99', 'suds'])
else:
    test_reqs.extend(['pyparsing'])


class SubUnitTee(object):
    def __init__(self, name):
        self.name = name
    def __enter__(self):
        self.file = open(self.name, 'wb')
        self.stdout = sys.stdout
        self.stderr = sys.stderr
        sys.stdout = sys.stderr = self

    def __exit__(self, *args):
        sys.stdout = self.stdout
        sys.stderr = self.stderr
        print "CLOSED"
        self.file.close()

    def writelines(self, data):
        for d in data:
            self.write(data)
            self.write('\n')

    def write(self, data):
        if data.startswith("test:") \
                or data.startswith("successful:") \
                or data.startswith("error:") \
                or data.startswith("failure:") \
                or data.startswith("skip:") \
                or data.startswith("notsupported:"):
            self.file.write(data)
            if not data.endswith("\n"):
                self.file.write("\n")

        self.stdout.write(data)

    def read(self,d=0):
        return ''

    def flush(self):
        self.stdout.flush()
        self.stderr.flush()

# Testing stuff ends here.
###############################

setup(
    name='spyne',
    packages=find_packages(),

    version=VERSION,
    description=SHORT_DESC,
    long_description=LONG_DESC,
    classifiers=[
        'Programming Language :: Python',
        'Programming Language :: Python :: 2',
        'Programming Language :: Python :: 2.6',
        'Programming Language :: Python :: 2.7',
        'Operating System :: OS Independent',
        'Natural Language :: English',
        'Development Status :: 5 - Production/Stable',
        'Intended Audience :: Developers',
        'Topic :: Internet :: WWW/HTTP :: Dynamic Content',
    ],
    keywords=('soap', 'wsdl', 'wsgi', 'zeromq', 'rest', 'rpc', 'json', 'http',
              'msgpack', 'xml', 'django', 'pyramid', 'postgresql', 'sqlalchemy',
              'werkzeug', 'twisted', 'yaml'),
    author='Burak Arslan',
    author_email='burak+spyne@arskom.com.tr',
    maintainer='Burak Arslan',
    maintainer_email='burak+spyne@arskom.com.tr',
    url='http://spyne.io',
    license='LGPL-2.1',
    zip_safe=False,
    install_requires=[
      'pytz',
    ],

    entry_points={
        'console_scripts': [
            'sort_wsdl=spyne.test.sort_wsdl:main',
        ]
    },

    tests_require = test_reqs,
    cmdclass = {'test': RunTests, 'install_test_deps': InstallTestDeps},
)
