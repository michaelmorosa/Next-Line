from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from rest_framework import status
from rest_framework.generics import RetrieveUpdateAPIView
from rest_framework.response import Response
from rest_framework.views import APIView

from .serializers import UserSerializer


class MeView(RetrieveUpdateAPIView):
    serializer_class = UserSerializer

    def get_object(self):
        return self.request.user


class DeleteAccountView(APIView):
    def delete(self, request):
        request.user.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class ChangePasswordView(APIView):
    def post(self, request):
        user = request.user
        current_password = request.data.get("current_password")
        new_password = request.data.get("new_password")
        if not current_password or not new_password:
            return Response({"detail": "Both current and new password are required."}, status=400)
        if not user.check_password(current_password):
            return Response({"current_password": "Current password is incorrect."}, status=400)
        if current_password == new_password:
            return Response({"new_password": "New password cannot be the same as current password."}, status=400)
        try:
            validate_password(new_password, user=user)
        except ValidationError as e:
            return Response({"new_password": e.messages}, status=400)
        user.set_password(new_password)
        user.save()
        return Response({"detail": "Password changed."})
