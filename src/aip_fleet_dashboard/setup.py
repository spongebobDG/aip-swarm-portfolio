from setuptools import find_packages, setup
import os
from glob import glob

package_name = 'aip_fleet_dashboard'

setup(
    name=package_name,
    version='0.1.0',
    packages=find_packages(exclude=['test']),
    data_files=[
        ('share/ament_index/resource_index/packages',
            ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
        ('share/' + package_name + '/static',
            glob('static/*')),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='AIP Team',
    maintainer_email='dst04072@gmail.com',
    description='AIP Fleet standalone central control dashboard',
    license='Apache-2.0',
    tests_require=['pytest'],
    entry_points={
        'console_scripts': [
            'dashboard_server = aip_fleet_dashboard.dashboard_server:main',
        ],
    },
)
