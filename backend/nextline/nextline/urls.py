from django.conf import settings
from django.contrib import admin
from django.urls import include, path
from rest_framework.routers import DefaultRouter

from rides.views import RideViewSet, crash_alert, level_rules, progress
from trails.views import FeatureViewSet, TrailViewSet

router = DefaultRouter()
router.register(r'rides', RideViewSet, basename='ride')
router.register(r'trails', TrailViewSet, basename='trail')
router.register(r'features', FeatureViewSet, basename='feature')

urlpatterns = [
    path('api/', include(router.urls)),
    path('api/progress/', progress, name='progress'),
    path('api/level-rules/', level_rules, name='level-rules'),
    path('api/crash-alerts/', crash_alert, name='crash-alert'),
    path('api/auth/', include('djoser.urls')),
    path('api/auth/', include('djoser.urls.jwt')),
    path('api/user/', include('users.urls')),
    # Bots scan /admin/ for login pages; set ADMIN_URL to something unguessable in production.
    path(settings.ADMIN_URL, admin.site.urls),
]
