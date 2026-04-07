from setuptools import setup


def read_requirements(path='requirements.txt'):
    with open(path, encoding='utf-8') as f:
        return [line.strip() for line in f if line.strip() and not line.startswith('#')]


def read_readme(path='README.md'):
    with open(path, encoding='utf-8') as f:
        return f.read()


setup(
    name='localweb',
    version='0.1.0',
    description='LocalWeb website downloader for offline viewing',
    long_description=read_readme(),
    long_description_content_type='text/markdown',
    author='Bashir',
    author_email='no-reply@example.com',
    url='https://github.com/Bashir0076/LocalWeb',
    packages=['localweb'],
    package_dir={'localweb': '.'},
    include_package_data=True,
    package_data={
        'localweb': ['config.default.json', 'config.example.json'],
    },
    python_requires='>=3.10',
    install_requires=read_requirements(),
    entry_points={
        'console_scripts': [
            'localweb=localweb.main:run',
        ],
    },
    classifiers=[
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.10',
        'License :: OSI Approved :: MIT License',
        'Operating System :: OS Independent',
    ],
)
