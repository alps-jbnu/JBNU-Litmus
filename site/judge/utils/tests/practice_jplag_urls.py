# 연습(practice) 화면의 라우트는 dmoj/urls.py에서 주석 처리돼 있다. 테스트에서만 JPlag 화면을 연결한다.
from django.urls import path

from dmoj.urls import urlpatterns as site_urlpatterns
from judge.views import practices

urlpatterns = [
    path('practice/<str:contest>/jplag', practices.ContestJplagView.as_view(), name='practice_jplag'),
    path('practice/<str:contest>/jplag/delete', practices.ContestJplagDelete.as_view(), name='practice_jplag_delete'),
] + site_urlpatterns
