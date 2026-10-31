from django.urls import path

from .views import ChangePasswordView, DeleteAccountView, MeView

urlpatterns = [
    path('me/', MeView.as_view(), name='me'),
    path('delete-account/', DeleteAccountView.as_view(), name='delete-account'),
    path('change-password/', ChangePasswordView.as_view(), name='change-password'),
]
