from django.urls import path

from . import team

urlpatterns = [
    path('team/me/', team.me, name='team-me'),
    path('team/features/', team.features, name='team-features'),
    path('team/features/<int:pk>/', team.feature_detail, name='team-feature'),
    path('team/features/<int:pk>/media/', team.add_media, name='team-feature-media'),
    path('team/features/<int:pk>/media/<int:media_id>/', team.delete_media, name='team-feature-media-delete'),
    *[
        path(f'team/features/<int:pk>/{action}/', team.workflow(action), name=f'team-feature-{action}')
        for action in ('submit', 'certify', 'flag', 'reopen', 'verify')
    ],
    path('team/reports/<int:report_id>/resolve/', team.resolve_report, name='team-report-resolve'),
    path('team/guidelines/', team.guidelines, name='team-guidelines'),
    path('team/trails/', team.trails_nearby, name='team-trails'),
]
