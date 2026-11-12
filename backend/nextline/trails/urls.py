from django.urls import path

from . import rider, team

urlpatterns = [
    path('systems/', rider.systems, name='systems'),
    path('systems/<int:pk>/', rider.system_detail, name='system'),
    path('systems/<int:pk>/ladders/', rider.system_ladders, name='system-ladders'),
    path('trails/<int:pk>/features/', rider.trail_features, name='trail-features'),
    path('features/<int:pk>/', rider.feature_detail, name='feature'),
    path('features/<int:pk>/log/', rider.log_feature, name='feature-log'),
    path('logs/batch/', rider.log_batch, name='log-batch'),
    path('logs/<int:pk>/', rider.log_detail, name='log'),
    path('next-up/', rider.next_up, name='next-up'),
    path('safety/', rider.safety, name='safety'),
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
