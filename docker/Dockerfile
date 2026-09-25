# ROS 2 Lyrical Luth + Gazebo Jetty (LTS) on Ubuntu 26.04, with the ported
# master's-thesis workspace built in /ws.
#
# osrf/ros:lyrical-desktop-full already ships Gazebo Jetty (gz sim 10) and
# ros_gz (bridge, sim), so nothing has to come from packages.ros.org at build
# time. Python scientific packages come from the Ubuntu archive.
#
# Build (from the repository root):
#   docker compose -f docker/compose.yaml build
ARG ROS_DISTRO=lyrical
FROM osrf/ros:${ROS_DISTRO}-desktop-full

ARG ROS_DISTRO
# Set to 1 where packages.ros.org is unreachable (e.g. a restricted CI/cloud
# sandbox): the ROS apt source is disabled for this build step only.
ARG SKIP_ROS_APT_SOURCE=0

ENV ROS_DISTRO=${ROS_DISTRO} \
    DEBIAN_FRONTEND=noninteractive \
    PYTHONDONTWRITEBYTECODE=1

SHELL ["/bin/bash", "-o", "pipefail", "-c"]

RUN if [ "${SKIP_ROS_APT_SOURCE}" = "1" ]; then \
        mv /etc/apt/sources.list.d/ros2.sources /tmp/ros2.sources.disabled; \
    fi \
 && apt-get update \
 && apt-get install -y --no-install-recommends \
        python3-numpy \
        python3-scipy \
        python3-pandas \
        python3-sklearn \
        python3-pywt \
        python3-joblib \
        python3-serial \
        python3-pytest \
 && rm -rf /var/lib/apt/lists/* \
 && if [ -f /tmp/ros2.sources.disabled ]; then \
        mv /tmp/ros2.sources.disabled /etc/apt/sources.list.d/ros2.sources; \
    fi

WORKDIR /ws
COPY ros2_ws/src /ws/src
RUN source /opt/ros/${ROS_DISTRO}/setup.bash \
 && colcon build --event-handlers console_direct- \
 && rm -rf build log

COPY docker/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh
ENTRYPOINT ["/entrypoint.sh"]
CMD ["bash"]
