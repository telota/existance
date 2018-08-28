from pathlib import Path

from setuptools import setup, find_packages


BASE_DIR = Path(__file__).parent


with (BASE_DIR / 'README.md').open('rt') as f:
    long_description = f.read()

setup(
    name='existance',
    version='0.1.b1',
    description='A tool to integrate eXist-db instances on a Linux host.',
    long_description=long_description,
    long_description_content_type='text/markdown',
    url='https://github.com/telota/existance',
    author='Martin Wagner',
    author_email='martin.wagner@bbaw.de',
    classifiers=[
        'Development Status :: 4 - Beta',
        'Intended Audience :: System Administrators',
        'License :: OSI Approved'
        ' :: GNU Library or Lesser General Public License (LGPL)',
        'Operating System :: POSIX',
        'Programming Language :: Python :: 3 :: Only',
        'Programming Language :: Python :: 3.6',
        'Topic :: System :: Installation/Setup'
    ],
    keywords='eXist-db',
    packages=find_packages(exclude=['docs', 'tests']),
    requires=['requests'],
    python_requires=">=3.6",
    entry_points={
        'console_scripts': [
            'existance=existance:main',
        ],
    },
)
