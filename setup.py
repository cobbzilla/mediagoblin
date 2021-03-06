# GNU MediaGoblin -- federated, autonomous media hosting
# Copyright (C) 2011, 2012 MediaGoblin contributors.  See AUTHORS.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.


from setuptools import setup, find_packages
import os
import re

import sys

READMEFILE = "README"
VERSIONFILE = os.path.join("mediagoblin", "_version.py")
VSRE = r"^__version__ = ['\"]([^'\"]*)['\"]"


def get_version():
    with open(VERSIONFILE) as fobj:
        verstrline = fobj.read()
    mo = re.search(VSRE, verstrline, re.M)
    if mo:
        return mo.group(1)
    else:
        raise RuntimeError("Unable to find version string in %s." %
                           VERSIONFILE)

install_requires = [
    'waitress',
    'alembic>=0.7.5',
    'python-dateutil',
    # WTForms removed the "ext" module in 3.0.
    'wtforms<3.0',
    'py-bcrypt',
    'pytest>=2.3.1',
    'pytest-xdist',
    'werkzeug>=0.7,<1.0.0',
    # Celery 4.3.0 drops the "sqlite" transport alias making our tests fail.
    'celery>=3.0,<4.3.0',
    # Jinja2 3.0.0 uses f-strings (Python 3.7 and above) but `pip install` on
    # Debian 9 doesn't seem to respect Jinja2's 'python_requires=">=3.6"' line.
    'jinja2<3.0.0',
    'Babel>=1.3',
    'WebTest>=2.0.18',
    'ConfigObj',
    'Markdown',
    'sqlalchemy<1.4.0',
    'itsdangerous',
    'pytz',
    'sphinx',
    'oauthlib',
    'unidecode',
    'jsonschema',
    'PasteDeploy',
    'PasteScript',
    'requests>=2.6.0',
    'certifi>=2017.4.17', # Reported to be a requirement on Fedora 31 (TODO: test)
    'PyLD<2.0.0', # Breaks a Python 3 test if >= 2.0.0.
    'ExifRead>=2.0.0',
    'email-validator', # Seems that WTForms must have dropped this.
    'soundfile<=0.10.999' # Tested with 0.10.3.post1

    # This is optional:
    # 'translitcodec',
    # For now we're expecting that users will install this from
    # their package managers.
    # 'lxml',
    # 'Pillow',
]

with open(READMEFILE, encoding="utf-8") as fobj:
    long_description = fobj.read()

try:
    setup(
    name="mediagoblin",
    version=get_version(),
    packages=find_packages(exclude=['ez_setup', 'examples', 'tests']),
    zip_safe=False,
    include_package_data = True,
    # scripts and dependencies
    install_requires=install_requires,
    test_suite='nose.collector',
    entry_points="""\
        [console_scripts]
        gmg = mediagoblin.gmg_commands:main_cli

        [paste.app_factory]
        app = mediagoblin.app:paste_app_factory

        [paste.server_runner]
        paste_server_selector = mediagoblin.app:paste_server_selector

        [paste.filter_app_factory]
        errors = mediagoblin.errormiddleware:mgoblin_error_middleware

        [zc.buildout]
        make_user_dev_dirs = mediagoblin.buildout_recipes:MakeUserDevDirs

        [babel.extractors]
        jinja2 = jinja2.ext:babel_extract
        """,
    license='AGPLv3',
    author='Free Software Foundation and contributors',
    author_email='cwebber@gnu.org',
    url="http://mediagoblin.org/",
    long_description=long_description,
    description='MediaGoblin is a web application for publishing all kinds of media',
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Environment :: Web Environment",
        "License :: OSI Approved :: GNU Affero General Public License v3 or later (AGPLv3+)",
        "Operating System :: OS Independent",
        "Programming Language :: Python",
        'Programming Language :: Python :: 2',
        'Programming Language :: Python :: 2.7',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.3',
        'Programming Language :: Python :: 3.4',
        "Topic :: Internet :: WWW/HTTP :: Dynamic Content"
        ],
    )
except TypeError as e:
    import sys

    # Check if the problem is caused by the sqlalchemy/setuptools conflict
    msg_as_str = str(e)
    if not (msg_as_str == 'dist must be a Distribution instance'):
        raise

    # If so, tell the user it is OK to just run the script again.
    print("\n\n---------- NOTE ----------", file=sys.stderr)
    print("The setup.py command you ran failed.\n", file=sys.stderr)
    print("It is a known possible failure. Just run it again. It works the "
          "second time.", file=sys.stderr)
    sys.exit(1)
