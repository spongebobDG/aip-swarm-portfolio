from setuptools import find_packages, setup
import os
from glob import glob

package_name = 'aip_fleet_perception'

setup(
    name=package_name,
    version='0.1.0',
    packages=find_packages(exclude=['test']),
    data_files=[
        ('share/ament_index/resource_index/packages',
         [f'resource/{package_name}']),
        (f'share/{package_name}',           ['package.xml']),
        (f'share/{package_name}/launch',    glob('launch/*.py')),
        (f'share/{package_name}/config',    glob('config/*.yaml')),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='AIP Team',
    maintainer_email='aip@example.com',
    description='Thermal + RGB fusion for patrol anomaly detection',
    license='MIT',
    entry_points={
        'console_scripts': [
            'thermal_driver_node   = aip_fleet_perception.thermal_driver_node:main',
            'thermal_uart_driver_node = aip_fleet_perception.thermal_uart_driver_node:main',
            'patrol_monitor_node   = aip_fleet_perception.patrol_monitor_node:main',
            'central_fusion_node   = aip_fleet_perception.central_fusion_node:main',
            'arm_scan_node         = aip_fleet_perception.arm_scan_node:main',
            'alert_visualizer_node = aip_fleet_perception.alert_visualizer_node:main',
            'vision_pi_bridge_node = aip_fleet_perception.vision_pi_bridge_node:main',
        ],
    },
)
