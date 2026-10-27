"""项目总路由：后台、账户入口、game 应用以及开发期媒体文件。"""

from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("accounts/login/", auth_views.LoginView.as_view(template_name="game/login.html"), name="login"),
    path("accounts/logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("", include("game.urls")),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
