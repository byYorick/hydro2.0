#!/bin/sh
# Скрипт для архивирования WAL файлов PostgreSQL

test ! -f "$2" && cp "$1" "$2"

