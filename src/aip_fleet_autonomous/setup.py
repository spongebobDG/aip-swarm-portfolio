from glob import glob
import os
from setuptools import find_packages, setup

package_name = 'aip_fleet_autonomous'

setup(
    name=package_name,
    version='0.1.0',
    packages=find_packages(exclude=['test']),
    data_files=[
        ('share/ament_index/resource_index/packages',
            ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
        (os.path.join('share', package_name, 'launch'),
            glob('launch/*.launch.py')),
        (os.path.join('share', package_name, 'params'),
            glob('params/*.yaml')),
        (os.path.join('share', package_name, 'config'),
            glob('config/*.yaml')),
        (os.path.join('share', package_name, 'behavior_trees'),
            glob('behavior_trees/*.xml')),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='AIP Team',
    maintainer_email='aip@example.com',
    description='Independent autonomous navigation for AIP fleet peers',
    license='MIT',
    entry_points={
        'console_scripts': [
            'patrol_node           = aip_fleet_autonomous.patrol_node:main',
            'map_readiness_node    = aip_fleet_autonomous.map_readiness_node:main',
            'follower_trigger_node = aip_fleet_autonomous.follower_trigger_node:main',
            'patrol_planner_node   = aip_fleet_autonomous.patrol_planner_node:main',
            'keepout_zone_node     = aip_fleet_autonomous.keepout_zone_node:main',
        ],
    },
)
