from setuptools import find_packages, setup

package_name = "mestrado_emg"

setup(
    name=package_name,
    version="0.1.0",
    packages=find_packages(exclude=["test"]),
    data_files=[
        ("share/ament_index/resource_index/packages", ["resource/" + package_name]),
        ("share/" + package_name, ["package.xml"]),
    ],
    install_requires=["setuptools"],
    zip_safe=True,
    maintainer="Caio Lima",
    maintainer_email="clima@ufabc.edu.br",
    description="sEMG pipeline, drivers and classifier ported from the master's thesis.",
    license="Apache-2.0",
    entry_points={
        "console_scripts": [
            "myo_driver = mestrado_emg.nodes.myo_driver:main",
            "emg_replay = mestrado_emg.nodes.emg_replay:main",
            "emg_classifier = mestrado_emg.nodes.emg_classifier:main",
            "angle_monitor = mestrado_emg.nodes.angle_monitor:main",
            "train_legacy = mestrado_emg.training:main",
        ],
    },
)
