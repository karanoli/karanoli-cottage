"""game 应用启动配置。"""

from django.apps import AppConfig


class GameConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "game"

    def ready(self):
        # 启动时注册用户档案创建信号。
        import game.signals  # noqa: F401
