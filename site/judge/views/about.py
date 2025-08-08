from django.shortcuts import render

def about_view(request):
    # 여기서 SITE_LONG_NAME 등의 변수를 설정할 수 있습니다.
    context = {
        'SITE_LONG_NAME': 'DMOJ - Online Judge'
    }
    return render(request, 'about/about.html', context)
