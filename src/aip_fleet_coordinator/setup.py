from setuptools import find_packages, setup

package_name = 'aip_fleet_coordinator'

setup(
    name=package_name,
    version='0.1.0',
    packages=find_packages(exclude=['test']),
    data_files=[
        ('share/ament_index/resource_index/packages', ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='AIP Team',
    maintainer_email='aip@example.com',
    description='Fleet coordination node.',
    license='Apache-2.0',
    entry_points={
        'console_scripts': [
            'coordinator_node = aip_fleet_coordinator.coordinator_node:main',
            'scout_localizer_node = aip_fleet_coordinator.scout_localizer_node:main',
            # DEPRECATED (2026-06-15): 전 차량 LiDAR+SLAM 채택으로 불필요
            'uwb_localizer_node = aip_fleet_coordinator.uwb_localizer_node:main',
        ],
    },
)
