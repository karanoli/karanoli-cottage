#!/usr/bin/env python3
"""Django 项目的命令行入口，用于启动、迁移、测试和维护任务。"""

import os
import sys


def main():
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "sudoku_site.settings")
    from django.core.management import execute_from_command_line
    execute_from_command_line(sys.argv)


if __name__ == "__main__":
    main()
