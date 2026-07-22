from setuptools import setup

package_name = 'aip_fleet_supervisor'

setup(
    name=package_name,
    version='0.1.0',
    packages=[package_name],
    data_files=[
        ('share/ament_index/resource_index/packages',
         ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='AIP Team',
    maintainer_email='aip@example.com',
    description='Heartbeat aggregation, watchdog, and override gateway for the AIP fleet.',
    license='Apache-2.0',
    tests_require=['pytest'],
    entry_points={
        'console_scripts': [
            'supervisor_node = aip_fleet_supervisor.supervisor_node:main',
            'watchdog_node = aip_fleet_supervisor.watchdog_node:main',
        ],
    },
)
