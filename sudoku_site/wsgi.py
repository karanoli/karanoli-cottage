"""WSGI 部署入口，供传统 Python Web 服务器加载项目。"""

import os
from django.core.wsgi import get_wsgi_application
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "sudoku_site.settings")
application = get_wsgi_application()
