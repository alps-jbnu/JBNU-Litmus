from django.shortcuts import render

def render_term_view(request, template_name, title=None, title_info=None):
    title = 'Litmus 서비스 표준약관'  # 기본 제목 설정
    # 공통된 로직 및 context 설정
    context = {
        'title': title,
        'title_info': title_info,  # title_info를 context에 포함
    }
    return render(request, template_name, context)

def term_view(request):
    title_info = '제1장 총칙'
    return render_term_view(request, 'term/term-one.html', title_info=title_info) 

def term_two_view(request):
    title_info = '제2장 이용계약의 체결'
    return render_term_view(request, 'term/term-two.html', title_info=title_info)

def term_three_view(request):
    title_info = '제3장 계약 당사자의 의무'
    return render_term_view(request, 'term/term-three.html', title_info=title_info) 

def term_four_view(request):
    title_info = '제4장 서비스 이용'
    return render_term_view(request, 'term/term-four.html', title_info=title_info)

def term_five_view(request):
    title_info = '제5장 계약 해제·해지 및 이용제한'
    return render_term_view(request, 'term/term-five.html', title_info=title_info)  

def term_six_view(request):
    title_info = '제6장 손해배상 및 환불 등'
    return render_term_view(request, 'term/term-six.html', title_info=title_info) 
