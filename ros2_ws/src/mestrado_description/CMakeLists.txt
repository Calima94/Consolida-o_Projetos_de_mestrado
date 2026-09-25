cmake_minimum_required(VERSION 3.16)
project(mestrado_description)

find_package(ament_cmake REQUIRED)

install(DIRECTORY models worlds DESTINATION share/${PROJECT_NAME})

# Adds share/mestrado_description/models to GZ_SIM_RESOURCE_PATH on sourcing,
# so worlds can use model://braco_antebraco_garra.
ament_environment_hooks("${CMAKE_CURRENT_SOURCE_DIR}/hooks/${PROJECT_NAME}.dsv.in")

ament_package()
