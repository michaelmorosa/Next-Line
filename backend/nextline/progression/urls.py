from django.urls import path

from . import views

urlpatterns = [
    path('skills/', views.skill_tree, name='skill-tree'),
    path('skills/<slug:skill_id>/', views.skill_detail, name='skill-detail'),
    path('skills/<slug:skill_id>/sessions/', views.log_session, name='skill-sessions'),
    path('skills/<slug:skill_id>/attempts/', views.add_attempt, name='skill-attempts'),
    path('skills/<slug:skill_id>/master/', views.master_skill, name='skill-master'),
    path('attempts/<int:attempt_id>/video/', views.attempt_video, name='attempt-video'),
    path('xp/', views.xp_history, name='xp-history'),
    path('challenges/', views.challenges, name='challenges'),
    path('challenges/<int:challenge_id>/join/', views.join_challenge, name='challenge-join'),
]
