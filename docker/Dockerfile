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
        python3-pip \
        python3-absl \
        python3-flatbuffers \
        python3-matplotlib \
        python3-certifi \
        curl \
 && rm -rf /var/lib/apt/lists/* \
 && if [ -f /tmp/ros2.sources.disabled ]; then \
        mv /tmp/ros2.sources.disabled /etc/apt/sources.list.d/ros2.sources; \
    fi

# MediaPipe for the capture tool (mestrado_capture). Since 1.0 the wheel is
# py3-none (no CPython ABI), so it runs on Python 3.14. --no-deps keeps the
# apt numpy/OpenCV; its runtime deps are the apt packages above.
ARG MEDIAPIPE_VERSION=1.0.1
#
# Optional build secret `extra_ca` (a CA bundle) is only for networks that
# inspect TLS (corporate proxies, some cloud sandboxes):
#   docker build --secret id=extra_ca,src=/path/ca-bundle.crt ...
# Without it nothing changes; TLS verification is never disabled.
RUN --mount=type=secret,id=extra_ca,required=false \
    if [ -f /run/secrets/extra_ca ]; then export PIP_CERT=/run/secrets/extra_ca; fi \
 && pip install --no-cache-dir --no-deps --break-system-packages "mediapipe==${MEDIAPIPE_VERSION}" \
 && python3 -c "import mediapipe; print('mediapipe', mediapipe.__version__)"

# Pose model, pinned by version and SHA-256 (the thesis used model_complexity=1,
# the equivalent of the "full" model).
ARG POSE_MODEL_URL=https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_full/float16/1/pose_landmarker_full.task
ARG POSE_MODEL_SHA256=5134a3aad27a58b93da0088d431f366da362b44e3ccfbe3462b3827a839011b1
RUN --mount=type=secret,id=extra_ca,required=false \
    if [ -f /run/secrets/extra_ca ]; then export CURL_CA_BUNDLE=/run/secrets/extra_ca; fi \
 && mkdir -p /opt/mediapipe/models \
 && curl -fsSL --retry 3 "${POSE_MODEL_URL}" -o /opt/mediapipe/models/pose_landmarker_full.task \
 && echo "${POSE_MODEL_SHA256}  /opt/mediapipe/models/pose_landmarker_full.task" | sha256sum -c -

WORKDIR /ws
COPY ros2_ws/src /ws/src
RUN source /opt/ros/${ROS_DISTRO}/setup.bash \
 && colcon build --event-handlers console_direct- \
 && rm -rf build log

COPY docker/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh
ENTRYPOINT ["/entrypoint.sh"]
CMD ["bash"]
