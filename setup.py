#!/usr/bin/python

from setuptools import setup, find_packages

setup(
    name='jiocloud',
    version='0.1',
    description='Various Python utilities used for JioCloud',
    author='Soren Hansen',
    author_email='Soren.Hansen@ril.com',
    url='http://github.com/JioCloud/python-jiocloud',
    packages=find_packages(),
    include_package_data=True,
    license='Apache 2.0',
    keywords='etcd openstack cloud',
    install_requires=['etcd'],
)
