import os
from glob import glob

from setuptools import setup

package_name = 'aip_fleet_sim'

setup(
    name=package_name,
    version='0.1.0',
    packages=[package_name],
    data_files=[
        ('share/ament_index/resource_index/packages',
         ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
        (os.path.join('share', package_name, 'launch'), glob('launch/*.launch.py')),
        (os.path.join('share', package_name, 'config'), glob('config/*.yaml')),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='AIP Team',
    maintainer_email='aip@example.com',
    description='Lightweight kinematic simulator for the AIP fleet.',
    license='Apache-2.0',
    tests_require=['pytest'],
    entry_points={
        'console_scripts': [
            'sim_world_node = aip_fleet_sim.sim_world_node:main',
            'sim_vehicle_node = aip_fleet_sim.sim_vehicle_node:main',
            'sim_lidar_node = aip_fleet_sim.sim_lidar_node:main',
            'demo_patrol_node = aip_fleet_sim.demo_patrol_node:main',
        ],
    },
)
