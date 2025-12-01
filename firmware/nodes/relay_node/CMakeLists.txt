cmake_minimum_required(VERSION 3.16)
include($ENV{IDF_PATH}/tools/cmake/project.cmake)

# Добавляем путь к общим компонентам
set(EXTRA_COMPONENT_DIRS 
    "${CMAKE_CURRENT_SOURCE_DIR}/../common/components"
    "${CMAKE_CURRENT_SOURCE_DIR}/../common/components/sensors"
)

# Указываем таблицу разделов
set(PARTITION_TABLE_CSV_PATH "${CMAKE_CURRENT_SOURCE_DIR}/partitions.csv")

project(relay_node)

