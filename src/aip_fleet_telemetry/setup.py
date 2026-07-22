from setuptools import setup

package_name = 'aip_fleet_telemetry'

setup(
    name=package_name,
    version='0.1.0',
    packages=[package_name],
    data_files=[
        ('share/ament_index/resource_index/packages', ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='AIP Team',
    description='Fleet telemetry bridge: /fleet/status → InfluxDB 2.x',
    license='Apache-2.0',
    entry_points={
        'console_scripts': [
            'telemetry_node = aip_fleet_telemetry.telemetry_node:main',
        ],
    },
)
