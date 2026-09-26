from setuptools import find_packages, setup

package_name = "mestrado_capture"

setup(
    name=package_name,
    version="0.1.0",
    packages=find_packages(),
    data_files=[
        ("share/ament_index/resource_index/packages", ["resource/" + package_name]),
        ("share/" + package_name, ["package.xml"]),
    ],
    install_requires=["setuptools"],
    zip_safe=True,
    maintainer="Caio Lima",
    maintainer_email="clima@ufabc.edu.br",
    description="Webcam elbow angle (MediaPipe) and labelled sEMG recording.",
    license="MIT",
    entry_points={
        "console_scripts": [
            "elbow_angle_camera = mestrado_capture.nodes.elbow_angle_camera:main",
            "emg_recorder = mestrado_capture.nodes.emg_recorder:main",
        ],
    },
)
