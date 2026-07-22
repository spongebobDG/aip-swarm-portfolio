import os
from glob import glob

from setuptools import find_packages, setup

package_name = 'aip_fleet_real'


def config_data_files():
    """config/ 하위 모든 yaml 을 디렉터리 구조 그대로 share 에 설치."""
    grouped = {}
    for path in glob('config/**/*.yaml', recursive=True):
        dest = os.path.join('share', package_name, os.path.dirname(path))
        grouped.setdefault(dest, []).append(path)
    return [(dest, files) for dest, files in grouped.items()]


def mesh_data_files():
    """meshes/ 하위 STL 파일을 share 에 설치."""
    files = glob('meshes/*.STL')
    return [(os.path.join('share', package_name, 'meshes'), files)] if files else []


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
        (os.path.join('share', package_name, 'rviz'),
         glob('rviz/*.rviz')),
        (os.path.join('share', package_name, 'urdf'),
         glob('urdf/*.urdf')),
    ] + config_data_files() + mesh_data_files(),
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='AIP Team',
    maintainer_email='aip@example.com',
    description='AIP 플릿 실차량 전용 bringup (LiDAR+SLAM+Nav2+twist_mux).',
    license='Apache-2.0',
    entry_points={
        'console_scripts': [
            'serial_bridge  = aip_fleet_real.serial_bridge:main',
            'heartbeat_pub  = aip_fleet_real.heartbeat_pub:main',
            'scan_deskew_node = aip_fleet_real.scan_deskew_node:main',
        ],
    },
)
