from setuptools import setup, find_packages

version = '0.0.0'

setup(
    name = 'isotoma.buildbot.sauceconnect',
    version = version,
    description = "Buildout steps for integrating with saucelabs",
    url = "http://pypi.python.org/pypi/isotoma.buildbot.sauceconnect",
    long_description = open("README.rst").read() + "\n" + \
                       open("CHANGES.txt").read(),
    classifiers = [
        "License :: OSI Approved :: Apache Software License",
    ],
    keywords = "buildbot selenium saucelabs",
    author = "John Carr",
    author_email = "john.carr@isotoma.com",
    license="Apache Software License",
    packages = find_packages(exclude=['ez_setup']),
    package_data = {
        '': ['README.rst', 'CHANGES.txt'],
        'isotoma.buildbot.sauceconnect': [],
    },
    namespace_packages = ['isotoma', 'isotoma.buildbot'],
    include_package_data = True,
    zip_safe = False,
    install_requires = [
        'setuptools',
        'jinja2',
    ],
)
