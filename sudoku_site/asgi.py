"""ASGI 部署入口，供异步 Web 服务器加载项目。"""

import os
from django.core.asgi import get_asgi_application
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "sudoku_site.settings")
application = get_asgi_application()
